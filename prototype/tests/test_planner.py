"""Investigation Planner (설계 07 §3.2) TDD.

질문 → 조사 가능한 하위 주장(subclaim) 트리 분해 — 그래프 기존 지식/공백 구분.

- plan(question, scope?) → {subclaims: [{id, text, required_evidence_types[],
  known, gap_reason?}], plan: {tool_calls[]}} (07 §3.2 strict JSON).
- subclaim마다 known/gap 라벨 필수 (07 §3.2 불변식).
- 질문의 subject·predicate·위치를 분해 — 결정적 규칙(± 그래프 known/gap 판정).
- 질문에 등장한 subject는 graph:read(zone assertions)로 known/gap 판정 —
  existing 지식 vs 공백 명시 분리 (07 §3.2·§3.1 비목표).
- **read-only** (불변식 §3-3): 분해·조회만, mutation 미노출.
- 결정적 (동일 질문·zone → 동일 트리).

Atomic TDD: Red → Green.
"""
from __future__ import annotations

import pytest

from orc_citadel.planner import InvestigationPlanner, Plan, PlannedSubclaim
from orc_citadel.curated_zone import CuratedZone


def _zone() -> CuratedZone:
    from orc_citadel.assertions import materialize
    from orc_citadel.extract import Mention
    from orc_citadel.extract_claims import ClaimCandidate
    from datetime import datetime, timezone

    z = CuratedZone(":memory:")
    z.initialize()
    # NVDA subject announce 어세션 2건 → 알려진 지식.
    cc = ClaimCandidate(
        claim_candidate_id="clm-a", doc_id="doc-a", predicate="announces",
        subject_id="NVDA", object_id="org-b", object_literal=None,
        modality="asserted", polarity="positive", confidence=0.8,
        seg_order=0, char_start=0, char_end=4, surface_fragment="x",
        event_type_hint=None, status="promoted")
    z.persist_claim(cc)
    z.persist_mention(Mention(mention_id="men-a", doc_id="doc-a",
                              segment_id="doc-a#s0", surface_text="NVDA",
                              mention_type="ORG", char_start=0, char_end=4,
                              context_window=None))
    z.persist_assertion(materialize(cc, observed_at=datetime(2026, 1, 1,
                                                             tzinfo=timezone.utc),
                                    mutation="mut-a"))
    return z


def test_plan_structure():
    """plan — strict JSON 스키마 (07 §3.2)."""
    z = _zone()
    plan = InvestigationPlanner(z).plan("NVDA가 어떤 파트너사를 announces 했는가?")
    assert isinstance(plan.subclaims, list) and plan.subclaims
    sc = plan.subclaims[0]
    for field in ("id", "text", "required_evidence_types", "known", "gap_reason"):
        assert hasattr(sc, field), f"subclaim 필드 부재: {field}"
    assert isinstance(plan.tool_calls, list)


def test_plan_tool_calls():
    """plan — tool_calls 포함 (graph:read 기존 지식 확인)."""
    z = _zone()
    plan = InvestigationPlanner(z).plan("NVDA announces?")
    assert plan.tool_calls
    assert any(tc["tool"] == "graph:read" for tc in plan.tool_calls)


def test_known_gap_label():
    """질문 subject NVDA — zone 어세션 존재 → known=True (기존 지식)."""
    z = _zone()
    plan = InvestigationPlanner(z).plan("NVDA가 announces 했는가?")
    sc = next(s for s in plan.subclaims if s.subject_id == "NVDA")
    assert sc.known is True
    assert sc.gap_reason is None


def test_unknown_subject_gap():
    """질문 subject INTEL — zone 어세션 없음 → gap (라벨 필수)."""
    z = _zone()
    plan = InvestigationPlanner(z).plan("INTEL이 announces 했는가?")
    assert plan.subclaims
    itc = [s for s in plan.subclaims if s.subject_id == "INTEL"]
    assert itc and itc[0].known is False
    assert itc[0].gap_reason is not None


def test_required_evidence_types():
    """subclaim — required_evidence_types 포함 (주장·근거 증거 유형)."""
    z = _zone()
    plan = InvestigationPlanner(z).plan("NVDA announces?")
    sc = plan.subclaims[0]
    assert sc.required_evidence_types
    assert isinstance(sc.required_evidence_types, list)


def test_read_only_no_mutation():
    """planner는 read-only — 쓰기·mutation 미노출."""
    p = InvestigationPlanner(_zone())
    for bad in ("apply", "persist", "create_node", "create_edge", "insert"):
        assert not hasattr(p, bad), f"read-only 위반: {bad} 노출"


def test_determinism():
    """동일 질문·zone → 동일 트리."""
    p = InvestigationPlanner(_zone())
    a = p.plan("NVDA announces?")
    b = p.plan("NVDA announces?")
    assert a == b
