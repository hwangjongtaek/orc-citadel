"""S8 그래프 반영 게이트 (설계 05 §6, 03 §7) — TDD.

claim_candidates가 authoritative graph로 승격되기 전 거치는 4검증:
(1) schema (2) provenance (3) predicate 폐쇄성 (4) confidence 임계.
통과 → promoted(+ append-only create_node 이벤트), 실패 → quarantined(+ reason).
임계값은 05 §6이 10에 위임 — prototype은 placeholder 상수 (ADR).
"""
from __future__ import annotations

import pytest

from orc_citadel.extract_claims import ClaimCandidate, claim_id_for
from orc_citadel.gate import (
    CONTROLLED_PREDICATES,
    PROMOTION_CONFIDENCE,
    Gate,
    PromotionResult,
)


def _claim(conf: float = 0.8, predicate: str = "announces",
           subject: str | None = "org-abc", seg=0, start=0, end=12,
           frag="will host") -> ClaimCandidate:
    return ClaimCandidate(
        claim_candidate_id=claim_id_for("doc-1", seg, start, end, predicate),
        doc_id="doc-1", predicate=predicate, subject_id=subject,
        object_id=None, object_literal=None, modality="asserted",
        polarity="positive", confidence=conf, seg_order=seg,
        char_start=start, char_end=end, surface_fragment=frag,
        event_type_hint="earnings", status="candidate",
    )


def test_promotes_valid_claim():
    """모든 검증 통과 → promote(create_node 이벤트) + 상태 promoted."""
    gate = Gate()
    c = _claim()
    result = gate.evaluate(c)
    assert result.promote
    assert result.reasons == []
    assert result.status == "promoted"
    # append-only 이벤트 발행 (재구축 가능).
    ms = gate.mutations()
    assert len(ms) == 1
    assert ms[0]["op"] == "create_node"
    assert ms[0]["element_ref"] == c.claim_candidate_id


def test_rejects_low_confidence():
    """confidence < 임계 → quarantine(+ reason)."""
    gate = Gate()
    c = _claim(conf=max(0.0, PROMOTION_CONFIDENCE - 0.1))
    result = gate.evaluate(c)
    assert not result.promote
    assert result.status == "quarantined"
    assert any("confidence" in r for r in result.reasons)
    assert gate.mutations() == []  # 실패는 승격 이벤트 발행 안 함


def test_rejects_unknown_predicate():
    """predicate ∉ controlled vocabulary → quarantine (+ 온톨로지 proposal hint)."""
    gate = Gate()
    c = _claim(predicate="eats_cookies")
    result = gate.evaluate(c)
    assert not result.promote
    assert any("predicate" in r for r in result.reasons)


def test_rejects_missing_subject():
    """subject 미해소(빈 스트링) → Reference 무결성 위반 quarantine."""
    gate = Gate()
    c = _claim(subject="")
    result = gate.evaluate(c)
    assert not result.promote
    assert any("subject" in r for r in result.reasons)


def test_rejects_bad_span():
    """span 비정상 (char_start>=char_end) → provenance/schema 실패."""
    gate = Gate()
    c = _claim(start=5, end=5)  # 0 길이 span
    result = gate.evaluate(c)
    assert not result.promote


def test_rejects_confidence_out_of_range():
    """confidence ∉ [0,1] → schema 실패 quarantine."""
    gate = Gate()
    c = _claim(conf=1.5)
    result = gate.evaluate(c)
    assert not result.promote


def test_controlled_predicates_include_announces():
    """02 §5.1 어휘 — announces/depends_on/supplies 등 포함."""
    assert "announces" in CONTROLLED_PREDICATES
    assert "depends_on" in CONTROLLED_PREDICATES
    assert "supplies" in CONTROLLED_PREDICATES


def test_idempotent_event():
    """동일 claim 재평가 → 동일/추가 없는 이벤트 (03 §7 idempotency)."""
    gate = Gate()
    c = _claim()
    gate.evaluate(c)
    gate.evaluate(c)
    assert len(gate.mutations()) == 1
