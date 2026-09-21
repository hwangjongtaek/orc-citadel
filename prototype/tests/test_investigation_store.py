"""영속 investigation/job 저장소의 PostgreSQL 계약."""
from __future__ import annotations

import hashlib
import json
import pytest

psycopg = pytest.importorskip("psycopg")

from orc_citadel.postgres_mutation_log import build_dsn


TEST_PREFIX = "investigation_test"

REPORT_PROFILE = {
    "generation_mode": "llm_assisted",
    "template_version": "citadel-report-1",
    "output_schema_version": "report-draft/1.0.0",
    "prompt_template_hash": "sha256:" + "a" * 64,
}


def _canonical(value) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _artifact(
    *,
    report: dict | None = None,
    audit_trace: dict | None = None,
    html: bytes = b"<!doctype html><title>report</title>",
) -> dict:
    report = {} if report is None else report
    audit_trace = {} if audit_trace is None else audit_trace
    draft = {
        "draft_schema_version": "report-draft/1.0.0",
        "investigation_id": "ignored-by-store",
    }
    digest = lambda value: "sha256:" + hashlib.sha256(value).hexdigest()
    return {
        "html_bytes": html,
        "content_hash": digest(html),
        "source_report_hash": digest(_canonical({
            "report": report,
            "audit_trace": audit_trace,
        })),
        "draft_json": draft,
        "draft_hash": digest(_canonical(draft)),
        "generation_mode": "deterministic_fallback",
        "fallback_reason": "llm_unavailable",
        "template_version": "citadel-report-1",
        "output_schema_version": "report-draft/1.0.0",
        "provider": None,
        "model_id": None,
        "prompt_template_hash": "sha256:" + "a" * 64,
        "usage": {},
        "audit_summary": {"linked": 1, "verifiable": 1, "blocked": 0},
    }


@pytest.fixture()
def pg():
    try:
        conn = psycopg.connect(build_dsn())
    except Exception as exc:
        pytest.skip(f"postgres 연결 불가: {exc}")
    conn.autocommit = True
    cur = conn.cursor()
    for suffix in ("report_artifacts", "steps", "jobs", "investigations"):
        cur.execute(f'DROP TABLE IF EXISTS "{TEST_PREFIX}_{suffix}"')
    yield conn
    for suffix in ("report_artifacts", "steps", "jobs", "investigations"):
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
        report_profile=REPORT_PROFILE,
    )
    second = store.create(
        question="NVIDIA 신제품 발표를 조사",
        subject_id=None,
        scope={"depth": "standard"},
        mode="deterministic",
        idempotency_key="request-1",
        report_profile=REPORT_PROFILE,
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
        report_profile=REPORT_PROFILE,
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
        report_profile=REPORT_PROFILE,
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
        report_profile=REPORT_PROFILE,
    )
    claimed = store.claim_next(worker_id="worker-a")
    report = {"statements": [{"text": "근거 있는 문장", "claim_ref": "clm-1"}]}
    audit_trace = {"linked": 1, "verifiable": 1, "trace": []}

    assert store.complete_with_report_artifact(
        job_id=claimed["job_id"], claim_token=claimed["claim_token"],
        report=report, audit_trace=audit_trace,
        coverage={"ratio": 1.0}, termination="coverage",
        artifact=_artifact(report=report, audit_trace=audit_trace),
    ) is True

    restarted = InvestigationStore(pg, table_prefix=TEST_PREFIX)
    assert restarted.get_job(created["job"]["job_id"])["status"] == "succeeded"
    assert restarted.get_investigation(created["investigation_id"])["status"] == "completed"
    assert restarted.get_report(created["investigation_id"]) == {
        "report": report, "audit_trace": audit_trace,
    }
    artifact = restarted.get_report_artifact(created["investigation_id"])
    assert artifact["generation_mode"] == "deterministic_fallback"
    assert "html_bytes" not in artifact
    assert restarted.get_report_artifact(
        created["investigation_id"], include_html=True,
    )["html_bytes"] == b"<!doctype html><title>report</title>"
    assert restarted.get_latest_step(created["investigation_id"])["stage"] == "REPORT"


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
        report_profile=REPORT_PROFILE,
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
        report_profile=REPORT_PROFILE,
    )
    original = store.claim_next(worker_id="worker-a", lease_seconds=1)
    pg.execute(
        f'UPDATE "{TEST_PREFIX}_jobs" SET lease_expires_at = now() - interval \'1 second\''
    )

    reclaimed = store.claim_next(worker_id="worker-b")

    assert reclaimed["job_id"] == original["job_id"] == created["job"]["job_id"]
    assert reclaimed["claim_token"] != original["claim_token"]
    assert store.complete_with_report_artifact(
        job_id=original["job_id"], claim_token=original["claim_token"],
        report={}, audit_trace={}, coverage={}, termination="coverage",
        artifact=_artifact(),
    ) is False
    assert store.get_report_artifact(created["investigation_id"]) is None


def test_report_profile_migration_preserves_legacy_null_rows(pg):
    """기존 row는 profile을 backfill하지 않아 legacy JSON-only 상태로 구분된다."""
    from orc_citadel.investigation_store import InvestigationStore

    store = InvestigationStore(pg, table_prefix=TEST_PREFIX)
    store.ensure_tables()
    pg.execute(
        f'''INSERT INTO "{TEST_PREFIX}_investigations"
            (investigation_id, idempotency_key, question, subject_id, scope, mode,
             owner, version_tuple, correlation_id, status, report, audit_trace,
             completed_at)
            VALUES ('inv-legacy', 'legacy', 'legacy report', NULL, '{{}}', 'deterministic',
                    NULL, '{{}}', 'corr-legacy', 'completed', '{{}}', '{{}}', now())'''
    )
    pg.execute(
        f'''INSERT INTO "{TEST_PREFIX}_jobs"
            (job_id, investigation_id, kind, status, finished_at)
            VALUES ('job-legacy', 'inv-legacy', 'investigation', 'succeeded', now())'''
    )

    store.ensure_tables()

    assert store.get_investigation("inv-legacy")["report_profile"] is None
    listed = store.list_investigations()
    assert listed["items"][0]["artifact_state"] == "legacy_json_only"


def test_claim_and_get_expose_immutable_report_profile(pg):
    from orc_citadel.investigation_store import InvestigationStore

    store = InvestigationStore(pg, table_prefix=TEST_PREFIX)
    created = store.create(
        question="profile",
        subject_id=None,
        scope={},
        mode="deterministic",
        idempotency_key="request-profile",
        report_profile=REPORT_PROFILE,
    )

    assert store.claim_next(worker_id="worker-a")["report_profile"] == REPORT_PROFILE
    assert store.get_investigation(created["investigation_id"])[
        "report_profile"
    ] == REPORT_PROFILE


def test_cancel_fence_rolls_back_artifact_and_report_step(pg):
    from orc_citadel.investigation_store import InvestigationStore

    store = InvestigationStore(pg, table_prefix=TEST_PREFIX)
    created = store.create(
        question="cancel at report boundary",
        subject_id=None,
        scope={},
        mode="deterministic",
        idempotency_key="request-report-cancel",
        report_profile=REPORT_PROFILE,
    )
    claimed = store.claim_next(worker_id="worker-a")
    store.cancel(created["investigation_id"])

    assert store.complete_with_report_artifact(
        job_id=claimed["job_id"],
        claim_token=claimed["claim_token"],
        report={},
        audit_trace={},
        coverage={},
        termination="coverage",
        artifact=_artifact(),
    ) is False
    assert store.get_report_artifact(created["investigation_id"]) is None
    assert store.get_latest_step(created["investigation_id"]) is None


def test_list_uses_newest_first_opaque_keyset_without_html(pg):
    from orc_citadel.investigation_store import InvestigationStore

    store = InvestigationStore(pg, table_prefix=TEST_PREFIX)
    ids = []
    for sequence in range(3):
        created = store.create(
            question=f"report {sequence}",
            subject_id=None,
            scope={},
            mode="deterministic",
            idempotency_key=f"request-list-{sequence}",
            report_profile=REPORT_PROFILE,
        )
        ids.append(created["investigation_id"])
        pg.execute(
            f'''UPDATE "{TEST_PREFIX}_investigations"
                SET created_at = '2026-01-01 00:00:00+00'::timestamptz
                                 + (%s * interval '1 second')
                WHERE investigation_id = %s''',
            (sequence, created["investigation_id"]),
        )

    first = store.list_investigations(limit=2)
    second = store.list_investigations(limit=2, cursor=first["page"]["next_cursor"])

    assert [item["investigation_id"] for item in first["items"]] == ids[:0:-1]
    assert [item["investigation_id"] for item in second["items"]] == ids[:1]
    assert first["page"]["next_cursor"] is not None
    assert second["page"]["next_cursor"] is None
    assert all(item["artifact"] is None for item in first["items"] + second["items"])


def test_report_step_uniqueness_rolls_back_artifact_and_completion(pg):
    """REPORT step 충돌은 먼저 insert한 artifact까지 같은 transaction에서 되돌린다."""
    from orc_citadel.investigation_store import InvestigationStore

    store = InvestigationStore(pg, table_prefix=TEST_PREFIX)
    created = store.create(
        question="atomic report completion",
        subject_id=None,
        scope={},
        mode="deterministic",
        idempotency_key="request-report-atomicity",
        report_profile=REPORT_PROFILE,
    )
    claimed = store.claim_next(worker_id="worker-a")
    store.record_step(
        created["investigation_id"],
        step_id="step-005",
        stage="REPORT",
        payload={},
        correlation_id=claimed["correlation_id"],
    )

    assert store.complete_with_report_artifact(
        job_id=claimed["job_id"],
        claim_token=claimed["claim_token"],
        report={},
        audit_trace={},
        coverage={},
        termination="coverage",
        artifact=_artifact(),
    ) is False
    assert store.get_report_artifact(created["investigation_id"]) is None
    assert store.get_job(created["job"]["job_id"])["status"] == "running"
    assert store.get_investigation(created["investigation_id"])["status"] == "running"


def test_active_legacy_job_receives_report_profile_before_claim(pg):
    """배포 전에 queued였던 job도 새 worker에서 HTML report를 생성할 수 있다."""
    from orc_citadel.investigation_report import default_report_profile
    from orc_citadel.investigation_store import InvestigationStore

    store = InvestigationStore(pg, table_prefix=TEST_PREFIX)
    store.ensure_tables()
    pg.execute(
        f'''INSERT INTO "{TEST_PREFIX}_investigations"
            (investigation_id, idempotency_key, question, subject_id, scope, mode,
             owner, version_tuple, correlation_id, status)
            VALUES ('inv-active-legacy', 'active-legacy', 'queued report', NULL,
                    '{{}}', 'deterministic', NULL, '{{}}', 'corr-active',
                    'queued')'''
    )
    pg.execute(
        f'''INSERT INTO "{TEST_PREFIX}_jobs"
            (job_id, investigation_id, kind, status)
            VALUES ('job-active-legacy', 'inv-active-legacy',
                    'investigation', 'queued')'''
    )

    store.ensure_tables()

    claimed = store.claim_next(worker_id="worker-migrated")
    assert claimed["investigation_id"] == "inv-active-legacy"
    assert claimed["report_profile"] == default_report_profile()


def test_completion_rejects_unbound_hashes_and_profile_pins(pg):
    """성공 경계는 저장할 bytes/report/draft와 investigation pin을 직접 검증한다."""
    from orc_citadel.investigation_store import InvestigationStore

    store = InvestigationStore(pg, table_prefix=TEST_PREFIX)
    created = store.create(
        question="integrity",
        subject_id=None,
        scope={},
        mode="deterministic",
        idempotency_key="request-integrity",
        report_profile=REPORT_PROFILE,
    )
    claimed = store.claim_next(worker_id="worker-a")

    bad_hash = _artifact()
    bad_hash["content_hash"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="content_hash"):
        store.complete_with_report_artifact(
            job_id=claimed["job_id"],
            claim_token=claimed["claim_token"],
            report={},
            audit_trace={},
            coverage={},
            termination="coverage",
            artifact=bad_hash,
        )

    bad_pin = _artifact()
    bad_pin["template_version"] = "wrong-template"
    with pytest.raises(ValueError, match="template_version"):
        store.complete_with_report_artifact(
            job_id=claimed["job_id"],
            claim_token=claimed["claim_token"],
            report={},
            audit_trace={},
            coverage={},
            termination="coverage",
            artifact=bad_pin,
        )

    assert store.get_report_artifact(created["investigation_id"]) is None
    assert store.get_job(created["job"]["job_id"])["status"] == "running"


def test_terminal_unsuccessful_list_item_never_reports_pending_artifact(pg):
    from orc_citadel.investigation_store import InvestigationStore

    store = InvestigationStore(pg, table_prefix=TEST_PREFIX)
    created = store.create(
        question="failure",
        subject_id=None,
        scope={},
        mode="deterministic",
        idempotency_key="request-failed-artifact-state",
        report_profile=REPORT_PROFILE,
    )
    claimed = store.claim_next(worker_id="worker-a")
    assert store.fail(
        job_id=claimed["job_id"],
        claim_token=claimed["claim_token"],
        error={"code": "failed"},
    )

    item = store.list_investigations()["items"][0]
    assert item["investigation_id"] == created["investigation_id"]
    assert item["artifact_state"] == "unavailable"


def test_create_bounds_report_inputs_before_persistence(pg):
    from orc_citadel.investigation_store import InvestigationStore

    store = InvestigationStore(pg, table_prefix=TEST_PREFIX)
    with pytest.raises(ValueError, match="question.*32 KiB"):
        store.create(
            question="x" * (32 * 1024 + 1),
            subject_id=None,
            scope={},
            mode="deterministic",
            idempotency_key="request-large-question",
            report_profile=REPORT_PROFILE,
        )
    with pytest.raises(ValueError, match="scope.*64 KiB"):
        store.create(
            question="bounded",
            subject_id=None,
            scope={"payload": "x" * (64 * 1024)},
            mode="deterministic",
            idempotency_key="request-large-scope",
            report_profile=REPORT_PROFILE,
        )
