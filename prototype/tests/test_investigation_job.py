"""영속 read-only investigation worker의 claim·단계·완료 계약."""
from __future__ import annotations

import threading
import time
import pytest

psycopg = pytest.importorskip("psycopg")

from orc_citadel.postgres_mutation_log import build_dsn

TEST_PREFIX = "investigation_worker_test"


@pytest.fixture()
def store():
    from orc_citadel.investigation_store import InvestigationStore

    conn = psycopg.connect(build_dsn())
    conn.autocommit = True
    cur = conn.cursor()
    for suffix in ("steps", "jobs", "investigations"):
        cur.execute(f'DROP TABLE IF EXISTS "{TEST_PREFIX}_{suffix}"')
    out = InvestigationStore(conn, table_prefix=TEST_PREFIX)
    out.ensure_tables()
    yield out
    for suffix in ("steps", "jobs", "investigations"):
        cur.execute(f'DROP TABLE IF EXISTS "{TEST_PREFIX}_{suffix}"')
    conn.close()


def test_worker_runs_claimed_job_once_and_persists_four_stages(store):
    """worker는 existing evidence 결과만 저장하고 PLAN/RUN/SYNTHESIZE/AUDIT를 남긴다."""
    from orc_citadel.investigation_job import InvestigationWorker

    created = store.create(
        question="NVIDIA 신제품 발표를 조사",
        subject_id=None,
        scope={"depth": "standard"},
        mode="deterministic",
        idempotency_key="worker-request",
    )
    result = {
        "coverage": 1.0,
        "terminated_by": "coverage",
        "statements": [{"text": "근거 있는 문장", "claim_ref": "clm-1"}],
        "audit_trace": {"linked": 1, "verifiable": 1, "trace": []},
        "llm": None,
    }
    execution = {}

    class _Zone:
        closed = False

        def close(self):
            self.closed = True

    class _Facade:
        zone = _Zone()

    facade = _Facade()

    def execute(read_facade, **kwargs):
        execution.update(kwargs)
        assert read_facade is facade
        return result

    worker = InvestigationWorker(
        store, worker_id="worker-a", facade_factory=lambda: facade,
        execute=execute,
    )

    assert worker.run_once() is True
    assert store.get_job(created["job"]["job_id"])["status"] == "succeeded"
    assert store.get_investigation(created["investigation_id"])["status"] == "completed"
    assert store.get_report(created["investigation_id"])["report"] == result
    assert store.counts()["steps"] == 4
    assert execution["investigation_id"] == created["investigation_id"]
    assert execution["scope"] == {"depth": "standard"}
    assert facade.zone.closed is True
    assert worker.run_once() is False


def test_worker_renews_lease_while_run_stage_is_active(store):
    """장기 RUN 중에도 lease를 갱신해 경쟁 worker의 중복 실행을 막는다."""
    from orc_citadel.investigation_job import InvestigationWorker
    from orc_citadel.investigation_store import InvestigationStore

    store.create(
        question="NVIDIA 신제품 발표를 조사",
        subject_id=None,
        scope={},
        mode="deterministic",
        idempotency_key="worker-heartbeat",
    )
    started = threading.Event()
    release = threading.Event()
    calls = []

    def execute(*args, **kwargs):
        calls.append(kwargs["investigation_id"])
        started.set()
        assert release.wait(timeout=2)
        return {
            "coverage": 1.0, "terminated_by": "coverage", "statements": [],
            "audit_trace": {}, "llm": None,
        }

    worker = InvestigationWorker(
        store,
        worker_id="worker-a",
        facade_factory=lambda: object(),
        execute=execute,
        lease_seconds=0.2,
        heartbeat_interval=0.05,
    )
    thread = threading.Thread(target=worker.run_once)
    thread.start()
    assert started.wait(timeout=1)
    time.sleep(0.35)

    second_conn = psycopg.connect(build_dsn())
    second_conn.autocommit = True
    competing_store = InvestigationStore(second_conn, table_prefix=TEST_PREFIX)
    try:
        assert competing_store.claim_next(worker_id="worker-b") is None
    finally:
        second_conn.close()
        release.set()
        thread.join(timeout=2)

    assert thread.is_alive() is False
    assert len(calls) == 1


def test_worker_persists_unhandled_execution_error_as_failed_job(store):
    """실행 예외는 가짜 성공 없이 failed 상태와 구조화 오류로 남는다."""
    from orc_citadel.investigation_job import InvestigationWorker

    created = store.create(
        question="NVIDIA 신제품 발표를 조사",
        subject_id=None,
        scope={},
        mode="deterministic",
        idempotency_key="worker-failure",
    )

    def fail(*args, **kwargs):
        raise RuntimeError("simulated execution error")

    worker = InvestigationWorker(
        store, worker_id="worker-a", facade_factory=lambda: object(), execute=fail,
    )

    assert worker.run_once() is True
    job = store.get_job(created["job"]["job_id"])
    assert job["status"] == "failed"
    assert job["error_json"] == {"code": "investigation_execution_failed",
                                 "message": "simulated execution error"}
    assert store.get_investigation(created["investigation_id"])["status"] == "failed"


def test_running_cancel_request_wins_over_late_worker_result(store):
    """RUN 중 cancel request가 오면 완료 report는 저장되지 않는다."""
    from orc_citadel.investigation_job import InvestigationWorker

    created = store.create(
        question="NVIDIA 신제품 발표를 조사",
        subject_id=None,
        scope={},
        mode="deterministic",
        idempotency_key="worker-cancel",
    )
    cancel_response = {}

    def request_cancel(*args, **kwargs):
        cancel_response.update(store.cancel(created["investigation_id"]))
        return {"coverage": 1.0, "terminated_by": "coverage",
                "statements": [], "audit_trace": {}, "llm": None}

    worker = InvestigationWorker(
        store, worker_id="worker-a", facade_factory=lambda: object(),
        execute=request_cancel,
    )

    assert worker.run_once() is True
    assert cancel_response["status"] == "running"
    assert cancel_response["job"]["cancel_requested"] is True
    assert store.get_job(created["job"]["job_id"])["status"] == "cancelled"
    assert store.get_investigation(created["investigation_id"])["status"] == "cancelled"
    assert store.get_report(created["investigation_id"]) is None
