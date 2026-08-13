"""S24 정식 파이프라인 모듈 — 단일 진입점 (아키텍처 01, 05 §5/§6, 06 §2).

결정적 체인(S1→S20)과 LLM 판정·영속(S21→S23)을 하나의 `run_pipeline`로 묶는다.

- `run_pipeline(metas, zone, judge=None) -> PipelineResult`:
  각 raw doc → extract_html → parse → mentions → resolve → mention 게이트 → claims
  → claim 게이트 → assertion materialize. 이후 canonicalize(judge)→contradiction(judge)
  → LLM verdict 영속(S23) → gate events 재구축으로 GraphService authoritative 노드-엣지
  → aggregate 결과 반환.
- judge 미주입 = 순수 결정적 (기존 체인과 동일, 재생성 안전 — 03 §5).
- judge 주입 = 결정적 미결 쌍만 LLM (deterministic-first, 05 §5/§6).
- 결정성 불변식: 동일 입력 → 동일 산출 (멱등성·재현성).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from orc_citadel.assertions import materialize
from orc_citadel.canonicalize import canonicalize_claims
from orc_citadel.contradiction import find_conflict_candidates
from orc_citadel.extract import extract_mentions
from orc_citadel.extract_claims import extract_claims
from orc_citadel.gate import Gate
from orc_citadel.graph_service import GraphService
from orc_citadel.parse import extract_html, parse_document
from orc_citadel.resolve import EntityResolver

FALLBACK_OBSERVED_AT = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)


def _now_ms() -> float:
    """현재 벽시계 ms (MVP #9 문서당 처리 시간 계측용)."""
    import time

    return time.perf_counter() * 1000


@dataclass
class PipelineResult:
    """파이프라인 실행 요약 — aggregate + 그래프 + 판정 통계 (검증·감사 계약)."""
    docs: int = 0
    parse_fail: int = 0
    mentions: int = 0
    authoritative_mentions: int = 0
    claims: int = 0
    promoted_claims: int = 0
    assertions: int = 0
    canonicals: int = 0
    canonical_members: int = 0
    conflicts: int = 0
    llm_canonical_verdicts: int = 0
    llm_conflict_verdicts: int = 0
    nodes: int = 0
    edges: int = 0
    clusters: int = 0  # S4 dedup — 근접 복제 클러스터 수.
    elapsed_ms: float = 0.0  # 대량 실행 드라이버 — 벽시계 (Q4/성능 기록용, 파이프라인 무관).
    per_doc_elapsed_ms: list[float] = field(default_factory=list)  # MVP #9 — 문서당 벽시계 (design 10 §1.4 throughput/latency).


def _run_chain(metas, zone, gate, resolver, judge, result: PipelineResult,
               mutation_log=None) -> list:
    """문서별 결정적 추출·해소·게이트·claim·어세션 체인. 전체 claim 리스트 반환.

    `mutation_log`(① postgres SoT) 제공 시, 승격 claim 의 그래프 mutation 을
    `create_node {id, props}` 로 기록한다 (ADR-602 — 그래프 변경은 로그로만).
    """
    all_claims = []
    docs_meta: list = []  # S4 dedup 배선용 (04 §4) — 근접 복제 축소.
    for m in metas:
        result.docs += 1
        _doc_t0 = _now_ms()  # MVP #9 — 문서당 벽시계 (design 10 §1.4).
        try:
            doc = extract_html(m["content"], m["url"])
        except Exception:
            result.parse_fail += 1
            continue
        segs = parse_document(m["doc_id"], doc)
        # S4 입력 — 결정적 체인에서 생성된 clean text·시간·신뢰 메타 수집.
        docs_meta.append({
            "doc_id": m["doc_id"],
            "text": doc.text,
            "publication_time": (doc.publication_time or "").isoformat()
            if hasattr(doc.publication_time, "isoformat") else (doc.publication_time or ""),
            "source_type": m.get("source_type", ""),
        })
        ms = extract_mentions(m["doc_id"], doc, segs)
        for men in ms:
            zone.persist_mention(men)
        result.mentions += len(ms)
        entities, resolved = resolver.resolve(m["doc_id"], ms)
        for e in entities:
            zone.persist_resolved(e, resolved)
        for rm in resolved:
            r = gate.evaluate_mention(rm.mention,
                                      resolved_entity_id=rm.resolved_entity_id)
            if r.promote:
                zone.set_mention_authoritative(rm.mention.mention_id)
                result.authoritative_mentions += 1
        claims = extract_claims(m["doc_id"], segs, resolved,
                                {e.entity_id: e for e in entities})
        for c in claims:
            # §8.2 extraction_record 영속 → claim에 provenance_ref 부여 (ADR-305 게이트 충족).
            ext_id = zone.persist_extraction_record(
                element_id=c.claim_candidate_id,
                doc_id=c.doc_id,
                segment_id=f"{c.doc_id}#p{c.seg_order}",
                char_start=c.char_start, char_end=c.char_end,
                model_id="det",
            )
            # frozen dataclass — object.__setattr__ 로 provenance_ref 부여
            object.__setattr__(c, "provenance_ref", [ext_id])
            zone.persist_claim(c)
            cr = gate.evaluate(c)
            zone.update_claim_status(c.claim_candidate_id, cr.status,
                                     ",".join(cr.reasons) if cr.reasons else None)
            if cr.promote:
                mut = next((mm["mutation_id"] for mm in gate.mutations()
                            if mm["op"] == "create_node"
                            and mm["element_ref"] == c.claim_candidate_id), "")
                # ① postgres SoT 배선 — 그래프 변경을 append-only 로그에 기록 (ADR-602).
                if mutation_log is not None:
                    mutation_log.apply(
                        doc_id=c.doc_id,
                        op="create_node",
                        source_span=(f"{c.doc_id}#p{c.seg_order}", c.char_start, c.char_end),
                        idempotency_key=f"create_node:{c.claim_candidate_id}",
                        payload={"id": c.claim_candidate_id, "props": {}},
                        actor="pipeline",
                        version_tuple={"ontology_version": "1.0.0", "schema_version": "0.1.0",
                                       "model_id": "det", "extraction_code_version": "p1"},
                    )
                observed = doc.publication_time or FALLBACK_OBSERVED_AT
                a = materialize(c, observed_at=observed, mutation=mut)
                zone.persist_assertion(a)
                result.assertions += 1
                # 정규 삼항 스키 (subject--predicate-->object) 로 공급망 관계 엣지 배선.
                # object 가 해소 엔티티인 승격 claim 만 (미상은 노드만, GR 참조 무결성).
                if mutation_log is not None and c.object_id is not None:
                    # 엣지 끝점(엔티티) 노드를 먼저 보장 — replay 시 dangling_ref quarantine
                    # 방지 (불변식 §3-4 참조 무결성: 양 끝 노드 존재). entity_id 별 멱등.
                    for eid in (c.subject_id, c.object_id):
                        mutation_log.apply(
                            doc_id=c.doc_id,
                            op="create_node",
                            source_span=(f"{c.doc_id}#p{c.seg_order}", c.char_start, c.char_end),
                            idempotency_key=f"create_entity:{eid}",
                            payload={"id": eid, "props": {}},
                            actor="pipeline",
                            version_tuple={"ontology_version": "1.0.0",
                                           "schema_version": "0.1.0",
                                           "model_id": "det",
                                           "extraction_code_version": "p1"},
                        )
                    mutation_log.apply(
                        doc_id=c.doc_id,
                        op="create_edge",
                        source_span=(f"{c.doc_id}#p{c.seg_order}", c.char_start, c.char_end),
                        idempotency_key=f"create_edge:{c.claim_candidate_id}",
                        payload={"type": c.predicate, "from": c.subject_id,
                                 "to": c.object_id, "props": {}},
                        actor="pipeline",
                        version_tuple={"ontology_version": "1.0.0", "schema_version": "0.1.0",
                                       "model_id": "det", "extraction_code_version": "p1"},
                    )
        result.claims += len(claims)
        all_claims.extend(claims)
        # MVP #9 — 문서당 처리 시간 (design 10 §1.4 latency). 파싱 실패는 제외.
        result.per_doc_elapsed_ms.append(round(_now_ms() - _doc_t0, 3))

    # S4 dedup 배선 — 근접 복제를 dup_clusters 로 축소 (04 §4, ADR-403). 결정적.
    if docs_meta:
        from .dedup import Deduplicator

        clusters = Deduplicator().dedup(docs_meta)
        for cl in clusters:
            zone.persist_cluster(
                cluster_id=cl.cluster_id,
                root_doc_id=cl.root_doc_id,
                member_doc_ids=list(cl.member_doc_ids),
                independent_addition_doc_ids=list(cl.independent_addition_doc_ids),
                dedup_method=cl.dedup_method,
            )
        result.clusters = len(clusters)
    return all_claims


def _build_graph(gate: Gate) -> GraphService:
    """gate 이벤트(create_node/edge)를 GraphService 재구축으로 authoritative 그래프 생성."""
    events = []
    for mut in gate.mutations():
        op = mut["op"]
        if op == "create_node":
            events.append({
                "mutation_id": mut["mutation_id"],
                "idempotency_key": mut["idempotency_key"],
                "op": "create_node",
                "payload": {"id": mut["element_ref"], "props": {}, "labels": []},
            })
        elif op == "create_edge":
            events.append({
                "mutation_id": mut["mutation_id"],
                "idempotency_key": mut["idempotency_key"],
                "op": "create_edge",
                "payload": {"type": "POSSIBLY_SAME_AS", "from": "",
                            "to": "", "props": {}},
            })
    g = GraphService()
    g.apply(events)
    return g


def _persist_llm_canonical(zone, llm_records: list) -> None:
    """canonicalize_claims가 누적한 LLM CanonicalRecord를 S23 테이블에 영속.

    version tuple(03 §7.1 5축)을 조립해 canonical_llm_records에 저장 — 판정 근거가
    judge flavor에 무관하게 보존된다 (S27: 기존 _persist_llm_verdicts는 확장형 judge의
    `verdicts` 만 봐서 plain judge의 판정이 유실되는 통합 버그 수정).
    """
    from orc_citadel.canonicalize import LlmCanonicalRecord

    for rec in llm_records:
        if not isinstance(rec, LlmCanonicalRecord):
            continue
        zone.persist_canonical_llm_record(
            claim_id_a=rec.claim_id_a, claim_id_b=rec.claim_id_b,
            relation=rec.relation, canonical_text=rec.canonical_text,
            confidence=rec.confidence, rationale=rec.rationale,
            version_tuple={"ontology_version": "1.0.0", "schema_version": "0.1.0",
                           "prompt_template_hash": "", "model_id": "",
                           "extraction_code_version": "p1"},
            judged_by=rec.judged_by,
        )


def _persist_llm_verdicts(zone, judge) -> None:
    """LLM 판정을 S23 테이블에 영속 — judge가 기록한 verdict를 소비.

    canonicalize/contradiction은 judge의 dict 결과를 내부 소비하므로, 판정 기록은
    judge가 `verdicts`(S23 `_BoundedJudge` 형식: (kind, pair, dict))로 노출해야
    저장 가능하다. 확장형 judge가 없으면 안전하게 no-op (영속은 call-site 위임).
    """
    if judge is None or not hasattr(judge, "verdicts"):
        return
    from orc_citadel.llm_pipeline_smoke import persist_llm_verdicts as _p

    _p(zone, judge)


def run_pipeline(metas, zone, judge=None, mutation_log=None) -> PipelineResult:
    """raw docs(meta list)를 단일 진입점으로 실행해 결정적 체인 + 그래프 + 영속 완료.

    `mutation_log`(① postgres SoT) 제공 시 graph mutation 을 로그에 기록하고,
    그래프는 로그의 **replay**(⑤ `replay_graph`)로 재구축한다 (ADR-304 실경로).
    미제공 시 기존 in-memory `_build_graph(gate)` 유지 (파괴 없음).
    """
    resolver = EntityResolver()
    gate = Gate()
    result = PipelineResult()

    all_claims = _run_chain(metas, zone, gate, resolver, judge, result,
                            mutation_log=mutation_log)

    # 캐노니컬·모순 — judge 주입 시 미결 쌍만 LLM (05 §4.2·§5.2).
    promoted = [c for c in all_claims
                if gate.result(c.claim_candidate_id) is not None
                and gate.result(c.claim_candidate_id).promote]
    # LLM 캐노니컬 판정을 누적 → S23 영속 (judge가 _BoundedJudge든 평면 dict든 동작).
    llm_records: list = []
    canonicals = canonicalize_claims(promoted, judge=judge, llm_records=llm_records)
    _persist_llm_canonical(zone, llm_records)
    for cc in canonicals:
        zone.persist_canonical(cc)
        for cid in cc.member_claim_ids:
            zone.set_claim_canonical(cid, cc.canonical_claim_id)
    result.canonicals = len(canonicals)
    result.canonical_members = sum(len(c.member_claim_ids) for c in canonicals)

    conflicts = find_conflict_candidates(all_claims, judge=judge)
    for cf in conflicts:
        zone.persist_conflict(cf)
    result.conflicts = len(conflicts)
    result.promoted_claims = len(promoted)

    # LLM verdict 영속 (S23) — judge가 verdict를 기록하는 확장형이면 저장.
    _persist_llm_verdicts(zone, judge)
    result.llm_canonical_verdicts = len(zone.canonical_llm_records())
    result.llm_conflict_verdicts = len(zone.conflict_verdicts())

    # 그래프 재구축 (06 §2) + aggregate.
    # mutation_log(① postgres SoT) 제공 시 로그 재생(⑤)으로, 아니면 기존 in-memory(파괴 없음).
    if mutation_log is not None:
        from orc_citadel.graph_replay import replay_graph

        g = replay_graph(mutation_log.all_mutations())
    else:
        g = _build_graph(gate)
    result.nodes = len(g.nodes())
    result.edges = len(g.edges())

    return result
