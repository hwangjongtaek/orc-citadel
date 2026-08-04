"""S10 Contradiction — 결정적 충돌 후보 규칙 (설계 05 §5.1, 02 §3.1·ADR-504) TDD.

same subject ∧ (동일|호환) predicate · 상충 object/양극 → conflict_candidates 후보.
LLM 판정(§5.2)은 스텁 — 여기선 규칙으로 상충 후보 생성까지만. rationale·judged_by
저장 계약(§5.3) 유지 (규칙 판정 actor=pipeline). 결정적·idempotent (03 §5).
"""
from __future__ import annotations

import pytest

from orc_citadel.contradiction import ConflictCandidate, find_conflict_candidates
from orc_citadel.extract_claims import ClaimCandidate, claim_id_for


def _c(claim_id: str, pred: str, subj: str, polarity: str = "positive",
       obj: str | None = None, frag: str = "x") -> ClaimCandidate:
    return ClaimCandidate(
        claim_candidate_id=claim_id, doc_id="doc-1", predicate=pred,
        subject_id=subj, object_id=obj, object_literal=None,
        modality="asserted", polarity=polarity, confidence=0.8,
        seg_order=0, char_start=0, char_end=4, surface_fragment=frag,
        event_type_hint=None, status="candidate",
    )


def test_opposite_polarity_conflict():
    """same subject+predicate, positive vs negative → value_conflict 후보."""
    a = _c("clm-a", "depends_on", "org-1", polarity="positive")
    b = _c("clm-b", "depends_on", "org-1", polarity="negative")
    cc = find_conflict_candidates([a, b])
    assert len(cc) == 1
    c = cc[0]
    assert {c.claim_id_a, c.claim_id_b} == {"clm-a", "clm-b"}
    assert c.conflict_type in {"value_conflict", "polarity"}
    assert c.judged_by == "pipeline"
    assert c.rationale  # 비어있지 않음


def test_identical_claims_no_conflict():
    """동일 claim 쌍은 모순 아님."""
    a = _c("clm-a", "announces", "org-1")
    b = _c("clm-b", "announces", "org-1")
    cc = find_conflict_candidates([a, b])
    # 같은 subject+predicate+음극 없다 → 후보 없음 (같은 단순 주장).
    assert cc == []


def test_different_subject_no_conflict():
    """subject 다르면 모순 후보 아님 (blocking, §5.1)."""
    a = _c("clm-a", "depends_on", "org-1", polarity="positive")
    b = _c("clm-b", "depends_on", "org-2", polarity="negative")
    assert find_conflict_candidates([a, b]) == []


def test_different_predicate_no_conflict():
    """predicate 완전 다르면 후보 아님 (호환성 고려)."""
    a = _c("clm-a", "depends_on", "org-1", polarity="positive")
    b = _c("clm-b", "manufactures", "org-1", polarity="negative")
    assert find_conflict_candidates([a, b]) == []


def test_conflicting_object_literal():
    """같은 subject+predicate, 서로 다른 object → value_conflict 후보."""
    a = _c("clm-a", "has_market_share", "org-1", obj="org-a")
    b = _c("clm-b", "has_market_share", "org-1", obj="org-b")
    cc = find_conflict_candidates([a, b])
    assert len(cc) == 1
    assert cc[0].conflict_type == "value_conflict"


def test_same_object_no_conflict():
    """object 동일 → 모순 아님."""
    a = _c("clm-a", "has_market_share", "org-1", obj="org-a")
    b = _c("clm-b", "has_market_share", "org-1", obj="org-a")
    assert find_conflict_candidates([a, b]) == []


def test_deterministic():
    """동일 입력 → 동일 conflict 후보 (idempotency, 03 §5)."""
    claims = [
        _c("clm-a", "depends_on", "org-1", polarity="positive"),
        _c("clm-b", "depends_on", "org-1", polarity="negative"),
    ]
    a = find_conflict_candidates(claims)
    b = find_conflict_candidates(claims)
    assert [(c.claim_id_a, c.claim_id_b, c.conflict_type) for c in a] == \
           [(c.claim_id_a, c.claim_id_b, c.conflict_type) for c in b]
