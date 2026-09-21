"""영속 read-only investigation worker의 claim·단계·완료 계약."""
from __future__ import annotations

import hashlib
import json
import threading
import time
import pytest

psycopg = pytest.importorskip("psycopg")

from orc_citadel.postgres_mutation_log import build_dsn

TEST_PREFIX = "investigation_worker_test"

REPORT_PROFILE = {
    "generation_mode": "llm_assisted",
    "template_version": "citadel-report-1",
    "output_schema_version": "report-draft/1.0.0",
    "prompt_template_hash": "sha256:" + "a" * 64,
}


class _Artifact:
    def __init__(self, result=None, report_profile=None):
        self._result = result or {}
        self._profile = report_profile or REPORT_PROFILE

    def as_store_dict(self):
        html = b"<!doctype html><title>fallback</title>"
        draft = {
            "draft_schema_version": "report-draft/1.0.0",
            "investigation_id": "inv-test",
        }
        canonical = lambda value: json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        digest = lambda value: "sha256:" + hashlib.sha256(value).hexdigest()
        return {
            "html_bytes": html,
            "content_hash": digest(html),
            "source_report_hash": digest(canonical({
                "report": self._result,
                "audit_trace": self._result.get("audit_trace", {}),
            })),
            "draft_json": draft,
            "draft_hash": digest(canonical(draft)),
            "generation_mode": "deterministic_fallback",
            "fallback_reason": "llm_unavailable",
            "template_version": self._profile["template_version"],
            "output_schema_version": self._profile["output_schema_version"],
            "provider": None,
            "model_id": None,
            "prompt_template_hash": self._profile["prompt_template_hash"],
            "usage": {},
            "audit_summary": {"linked": 1, "verifiable": 1, "blocked": 0},
        }


class _Generator:
    def __init__(self):
        self.calls = []

    def generate(self, result, investigation_meta, report_profile):
        self.calls.append((result, investigation_meta, report_profile))
        return _Artifact(result, report_profile)


@pytest.fixture()
def store():
    from orc_citadel.investigation_store import InvestigationStore

    conn = psycopg.connect(build_dsn())
    conn.autocommit = True
    cur = conn.cursor()
    for suffix in ("report_artifacts", "steps", "jobs", "investigations"):
        cur.execute(f'DROP TABLE IF EXISTS "{TEST_PREFIX}_{suffix}"')
    out = InvestigationStore(conn, table_prefix=TEST_PREFIX)
    out.ensure_tables()
    yield out
    for suffix in ("report_artifacts", "steps", "jobs", "investigations"):
        cur.execute(f'DROP TABLE IF EXISTS "{TEST_PREFIX}_{suffix}"')
    conn.close()


def test_worker_runs_claimed_job_once_and_persists_report_stage(store):
    """worker는 감사 결과와 fallback HTML을 단일 REPORT 완료 경계에 저장한다."""
    from orc_citadel.investigation_job import InvestigationWorker

    created = store.create(
        question="NVIDIA 신제품 발표를 조사",
        subject_id=None,
        scope={"depth": "standard"},
        mode="deterministic",
        idempotency_key="worker-request",
        report_profile=REPORT_PROFILE,
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
    generator = _Generator()

    def execute(read_facade, **kwargs):
        execution.update(kwargs)
        assert read_facade is facade
        return result

    worker = InvestigationWorker(
        store, worker_id="worker-a", facade_factory=lambda: facade,
        execute=execute, report_generator=generator,
    )

    assert worker.run_once() is True
    assert store.get_job(created["job"]["job_id"])["status"] == "succeeded"
    assert store.get_investigation(created["investigation_id"])["status"] == "completed"
    assert store.get_report(created["investigation_id"])["report"] == result
    assert store.counts()["steps"] == 5
    assert execution["investigation_id"] == created["investigation_id"]
    assert execution["scope"] == {"depth": "standard"}
    assert facade.zone.closed is True
    assert generator.calls[0][1]["audit_trace"] == result["audit_trace"]
    assert store.get_report_artifact(created["investigation_id"])[
        "generation_mode"
    ] == "deterministic_fallback"
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
        report_profile=REPORT_PROFILE,
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
        report_generator=_Generator(),
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
        report_profile=REPORT_PROFILE,
    )

    def fail(*args, **kwargs):
        raise RuntimeError("simulated execution error")

    worker = InvestigationWorker(
        store, worker_id="worker-a", facade_factory=lambda: object(), execute=fail,
        report_generator=_Generator(),
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
        report_profile=REPORT_PROFILE,
    )
    cancel_response = {}

    def request_cancel(*args, **kwargs):
        cancel_response.update(store.cancel(created["investigation_id"]))
        return {"coverage": 1.0, "terminated_by": "coverage",
                "statements": [], "audit_trace": {}, "llm": None}

    worker = InvestigationWorker(
        store, worker_id="worker-a", facade_factory=lambda: object(),
        execute=request_cancel, report_generator=_Generator(),
    )

    assert worker.run_once() is True
    assert cancel_response["status"] == "running"
    assert cancel_response["job"]["cancel_requested"] is True
    assert store.get_job(created["job"]["job_id"])["status"] == "cancelled"
    assert store.get_investigation(created["investigation_id"])["status"] == "cancelled"
    assert store.get_report(created["investigation_id"]) is None
    assert store.get_report_artifact(created["investigation_id"]) is None


def test_worker_renews_lease_while_report_generation_is_active(store):
    """장기 REPORT 생성 중 heartbeat가 claim을 다른 worker에게 넘기지 않는다."""
    from orc_citadel.investigation_job import InvestigationWorker
    from orc_citadel.investigation_store import InvestigationStore

    created = store.create(
        question="REPORT heartbeat",
        subject_id=None,
        scope={},
        mode="deterministic",
        idempotency_key="worker-report-heartbeat",
        report_profile=REPORT_PROFILE,
    )
    started = threading.Event()
    release = threading.Event()

    class BlockingGenerator:
        def generate(self, *args):
            started.set()
            assert release.wait(timeout=2)
            return _Artifact(args[0], args[2])

    def execute(*args, **kwargs):
        return {
            "coverage": 1.0,
            "terminated_by": "coverage",
            "statements": [],
            "audit_trace": {},
            "llm": None,
        }

    worker = InvestigationWorker(
        store,
        worker_id="worker-a",
        facade_factory=lambda: object(),
        execute=execute,
        report_generator=BlockingGenerator(),
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
    assert store.get_job(created["job"]["job_id"])["status"] == "succeeded"


def test_report_renderer_error_fails_without_artifact_or_report_step(store):
    from orc_citadel.investigation_job import InvestigationWorker

    created = store.create(
        question="renderer failure",
        subject_id=None,
        scope={},
        mode="deterministic",
        idempotency_key="worker-renderer-failure",
        report_profile=REPORT_PROFILE,
    )

    class FailingGenerator:
        def generate(self, *args):
            raise RuntimeError("simulated renderer error")

    worker = InvestigationWorker(
        store,
        worker_id="worker-a",
        facade_factory=lambda: object(),
        execute=lambda *args, **kwargs: {
            "coverage": 1.0,
            "terminated_by": "coverage",
            "statements": [],
            "audit_trace": {},
            "llm": None,
        },
        report_generator=FailingGenerator(),
    )

    assert worker.run_once() is True
    assert store.get_job(created["job"]["job_id"])["error_json"] == {
        "code": "investigation_report_failed",
        "message": "simulated renderer error",
    }
    assert store.get_report_artifact(created["investigation_id"]) is None
    assert store.get_latest_step(created["investigation_id"])["stage"] == "AUDIT"


def test_cancel_during_report_generation_wins_without_partial_completion(store):
    from orc_citadel.investigation_job import InvestigationWorker

    created = store.create(
        question="cancel during REPORT",
        subject_id=None,
        scope={},
        mode="deterministic",
        idempotency_key="worker-report-cancel",
        report_profile=REPORT_PROFILE,
    )

    class CancellingGenerator:
        def generate(self, *args):
            store.cancel(created["investigation_id"])
            return _Artifact(args[0], args[2])

    worker = InvestigationWorker(
        store,
        worker_id="worker-a",
        facade_factory=lambda: object(),
        execute=lambda *args, **kwargs: {
            "coverage": 1.0,
            "terminated_by": "coverage",
            "statements": [],
            "audit_trace": {},
            "llm": None,
        },
        report_generator=CancellingGenerator(),
    )

    assert worker.run_once() is True
    assert store.get_job(created["job"]["job_id"])["status"] == "cancelled"
    assert store.get_report_artifact(created["investigation_id"]) is None
    assert store.get_latest_step(created["investigation_id"])["stage"] == "AUDIT"


def test_artifact_storage_error_rolls_back_and_fails_job(store):
    from orc_citadel.investigation_job import InvestigationWorker

    created = store.create(
        question="storage failure",
        subject_id=None,
        scope={},
        mode="deterministic",
        idempotency_key="worker-storage-failure",
        report_profile=REPORT_PROFILE,
    )

    class InvalidArtifact(_Artifact):
        def as_store_dict(self):
            artifact = super().as_store_dict()
            artifact["content_hash"] = "not-a-sha256"
            return artifact

    class InvalidArtifactGenerator:
        def generate(self, *args):
            return InvalidArtifact(args[0], args[2])

    worker = InvestigationWorker(
        store,
        worker_id="worker-a",
        facade_factory=lambda: object(),
        execute=lambda *args, **kwargs: {
            "coverage": 1.0,
            "terminated_by": "coverage",
            "statements": [],
            "audit_trace": {},
            "llm": None,
        },
        report_generator=InvalidArtifactGenerator(),
    )

    assert worker.run_once() is True
    job = store.get_job(created["job"]["job_id"])
    assert job["status"] == "failed"
    assert job["error_json"]["code"] == "investigation_report_storage_failed"
    assert store.get_report_artifact(created["investigation_id"]) is None
    assert store.get_latest_step(created["investigation_id"])["stage"] == "AUDIT"
