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
