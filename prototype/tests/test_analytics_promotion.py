"""ClickHouse 분석 승격 — 분석 쿼리 지연 게이트 + OLAP 집계 (01 §5, 11 §2.2, Phase 4) TDD.

Phase 4 「ClickHouse 분석 승격」 — 01 §5(분석·관측 계층) 확장 지점을 봉인한다.

- **승격 트리거 (01 §5, 11 §2.2):** 초기 = DuckDB/PostgreSQL, 확장 = ClickHouse + Grafana,
  승격 트리거 = **분석 쿼리 지연**. ClickHouse 미설치 → executor(주입)로 실측 격리,
  결정성은 순수 에뮬레이션 (mock/실측 격리, 분산 batch #14 와 동일).
- `evaluate_analytics_promotion` — 지연이 승격 트리거 임계(ANALYTICS_SLO_MS)를 넘으면
  ClickHouse 승격 필요 (Q4/Q6 게이트와 동일 성격, slo-gate·CI 비차단 nightly).
- 미측정 → not-measured + escalate False — honest-gap (§6.2).
- `aggregate_metrics` — OLAP 집계, correlation_id/version_tuple 로 drill-down (11 §2.2).

결정적·read-only·mock/실측 격리 원칙 (Phase 4 전 작업과 동일).
"""
from __future__ import annotations

import pytest

from orc_citadel.analytics_promotion import (
    ANALYTICS_SLO_MS,
    CURRENT_ANALYTICS_TIER,
    SCALE_ANALYTICS_TIER,
    aggregate_metrics,
    evaluate_analytics_promotion,
    measure_analytics_latency,
    p95_ms,
)


# --- p95_ms (결정적 백분위) -------------------------------------------------


def test_p95_known_distribution():
    """0..99 균등 → p95 인덱스 값 (idx = int(0.95×99)=94 → 값 94.0)."""
    vals = [float(i) for i in range(100)]
    assert p95_ms(vals) == 94.0


def test_p95_small_list():
    """소규모도 인덱스 클램프 — n=1 → 자기 자신 (0.95×0=0)."""
    assert p95_ms([42.0]) == 42.0


def test_p95_empty_is_zero():
    """빈 값 → 0.0 (가드, 분포 부재)."""
    assert p95_ms([]) == 0.0


def test_p95_deterministic():
    """동일 입력 → 동일 p95 (결정성)."""
    vals = [5.0, 1.0, 9.0, 3.0, 7.0]
    assert p95_ms(vals) == p95_ms(vals)


# --- measure_analytics_latency (mock executor) ------------------------------


def test_measure_analytics_deterministic():
    """미주입 mock — 동일 쿼리 목록 → 동일 지연 분포 (결정성)."""
    qs = ["select 1", "select 2", "select 3"]
    assert measure_analytics_latency(qs) == measure_analytics_latency(qs)


def test_measure_analytics_reports_stats():
    """통계 필드 채움 — p95·avg·max·n_queries (01 §5 분석 쿼리 지연)."""
    res = measure_analytics_latency(["a", "b", "c", "d", "e"])
    assert res["n_queries"] == 5
    assert res["p95_ms"] >= 0
    assert res["per_query_ms"] is not None


def test_measure_analytics_executor_injected():
    """executor 주입 → 실측 백엔드 지연 대체 (mock/실측 격리)."""
    def ex(q):
        return {"a": 10.0, "b": 20.0, "c": 30.0, "d": 40.0, "e": 50.0}[q]
    res = measure_analytics_latency(["a", "b", "c", "d", "e"], executor=ex)
    assert res["p95_ms"] == 40.0  # 정렬 10..50, idx = int(0.95×4)=3 → 40
    assert res["max_ms"] == 50.0
    assert res["avg_ms"] == 30.0


def test_measure_analytics_empty():
    """빈 쿼리 목록 → 통계 가드 (분모·max 부재)."""
    res = measure_analytics_latency([])
    assert res["n_queries"] == 0
    assert res["p95_ms"] == 0.0
    assert res["max_ms"] == 0.0


# --- evaluate_analytics_promotion (01 §5 승격 트리거) -----------------------


def test_promotion_no_escalation_below_threshold():
    """분석 쿼리 지연이 SLO 이내 → ClickHouse 승격 필요 없음 (초기 tier 유지)."""
    g = evaluate_analytics_promotion({"p95_ms": 50.0, "n_queries": 3})
    assert g["escalate_clickhouse"] is False
    assert g["classified"] == "ok"
    assert g["current_tier"] == CURRENT_ANALYTICS_TIER


def test_promotion_escalation_at_threshold():
    """분석 쿼리 지연이 승격 트리거 임계 이상 → ClickHouse 승격 (01 §5)."""
    g = evaluate_analytics_promotion({"p95_ms": ANALYTICS_SLO_MS, "n_queries": 3})
    assert g["escalate_clickhouse"] is True
    assert g["classified"] == "slo-gate"  # CI 비차단 nightly 승격 평가.
    assert g["scale_tier"] == SCALE_ANALYTICS_TIER


def test_promotion_slo_gate_not_blocking():
    """승격 트리거는 CI 차단 게이트 아님 — slo-gate 분류 (01 §5, 11 획득 정책)."""
    g = evaluate_analytics_promotion({"p95_ms": ANALYTICS_SLO_MS + 1})
    assert g["classified"] == "slo-gate"


def test_promotion_unmeasured_honest_gap():
    """미측정(None) → escalate False · not-measured — honest-gap (§6.2)."""
    g = evaluate_analytics_promotion(None)
    assert g["escalate_clickhouse"] is False
    assert g["classified"] == "not-measured"


def test_promotion_missing_p95_is_unmeasured():
    """p95 필드 부재 → not-measured (측정 부재가 승격 불필요 라는 근거 아님)."""
    g = evaluate_analytics_promotion({"n_queries": 0})
    assert g["classified"] == "not-measured"
    assert g["escalate_clickhouse"] is False


# --- aggregate_metrics (OLAP drill-down, 11 §2.2) ---------------------------


def test_aggregate_by_correlation_id():
    """correlation_id 별 OLAP 집계 — 숫자 메트릭 합산 (11 §2.2 drill-down)."""
    rows = [
        {"correlation_id": "corr-1", "docs": 10, "queries": 2, "latency_ms": 5},
        {"correlation_id": "corr-1", "docs": 20, "queries": 1, "latency_ms": 7},
        {"correlation_id": "corr-2", "docs": 30, "queries": 3, "latency_ms": 9},
    ]
    out = aggregate_metrics(rows, lambda r: r["correlation_id"])
    assert out["corr-1"]["docs"] == 30
    assert out["corr-1"]["queries"] == 3
    assert out["corr-1"]["latency_ms"] == 12
    assert out["corr-2"]["docs"] == 30


def test_aggregate_does_not_mutate_input():
    """aggregate_metrics 는 입력 rows 를 변경하지 않는다 (순수 함수 — read-only)."""
    rows = [{"correlation_id": "c", "docs": 1}]
    snapshot = [dict(r) for r in rows]
    aggregate_metrics(rows, lambda r: r["correlation_id"])
    assert rows == snapshot


def test_aggregate_empty():
    """빈 입력 → 빈 dict (가드)."""
    assert aggregate_metrics([], lambda r: r.get("correlation_id")) == {}


def test_aggregate_scalar_fields_preserved():
    """비집계 필드는 합산하지 않음 — drill-down 키의 나머지 원소 보존 주의."""
    rows = [{"correlation_id": "c", "docs": 1, "note": "x"}]
    out = aggregate_metrics(rows, lambda r: r["correlation_id"])
    # note 는 AGGREGATE_METRICS 에 없으므로 집계되지 않는다.
    assert "note" not in out["c"]


# --- 불변식 (read-only·결정성) -----------------------------------------------


def test_read_only_no_mutation():
    """analytics_promotion 모듈은 read-only — 쓰기·mutation 미노출 (불변식 §3-3)."""
    from orc_citadel import analytics_promotion as ap

    for bad in ("apply", "persist", "create_node", "create_edge", "insert",
                "write", "upsert"):
        assert not hasattr(ap, bad), f"read-only 위반: {bad} 노출"


def test_promotion_deterministic():
    """동일 입력 → 동일 승격 판정 (결정성 — 재현성)."""
    a = evaluate_analytics_promotion({"p95_ms": 300.0})
    b = evaluate_analytics_promotion({"p95_ms": 300.0})
    assert a == b
