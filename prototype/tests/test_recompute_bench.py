"""Full rebuild vs partial recomputation benchmark (설계 10 §1.4·§4.5) TDD.

Phase 4 완료조건 — "증분(partial recomputation)이 full rebuild 대비 유의미 절감".
`measure_rebuild`(06 §9 3항 재구축/증분 비율, Q4 게이트 REBUILD_RATIO_GATE=10×)를
랜핑한 순수 함수 벤치 보고서로 계량 (read-only·결정적).

- full_vs_incremental(base·delta·edges_per_node): {full_ms, incremental_ms, ratio}
  — ratio = full/incremental (증분 대비 full 비용 배수).
- evaluate_recompute_bench(bench): 완료조건 게이트 — 증분이 full 대비 유의미 절감
  (ratio > REBUILD_RATIO_GATE=10×, 06 §9 3항) + slo-gate 분류(CI 비차단, 10 §1.4).
- read-only — 벤치 계산은 store·아이오 없이 결정적 (mock store 대조만).
- 10 §1.4 slo-gate 원칙 — 성능은 nightly 경보·부하 단계 재측정, CI 차단 아님.
"""
from __future__ import annotations

import pytest

from orc_citadel.recompute_bench import (
    full_vs_incremental,
    evaluate_recompute_bench,
    REBUILD_RATIO_GATE,
)


class _FakeStore:
    """측정 훅(un)을 결정적 벽시계로 주는 mock store — ratio 계약 대조."""

    def __init__(self, full_ms, incr_ms):
        self._full = full_ms
        self._incr = incr_ms

    def full_rebuild_ms(self, base, delta, eper):
        return self._full

    def incremental_rebuild_ms(self, base, delta, eper):
        return self._incr


def test_full_vs_incremental_ratio():
    """wall-clock 대리값으로 ratio = full/incremental 계산."""
    bench = full_vs_incremental(
        _FakeStore(full_ms=1000.0, incr_ms=100.0),
        base_nodes=100, delta_nodes=10)
    assert bench["full_ms"] == pytest.approx(1000.0)
    assert bench["incremental_ms"] == pytest.approx(100.0)
    assert bench["ratio"] == pytest.approx(10.0)


def test_bench_meaningful_saving_gate():
    """증분이 full 대비 유의미 절감 — ratio > 10× (완료조건, 06 §9 3항)."""
    bench = full_vs_incremental(
        _FakeStore(full_ms=5000.0, incr_ms=100.0),
        base_nodes=100, delta_nodes=10)
    ev = evaluate_recompute_bench(bench)
    assert ev["ratio"] == pytest.approx(50.0)
    assert ev["saving_meaningful"] is True
    assert ev["gate"]["threshold"] == REBUILD_RATIO_GATE


def test_bench_no_saving_fails_gate():
    """증분이 full 대비 절감 부족(ratio ≤ 10×) → 게이트 미충족."""
    bench = full_vs_incremental(
        _FakeStore(full_ms=100.0, incr_ms=100.0),
        base_nodes=100, delta_nodes=10)
    ev = evaluate_recompute_bench(bench)
    assert ev["saving_meaningful"] is False
    # 완료조건 미충족 — fail 노출 (nightly, slo-gate).
    assert ev["gate"]["pass"] is False


def test_bench_slo_gate_non_blocking():
    """slo-gate 분류 — 게이트 fail이 CI 승격 차단이 아닌 nightly 경보로 라우팅 (10 §1.4)."""
    bench = full_vs_incremental(
        _FakeStore(full_ms=100.0, incr_ms=100.0),
        base_nodes=100, delta_nodes=10)
    ev = evaluate_recompute_bench(bench)
    assert ev["slo_gate"] is True   # CI 차단 아님.


def test_bench_zero_incremental_inf_ratio():
    """증분 0ms → ratio inf (절감 최대)."""
    bench = full_vs_incremental(
        _FakeStore(full_ms=100.0, incr_ms=0.0),
        base_nodes=100, delta_nodes=10)
    assert bench["ratio"] == float("inf")


def test_read_only_no_mutation():
    """벤치 계산은 read-only — 쓰기·mutation 미노출."""
    bench = full_vs_incremental(
        _FakeStore(full_ms=100.0, incr_ms=10.0),
        base_nodes=100, delta_nodes=10)
    for bad in ("apply", "persist", "create_node", "create_edge"):
        assert not hasattr(bench, bad), f"read-only 위반: {bad} 노출"


def test_determinism():
    """동일 mock → 동일 벤치."""
    a = full_vs_incremental(_FakeStore(100.0, 10.0), 100, 10)
    b = full_vs_incremental(_FakeStore(100.0, 10.0), 100, 10)
    assert a == b
