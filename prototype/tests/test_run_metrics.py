"""run 메트릭 postgres flush (specs/ui-overhaul-astryx Step 14a — TS-6, design 11 §2.2).

nightly 런 종료 시 런 요약 메트릭(`pipeline_run_metrics`)과 SLO 원시 관측
(`pipeline_slo_observations`)을 postgres 에 append-only flush 한다 — Grafana
대시보드(D1 수집 성공률·freshness, D2 처리량)의 유일한 데이터 소스.

계약:
- append-only — 수정·삭제 없음, 재-flush 는 행 추가 (11 §2.2 metric 은
  correlation_id·run 축으로 분해(drill-down) 가능).
- flush 실패 비차단 — 관측 계층 장애가 수집 런을 실패시키지 않는다 (§6.2:
  실패는 {"flushed": False, "error"} 로 정직 반환, 예외 전파 금지).
- postgres 부재 시 pg 테스트는 skip (`importorskip` 격리 규약 — 순수 분해
  테스트는 오프라인에서도 돈다). 전용 테이블명 주입으로 운영 테이블과 격리.
"""
from __future__ import annotations

import pytest

from orc_citadel.run_metrics import (
    METRICS_TABLE,
    OBSERVATIONS_TABLE,
    pipeline_run_metrics_ddl,
    pipeline_slo_observations_ddl,
    summary_metrics,
    flush_run,
    flush_after_run,
    safe_flush,
)
from orc_citadel.slo_observation_log import SloObservationLog

# 전용 격리 테이블명 (운영 테이블과 분리 — test_postgres_mutation_log 규약).
T_METRICS = "pipeline_run_metrics_test"
T_OBS = "pipeline_slo_observations_test"


# --- 순수 계층 (postgres 불요 — 오프라인에서도 실행) ---------------------------

def test_summary_metrics_decomposes_sources():
    """수집 런 요약 → metric 행 분해: source 축 labels + 런 총계."""
    summary = {"total_new": 3,
               "sources": {"press-a": {"saved": 2, "skipped": 5, "errors": 0},
                           "gov-b": {"saved": 1, "skipped": 0, "errors": 1}}}
    rows = summary_metrics(summary)
    # 런 총계 1행 + source 별 (saved/skipped/errors) 3행 × 2 source
    assert {"metric": "total_new", "value": 3.0, "labels": {}} in rows
    assert {"metric": "saved", "value": 2.0, "labels": {"source_id": "press-a"}} in rows
    assert {"metric": "errors", "value": 1.0, "labels": {"source_id": "gov-b"}} in rows
    assert len(rows) == 7


def test_summary_metrics_empty_is_honest():
    """빈 요약 → 빈 행 (가공 금지 — 0 행 조작 없음)."""
    assert summary_metrics({}) == []
    assert summary_metrics(None) == []


def test_safe_flush_failure_is_non_blocking():
    """flush 실패 비차단 — 연결 실패가 예외로 전파되지 않고 정직 반환된다."""
    def broken_connect():
        raise RuntimeError("pg down")
    res = safe_flush(job_id="nightly_collect",
                     metrics=[{"metric": "total_new", "value": 1.0, "labels": {}}],
                     connect=broken_connect)
    assert res["flushed"] is False
    assert "pg down" in res["error"]


def test_ddl_uses_if_not_exists_and_injected_table():
    """운영 flush 는 멱등 ensure — DDL 은 IF NOT EXISTS + 테이블명 주입."""
    for ddl, table in ((pipeline_run_metrics_ddl(T_METRICS), T_METRICS),
                       (pipeline_slo_observations_ddl(T_OBS), T_OBS)):
        assert "CREATE TABLE IF NOT EXISTS" in ddl
        assert f'"{table}"' in ddl
    # 기본 테이블명은 설계 11 §2.2 대시보드 소스 명칭.
    assert METRICS_TABLE == "pipeline_run_metrics"
    assert OBSERVATIONS_TABLE == "pipeline_slo_observations"


def test_flush_after_run_hook_is_non_blocking():
    """런 종료 훅 — 요약 분해 + flush 합성, 실패도 비차단 정직 반환."""
    def broken_connect():
        raise RuntimeError("pg down")
    res = flush_after_run("nightly_collect",
                          {"total_new": 1, "sources": {}},
                          connect=broken_connect)
    assert res["flushed"] is False and "pg down" in res["error"]


# --- postgres 계층 (연결 불가 시 skip) -----------------------------------------

@pytest.fixture()
def pg():
    """실 postgres 연결 + 전용 테이블 DROP+CREATE 격리."""
    psycopg = pytest.importorskip("psycopg")
    from orc_citadel.postgres_mutation_log import build_dsn
    try:
        conn = psycopg.connect(build_dsn())
    except Exception as exc:  # 오프라인/미가동 — 전체 skip
        pytest.skip(f"postgres 연결 불가: {exc}")
    conn.autocommit = True
    cur = conn.cursor()
    for t in (T_METRICS, T_OBS):
        cur.execute(f'DROP TABLE IF EXISTS "{t}"')
    cur.execute(pipeline_run_metrics_ddl(T_METRICS))
    cur.execute(pipeline_slo_observations_ddl(T_OBS))
    yield conn
    for t in (T_METRICS, T_OBS):
        cur.execute(f'DROP TABLE IF EXISTS "{t}"')
    conn.close()


def _cols(conn, table: str) -> set[str]:
    cur = conn.cursor()
    cur.execute("SELECT column_name FROM information_schema.columns "
                "WHERE table_name = %s", (table,))
    return {r[0] for r in cur.fetchall()}


def test_metrics_table_column_contract(pg):
    """pipeline_run_metrics — run·metric·labels·correlation·version 분해 축."""
    assert _cols(pg, T_METRICS) >= {
        "metric_id", "run_id", "job_id", "metric", "value", "labels",
        "correlation_id", "version_tuple", "recorded_at"}


def test_observations_table_column_contract(pg):
    """pipeline_slo_observations — SLO 원시 관측 (slo·source·ok·detail)."""
    assert _cols(pg, T_OBS) >= {
        "obs_id", "run_id", "job_id", "slo", "source_id", "kind", "ok",
        "detail", "correlation_id", "recorded_at"}


def _slo_log() -> SloObservationLog:
    clock = iter(range(1000, 5000, 100))
    log = SloObservationLog(now_ms=lambda: float(next(clock)))
    log.record_collect("press-a", "https://a/1", ok=True)
    log.record_collect("press-a", "https://a/2", ok=False)
    log.record_schema("claude_judge", kind="canonical_verdict", valid=True)
    log.record_quarantine_enter("edge-1")
    log.record_quarantine_exit("edge-1")
    return log


def test_flush_run_appends_metrics_and_observations(pg):
    """flush 1회 — metric 행 + SLO-05/06/07 원시 관측이 run_id 로 분해된다."""
    out = flush_run(pg, job_id="nightly_collect",
                    metrics=[{"metric": "total_new", "value": 2.0, "labels": {}},
                             {"metric": "saved", "value": 2.0,
                              "labels": {"source_id": "press-a"}}],
                    slo_log=_slo_log(),
                    metrics_table=T_METRICS, obs_table=T_OBS)
    assert out["metrics"] == 2 and out["observations"] == 4
    cur = pg.cursor()
    cur.execute(f'SELECT DISTINCT run_id FROM "{T_METRICS}"')
    (run_id,) = cur.fetchone()
    assert run_id == out["run_id"]
    # drill-down: run_id + labels source 축 (11 §2.2)
    cur.execute(f"""SELECT value FROM "{T_METRICS}"
                    WHERE run_id = %s AND labels->>'source_id' = 'press-a'""",
                (run_id,))
    assert cur.fetchone()[0] == 2.0
    # SLO 관측 분해 — slo 축 + ok/dwell detail
    cur.execute(f'SELECT slo, COUNT(*) FROM "{T_OBS}" GROUP BY slo ORDER BY slo')
    assert dict(cur.fetchall()) == {"slo05": 2, "slo06": 1, "slo07": 1}
    cur.execute(f"""SELECT detail->>'dwell_ms' FROM "{T_OBS}" WHERE slo='slo07'""")
    assert float(cur.fetchone()[0]) > 0


def test_flush_is_append_only(pg):
    """재-flush 는 행 추가(다른 run_id) — 수정·삭제 없음 (append-only)."""
    m = [{"metric": "total_new", "value": 1.0, "labels": {}}]
    a = flush_run(pg, job_id="j", metrics=m,
                  metrics_table=T_METRICS, obs_table=T_OBS)
    b = flush_run(pg, job_id="j", metrics=m,
                  metrics_table=T_METRICS, obs_table=T_OBS)
    assert a["run_id"] != b["run_id"]
    cur = pg.cursor()
    cur.execute(f'SELECT COUNT(*) FROM "{T_METRICS}"')
    assert cur.fetchone()[0] == 2


def test_safe_flush_success_with_injected_connect(pg):
    """safe_flush 성공 경로 — 주입 connect 로 격리 테이블에 flush·정직 반환."""
    res = safe_flush(job_id="nightly_slo06",
                     metrics=[{"metric": "schema_n", "value": 1.0, "labels": {}}],
                     slo_log=None,
                     connect=lambda: pg,
                     close=False,  # fixture 소유 커넥션 — 닫지 않는다
                     metrics_table=T_METRICS, obs_table=T_OBS)
    assert res["flushed"] is True and res["metrics"] == 1
