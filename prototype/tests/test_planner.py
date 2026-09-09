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


# --- 질문 → entity name 해소 (조사 지시 입구 — W1) -------------------------------
#
# 실데이터 subject 는 `org-<해시>` 라 대문자 약어 추출로는 지식에 닿을 수 없다.
# 질문의 표면형(canonical_name·surface_forms — 한글 포함)을 zone entities 로
# 결정적 해소해 subject_id 에 잇는다. 미해소는 기존대로 gap 정직 표기.


def _zone_with_named_entity() -> CuratedZone:
    """실데이터형: subject 가 org-해시, entities 에 name/surface 가 있는 zone."""
    from orc_citadel.assertions import materialize
    from orc_citadel.extract_claims import ClaimCandidate
    from orc_citadel.resolve import Entity
    from datetime import datetime, timezone

    z = CuratedZone(":memory:")
    z.initialize()
    z.persist_entity(Entity(
        entity_id="org-1111111111", mention_type="ORG",
        canonical_name="NVIDIA Corp", surface_forms=("NVIDIA", "엔비디아")))
    z.persist_entity(Entity(
        entity_id="org-2222222222", mention_type="ORG",
        canonical_name="BN", surface_forms=("BN",)))
    cc = ClaimCandidate(
        claim_candidate_id="clm-o", doc_id="doc-o", predicate="announces",
        subject_id="org-1111111111", object_id=None, object_literal="x",
        modality="asserted", polarity="positive", confidence=0.8,
        seg_order=0, char_start=0, char_end=4, surface_fragment="x",
        event_type_hint=None, status="promoted")
    z.persist_claim(cc)
    z.persist_assertion(materialize(
        cc, observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        mutation="mut-o"))
    return z


def test_question_resolves_entity_name_to_subject_id():
    """질문의 'NVIDIA' 표면형 → org-id 해소, 어세션 존재 → known."""
    plan = InvestigationPlanner(_zone_with_named_entity()).plan(
        "NVIDIA 신제품 발표를 조사하라")
    sc = next(s for s in plan.subclaims if s.subject_id == "org-1111111111")
    assert sc.known is True and sc.gap_reason is None


def test_question_resolves_korean_surface_form():
    """한글 표면형('엔비디아') — 조사가 붙어도 해소된다."""
    plan = InvestigationPlanner(_zone_with_named_entity()).plan(
        "엔비디아가 발표한 내용을 조사")
    assert any(s.subject_id == "org-1111111111" and s.known
               for s in plan.subclaims)


def test_resolution_requires_word_boundary():
    """짧은 표면형('BN')이 다른 단어(RBNZ) 안에서 오탐하지 않는다."""
    plan = InvestigationPlanner(_zone_with_named_entity()).plan(
        "RBNZ 금리 결정을 조사")
    assert not any(s.subject_id == "org-2222222222" for s in plan.subclaims)


def test_unresolved_question_stays_honest_gap():
    """지식에 없는 질문 — 해소 실패는 gap 그대로 (§6.2, 사전 지식 추가 금지)."""
    plan = InvestigationPlanner(_zone_with_named_entity()).plan(
        "알수없는회사 동향 조사")
    assert plan.subclaims
    assert all(not s.known and s.gap_reason for s in plan.subclaims)


def test_resolved_entity_dedupes_acronym_extraction():
    """'NVIDIA' 가 name 해소되면 약어 추출로 중복 subclaim 을 내지 않는다."""
    plan = InvestigationPlanner(_zone_with_named_entity()).plan(
        "NVIDIA announces?")
    ids = [s.subject_id for s in plan.subclaims]
    assert ids.count("org-1111111111") == 1
    assert "NVIDIA" not in ids
