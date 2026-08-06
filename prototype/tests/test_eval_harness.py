"""S33 평가 하네스 (설계 10 §1.2·§2, 소량 골든셋) TDD.

프로젝트 핵심 가치(design 10 §8 "KG가 얼마나 정확한가")에 수치로 답하는 경량.
**claim pair 골든셋**으로 파이프라인 산출(캐노니컬·모순)을 대조해 P/R/F1 계산.

- Canonicalization P/R (design 10 §1.2, gate ≥ 0.85): 골든 equivalent 쌍이 실제
  같은 CanonicalClaim으로 병합되는지 — TP/FP/FN.
- Contradiction P/R (design 10 §1.2, gate P ≥ 0.90, target R ≥ 0.75): 골든 contradicts
  쌍이 실제 conflict_candidates에 존재하는지.
- split ∈ {dev, test} (ADR-1007 튜닝/게이트 분리).
- 골든셋은 **human review as data** (design 10 §2.2, 불변식 §3-7).
- **read-only** (불변식 §3-3) — 대조만, 쓰기·영속·mutation 미노출.

Atomic TDD: Red → Green → Refactor.
"""
from __future__ import annotations

import pytest

from orc_citadel.eval_harness import EvalHarness, GoldenPair, Metric


def _membership(canonical_claims: list[dict], member_of: list[dict]) -> tuple[dict, dict]:
    """캐노니컬 상태를 (claim→canonical_id) 맵으로 정규화."""
    cc_by_id = {c["canonical_claim_id"]: set(c.get("member_claim_ids", [])) for c in canonical_claims}
    m = {}
    for row in member_of:
        m[row["claim_id"]] = row["canonical_claim_id"]
    return cc_by_id, m


def _harness(canonical_claims=(), member_of=(), conflicts=(), golden=()):
    return EvalHarness(
        canonical_claims=canonical_claims, member_of=member_of,
        conflicts=conflicts, golden=golden)


# --- Metric 경계 안전 ------------------------------------------------------

def test_metric_zero_division_safe():
    """TP=0 → precision/recall/f1 = 0.0 (division by zero 안전)."""
    m = Metric(tp=0, fp=0, fn=0)
    assert m.precision == 0.0
    assert m.recall == 0.0
    assert m.f1 == 0.0


def test_metric_perfect():
    """TP만 → 1.0."""
    m = Metric(tp=5, fp=0, fn=0)
    assert m.precision == 1.0
    assert m.recall == 1.0
    assert m.f1 == 1.0


def test_metric_f1():
    """P=0.75, R=0.6 → F1."""
    m = Metric(tp=3, fp=1, fn=2)  # P=3/4=0.75, R=3/5=0.6.
    assert m.precision == pytest.approx(0.75)
    assert m.recall == pytest.approx(0.6)
    assert m.f1 == pytest.approx(2 * 0.75 * 0.6 / (0.75 + 0.6))


# --- Canonicalization -------------------------------------------------------

def test_canonicalization_tp():
    """골든 equivalent 쌍이 같은 캐노니컬로 병합 → TP."""
    h = _harness(
        canonical_claims=[{"canonical_claim_id": "ccl-1", "member_claim_ids": ["clm-a", "clm-b"]}],
        member_of=[{"claim_id": "clm-a", "canonical_claim_id": "ccl-1"},
                   {"claim_id": "clm-b", "canonical_claim_id": "ccl-1"}],
        golden=[GoldenPair("clm-a", "clm-b", "equivalent")])
    m = h.canonicalization_metrics()
    assert (m.tp, m.fp, m.fn) == (1, 0, 0)


def test_canonicalization_unrelated_separate():
    """골든 unrelated 쌍이 서로 다른 캐노니컬 → 오분류 없음 (TP/FN 0)."""
    h = _harness(
        canonical_claims=[{"canonical_claim_id": "ccl-1", "member_claim_ids": ["clm-a"]},
                          {"canonical_claim_id": "ccl-2", "member_claim_ids": ["clm-b"]}],
        member_of=[{"claim_id": "clm-a", "canonical_claim_id": "ccl-1"},
                   {"claim_id": "clm-b", "canonical_claim_id": "ccl-2"}],
        golden=[GoldenPair("clm-a", "clm-b", "unrelated")])
    m = h.canonicalization_metrics()
    # unrelated는 캐노니컬화 대상이 아니므로 not-defining — TP/FN 0.
    assert (m.tp, m.fp, m.fn) == (0, 0, 0)


def test_canonicalization_wrong_merge_fp():
    """골든 unrelated가 같은 캐노니컬로 잘못 병합 → FP (precision 하락)."""
    h = _harness(
        canonical_claims=[{"canonical_claim_id": "ccl-1", "member_claim_ids": ["clm-a", "clm-b"]}],
        member_of=[{"claim_id": "clm-a", "canonical_claim_id": "ccl-1"},
                   {"claim_id": "clm-b", "canonical_claim_id": "ccl-1"}],
        golden=[GoldenPair("clm-a", "clm-b", "unrelated")])
    m = h.canonicalization_metrics()
    assert (m.tp, m.fp, m.fn) == (0, 1, 0)
    assert m.precision == 0.0  # TP=0, FP=1.


def test_canonicalization_missed_merge_fn():
    """골든 equivalent가 서로 다른 캐노니컬로 분리 → FN (recall 하락)."""
    h = _harness(
        canonical_claims=[{"canonical_claim_id": "ccl-1", "member_claim_ids": ["clm-a"]},
                          {"canonical_claim_id": "ccl-2", "member_claim_ids": ["clm-b"]}],
        member_of=[{"claim_id": "clm-a", "canonical_claim_id": "ccl-1"},
                   {"claim_id": "clm-b", "canonical_claim_id": "ccl-2"}],
        golden=[GoldenPair("clm-a", "clm-b", "equivalent")])
    m = h.canonicalization_metrics()
    assert (m.tp, m.fp, m.fn) == (0, 0, 1)
    assert m.recall == 0.0


# --- Contradiction ----------------------------------------------------------

def test_contradiction_tp():
    """골든 contradicts 쌍이 conflict로 발견 → TP."""
    h = _harness(
        conflicts=[{"claim_id_a": "clm-a", "claim_id_b": "clm-b", "conflict_type": "value_conflict"}],
        golden=[GoldenPair("clm-a", "clm-b", "contradicts")])
    m = h.contradiction_metrics()
    assert (m.tp, m.fp, m.fn) == (1, 0, 0)


def test_contradiction_missed_fn():
    """골든 contradicts가 conflict에 없음 → FN."""
    h = _harness(
        conflicts=[],
        golden=[GoldenPair("clm-a", "clm-b", "contradicts")])
    m = h.contradiction_metrics()
    assert (m.tp, m.fp, m.fn) == (0, 0, 1)


def test_contradiction_false_positive():
    """골든 unrelated가 conflict로 오판 → FP (precision 하락)."""
    h = _harness(
        conflicts=[{"claim_id_a": "clm-a", "claim_id_b": "clm-b", "conflict_type": "value_conflict"}],
        golden=[GoldenPair("clm-a", "clm-b", "unrelated")])
    m = h.contradiction_metrics()
    assert (m.tp, m.fp, m.fn) == (0, 1, 0)


# --- split / report ---------------------------------------------------------

def test_split_filter_dev():
    """split=dev만 평가 (ADR-1007)."""
    h = _harness(
        canonical_claims=[{"canonical_claim_id": "ccl-1", "member_claim_ids": ["clm-a", "clm-b"]}],
        member_of=[{"claim_id": "clm-a", "canonical_claim_id": "ccl-1"},
                   {"claim_id": "clm-b", "canonical_claim_id": "ccl-1"}],
        golden=[GoldenPair("clm-a", "clm-b", "equivalent", split="dev"),
                GoldenPair("clm-x", "clm-y", "equivalent", split="test")])
    m = h.canonicalization_metrics(split="dev")
    assert m.tp == 1  # dev만.


def test_report():
    """report — 지표 + gate 통과 여부."""
    h = _harness(
        canonical_claims=[{"canonical_claim_id": "ccl-1", "member_claim_ids": ["clm-a", "clm-b"]}],
        member_of=[{"claim_id": "clm-a", "canonical_claim_id": "ccl-1"},
                   {"claim_id": "clm-b", "canonical_claim_id": "ccl-1"}],
        golden=[GoldenPair("clm-a", "clm-b", "equivalent")])
    rep = h.report()
    assert "canonicalization" in rep and "contradiction" in rep
    cc = rep["canonicalization"]
    assert cc["metrics"]["precision"] == 1.0
    assert "gate" in cc
    assert cc["gate"]["pass"] is not None  # 임계 비교 결과.
    # phase 0 소량 — gate 미충족해도 block 안 함 (리포트만).


def test_read_only_no_mutation():
    """harness는 read-only — 쓰기·영속·mutation 미노출."""
    h = _harness(golden=[GoldenPair("a", "b", "equivalent")])
    for bad in ("apply", "persist", "create_node", "create_edge", "insert"):
        assert not hasattr(h, bad), f"read-only 위반: {bad} 노출"
