"""Phase 2 Task #5 — Quarantine review → 골든셋 파생 (설계 05 §8.2, 10 §2.2, ADR-506) TDD.

human review as data (불변식 §3-7): 사람의 검토 결정(원 모델출력 + 수정결과 + 이유 +
reviewer)이 회귀 평가 골든셋의 원천이 된다 (05 §8.2). prototype 의 ReviewQueue 는
결정을 보존하지만 이를 zone 의 골든 claim/entity pair 로 승격하는 파생 경로가 없어,
human review 가 골든셋 평가(metrics_report/DoD ①)로 이어지지 않는다.
- `derive_golden_pairs(review_queue)` — corrected/approved review 결정을 zone 의
  golden_pairs (claim pair) / golden_entity_pairs (entity pair) 로 파생.
- 원 모델출력·수정결과를 바탕으로 라벨 결정 (независимо 파생 — 골든 라벨은 인간 결정).
- 결정적·멱등 파생 — 재실행 시 중복 없음 (03 §5).

Atomic TDD: Red → Green.
"""
from __future__ import annotations

import pytest

from orc_citadel.review import ReviewQueue, derive_golden
from orc_citadel.curated_zone import CuratedZone


def _zone():
    z = CuratedZone(":memory:")
    z.initialize()
    return z


def test_derive_claim_golden_from_correct():
    """corrected review (claim equivalence) → 골든 claim pair 로 파생 (05 §8.2)."""
    rq = ReviewQueue()
    # 원 모델출력: clm-a == clm-b 로 잘못 판정, 사람이 corrected 로 교정 (equivalent 유지).
    rq.enqueue("clm-a", {"verdict": "not_equivalent", "claim_b": "clm-b"}, "분류 불확실")
    rq.correct("clm-a", "human:reviewer", {"verdict": "equivalent", "claim_b": "clm-b",
                                           "reason": "동일 사안 기술"})
    z = _zone()
    n = derive_golden(rq, z, gold_version="g1", labeled_by="human:reviewer")
    # 파생된 골든 claim pair (equivalent 라벨).
    assert n == 1
    pairs = [g for g in z.golden_pairs() if g["label"] == "equivalent"]
    assert len(pairs) == 1
    assert {"clm-a", "clm-b"} == {pairs[0]["claim_a"], pairs[0]["claim_b"]}
    assert pairs[0]["labeled_by"] == "human:reviewer"


def test_derive_entity_golden_from_correct():
    """corrected review (entity same) → 골든 entity pair 로 파생 (5 §8.2)."""
    rq = ReviewQueue()
    rq.enqueue("res-NVDA", {"verdict": "not_same", "entity_b": "org:0"}, "해소 불확실")
    rq.correct("res-NVDA", "human:jane",
               {"verdict": "same", "entity_a": "surface:Organization:NVDA",
                "entity_b": "surface:Organization:NVIDIA", "reason": "동일 회사"})
    z = _zone()
    n = derive_golden(rq, z, gold_version="g1", labeled_by="human:jane")
    assert n == 1
    pairs = [g for g in z.golden_entity_pairs() if g["label"] == "same"]
    assert len(pairs) == 1
    assert pairs[0]["labeled_by"] == "human:jane"


def test_derive_skips_unreviewed():
    """아직 in_review/pending 인 결정은 파생 안 함 (인간 결정만 골든 원천)."""
    rq = ReviewQueue()
    rq.enqueue("clm-x", {"verdict": "not_equivalent"}, "대기")
    z = _zone()
    n = derive_golden(rq, z, gold_version="g1")
    assert n == 0
    assert z.golden_pairs() == []


def test_derive_idempotent():
    """동일 review 결정 재파생 → 중복 골든 없음 (멱등, 03 §5)."""
    rq = ReviewQueue()
    rq.enqueue("clm-a", {"verdict": "not_equivalent", "claim_b": "clm-b"}, "x")
    rq.correct("clm-a", "human:r", {"verdict": "equivalent", "claim_b": "clm-b"})
    z = _zone()
    derive_golden(rq, z, gold_version="g1")
    derive_golden(rq, z, gold_version="g1")  # 재실행.
    assert len(z.golden_pairs()) == 1  # 중복 없음.


def test_derive_deterministic_split():
    """파생은 결정적 split(gold_version 반영) — 재실행 동일."""
    rq = ReviewQueue()
    rq.enqueue("clm-a", {"verdict": "not_equivalent", "claim_b": "clm-b"}, "x")
    rq.correct("clm-a", "human:r", {"verdict": "equivalent", "claim_b": "clm-b"})
    z1, z2 = _zone(), _zone()
    derive_golden(rq, z1, gold_version="g2")
    derive_golden(rq, z2, gold_version="g2")
    a = [(g["claim_a"], g["claim_b"], g["label"], g["split"]) for g in z1.golden_pairs()]
    b = [(g["claim_a"], g["claim_b"], g["label"], g["split"]) for g in z2.golden_pairs()]
    assert a == b
