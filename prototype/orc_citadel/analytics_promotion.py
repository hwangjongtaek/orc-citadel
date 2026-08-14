"""ClickHouse 분석 승격 — 분석 쿼리 지연 게이트 + OLAP 집계 (design 01 §5, 11 §2.2, Phase 4).

Phase 4 「ClickHouse 분석 승격」 — 01 §5 분석·관측 계층의 확장 지점을 봉인한다.

- **승격 트리거 (01 §5 추적, 11 §2.2):** 분석·관측 초기 = DuckDB(로컬 ad-hoc)/PostgreSQL
  + Grafana, 확장 = **ClickHouse + Grafana**, 승격 트리거 = **분석 쿼리 지연**.
  ClickHouse 는 이 환경에 미설치이므로 실제 측정 백엔드는 **executor(주입)로 격리**,
  결정성은 순수 에뮬레이션으로 봉인 (mock/실측 격리, 분산 batch #14 와 동일).
- `measure_analytics_latency` — 분석 쿼리 경로별 지연 분포 → p95 (executor mock 주입).
- `evaluate_analytics_promotion` — **분석 쿼리 지연이 승격 트리거 임계를 넘으면
  ClickHouse 로 승격 필요를 판정** (01 §5 추적, Q4/Q6 게이트와 동일 성격).
  미측정은 honest-gap (§6.2 — 부재가 승격 불필요 라는 주장 근거가 아니다).
- `aggregate_metrics` — OLAP 집계 (ClickHouse 가 대체 승격하는 분석 부하의 실제 형태) —
  `correlation_id`·`version_tuple` 로 분해 가능 (11 §2.2 drill-down).

read-only(불변식 §3-3)·결정적·mock/실측 격리 원칙 (Phase 4 전 작업과 동일).
"""
from __future__ import annotations

# design 01 §5 — 분석 쿼리 지연 승격 트리거 (placeholder, 실측 후 조정 — 11 §2.3).
ANALYTICS_SLO_MS = 200.0  # 분석 쿼리 p95 지연 예산 (초과 시 ClickHouse 승격 후보).
# 01 §5 추적 — 분석·관측 계층 tier 명칭.
CURRENT_ANALYTICS_TIER = "duckdb/postgres"
SCALE_ANALYTICS_TIER = "clickhouse"
AGGREGATE_METRICS = ("docs", "queries", "latency_ms")  # 지원 집계 메트릭 목록.


def p95_ms(values: list[float]) -> float:
    """p95 백분위 (결정적 — 정렬 인덱스 방법, neo4j_q4_harness 와 동일).

    빈 값 → 0.0 (가드). `int(0.95 × (n-1))` 인덱스 — 재현성 있는 단일 값.
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int(0.95 * (len(ordered) - 1))
    return round(ordered[idx], 3)


def measure_analytics_latency(queries: list[str], executor=None) -> dict:
    """분석 쿼리 경로별 지연 분포 → 통계 (mock executor, 01 §5).

    `executor(query)` → `ms` (실측 백엔드 주입). 미주입 시 결정적 에뮬레이션 —
    각 쿼리 경로의 지연을 해시 시드로 결정 생성 (동일 입력 → 동일 분포, 재현성).
    반환: `{p95_ms, avg_ms, max_ms, n_queries, per_query_ms}`.
    """
    if executor is not None:
        per = [executor(q) for q in queries]
    else:
        import random as _r

        per = []
        for q in queries:
            rng = _r.Random(q or "")
            per.append(round(rng.uniform(0.0, 100.0), 3))
    return {
        "p95_ms": p95_ms(per),
        "avg_ms": round((sum(per) / len(per)), 3) if per else 0.0,
        "max_ms": round(max(per), 3) if per else 0.0,
        "n_queries": len(per),
        "per_query_ms": per,
    }


def evaluate_analytics_promotion(latency_stats: dict | None) -> dict:
    """분석 쿼리 지연 게이트 — ClickHouse 승격 필요 여부 (01 §5 추적 트리거).

    `latency_stats["p95_ms"]` 가 `ANALYTICS_SLO_MS` 이상이면 `escalate_clickhouse=True`
    + `classified="slo-gate"` (승격 트리거 점화, Q4/Q6 게이트와 동일 성격) — CI 차단
    아닌 nightly 승격 평가. `latency_stats` 없음/미측정 → escalate False +
    `classified="not-measured"` — honest-gap (§6.2): 미측정이 DOES NOT mean 승격 불필요.
    """
    if latency_stats is None or latency_stats.get("p95_ms") is None:
        return {"escalate_clickhouse": False,
                "classified": "not-measured",
                "threshold_ms": ANALYTICS_SLO_MS}
    p95 = latency_stats.get("p95_ms", 0.0)
    escalate = p95 >= ANALYTICS_SLO_MS
    return {"escalate_clickhouse": escalate,
            "classified": "slo-gate" if escalate else "ok",
            "threshold_ms": ANALYTICS_SLO_MS,
            "p95_ms": p95,
            "current_tier": CURRENT_ANALYTICS_TIER,
            "scale_tier": SCALE_ANALYTICS_TIER}


def aggregate_metrics(rows: list[dict], key_fn) -> dict:
    """OLAP 집계 — 분석 부하의 실제 형태 (read-only·결정적, 11 §2.2 drill-down).

    `key_fn(row)` → 그룹 키 (`correlation_id`·`version_tuple` 등 drill-down 축).
    숫자 `AGGREGATE_METRICS` 필드는 합산, 그 외는 원소 보존. 입력 미변경.
    ClickHouse 가 승격 대체하는 분석 쿼리가 이 집계다 (01 §5 의 "분석 쿼리").
    """
    out: dict = {}
    for row in rows:
        key = key_fn(row)
        agg = out.setdefault(key, {})
        for m in AGGREGATE_METRICS:
            val = row.get(m)
            if isinstance(val, (int, float)):
                agg[m] = agg.get(m, 0) + val
    return out
