"""Nightly 스케줄러 상주 드라이버 (celery beat 대체 — 단일 호스트, A26 후속).

`orc_citadel.scheduler.build_scheduler_jobs()` 의 job 정의(순수 dict)를
APScheduler `BackgroundScheduler` 에 등록하고 **상주 실행**한다. cron 대신
파이썬 프로세스가 자기 주기(07:07 수집·07:37 SLO-06)로 dispatch — cron 외부
의존·샌드박스 hang 우회. 상주성은 launchd 가 유지.

- **단일 발화 주체**: 활성 스케줄러는 정확히 1개 (단일 호스트). 태스크 함수와
  job 정의는 분리 — 태스크는 기존 `scripts/nightly_*.main()` 이 소유 (단일 책임).
- 영속 job store(sqlite): 프로세스 재시작·재부팅 후에도 스케줄 유지.
- read-only(불변식 §3-3): dispatch 만, 실제 작업은 nightly 태스크(순수·결정적).
- 실행:  .venv/bin/python scripts/scheduler_runner.py
  launchd: scripts/com.orc-citadel.nightly.plist (표시 plist 로드)
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

_REPO = Path(__file__).resolve().parent.parent  # prototype/
sys.path.insert(0, str(_REPO))

from orc_citadel.scheduler import build_scheduler_jobs, COLLECT_JOB_ID, SLO06_JOB_ID

JOB_STORE_PATH = _REPO / "data" / "scheduler-jobs.sqlite"


def _flush_metrics(job_id: str, summary: dict | None, slo_log) -> None:
    """런 종료 훅 — run 메트릭 postgres flush (specs/ui-overhaul-astryx 14a).

    **비차단**: safe_flush 는 예외를 전파하지 않는다 — postgres 미가동이어도
    수집 런은 성공으로 끝나고, 여기서는 flush 결과만 정직하게 로그한다.
    """
    from orc_citadel.run_metrics import flush_after_run
    res = flush_after_run(job_id, summary, slo_log)
    if res.get("flushed"):
        print(f"[metrics] flushed run={res['run_id']} metrics={res['metrics']} "
              f"observations={res['observations']}", flush=True)
    else:
        print(f"[metrics] flush 실패(비차단 — 런은 정상): {res.get('error')}",
              flush=True)


def _snapshot_parquet() -> None:
    """런 종료 훅 — DuckDB 존 parquet 스냅샷 (specs/ui-overhaul-astryx 16a).

    **비차단**: safe_snapshot 은 예외를 전파하지 않는다 — 존 잠금·부재여도
    런은 성공하고, 실패한 존은 직전 스냅샷이 유지된다.
    """
    from orc_citadel.parquet_snapshot import safe_snapshot
    res = safe_snapshot()
    if res.get("exported"):
        zones = {z: v.get("tables", v.get("error")) for z, v in res["zones"].items()}
        print(f"[parquet] snapshot {zones}", flush=True)
    else:
        print(f"[parquet] export 실패(비차단 — 런은 정상): "
              f"{res.get('error') or res.get('zones')}", flush=True)


def _rebuild_zones() -> int:
    """전량 재빌드 — 파서·추출 버전이 바뀌어 과거 산출을 다시 만들어야 할 때만.

    nightly 는 `_promote_new_docs`(증분)를 쓴다. 테스트가 갈아끼울 수 있게 얇게 감싼다.
    """
    from scripts.rebuild_zones import rebuild
    return rebuild()


def _promote_new_docs() -> dict:
    """증분 승격 진입점 — 존에 없는 문서만 올린다 (테스트 seam)."""
    from orc_citadel.incremental_promote import promote_incremental
    return promote_incremental(DATA / "raw", DATA)


def _promote_zones(summary: dict | None) -> None:
    """런 종료 훅 — raw → normalized·curated 승격 (수집 직후, 스냅샷 직전).

    수집만 하고 승격하지 않으면 화면은 어제 지식에 멈춘다 (2026-09-18 prod 실측:
    raw 127건을 받고도 curated 0 — 사람이 손으로 `rebuild_zones` 를 돌려야 했다).

    **증분이다** — 존에 아직 없는 문서만 올린다. 전량 재빌드는 dedup 서명 재계산만
    1,000만 건에서 36시간(12.4ms/doc 실측)이라 nightly 주기에 들어가지 않는다.
    전량 경로(`_rebuild_zones`)는 파서·추출 버전 변경 시의 별도 작업으로 남는다.

    **신규 0건이면 건너뛴다.** 신규 판별 자체도 DuckDB anti-join 한 번이다.

    **비차단**: _flush_metrics·_snapshot_parquet 과 같은 정책이다 — 승격이 실패해도
    수집 결과(raw)는 이미 영속했고 다음 런이 다시 시도한다. 대신 실패를 조용히
    넘기지 않고 로그로 남긴다.
    """
    total_new = int((summary or {}).get("total_new") or 0)
    if total_new <= 0:
        print("[promote] 신규 문서 0건 — 승격 생략 (존은 직전 상태 유지)", flush=True)
        return
    t0 = time.perf_counter()
    try:
        summary = _promote_new_docs()
    except Exception as exc:  # noqa: BLE001 - 비차단 훅
        print(f"[promote] 승격 실패(비차단 — 수집은 정상): {exc!r}", flush=True)
        return
    elapsed = time.perf_counter() - t0
    print(f"[promote] 증분 승격 완료 {elapsed:.1f}s — 신규 {summary['new_docs']}건 · "
          f"mentions {summary['mentions']} · claims {summary['claims']}"
          f"(승격 {summary['promoted_claims']}) · 복제 클러스터 {summary['clusters']}",
          flush=True)


def run_collect() -> None:
    """nightly 수집 태스크 — 수집 → 승격 → 스냅샷 (RSS/sitemap 신규만)."""
    from orc_citadel.slo_observation_log import SloObservationLog
    from scripts.nightly_collect import main as nightly_collect
    slo_log = SloObservationLog()
    summary = nightly_collect(slo_log=slo_log)
    _flush_metrics("nightly_collect", summary, slo_log)
    # 승격이 스냅샷보다 **먼저** 와야 parquet 이 승격된 존을 담는다.
    _promote_zones(summary)
    _snapshot_parquet()


def run_slo06() -> None:
    """nightly SLO-06 태스크 — 무비용 LLM 판정 → 7d 누적 append."""
    from orc_citadel.slo_observation_log import SloObservationLog
    from scripts.nightly_slo06 import main as nightly_slo06
    slo_log = SloObservationLog()
    summary = nightly_slo06(slo_log=slo_log)
    _flush_metrics("nightly_slo06", summary, slo_log)


_TASKS = {"run_collect": run_collect, "run_slo06": run_slo06}


def _misfire_grace(job: dict) -> int:
    """job 정의의 슬립 보충 정책(misfire_grace_seconds) 반환 (기본 하루).

    상시 로컬에서 맥이 슬립으로 아침 스케줄을 놓치면, APScheduler 가 grace 내부면
    당일 job 을 보충 실행한다. 명시값 우선, 부재 시 기본 하루(86400) — misfire
    로 인한 작업 누락 방지 (§6.2). 순수(결정적) — dispatch 정책은 정의에서 분리 유지.
    """
    from orc_citadel.scheduler import GRACE_KEY, MISFIRE_GRACE_SECONDS
    return int(job.get(GRACE_KEY, MISFIRE_GRACE_SECONDS))


def build_scheduler(store_path: Path = JOB_STORE_PATH) -> BackgroundScheduler:
    """영속 sqlite store 를 붙인 BackgroundScheduler (job 은 register_jobs 몫)."""
    store_path.parent.mkdir(parents=True, exist_ok=True)
    sched = BackgroundScheduler()
    sched.add_jobstore("sqlalchemy", url=f"sqlite:///{store_path}")
    return sched


def register_jobs(sched: BackgroundScheduler) -> None:
    """job 정의를 영속 store 와 대사(reconcile) — 기존 job 의 next_run_time 보존.

    이전 구현의 `add_job(replace_existing=True)` 는 재시작마다 job 을 재생성해
    store 의 미발화 시각을 리셋했다 — **재시작을 가로지르는 grace 보충 불가**
    (2026-09-05 실측: 데몬 다운 중 놓친 당일 발화가 재기동 후 next_run=익일로
    스킵). 기존 job 은 보존하고 정의 변경(trigger/grace)만 반영한다. store 조회가
    유효하려면 `start(paused=True)` 후 호출해야 한다.
    """
    for job in build_scheduler_jobs():
        trigger = CronTrigger(**job["schedule"])
        grace = _misfire_grace(job)
        existing = sched.get_job(job["id"])
        if existing is None:
            sched.add_job(_TASKS[job["func"]], trigger=trigger, id=job["id"],
                          misfire_grace_time=grace)
            continue
        if str(existing.trigger) != str(trigger):
            # 스케줄 정의가 바뀐 경우만 next_run 재계산 (의도된 변경).
            sched.reschedule_job(job["id"], trigger=trigger)
        if existing.misfire_grace_time != grace:
            sched.modify_job(job["id"], misfire_grace_time=grace)


def main() -> None:
    sched = build_scheduler()
    # paused 기동 → store 대사 → resume: 놓친 발화가 보존된 채 misfire 판정에
    # 들어가 grace(하루) 내부면 당일 보충 실행된다.
    sched.start(paused=True)
    register_jobs(sched)
    sched.resume()
    jobs = sched.get_jobs()
    print("== nightly 스케줄러 시작 (단일 발화 주체) ==", flush=True)
    for j in jobs:
        print(f"  [{j.id}] next_run_at={j.next_run_time} "
              f"trigger={j.trigger}", flush=True)
    print("상주 중 (launchd 가 유지). 외부 중단은 TaskStop/kill.", flush=True)
    try:
        import time
        while True:
            time.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        sched.shutdown()


if __name__ == "__main__":
    main()
