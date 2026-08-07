"""S41 실데이터 승격 적용 + Open Question 실측 리포트 TDD.

S38–S40 승격 파이프라인을 실데이터에 적용해 design 10 §3.1 검증 + Q3/Q5 최소 실측.
- promotion: 5축 판정 (INITIALIZED/PROMOTED/BLOCKED major/minor).
- q3: claim·mention confidence 분포 + 저신뢰 임계 후보.
- q5: LLM 비용 상태 (결정적-only 여부).
- **read-mostly** (불변식 §3-3): 리포트는 조회, 골든 영속은 호출자가 임시 복사에서.
- 결정성 — 동일 zone → 동일 리포트.

Atomic TDD: Red → Green.
"""
from __future__ import annotations

import pytest

from orc_citadel.phase0_report import generate_report
from orc_citadel.curated_zone import CuratedZone
from orc_citadel.canonicalize import CanonicalClaim


def _zone() -> CuratedZone:
    z = CuratedZone(":memory:")
    z.initialize()
    # 캐노니컬 병합 + 골든 + claim confidence 배치.
    z.persist_golden_pair("clm-a", "clm-b", "equivalent", "dev", "g1",
                          "human:x", "t", "x")
    z.persist_canonical(CanonicalClaim("ccl-1", "org-a", "announces", "org-b",
                                       "x", ["clm-a", "clm-b"]))
    z.set_claim_canonical("clm-a", "ccl-1")
    z.set_claim_canonical("clm-b", "ccl-1")
    # claim confidence 배치 (0.5, 0.9).
    from orc_citadel.extract_claims import ClaimCandidate
    for cid, conf in (("clm-a", 0.5), ("clm-b", 0.9)):
        z.persist_claim(ClaimCandidate(
            claim_candidate_id=cid, doc_id="doc-1", predicate="announces",
            subject_id="org-a", object_id="org-b", object_literal=None,
            modality="asserted", polarity="positive", confidence=conf,
            seg_order=0, char_start=0, char_end=4, surface_fragment="x",
            event_type_hint=None, status="promoted"))
    return z


def test_report_structure():
    """promotion/q3/q5/summary 포함."""
    z = _zone()
    rep = generate_report(z)
    assert isinstance(rep.promotion, dict) and rep.promotion
    assert isinstance(rep.q3, dict) and rep.q3
    assert isinstance(rep.q5, dict) and rep.q5
    assert isinstance(rep.summary, str) and rep.summary


def test_promotion_axis_result():
    """승격 판정 — 초기(INITIALIZED) 포함 행위."""
    z = _zone()
    rep = generate_report(z)
    assert rep.promotion["action"] in ("INITIALIZED", "PROMOTED", "BLOCKED")
    assert "ontology_major_bump" in rep.promotion


def test_q3_confidence_distribution():
    """Q3 confidence 분포 — 범위·min/max/p50."""
    z = _zone()
    rep = generate_report(z)
    q3 = rep.q3
    assert q3["count"] == 2
    assert 0.0 <= q3["min"] <= q3["max"] <= 1.0
    assert q3["max"] == pytest.approx(0.9)
    assert q3["min"] == pytest.approx(0.5)
    assert "low_confidence_candidate" in q3


def test_q5_llm_cost_state():
    """Q5 — 결정적-only 상태."""
    z = _zone()
    rep = generate_report(z)
    assert rep.q5["llm_costs_measured"] is False  # 결정적 체인만 → 미측정.
    assert "note" in rep.q5


def test_read_only_no_original_mutation():
    """리포트는 조회만 — 골든·baseline을 zone에 영속하지 않음."""
    z = _zone()
    generate_report(z)
    assert len(z.golden_pairs()) == 1     # 기존 골든 그대로.
    assert z.active_baseline() is None    # baseline 생성 없음 (read-only).
    assert len(z.promotion_baselines()) == 0


def test_determinism():
    """동일 zone → 동일 리포트."""
    a = generate_report(_zone())
    b = generate_report(_zone())
    assert a == b
