"""S36 평가 스위트 러너 (설계 10 §6 CI 게이트) TDD.

S33(하네스)→S34(골든 영속)→S35(회귀)를 하나의 결정적 러너로 묶는다. 골든 자동 로드 →
P/R/F1 평가 → baseline 대비 회귀 → 통과/차단 최종 판정 + 인간 읽기 리포트.

- baseline 미주입: 게이트·지표만 (첫 실행).
- baseline 주입: 회귀·gate 종합 판정 (design 10 §6.2 promotion-block).
- passed: 게이트 전부 통과 && 회귀 없음.
- **read-only** (불변식 §3-3) — zone 읽기만, 영속·mutation 미노출.

Atomic TDD: Red → Green → Refactor.
"""
from __future__ import annotations

import pytest

from orc_citadel.eval_suite import EvalSuite
from orc_citadel.curated_zone import CuratedZone
from orc_citadel.regression import EvalSnapshot


def _zone(goldens=(), canonical_claims=(), member_of=()) -> CuratedZone:
    z = CuratedZone(":memory:")
    z.initialize()
    for g in goldens:
        z.persist_golden_pair(g["a"], g["b"], g["label"], split=g.get("split", "dev"),
                              gold_version="g1", labeled_by="human:test",
                              labeled_at="2026-08-01T00:00:00Z", rationale="x")
    for c in canonical_claims:
        z.persist_canonical(_cc(c["cid"], c["members"]))
    for m in member_of:
        z.set_claim_canonical(m["claim"], m["cc"])
    return z


def _cc(cid, members):
    from orc_citadel.canonicalize import CanonicalClaim
    return CanonicalClaim(canonical_claim_id=cid, subject_id="org-a",
                          predicate="announces", object_id="org-b",
                          canonical_text="x", member_claim_ids=members)


# --- run: 기본 --------------------------------------------------------------

def test_run_metrics_and_gates():
    """골든 자동 로드 → P/R/F1·gate 계산 (S33·S34 재사용)."""
    z = _zone(
        goldens=[{"a": "clm-a", "b": "clm-b", "label": "equivalent"}],
        canonical_claims=[{"cid": "ccl-1", "members": ["clm-a", "clm-b"]}],
        member_of=[{"claim": "clm-a", "cc": "ccl-1"}, {"claim": "clm-b", "cc": "ccl-1"}])
    res = EvalSuite(zone=z).run()
    assert res.metrics["canonicalization_f1"] == 1.0
    assert "canonicalization" in res.gates
    assert res.gates["canonicalization"]["pass"] is True


def test_run_baseline_none_passed_by_gates():
    """baseline 미주입 — 게이트 통과면 passed=True (첫 실행)."""
    z = _zone(
        goldens=[{"a": "clm-a", "b": "clm-b", "label": "equivalent"}],
        canonical_claims=[{"cid": "ccl-1", "members": ["clm-a", "clm-b"]}],
        member_of=[{"claim": "clm-a", "cc": "ccl-1"}, {"claim": "clm-b", "cc": "ccl-1"}])
    res = EvalSuite(zone=z).run()
    assert res.passed is True
    assert res.regressions == []


def test_run_gate_missed_fails():
    """골든 gate 미달 → passed=False (promotion_blocked)."""
    z = _zone(goldens=[{"a": "clm-a", "b": "clm-b", "label": "equivalent"}])
    res = EvalSuite(zone=z).run()
    assert res.gates["canonicalization"]["pass"] is False
    assert res.passed is False


# --- run: baseline 주입 -----------------------------------------------------

def test_run_baseline_identical_passed():
    """baseline 주입 동일(현재 지표와 일치) — 회귀 없음, passed=True."""
    z = _zone(
        goldens=[{"a": "clm-a", "b": "clm-b", "label": "equivalent"}],
        canonical_claims=[{"cid": "ccl-1", "members": ["clm-a", "clm-b"]}],
        member_of=[{"claim": "clm-a", "cc": "ccl-1"}, {"claim": "clm-b", "cc": "ccl-1"}])
    # 현재 지표: 캐노니컬 F1/P=1.0, 모순 골든 없음(vacuous) → 모순 P/R 0.0.
    m = {"canonicalization_f1": 1.0, "canonicalization_precision": 1.0,
         "contradiction_precision": 0.0, "contradiction_recall": 0.0}
    baseline = EvalSnapshot("g1", m)
    res = EvalSuite(zone=z, baseline=baseline).run()
    assert res.regressions == []
    assert res.passed is True


def test_run_baseline_regression_fails():
    """baseline 대비 회귀 → regressions 포함, passed=False."""
    z = _zone(
        goldens=[{"a": "clm-a", "b": "clm-b", "label": "equivalent"}],
        canonical_claims=[{"cid": "ccl-1", "members": ["clm-a", "clm-b"]}],
        member_of=[{"claim": "clm-a", "cc": "ccl-1"}, {"claim": "clm-b", "cc": "ccl-1"}])
    # baseline F1 0.95, 현재 1.0 — 상승이라 회귀 없음. 하락으로 바꾸기 위해 baseline을 높게.
    m = {"canonicalization_f1": 1.0, "canonicalization_precision": 1.0,
         "contradiction_precision": 0.97, "contradiction_recall": 0.97}
    baseline = EvalSnapshot("g1", m)  # 현재 모순 P/R 0.0 → 하락 회귀.
    res = EvalSuite(zone=z, baseline=baseline).run()
    assert "contradiction_precision" in res.regressions
    assert res.passed is False


# --- report / print ---------------------------------------------------------

def test_report_human_readable():
    """report — 한국어 요약 라인 (게이트·지표·회귀 포함)."""
    z = _zone(goldens=[{"a": "clm-a", "b": "clm-b", "label": "equivalent"}])
    res = EvalSuite(zone=z).run()
    assert "게이트" in res.report or "canonicalization" in res.report
    assert "PASS" in res.report or "FAIL" in res.report


def test_print_report_caps():
    """print_report — PASS/FAIL 축약 라인 (CI-friendly)."""
    z = _zone(goldens=[{"a": "clm-a", "b": "clm-b", "label": "equivalent"}])
    suite = EvalSuite(zone=z)
    out = suite.print_report()
    assert isinstance(out, str)
    assert out.strip()  # 비어있지 않음.
    assert ("PASS" in out) or ("FAIL" in out)


# --- read-only --------------------------------------------------------------

def test_read_only_no_mutation():
    """스위트는 read-only — 쓰기·영속·mutation 미노출."""
    z = _zone(goldens=[{"a": "clm-a", "b": "clm-b", "label": "equivalent"}])
    s = EvalSuite(zone=z)
    for bad in ("apply", "persist", "create_node", "create_edge", "insert"):
        assert not hasattr(s, bad), f"read-only 위반: {bad} 노출"


def test_determinism():
    """동일 zone·baseline → 동일 결과."""
    z = _zone(goldens=[{"a": "clm-a", "b": "clm-b", "label": "equivalent"}])
    m = {"canonicalization_f1": 0.9, "canonicalization_precision": 1.0,
         "contradiction_precision": 1.0, "contradiction_recall": 1.0}
    from orc_citadel.regression import EvalSnapshot as ES
    b = ES("g1", m)
    a = EvalSuite(zone=z, baseline=b).run()
    c = EvalSuite(zone=z, baseline=b).run()
    assert a.metrics == c.metrics and a.passed == c.passed
