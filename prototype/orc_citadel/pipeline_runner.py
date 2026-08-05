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


def _run_chain(metas, zone, gate, resolver, judge, result: PipelineResult) -> list:
    """문서별 결정적 추출·해소·게이트·claim·어세션 체인. 전체 claim 리스트 반환."""
    all_claims = []
    for m in metas:
        result.docs += 1
        try:
            doc = extract_html(m["content"], m["url"])
        except Exception:
            result.parse_fail += 1
            continue
        segs = parse_document(m["doc_id"], doc)
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
            zone.persist_claim(c)
            cr = gate.evaluate(c)
            zone.update_claim_status(c.claim_candidate_id, cr.status,
                                     ",".join(cr.reasons) if cr.reasons else None)
            if cr.promote:
                mut = next((mm["mutation_id"] for mm in gate.mutations()
                            if mm["op"] == "create_node"
                            and mm["element_ref"] == c.claim_candidate_id), "")
                observed = doc.publication_time or FALLBACK_OBSERVED_AT
                a = materialize(c, observed_at=observed, mutation=mut)
                zone.persist_assertion(a)
                result.assertions += 1
        result.claims += len(claims)
        all_claims.extend(claims)
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


def run_pipeline(metas, zone, judge=None) -> PipelineResult:
    """raw docs(meta list)를 단일 진입점으로 실행해 결정적 체인 + 그래프 + 영속 완료."""
    resolver = EntityResolver()
    gate = Gate()
    result = PipelineResult()

    all_claims = _run_chain(metas, zone, gate, resolver, judge, result)

    # 캐노니컬·모순 — judge 주입 시 미결 쌍만 LLM (05 §4.2·§5.2).
    promoted = [c for c in all_claims
                if gate.result(c.claim_candidate_id) is not None
                and gate.result(c.claim_candidate_id).promote]
    canonicals = canonicalize_claims(promoted, judge=judge)
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
    g = _build_graph(gate)
    result.nodes = len(g.nodes())
    result.edges = len(g.edges())

    return result
