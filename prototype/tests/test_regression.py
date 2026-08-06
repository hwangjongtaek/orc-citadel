"""S35 평가 회귀 실행기 (설계 10 §3) TDD.

EvalHarness 지표를 **last-promoted baseline** 스냅샷과 대조해 per-metric delta·
회귀·block 여부를 판정한다 (design 10 §3.1 승격 게이트, §3.2 상대 허용치 ADR-1008).

- EvalSnapshot.capture(harness) — report()에서 metric dict 추출.
- RegressionRunner.run(baseline, current) — delta, regressions(허용치 초과 하락), blocked.
- permitted 기본 (ADR-1008 placeholder): canonicalization_f1 ≤2%p,
  canonicalization_precision 0p(hard), contradiction_precision ≤1%p,
  contradiction_recall ≤2%p.
- 골든 gate 미달(Harness.promotion_blocked)도 block.
- **read-only** (불변식 §3-3) — 스냅샷·대조만, 쓰기·영속·mutation 미노출.

Atomic TDD: Red → Green → Refactor.
"""
from __future__ import annotations

import pytest

from orc_citadel.regression import EvalSnapshot, RegressionRunner
from orc_citadel.eval_harness import EvalHarness, GoldenPair


def _harness(golden, canonical_claims=(), member_of=()):
    return EvalHarness(
        canonical_claims=canonical_claims, member_of=member_of, conflicts=[],
        golden=golden)


def _snap(metrics, version="g1"):
    return EvalSnapshot(version=version, metrics=metrics)


F1_100 = {"canonicalization_f1": 1.0, "canonicalization_precision": 1.0,
          "contradiction_precision": 1.0, "contradiction_recall": 1.0}


# --- capture ---------------------------------------------------------------

def test_capture_from_harness():
    """EvalSnapshot.capture(harness) — report()에서 metric dict 추출."""
    h = _harness([GoldenPair("clm-a", "clm-b", "equivalent")],
                 canonical_claims=[{"canonical_claim_id": "ccl-1",
                                    "member_claim_ids": ["clm-a", "clm-b"]}],
                 member_of=[{"claim_id": "clm-a", "canonical_claim_id": "ccl-1"},
                            {"claim_id": "clm-b", "canonical_claim_id": "ccl-1"}])
    snap = EvalSnapshot.capture(h, version="g1")
    assert snap.metrics["canonicalization_f1"] == 1.0
    assert snap.metrics["canonicalization_precision"] == 1.0
    assert "contradiction_precision" in snap.metrics


# --- run: 동일 / 상승 ------------------------------------------------------

def test_identical_no_regression():
    """baseline == current → delta 0, blocked=False."""
    r = RegressionRunner().run(_snap(F1_100), _snap(F1_100))
    assert all(abs(v) < 1e-9 for v in r.deltas.values())
    assert r.regressions == []
    assert r.blocked is False


def test_improvement_no_regression():
    """상승(current > baseline) → delta 양수, 회귀 없음."""
    base = dict(F1_100, canonicalization_f1=0.80)
    cur = dict(F1_100, canonicalization_f1=0.90)
    r = RegressionRunner().run(_snap(base), _snap(cur))
    assert r.deltas["canonicalization_f1"] == pytest.approx(0.10)
    assert r.regressions == []
    assert r.blocked is False


# --- 허용치 초과 하락 ------------------------------------------------------

def test_exceeded_drop_blocks():
    """F1 하락 0.05 (허용 2%p 초과) → regression, blocked."""
    base = dict(F1_100, canonicalization_f1=0.90)
    cur = dict(F1_100, canonicalization_f1=0.85)
    r = RegressionRunner().run(_snap(base), _snap(cur))
    assert "canonicalization_f1" in r.regressions
    assert r.blocked is True


def test_within_tolerance_no_block():
    """F1 하락 0.01 (허용 2%p 내) → 회귀 없음, blocked=False."""
    base = dict(F1_100, canonicalization_f1=0.90)
    cur = dict(F1_100, canonicalization_f1=0.89)
    r = RegressionRunner().run(_snap(base), _snap(cur))
    assert r.regressions == []
    assert r.blocked is False


def test_precision_zero_tolerance():
    """canonicalization_precision 0p — 미세 하락(0.01)도 회귀 (design 10 §3.2 hard)."""
    base = dict(F1_100, canonicalization_precision=1.0)
    cur = dict(F1_100, canonicalization_precision=0.99)
    r = RegressionRunner().run(_snap(base), _snap(cur))
    assert "canonicalization_precision" in r.regressions
    assert r.blocked is True


# --- 골든 gate 미달과 조합 ---------------------------------------------------

def test_gate_missed_blocks_even_without_regression():
    """지표는 그대로지만 골든 gate 미달 → blocked (design 10 §3.1)."""
    cur = _snap(F1_100)
    # basic gate: 하네스에서 F1=0 < 0.85 이면 gate 미달.
    h = _harness([GoldenPair("clm-a", "clm-b", "equivalent")])  # 캐노니컬 없음 → FN.
    assert h.report()["promotion_blocked"] is True
    # RegressionRunner에 current harness를 직접 주입 → gate 미달 감지.
    r = RegressionRunner().run(cur, h)
    assert r.gate_missed is True
    assert r.blocked is True


# --- read-only -------------------------------------------------------------

def test_read_only_no_mutation():
    """실행기는 read-only — 쓰기·영속·mutation 미노출."""
    rr = RegressionRunner()
    for bad in ("apply", "persist", "create_node", "create_edge", "insert"):
        assert not hasattr(rr, bad), f"read-only 위반: {bad} 노출"


def test_determinism():
    """동일 baseline+current → 동일 delta."""
    base, cur = _snap(F1_100), _snap(dict(F1_100, canonicalization_f1=0.90))
    rr = RegressionRunner()
    assert rr.run(base, cur).deltas == rr.run(base, cur).deltas
