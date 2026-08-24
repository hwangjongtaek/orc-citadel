"""Nightly 스케줄러 job 정의 (celery beat 대체 — 단일 호스트, A26 후속).

APScheduler `BackgroundScheduler` 기반의 주기 dispatch 는 **상주 드라이버
(scripts/scheduler_runner.py)** 몫이다. 여기선 그 드라이버가 사용할 **job 정의를
순수 함수로 분리**해 오프라인 검증(결정성·단일 발화 주체·시각)한다.

단일 발화 주체 원칙: 단일 호스트 배포에서 **활성 스케줄러는 정확히 1개**여야
한다. 복수 pod(복제)가 각자 스케줄러를 띄우면 같은 날 같은 job 이 중복 발화되어
수집 경합·7d 누적 append 중복을 유발한다 (celery beat 가 Redis 잠금으로 방지하는
것과 동일한 문제). 단일 호스트(compose replicas=1)에서는 발화 슬롯 유일성으로
중복을 차단한다. 작업 자체는 이미 멱등(S1 URL-skip · S2 content-hash)이라, 미래
복제 시엔 공유 잠금(Postgres/MinIO)을 추가하는 지점이 여기서 명확해진다.

- read-only(불변식 §3-3): job 정의는 순수 dict, 실행·영속·스케줄링은 드라이버.
- 결정적: 호출 순서 무관, 정렬 반환.
- `schedule` 은 순수 dict 이라 테스트 용이 — 드라이버가 CronTrigger(**schedule) 로
  변환해 BackgroundScheduler 에 등록한다.
"""
from __future__ import annotations

# 실행 로직 소유: scripts/nightly_collect.main()·scripts/nightly_slo06.main()
# 드라이버가 태스크 함수를 주입해 바인딩한다 (job 정의는 이름만 결정).
COLLECT_JOB_ID = "nightly_collect"
SLO06_JOB_ID = "nightly_slo06"

# CronTrigger(**schedule) 로 변환된다. (hour, minute) 슬롯은 유일 — 중복 발화 없음.
JOB_SCHEDULES: dict[str, dict] = {
    COLLECT_JOB_ID: {"hour": 7, "minute": 7},   # 피드 갱신 주기(일) 정합
    SLO06_JOB_ID: {"hour": 7, "minute": 37},    # 수집 후, 7d 누적 append
}


def build_scheduler_jobs() -> list[dict]:
    """nightly job 정의 (결정적·정렬) — {"id", "func", "schedule"} 목록.

    `func` 는 드라이버가 주입하는 태스크 함수 이름. `schedule`(CronTrigger kwargs)
    는 순수 dict — 단일 스케줄러에서 발화 슬롯이 유일해 중복 발화가 없다.
    """
    jobs = [
        {"id": job_id, "func": "run_collect" if job_id == COLLECT_JOB_ID
         else "run_slo06", "schedule": dict(sch)}
        for job_id, sch in JOB_SCHEDULES.items()
    ]
    return sorted(jobs, key=lambda j: j["id"])
