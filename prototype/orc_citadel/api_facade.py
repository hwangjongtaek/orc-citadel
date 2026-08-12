"""S32 조사/근거/그래프 API 파사드 (설계 09 §2·§3) — read-only.

read-only 프로젝션 4종(S28 Catalog, S29 evidence, S30 conclusion, S31 ranking)을
설계 09 §2 조사 중심 **엔드포인트 wire 계약**으로 노출하는 **API 파사드**. 순수 핸들러
`(zone, graph, **params) -> dict`가 09 §2·§3 응답 JSON 스키마를 그대로 생성한다.

- get_claim              : GET /v1/claims/{id} — claim 상세 + 09 §4 confidence 봉투 (S29).
- get_claim_evidence     : GET /v1/claims/{id}/evidence — 지지 근거 + cursor (09 §2.3).
- get_evidence_provenance: GET /v1/evidence/{id}/provenance — Trail 객체 (09 §2.3).
- get_investigation_report: GET /v1/investigations/{id}/report — 09 §3 결론 + open_questions (S30).
- get_graph_node / get_graph_expand: 노드·인접 확장 cursor (09 §2.2, S28).

**read-only** (불변식 §3-3) — 조회 전용, 쓰기·영속·그래프 mutation 미노출. FastAPI
라우터는 이 파사드를 1:1 감싸기만 하면 되는 백엔드 (09 §1.1 REST+JSON).
"""
from __future__ import annotations

from orc_citadel.assertion_evidence import AssertionEvidenceProjector
from orc_citadel.catalog import Catalog, CatalogGraph
from orc_citadel.conclusion import ConclusionProjector
from orc_citadel.graph_explorer import GraphExplorer
from orc_citadel.ranking import ConclusionRanking

DEFAULT_EVIDENCE_LIMIT = 30


def _hex_cursor(key: str) -> str:
    """opaque cursor — key(ascii)를 hex 인코딩 (09 §1.4, 클라이언트 미파싱)."""
    return key.encode("ascii").hex()


def _dehex(cursor: str) -> str:
    try:
        return bytes.fromhex(cursor).decode("ascii")
    except (ValueError, UnicodeDecodeError):
        return ""


class ApiFacade:
    """09 §2·§3 wire 계약을 노출하는 read-only API 파사드."""

    def __init__(self, zone, graph, low_confidence: float = 0.4,
                 high_confidence: float = 0.8) -> None:
        self.zone = zone
        self.graph = graph
        self.low_confidence = low_confidence
        self.high_confidence = high_confidence
        self._catalog = Catalog(zone)
        self._graph_catalog = CatalogGraph(graph)
        self._evidence = AssertionEvidenceProjector(zone)
        self._conclusion = ConclusionProjector(zone, low_confidence=low_confidence)
        self._ranking = ConclusionRanking(zone, high_confidence=high_confidence)
        self._explorer = GraphExplorer(zone, graph)
        # claim_candidates (claim_id → row) / assertions 조회용.
        self._claims_rows = {r["claim_candidate_id"]: r for r in zone.claims()}
        self._assertions = zone.assertions()

    # --- claim -------------------------------------------------------------

    def get_claim(self, claim_id: str) -> dict | None:
        row = self._claims_rows.get(claim_id)
        if row is None:
            return None
        ev = self._evidence.for_assertion_by_claim(claim_id)
        return {
            "claim_id": claim_id,
            "subject_id": row["subject_id"],
            "predicate": row["predicate"],
            "object_id": row["object_id"],
            "modality": row["modality"],
            "confidence": ev.confidence if ev else None,
        }

    def get_claim_evidence(self, claim_id: str, relation: str | None = None,
                           cursor: str | None = None,
                           limit: int = DEFAULT_EVIDENCE_LIMIT) -> dict:
        ev = self._evidence.for_assertion_by_claim(claim_id)
        items = []
        if ev is not None:
            for doc in ev.supporting_docs:
                items.append({
                    "evidence_id": _hex_cursor(f"{claim_id}:{doc}"),
                    "relation": "supports",
                    "strength": ev.confidence["dimensions"]["support"],
                    "source_doc": doc,
                    "claim_id": claim_id,
                })
        # (relation 필터는 supports만 존재 — 반박은 후속 확장)
        if relation is not None:
            items = [it for it in items if it["relation"] == relation]
        # 고정 정렬 축: evidence_id. 결정적.
        items.sort(key=lambda it: it["evidence_id"])
        start = 0
        if cursor is not None:
            for i, it in enumerate(items):
                if it["evidence_id"] > _dehex(cursor):
                    start = i
                    break
        page = items[start:start + limit]
        has_more = start + limit < len(items)
        return {
            "items": page,
            "page": {"next_cursor": _hex_cursor(page[-1]["evidence_id"]) if has_more
                     else None, "limit": limit},
        }

    def get_evidence_provenance(self, evidence_id: str) -> dict | None:
        try:
            raw = _dehex(evidence_id)
            claim_id, doc = raw.split(":", 1)
        except ValueError:
            return None
        ev = self._evidence.for_assertion_by_claim(claim_id)
        if ev is None or doc not in ev.supporting_docs:
            return None
        # DoD ② — 추출 기록(extraction_record)의 char span 을 trail 에 연결 (03 §8, ADR-305).
        # claim_id 와 일치하는 record 의 segment_id·char offset 을 원문 왕복(불변식 §3-2)으로 노출.
        er_step = None
        for rec in self.zone.extraction_records():
            if rec["element_id"] == claim_id:
                er_step = {
                    "step": "extraction_record",
                    "extraction_id": rec["extraction_id"],
                    "segment_id": rec["segment_id"],
                    "char_start": rec["char_start"],
                    "char_end": rec["char_end"],
                    "content_hash": rec["content_hash"],
                }
                break
        trail = [
            {"step": "claim", "claim_id": claim_id,
             "predicate": ev.predicate},
        ]
        if er_step is not None:
            trail.append(er_step)
        trail.append({"step": "document", "doc_id": doc})
        return {
            "evidence_id": evidence_id,
            "relation": "supports",
            "strength": ev.confidence["dimensions"]["support"],
            "trail": trail,
        }

    # --- investigation report ----------------------------------------------

    def get_investigation_report(self, subject_id: str) -> dict | None:
        c = self._conclusion.for_subject(subject_id)
        if c is None:
            return None
        sigs = {r.subject_id: r.signal for r in self._ranking.ranked()
                if r.subject_id == subject_id}
        return {
            "subject_id": subject_id,
            "id": f"inv-{_hex_cursor(subject_id)[:16]}",
            "confidence": c.confidence,
            "by_predicate": c.by_predicate,
            "open_questions": c.open_questions,
            "signal": sigs.get(subject_id),
        }

    # --- graph -------------------------------------------------------------

    def get_graph_node(self, node_id: str) -> dict | None:
        return self._graph_catalog.node(node_id)

    def get_graph_expand(self, node_id: str, cursor: str | None = None,
                         limit: int = DEFAULT_EVIDENCE_LIMIT) -> dict:
        nbrs = self._graph_catalog.neighbors(node_id)
        # 고정 정렬 축: (id, type). 결정적.
        nbrs.sort(key=lambda n: (n["id"], n["type"]))
        start = 0
        if cursor is not None:
            last = _dehex(cursor)
            for i, n in enumerate(nbrs):
                key = f"{n['id']}:{n['type']}"
                if key > last:
                    start = i
                    break
        page = nbrs[start:start + limit]
        has_more = start + limit < len(nbrs)
        return {
            "items": page,
            "page": {"next_cursor":
                     _hex_cursor(f"{page[-1]['id']}:{page[-1]['type']}") if has_more
                     else None, "limit": limit},
        }

    def get_investigation_graph(self, subject_id: str, hops: int = 1,
                                subclaim_id: str | None = None) -> dict:
        """09 §2.2 GET /v1/investigations/{id}/graph — investigation subgraph seed.

        서브그래프 + relation_paths + independence_summary 를 반환하는 progressive
        disclosure seed (06 §8.1·§8.3, design 09 §2.2). read-only (불변식 §3-3).
        """
        return self._explorer.explore(
            subclaim_id=subclaim_id if subclaim_id is not None
            else f"subclaim:{subject_id}",
            subject_id=subject_id, hops=hops,
        )
