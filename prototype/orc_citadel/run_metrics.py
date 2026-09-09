"""run 메트릭 postgres flush — nightly 런 종료 훅의 관측 영속 계층 (design 11 §2.2).

`slo_log`(SloObservationLog)는 in-memory 라 런이 끝나면 관측이 증발한다 — 11 §2.3
실측 메모의 "런 간 누적 구조적 불가" 그 지점이다. 여기서 런 요약 메트릭
(`pipeline_run_metrics`)과 SLO 원시 관측(`pipeline_slo_observations`)을 postgres 에
**append-only** 로 내려, Grafana 대시보드(D1 수집 성공률·freshness, D2 처리량)와
7d rolling 재확정의 데이터 소스를 만든다.

계약:
- append-only — 수정·삭제 없음. 행은 `run_id`(런당 ulid)·labels·correlation_id
  축으로 분해(drill-down) 가능해야 한다 (11 §2.2).
- **비차단** — `safe_flush` 는 어떤 실패도 예외로 전파하지 않고
  `{"flushed": False, "error"}` 로 정직 반환한다. 관측 계층 장애가 수집 런을
  실패시키면 안 된다 (§6.2 — 관측 부재는 기록하되 본작업은 계속).
- psycopg 는 `safe_flush` 기본 연결 경로에서만 지연 import — 순수 분해 함수는
  드라이버 없는 환경에서도 동작한다 (importorskip 격리 규약과 짝).
"""
from __future__ import annotations

import json

from .identity import new_ulid

# 설계 11 §2.2 대시보드 소스 명칭 — Grafana provisioning 이 이 이름을 조회한다.
METRICS_TABLE = "pipeline_run_metrics"
OBSERVATIONS_TABLE = "pipeline_slo_observations"


def pipeline_run_metrics_ddl(table: str = METRICS_TABLE) -> str:
    """런 요약 메트릭 스키마 — 멱등 ensure(IF NOT EXISTS)·테이블명 주입 격리."""
    return (
        f'CREATE TABLE IF NOT EXISTS "{table}" ('
        "  metric_id       varchar PRIMARY KEY,"
        "  run_id          varchar NOT NULL,"
        "  job_id          varchar NOT NULL,"
        "  metric          varchar NOT NULL,"
        "  value           double precision,"
        "  labels          jsonb NOT NULL,"
        "  correlation_id  varchar,"
        "  version_tuple   jsonb NOT NULL,"
        "  recorded_at     timestamptz NOT NULL DEFAULT now()"
        ")"
    )


def pipeline_slo_observations_ddl(table: str = OBSERVATIONS_TABLE) -> str:
    """SLO 원시 관측 스키마 — SLO-05/06/07 이벤트를 런 축으로 영속."""
    return (
        f'CREATE TABLE IF NOT EXISTS "{table}" ('
        "  obs_id          varchar PRIMARY KEY,"
        "  run_id          varchar NOT NULL,"
        "  job_id          varchar NOT NULL,"
        "  slo             varchar NOT NULL,"
        "  source_id       varchar,"
        "  kind            varchar,"
        "  ok              boolean,"
        "  detail          jsonb NOT NULL,"
        "  correlation_id  varchar,"
        "  recorded_at     timestamptz NOT NULL DEFAULT now()"
        ")"
    )


def ensure_tables(conn, metrics_table: str = METRICS_TABLE,
                  obs_table: str = OBSERVATIONS_TABLE) -> None:
    """테이블 2종 멱등 생성 — 운영 flush 선행 단계."""
    cur = conn.cursor()
    cur.execute(pipeline_run_metrics_ddl(metrics_table))
    cur.execute(pipeline_slo_observations_ddl(obs_table))


def summary_metrics(summary: dict | None) -> list[dict]:
    """런 요약 → metric 행 분해 (런 총계 스칼라 + source 축 labels).

    입력: {"total_new": N, ..., "sources": {source_id: {saved, skipped, errors}}}.
    "sources" 외 최상위 수치 키는 그대로 런 총계 행이 된다 (job 별 요약 셰이프
    확장 — nightly_slo06 의 schema_n 등). 빈/None 은 빈 목록 (행 조작 없음).
    """
    if not summary:
        return []
    rows: list[dict] = []
    for key, val in summary.items():
        if key != "sources" and isinstance(val, (int, float)):
            rows.append({"metric": key, "value": float(val), "labels": {}})
    for source_id, counts in (summary.get("sources") or {}).items():
        for metric in ("saved", "skipped", "errors"):
            if metric in counts:
                rows.append({"metric": metric, "value": float(counts[metric]),
                             "labels": {"source_id": source_id}})
    return rows


def _slo_observations(slo_log) -> list[dict]:
    """SloObservationLog → 원시 관측 행 (SLO-05 수집·SLO-06 schema·SLO-07 체류)."""
    rows: list[dict] = []
    for c in slo_log.collect_log():
        rows.append({"slo": "slo05", "source_id": c["source_id"], "kind": "collect",
                     "ok": c["ok"], "detail": {"url": c["url"]}})
    for sc in slo_log.schema_log():
        rows.append({"slo": "slo06", "source_id": sc["source_id"], "kind": sc["kind"],
                     "ok": sc["valid"], "detail": {}})
    for enter, exit_ in slo_log.dwell_entries():
        rows.append({"slo": "slo07", "source_id": None, "kind": "quarantine_dwell",
                     "ok": True, "detail": {"enter_ms": enter, "exit_ms": exit_,
                                            "dwell_ms": exit_ - enter}})
    return rows


def flush_run(conn, *, job_id: str, metrics: list[dict], slo_log=None,
              correlation_id: str | None = None, version_tuple: dict | None = None,
              metrics_table: str = METRICS_TABLE,
              obs_table: str = OBSERVATIONS_TABLE) -> dict:
    """런 1회분 append-only flush — {"run_id", "metrics": n, "observations": m}.

    run_id 는 런당 신규 ulid — 재-flush 는 새 run_id 행 추가(수정·삭제 없음).
    """
    run_id = new_ulid("run")
    vt = json.dumps(version_tuple or {})
    cur = conn.cursor()
    for m in metrics:
        cur.execute(
            f'INSERT INTO "{metrics_table}" (metric_id, run_id, job_id, metric, '
            "value, labels, correlation_id, version_tuple) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (new_ulid("met"), run_id, job_id, m["metric"], m.get("value"),
             json.dumps(m.get("labels") or {}), correlation_id, vt))
    observations = _slo_observations(slo_log) if slo_log is not None else []
    for o in observations:
        cur.execute(
            f'INSERT INTO "{obs_table}" (obs_id, run_id, job_id, slo, source_id, '
            "kind, ok, detail, correlation_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (new_ulid("obs"), run_id, job_id, o["slo"], o["source_id"], o["kind"],
             o["ok"], json.dumps(o["detail"]), correlation_id))
    return {"run_id": run_id, "metrics": len(metrics),
            "observations": len(observations)}


def flush_after_run(job_id: str, summary: dict | None, slo_log=None, **kw) -> dict:
    """런 종료 훅 — 요약 분해 + 비차단 flush 합성 (scheduler_runner 전용 진입점)."""
    return safe_flush(job_id=job_id, metrics=summary_metrics(summary),
                      slo_log=slo_log, **kw)


def safe_flush(*, job_id: str, metrics: list[dict], slo_log=None,
               correlation_id: str | None = None, version_tuple: dict | None = None,
               connect=None, close: bool = True,
               metrics_table: str = METRICS_TABLE,
               obs_table: str = OBSERVATIONS_TABLE) -> dict:
    """비차단 flush — 어떤 실패도 예외로 전파하지 않는다 (런 종료 훅 전용).

    `connect` 주입(테스트·대체 드라이버)이 없으면 psycopg 를 지연 import 해
    `.env` DSN 으로 연결한다. `close=False` 는 호출자 소유 커넥션 유지.
    성공: {"flushed": True, "run_id", "metrics", "observations"}.
    실패: {"flushed": False, "error"} — 본작업(수집 런)은 계속된다.
    """
    conn = None
    try:
        if connect is not None:
            conn = connect()
        else:
            import psycopg
            from .postgres_mutation_log import build_dsn
            conn = psycopg.connect(build_dsn())
            conn.autocommit = True
        ensure_tables(conn, metrics_table, obs_table)
        out = flush_run(conn, job_id=job_id, metrics=metrics, slo_log=slo_log,
                        correlation_id=correlation_id, version_tuple=version_tuple,
                        metrics_table=metrics_table, obs_table=obs_table)
        if getattr(conn, "autocommit", True) is False:
            conn.commit()
        return {"flushed": True, **out}
    except Exception as exc:
        return {"flushed": False, "error": str(exc)}
    finally:
        if conn is not None and close and connect is None:
            try:
                conn.close()
            except Exception:
                pass
