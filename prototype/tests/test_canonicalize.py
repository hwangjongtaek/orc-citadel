"""S9 Claim Canonicalization — 결정적 최소 (설계 05 §4, 02 §2.4·§3.1) TDD.

동일 (subject, predicate) blocking 그룹 내에서 겹치는 source_span(같은 문장 표현)의
claim들을 `equivalent`로 판정해 하나의 CanonicalClaim으로 묶는다 (05 §4.1 후보 축소 +
결정적 equivalent). LLM 관계 판정(§4.2 나머지 라벨)은 스텁 · 후속.
"""
from __future__ import annotations

import pytest

from orc_citadel.canonicalize import CanonicalClaim, canonicalize_claims, canonical_claim_id_for
from orc_citadel.extract_claims import ClaimCandidate, claim_id_for


def _c(claim_id: str, pred: str, subj: str, seg: int, start: int, end: int,
       frag: str = "power") -> ClaimCandidate:
    return ClaimCandidate(
        claim_candidate_id=claim_id, doc_id=f"doc-{claim_id}",
        predicate=pred, subject_id=subj, object_id=None, object_literal=None,
        modality="asserted", polarity="positive", confidence=0.8,
        seg_order=seg, char_start=start, char_end=end, surface_fragment=frag,
        event_type_hint=None, status="candidate",
    )


def test_same_subject_predicate_grouped():
    """같은 (subject, predicate) + 겹치는 span → 1 CanonicalClaim."""
    claims = [
        _c("clm-a", "announces", "org-1", 0, 5, 10, "power"),
        _c("clm-b", "announces", "org-1", 0, 5, 10, "power"),
    ]
    cc = canonicalize_claims(claims)
    assert len(cc) == 1
    assert set(cc[0].member_claim_ids) == {"clm-a", "clm-b"}
    assert cc[0].subject_id == "org-1"
    assert cc[0].predicate == "announces"
    assert cc[0].canonical_claim_id.startswith("ccl-")


def test_same_fragment_across_segments_merged():
    """같은 blocking 그룹(subject+predicate)에서 같은 표면형이 다른 문장에 반복 →
    동일 주장으로 병합 (05 §4 equivalent, precision)."""
    claims = [
        _c("clm-a", "announces", "org-1", 0, 3, 8, "power"),
        _c("clm-b", "announces", "org-1", 4, 2, 7, "power"),
        _c("clm-c", "announces", "org-1", 9, 5, 12, "power"),
    ]
    cc = canonicalize_claims(claims)
    # 세 claim 모두 같은 표면형 "power" → 한 CanonicalClaim.
    assert len(cc) == 1
    assert len(cc[0].member_claim_ids) == 3


def test_different_fragment_different_segment_separate():
    """다른 표면형(다른 문장) claim은 병합하지 않음 — 결정적 precision."""
    claims = [
        _c("clm-a", "announces", "org-1", 0, 0, 4, "host"),
        _c("clm-b", "announces", "org-1", 3, 0, 5, "power"),
    ]
    cc = canonicalize_claims(claims)
    assert len(cc) == 2  # host vs power — 서로 다른 주장 표현


def test_different_predicate_no_merge():
    """predicate 다른 그룹은 묶지 않음 (blocking, §4.1)."""
    claims = [
        _c("clm-a", "announces", "org-1", 0, 0, 6, "host"),
        _c("clm-b", "supplies", "org-1", 0, 0, 6, "supplies"),
    ]
    cc = canonicalize_claims(claims)
    assert len(cc) == 2


def test_deterministic():
    """동일 입력 → 동일 ccl (idempotency, 03 §5)."""
    claims = [
        _c("clm-a", "announces", "org-1", 0, 2, 8, "power"),
        _c("clm-b", "announces", "org-1", 0, 2, 8, "power"),
    ]
    a = canonicalize_claims(claims)
    b = canonicalize_claims(claims)
    assert [c.canonical_claim_id for c in a] == [c.canonical_claim_id for c in b]


def test_canonical_text_repr():
    """canonical_text는 동치류의 대표 (결정적 — 첫/uniq 표면형)."""
    claims = [
        _c("clm-a", "announces", "org-1", 0, 5, 10, "power"),
        _c("clm-b", "announces", "org-1", 0, 5, 10, "powered"),
    ]
    cc = canonicalize_claims(claims)
    assert cc[0].canonical_text  # 비어있지 않음
    assert cc[0].member_claim_ids


def test_canonical_claim_id_deterministic():
    """canonical ID는 (subject, predicate, member set) 기반 결정적."""
    claims = [
        _c("clm-a", "announces", "org-1", 0, 2, 6),
        _c("clm-b", "announces", "org-1", 0, 2, 6),
    ]
    cc = canonicalize_claims(claims)
    assert cc[0].canonical_claim_id == canonical_claim_id_for("org-1", "announces", {"clm-a", "clm-b"})
