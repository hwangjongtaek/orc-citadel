"""Nightly 스케줄러 job 정의 (celery beat 대체, 단일 호스트 — A26 후속).

실제 예약 실행(상주 루프)은 드라이버(scripts/scheduler_runner.py)·launchd 몫.
여기선 **job 정의를 순수 함수 `build_scheduler_jobs()`** 로 분리해 오프라인
검증한다:
- schedule 시각(07:07 수집·07:37 SLO-06) 정확성
- 각 schedule 이 올바른 태스크 함수에 바인딩
- **단일 발화 주체**: 스케줄러는 유일한 디스패처(복제 시 복수 pod 중복 방지 원칙 —
  단일 호스트, 활성 스케줄러 1개) — 발화 슬롯 유일성으로 중복 차단
- 결정적·read-only(불변식 §3-3): job 정의는 순수 dict, 실행은 드라이버 몫.
"""
from __future__ import annotations

from orc_citadel.scheduler import build_scheduler_jobs, COLLECT_JOB_ID, SLO06_JOB_ID


def test_scheduler_registers_two_nightly_jobs():
    """두 nightly job (수집 + SLO-06) 정의 — 1번 시간 축 전환 배치."""
    jobs = build_scheduler_jobs()
    assert len(jobs) == 2
    assert {j["func"] for j in jobs} == {"run_collect", "run_slo06"}


def _slot(job):
    s = job["schedule"]
    return s.get("hour"), s.get("minute")


def test_collect_job_fires_0707():
    """수집 job — 07:07 (피드 갱신 주기 정합, 아침 런)."""
    jobs = {j["func"]: j for j in build_scheduler_jobs()}
    assert _slot(jobs["run_collect"]) == (7, 7)


def test_slo06_job_fires_0737():
    """SLO-06 job — 07:37 (수집 후, 7d 누적 append)."""
    jobs = {j["func"]: j for j in build_scheduler_jobs()}
    assert _slot(jobs["run_slo06"]) == (7, 37)


def test_job_ids_match_expected():
    """job id 는 실행 로직 소유 스크립트와 정합 (nightly_collect/nightly_slo06)."""
    ids = [j["id"] for j in build_scheduler_jobs()]
    assert ids == [COLLECT_JOB_ID, SLO06_JOB_ID]


def test_single_dispatch_principal():
    """단일 발화 주체 — 발화 슬롯이 하루에 유일(중복 없음).

    복수 pod(복제)가 각자 스케줄러를 띄우면 같은 day 에 같은 슬롯이 여러 번
    발화된다. 단일 호스트에서는 **활성 스케줄러가 정확히 1개**여야 하며, 각
    job 의 발화 시각이 유일(07:07 ≠ 07:37)함을 job 정의 차원에서 보장한다.
    """
    jobs = build_scheduler_jobs()
    times = [_slot(j) for j in jobs]
    assert len(times) == len(set(times))  # 슬롯 유일성 — 중복 발화 방지


def test_job_defs_are_deterministic_and_sorted():
    """job 정의는 결정적 (호출 순서 무관, 정렬됨) — read-only 순수 함수."""
    a = build_scheduler_jobs()
    b = build_scheduler_jobs()
    assert [j["func"] for j in a] == [j["func"] for j in b]
    assert [j["id"] for j in a] == [COLLECT_JOB_ID, SLO06_JOB_ID]  # 정렬


GRACE_SECONDS = 86400  # 슬립 보충: 하루(당일치) — 상시 로컬 §6.2


def test_each_job_has_graceful_sleep_backfill():
    """각 job 은 슬립 보충 정책(misfire_grace_seconds) 을 정의로 갖는다.

    상시 로컬에서 맥이 슬립으로 아침 07:07/07:37 을 놓치면, APScheduler 가
    스케줄러 살아있을 때 **grace 내부면 당일 job 을 보충 실행**한다 (기본
    misfire_grace=1 초는 다음날로 미루는 문제). 보충은 정의 차원에서 하루 이상
    보장해야 당일치가 깨어난 뒤에도 놓치지 않는다.
    """
    jobs = build_scheduler_jobs()
    assert len(jobs) == 2
    for j in jobs:
        grace = j.get("misfire_grace_seconds")
        assert grace is not None, f"{j['id']} 에 보충(grace) 정책 없음"
        assert grace >= GRACE_SECONDS, f"{j['id']} 보충이 하루 미만"


def test_misfire_grace_passed_to_apscheduler_job():
    """드라이버 배선 — 보충 정책(grace) 이 APScheduler add_job 의
    misfire_grace_time 으로 전달된다 (슬립으로 놓친 당일 보충 실행)."""
    from scripts.scheduler_runner import _TASKS, _misfire_grace

    jobs = build_scheduler_jobs()
    for j in jobs:
        assert _misfire_grace(j) == j.get("misfire_grace_seconds")
        assert _TASKS[j["func"]]  # 태스크 함수 바인딩 존재


# --- 재시작 보존: grace 보충이 프로세스 재시작을 가로지른다 (A30) ------------------

def test_restart_preserves_missed_next_run(tmp_path):
    """재시작이 영속 store 의 next_run_time(놓친 발화 시각)을 리셋하지 않는다.

    2026-09-05 실측: add_job(replace_existing=True) 재등록이 미발화 시각을
    지워 **재시작을 가로지르는 grace 보충이 불가**했다 (데몬 다운 중 놓친
    당일 발화가 재기동 후 next_run=익일로 스킵). 재기동 후 next_run 이
    보존되어야 resume 시 misfire 판정(grace 내부 → 당일 보충)이 가능하다.
    """
    from datetime import datetime, timedelta, timezone
    from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
    from scripts.scheduler_runner import build_scheduler, register_jobs

    store = tmp_path / "jobs.sqlite"
    s1 = build_scheduler(store)
    s1.start(paused=True)
    register_jobs(s1)
    s1.shutdown()

    # 놓친 발화 시뮬레이션 — store 를 직접 과거로 되돌린다. (스케줄러 modify 로
    # 만들면 shutdown 시 APScheduler 가 due job 을 STOPPED 상태에서 처리해
    # next_run 을 전진시키는 자체 레이스가 있어, 오프라인 store 조작이 결정적.)
    past = datetime.now(timezone.utc) - timedelta(hours=3)
    off = SQLAlchemyJobStore(url=f"sqlite:///{store}")
    missed = off.lookup_job(COLLECT_JOB_ID)
    missed.next_run_time = past
    off.update_job(missed)
    off.shutdown()

    s2 = build_scheduler(store)
    s2.start(paused=True)
    register_jobs(s2)
    j = s2.get_job(COLLECT_JOB_ID)
    preserved = j.next_run_time if j is not None else None
    s2.shutdown()
    assert preserved is not None
    assert abs((preserved - past).total_seconds()) < 1  # 보존 — grace 보충 대상


def test_register_jobs_is_idempotent(tmp_path):
    """register_jobs 재호출이 job 을 중복 생성하지 않는다 (단일 발화 주체)."""
    from scripts.scheduler_runner import build_scheduler, register_jobs

    s = build_scheduler(tmp_path / "jobs.sqlite")
    s.start(paused=True)
    register_jobs(s)
    register_jobs(s)
    jobs = s.get_jobs()
    s.shutdown()
    assert sorted(j.id for j in jobs) == [COLLECT_JOB_ID, SLO06_JOB_ID]


# --- nightly 승격 (수집 → 승격 → 스냅샷) ------------------------------------

def test_collect_task_promotes_zones_before_snapshot(monkeypatch):
    """수집만 하고 승격을 안 하면 화면은 어제 지식에 멈춘다.

    2026-09-18 prod 실측: nightly 가 raw 127건을 받아왔지만 승격이 스케줄에 없어
    curated 는 0 이었고, 사람이 `rebuild_zones` 를 손으로 돌려야 했다. 스냅샷은
    승격 **뒤**여야 DuckDB UI 가 빈 테이블을 보지 않는다.
    """
    from scripts import scheduler_runner as sr

    calls = []
    monkeypatch.setattr(sr, "_flush_metrics", lambda *a, **k: calls.append("metrics"))
    monkeypatch.setattr(sr, "_snapshot_parquet", lambda: calls.append("snapshot"))
    monkeypatch.setattr(sr, "_promote_zones",
                        lambda summary: calls.append("promote"))
    monkeypatch.setitem(
        __import__("sys").modules,
        "scripts.nightly_collect",
        type("M", (), {"main": staticmethod(
            lambda slo_log=None: calls.append("collect") or {"total_new": 3})})(),
    )
    sr.run_collect()

    assert calls.index("collect") < calls.index("promote") < calls.index("snapshot"), calls


def test_promotion_failure_does_not_abort_the_nightly_run(monkeypatch):
    """승격 실패는 비차단 — 수집 결과·스냅샷까지 잃지 않는다 (_flush_metrics 정책)."""
    from scripts import scheduler_runner as sr

    calls = []
    monkeypatch.setattr(sr, "_flush_metrics", lambda *a, **k: None)
    monkeypatch.setattr(sr, "_snapshot_parquet", lambda: calls.append("snapshot"))
    monkeypatch.setitem(
        __import__("sys").modules,
        "scripts.nightly_collect",
        type("M", (), {"main": staticmethod(lambda slo_log=None: {"total_new": 1})})(),
    )

    def _boom():
        raise RuntimeError("raw 존 잠김")

    monkeypatch.setattr(sr, "_promote_new_docs", _boom)
    sr._promote_zones({"total_new": 1})   # 예외가 전파되면 실패
    sr.run_collect()
    assert "snapshot" in calls


def test_rebuild_zones_exposes_callable_api():
    """스케줄러가 argv 파싱 없이 부를 수 있어야 한다 (CLI 는 얇은 래퍼)."""
    from scripts.rebuild_zones import rebuild

    assert callable(rebuild)


def test_collect_task_skips_promotion_when_nothing_new(monkeypatch):
    """신규 문서 0건이면 승격을 건너뛴다 — 전량 재적재는 공짜가 아니다.

    승격은 raw 전량을 다시 읽는다(로컬 dev 존 1.6GB 실측 — 수 분). 새 문서가
    없으면 결과가 같으므로 돌릴 이유가 없고, `run_collect` 를 부르는 다른 테스트가
    실수로 전량 재적재를 트리거하는 사고도 막는다 (실측으로 겪음).
    """
    from scripts import scheduler_runner as sr

    calls = []
    monkeypatch.setattr(sr, "_flush_metrics", lambda *a, **k: None)
    monkeypatch.setattr(sr, "_snapshot_parquet", lambda: None)
    monkeypatch.setattr(sr, "_rebuild_zones", lambda: calls.append("rebuild") or 0)
    monkeypatch.setitem(
        __import__("sys").modules,
        "scripts.nightly_collect",
        type("M", (), {"main": staticmethod(lambda slo_log=None: {"total_new": 0})})(),
    )
    sr.run_collect()
    assert calls == [], "신규 0건인데 전량 재적재를 돌렸다"


def test_promote_uses_incremental_not_full_rebuild(monkeypatch):
    """nightly 승격은 신규 문서만 올린다 — 전량 재빌드는 버전 변경 시의 별도 경로다.

    전량 재빌드는 dedup 서명 재계산만 1,000만 건에서 36시간이다 (2026-09-20 실측
    12.4ms/doc). 신규 1건 때문에 코퍼스 전체를 다시 읽지 않는다.
    """
    from scripts import scheduler_runner as sr

    calls = []
    monkeypatch.setattr(sr, "_promote_new_docs", lambda: calls.append("incremental") or
                        {"new_docs": 3, "mentions": 9, "claims": 2,
                         "promoted_claims": 2, "clusters": 0})
    monkeypatch.setattr(sr, "_rebuild_zones",
                        lambda: calls.append("full") or 0)

    sr._promote_zones({"total_new": 3})

    assert calls == ["incremental"], "nightly 가 전량 재빌드를 돌렸다"
