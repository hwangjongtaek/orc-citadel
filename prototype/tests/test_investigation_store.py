"""영속 investigation/job 저장소의 PostgreSQL 계약."""
from __future__ import annotations

import pytest

psycopg = pytest.importorskip("psycopg")

from orc_citadel.postgres_mutation_log import build_dsn


TEST_PREFIX = "investigation_test"


@pytest.fixture()
def pg():
    try:
        conn = psycopg.connect(build_dsn())
    except Exception as exc:
        pytest.skip(f"postgres 연결 불가: {exc}")
    conn.autocommit = True
    cur = conn.cursor()
    for suffix in ("steps", "jobs", "investigations"):
        cur.execute(f'DROP TABLE IF EXISTS "{TEST_PREFIX}_{suffix}"')
    yield conn
    for suffix in ("steps", "jobs", "investigations"):
        cur.execute(f'DROP TABLE IF EXISTS "{TEST_PREFIX}_{suffix}"')
    conn.close()


def test_create_is_idempotent_and_persists_queued_job(pg):
    """같은 Idempotency-Key는 최초 investigation/job과 정확히 한 번 연결된다."""
    from orc_citadel.investigation_store import InvestigationStore

    store = InvestigationStore(pg, table_prefix=TEST_PREFIX)
    store.ensure_tables()
    first = store.create(
        question="NVIDIA 신제품 발표를 조사",
        subject_id=None,
        scope={"depth": "standard"},
        mode="deterministic",
        idempotency_key="request-1",
    )
    second = store.create(
        question="NVIDIA 신제품 발표를 조사",
        subject_id=None,
        scope={"depth": "standard"},
        mode="deterministic",
        idempotency_key="request-1",
    )

    assert second == first
    assert first["investigation_id"].startswith("inv-")
    assert first["job"]["job_id"].startswith("job-")
    assert first["job"]["status"] == "queued"
    assert store.counts() == {"investigations": 1, "jobs": 1, "steps": 0}


def test_claim_allows_only_one_worker_to_run_a_queued_job(pg):
    """원자 claim 뒤에는 다른 worker가 같은 queued job을 얻지 못한다."""
    from orc_citadel.investigation_store import InvestigationStore

    store = InvestigationStore(pg, table_prefix=TEST_PREFIX)
    created = store.create(
        question="NVIDIA 신제품 발표를 조사",
        subject_id=None,
        scope={},
        mode="deterministic",
        idempotency_key="request-claim",
    )

    claimed = store.claim_next(worker_id="worker-a")

    assert claimed["job_id"] == created["job"]["job_id"]
    assert claimed["status"] == "running"
    assert claimed["claim_token"]
    assert store.claim_next(worker_id="worker-b") is None


def test_steps_are_append_only_and_idempotent_per_investigation(pg):
    """재claim 뒤에도 같은 step은 한 번만 기록된다."""
    from orc_citadel.investigation_store import InvestigationStore

    store = InvestigationStore(pg, table_prefix=TEST_PREFIX)
    created = store.create(
        question="NVIDIA 신제품 발표를 조사",
        subject_id=None,
        scope={},
        mode="deterministic",
        idempotency_key="request-steps",
    )

    assert store.record_step(
        created["investigation_id"], step_id="step-001", stage="PLAN",
        payload={"subclaims": []}, correlation_id="corr-test",
    ) is True
    assert store.record_step(
        created["investigation_id"], step_id="step-001", stage="PLAN",
        payload={"subclaims": []}, correlation_id="corr-test",
    ) is False
    assert store.counts()["steps"] == 1


def test_complete_persists_report_and_audit_for_restart_safe_retrieval(pg):
    """완료 report와 Audit trace는 새 store 인스턴스에서도 그대로 조회된다."""
    from orc_citadel.investigation_store import InvestigationStore

    store = InvestigationStore(pg, table_prefix=TEST_PREFIX)
    created = store.create(
        question="NVIDIA 신제품 발표를 조사",
        subject_id=None,
        scope={},
        mode="deterministic",
        idempotency_key="request-report",
    )
    claimed = store.claim_next(worker_id="worker-a")
    report = {"statements": [{"text": "근거 있는 문장", "claim_ref": "clm-1"}]}
    audit_trace = {"linked": 1, "verifiable": 1, "trace": []}

    assert store.complete(
        job_id=claimed["job_id"], claim_token=claimed["claim_token"],
        report=report, audit_trace=audit_trace,
        coverage={"ratio": 1.0}, termination="coverage",
    ) is True

    restarted = InvestigationStore(pg, table_prefix=TEST_PREFIX)
    assert restarted.get_job(created["job"]["job_id"])["status"] == "succeeded"
    assert restarted.get_investigation(created["investigation_id"])["status"] == "completed"
    assert restarted.get_report(created["investigation_id"]) == {
        "report": report, "audit_trace": audit_trace,
    }


def test_cancelled_queued_job_cannot_be_claimed(pg):
    """queued 취소는 job과 investigation을 즉시 cancelled로 전이한다."""
    from orc_citadel.investigation_store import InvestigationStore

    store = InvestigationStore(pg, table_prefix=TEST_PREFIX)
    created = store.create(
        question="NVIDIA 신제품 발표를 조사",
        subject_id=None,
        scope={},
        mode="deterministic",
        idempotency_key="request-cancel",
    )

    cancelled = store.cancel(created["investigation_id"])

    assert cancelled["job"]["status"] == "cancelled"
    assert cancelled["status"] == "cancelled"
    assert store.claim_next(worker_id="worker-a") is None


def test_expired_running_job_is_reclaimed_without_accepting_old_worker_result(pg):
    """고아 running job은 새 claim으로 회수되고 이전 worker의 완료는 거부된다."""
    from orc_citadel.investigation_store import InvestigationStore

    store = InvestigationStore(pg, table_prefix=TEST_PREFIX)
    created = store.create(
        question="NVIDIA 신제품 발표를 조사",
        subject_id=None,
        scope={},
        mode="deterministic",
        idempotency_key="request-reclaim",
    )
    original = store.claim_next(worker_id="worker-a", lease_seconds=1)
    pg.execute(
        f'UPDATE "{TEST_PREFIX}_jobs" SET lease_expires_at = now() - interval \'1 second\''
    )

    reclaimed = store.claim_next(worker_id="worker-b")

    assert reclaimed["job_id"] == original["job_id"] == created["job"]["job_id"]
    assert reclaimed["claim_token"] != original["claim_token"]
    assert store.complete(
        job_id=original["job_id"], claim_token=original["claim_token"],
        report={}, audit_trace={}, coverage={}, termination="coverage",
    ) is False
