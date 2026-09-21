"""PostgreSQL-backed durable investigation/job 저장소.

그래프·curated zone을 변경하지 않는다. 이 모듈은 investigation 실행의 운영
메타데이터와 결과만 영속하며, queue claim은 PostgreSQL 트랜잭션으로 직렬화한다.
"""
from __future__ import annotations

import base64
import hashlib
import binascii
import json
import re
from datetime import datetime, timedelta, timezone

from .identity import new_ulid

JOB_STATUSES = {"queued", "running", "succeeded", "failed", "cancelled"}
INVESTIGATION_STATUSES = {"queued", "running", "completed", "failed", "cancelled"}
MODES = {"deterministic", "llm"}

REPORT_GENERATION_MODES = {"llm_assisted", "deterministic_fallback"}
REPORT_FALLBACK_REASONS = {
    "llm_unavailable",
    "llm_provider_error",
    "invalid_draft",
    "audit_rejected",
}
REPORT_PROFILE_FIELDS = {
    "generation_mode",
    "template_version",
    "output_schema_version",
    "prompt_template_hash",
}
MAX_QUESTION_BYTES = 32 * 1024
MAX_SCOPE_BYTES = 64 * 1024


def _canonical_json_bytes(value) -> bytes:
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("investigation data must be canonical JSON") from exc
    return text.encode("utf-8")


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()



class _CompletionRejected(Exception):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class InvestigationStore:
    """investigation, job, append-only step, report를 한 연결에서 관리한다."""

    def __init__(self, conn, *, table_prefix: str = "investigation") -> None:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table_prefix):
            raise ValueError("table_prefix는 SQL identifier여야 합니다")
        self._conn = conn
        self._prefix = table_prefix

    @property
    def investigations_table(self) -> str:
        return f"{self._prefix}_investigations"

    @property
    def jobs_table(self) -> str:
        return f"{self._prefix}_jobs"

    @property
    def steps_table(self) -> str:
        return f"{self._prefix}_steps"

    @property
    def report_artifacts_table(self) -> str:
        return f"{self._prefix}_report_artifacts"

    def ensure_tables(self) -> None:
        cur = self._conn.cursor()
        cur.execute(
            f'''CREATE TABLE IF NOT EXISTS "{self.investigations_table}" (
                investigation_id varchar PRIMARY KEY,
                idempotency_key varchar UNIQUE NOT NULL,
                question text NOT NULL,
                subject_id varchar,
                scope jsonb NOT NULL,
                mode varchar NOT NULL,
                owner varchar,
                version_tuple jsonb NOT NULL,
                correlation_id varchar NOT NULL,
                status varchar NOT NULL,
                coverage jsonb NOT NULL DEFAULT '{{}}'::jsonb,
                termination varchar,
                report jsonb,
                audit_trace jsonb,
                created_at timestamptz NOT NULL DEFAULT now(),
                updated_at timestamptz NOT NULL DEFAULT now(),
                completed_at timestamptz
            )'''
        )
        cur.execute(
            f'''ALTER TABLE "{self.investigations_table}"
                ADD COLUMN IF NOT EXISTS report_profile jsonb'''
        )
        cur.execute(
            f'''CREATE TABLE IF NOT EXISTS "{self.jobs_table}" (
                job_id varchar PRIMARY KEY,
                investigation_id varchar UNIQUE NOT NULL
                    REFERENCES "{self.investigations_table}" (investigation_id),
                kind varchar NOT NULL,
                status varchar NOT NULL,
                cancel_requested boolean NOT NULL DEFAULT false,
                worker_id varchar,
                claim_token varchar,
                lease_expires_at timestamptz,
                error_json jsonb,
                created_at timestamptz NOT NULL DEFAULT now(),
                started_at timestamptz,
                updated_at timestamptz NOT NULL DEFAULT now(),
                finished_at timestamptz
            )'''
        )
        cur.execute(
            f'''CREATE TABLE IF NOT EXISTS "{self.steps_table}" (
                investigation_id varchar NOT NULL
                    REFERENCES "{self.investigations_table}" (investigation_id),
                step_id varchar NOT NULL,
                stage varchar NOT NULL,
                payload jsonb NOT NULL,
                correlation_id varchar NOT NULL,
                created_at timestamptz NOT NULL DEFAULT now(),
                PRIMARY KEY (investigation_id, step_id)
            )'''
        )
        cur.execute(
            f'''CREATE TABLE IF NOT EXISTS "{self.report_artifacts_table}" (
                artifact_id varchar PRIMARY KEY,
                investigation_id varchar UNIQUE NOT NULL
                    REFERENCES "{self.investigations_table}" (investigation_id),
                media_type varchar NOT NULL
                    CHECK (media_type = 'text/html; charset=utf-8'),
                html_bytes bytea NOT NULL,
                byte_length bigint NOT NULL
                    CHECK (byte_length = octet_length(html_bytes)
                           AND byte_length <= 1048576),
                content_hash varchar NOT NULL
                    CHECK (content_hash ~ '^sha256:[0-9a-f]{{64}}$'),
                source_report_hash varchar NOT NULL
                    CHECK (source_report_hash ~ '^sha256:[0-9a-f]{{64}}$'),
                draft_json jsonb NOT NULL,
                draft_hash varchar NOT NULL
                    CHECK (draft_hash ~ '^sha256:[0-9a-f]{{64}}$'),
                generation_mode varchar NOT NULL
                    CHECK (generation_mode IN ('llm_assisted', 'deterministic_fallback')),
                fallback_reason varchar
                    CHECK (fallback_reason IS NULL OR fallback_reason IN
                           ('llm_unavailable', 'llm_provider_error',
                            'invalid_draft', 'audit_rejected')),
                template_version varchar NOT NULL,
                output_schema_version varchar NOT NULL,
                provider varchar,
                model_id varchar,
                prompt_template_hash varchar,
                usage jsonb NOT NULL DEFAULT '{{}}'::jsonb,
                audit_summary jsonb NOT NULL,
                version_tuple jsonb NOT NULL,
                correlation_id varchar NOT NULL,
                created_at timestamptz NOT NULL DEFAULT now(),
                CHECK ((generation_mode = 'llm_assisted' AND fallback_reason IS NULL)
                       OR (generation_mode = 'deterministic_fallback'
                           AND fallback_reason IS NOT NULL))
            )'''
        )
        cur.execute(
            f'''CREATE INDEX IF NOT EXISTS
                "{self._prefix}_investigations_created_keyset_idx"
                ON "{self.investigations_table}"
                (created_at DESC, investigation_id DESC)'''
        )
        cur.execute(
            f'''CREATE INDEX IF NOT EXISTS
                "{self._prefix}_investigations_status_created_idx"
                ON "{self.investigations_table}" (status, created_at DESC)'''
        )
        from .investigation_report import default_report_profile

        cur.execute(
            f'''UPDATE "{self.investigations_table}" i
                SET report_profile = %s
                WHERE i.report_profile IS NULL
                  AND i.status IN ('queued', 'running')
                  AND EXISTS (
                      SELECT 1 FROM "{self.jobs_table}" j
                      WHERE j.investigation_id = i.investigation_id
                        AND j.status IN ('queued', 'running')
                  )''',
            (json.dumps(default_report_profile()),),
        )

    def create(
        self,
        *,
        question: str,
        subject_id: str | None,
        scope: dict,
        mode: str,
        idempotency_key: str,
        report_profile: dict,
        owner: str | None = None,
        version_tuple: dict | None = None,
    ) -> dict:
        """investigation/job을 원자 생성하거나 같은 idempotency 결과를 재반환한다."""
        if mode not in MODES:
            raise ValueError(f"지원하지 않는 mode: {mode}")
        if not idempotency_key:
            raise ValueError("Idempotency-Key가 필요합니다")
        if not question and not subject_id:
            raise ValueError("question 또는 subject_id가 필요합니다")
        if not isinstance(question, str):
            raise ValueError("question은 string이어야 합니다")
        if len(question.encode("utf-8")) > MAX_QUESTION_BYTES:
            raise ValueError("question은 UTF-8 32 KiB를 초과할 수 없습니다")
        if subject_id is not None and not isinstance(subject_id, str):
            raise ValueError("subject_id는 string이어야 합니다")
        if not isinstance(scope, dict):
            raise ValueError("scope는 object여야 합니다")
        scope_json = _canonical_json_bytes(scope)
        if len(scope_json) > MAX_SCOPE_BYTES:
            raise ValueError("scope는 UTF-8 64 KiB를 초과할 수 없습니다")
        if (
            not isinstance(report_profile, dict)
            or not REPORT_PROFILE_FIELDS.issubset(report_profile)
        ):
            raise ValueError("report_profile의 버전 pin이 필요합니다")

        self.ensure_tables()
        with self._conn.transaction():
            cur = self._conn.cursor()
            investigation_id = new_ulid("inv")
            job_id = new_ulid("job")
            correlation_id = new_ulid("corr")
            cur.execute(
                f'''INSERT INTO "{self.investigations_table}"
                    (investigation_id, idempotency_key, question, subject_id, scope, mode,
                     owner, version_tuple, correlation_id, status, report_profile)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'queued', %s)
                    ON CONFLICT (idempotency_key) DO NOTHING
                    RETURNING investigation_id''',
                (investigation_id, idempotency_key, question, subject_id,
                 scope_json.decode("utf-8"), mode, owner,
                 json.dumps(version_tuple or {}), correlation_id,
                 json.dumps(report_profile)),
            )
            inserted = cur.fetchone()
            if inserted is None:
                cur.execute(
                    f'''SELECT i.investigation_id, i.status, j.job_id, j.status, j.created_at
                        FROM "{self.investigations_table}" i
                        JOIN "{self.jobs_table}" j USING (investigation_id)
                        WHERE i.idempotency_key = %s''',
                    (idempotency_key,),
                )
                return self._creation_row(cur.fetchone())

            cur.execute(
                f'''INSERT INTO "{self.jobs_table}"
                    (job_id, investigation_id, kind, status)
                    VALUES (%s, %s, 'investigation', 'queued')
                    RETURNING created_at''',
                (job_id, investigation_id),
            )
            (created_at,) = cur.fetchone()
            return self._creation_row(
                (investigation_id, "queued", job_id, "queued", created_at)
            )

    @staticmethod
    def _creation_row(row) -> dict:
        investigation_id, _, job_id, status, created_at = row
        return {
            "investigation_id": investigation_id,
            "job": {
                "job_id": job_id,
                "status": status,
                "kind": "investigation",
                "poll_url": f"/api/jobs/{job_id}",
                "result_url": f"/api/investigations/{investigation_id}/report",
                "created_at": created_at,
            },
        }

    def counts(self) -> dict[str, int]:
        cur = self._conn.cursor()
        return {
            "investigations": self._count(cur, self.investigations_table),
            "jobs": self._count(cur, self.jobs_table),
            "steps": self._count(cur, self.steps_table),
        }

    @staticmethod
    def _count(cur, table: str) -> int:
        cur.execute(f'SELECT COUNT(*) FROM "{table}"')
        return cur.fetchone()[0]

    def claim_next(self, *, worker_id: str, lease_seconds: float = 60) -> dict | None:
        """queued 또는 lease가 만료된 running job 하나를 원자적으로 claim한다."""
        if lease_seconds <= 0:
            raise ValueError("lease_seconds는 0보다 커야 합니다")
        self.ensure_tables()
        with self._conn.transaction():
            cur = self._conn.cursor()
            cur.execute(
                f'''SELECT j.job_id, j.investigation_id, i.question, i.subject_id,
                           i.scope, i.mode, i.version_tuple, i.correlation_id,
                           i.report_profile
                    FROM "{self.jobs_table}" j
                    JOIN "{self.investigations_table}" i USING (investigation_id)
                    WHERE j.cancel_requested = false
                      AND (j.status = 'queued'
                           OR (j.status = 'running'
                               AND j.lease_expires_at <= now()))
                    ORDER BY j.created_at
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1'''
            )
            row = cur.fetchone()
            if row is None:
                return None

            (job_id, investigation_id, question, subject_id, scope, mode,
             version_tuple, correlation_id, report_profile) = row
            claim_token = new_ulid("claim")
            cur.execute(
                f'''UPDATE "{self.jobs_table}"
                    SET status = 'running', worker_id = %s, claim_token = %s,
                        lease_expires_at = now() + (%s * interval '1 second'),
                        started_at = COALESCE(started_at, now()), updated_at = now()
                    WHERE job_id = %s''',
                (worker_id, claim_token, lease_seconds, job_id),
            )
            cur.execute(
                f'''UPDATE "{self.investigations_table}"
                    SET status = 'running', updated_at = now()
                    WHERE investigation_id = %s AND status = 'queued' ''',
                (investigation_id,),
            )
            return {
                "job_id": job_id,
                "investigation_id": investigation_id,
                "question": question,
                "subject_id": subject_id,
                "scope": scope,
                "mode": mode,
                "version_tuple": version_tuple,
                "correlation_id": correlation_id,
                "report_profile": report_profile,
                "status": "running",
                "claim_token": claim_token,
            }

    def renew_lease(
        self,
        *,
        job_id: str,
        claim_token: str,
        lease_seconds: float,
    ) -> bool:
        """현재 claim의 lease를 연장한다. 소유권을 잃었으면 갱신하지 않는다."""
        if lease_seconds <= 0:
            raise ValueError("lease_seconds는 0보다 커야 합니다")
        cur = self._conn.cursor()
        cur.execute(
            f'''UPDATE "{self.jobs_table}"
                SET lease_expires_at = now() + (%s * interval '1 second'),
                    updated_at = now()
                WHERE job_id = %s AND claim_token = %s AND status = 'running' ''',
            (lease_seconds, job_id, claim_token),
        )
        return cur.rowcount == 1

    def record_step(
        self,
        investigation_id: str,
        *,
        step_id: str,
        stage: str,
        payload: dict,
        correlation_id: str,
    ) -> bool:
        """step을 append한다. 같은 investigation의 같은 step은 no-op이다."""
        cur = self._conn.cursor()
        cur.execute(
            f'''INSERT INTO "{self.steps_table}"
                (investigation_id, step_id, stage, payload, correlation_id)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (investigation_id, step_id) DO NOTHING''',
            (investigation_id, step_id, stage, json.dumps(payload), correlation_id),
        )
        return cur.rowcount == 1

    def complete_with_report_artifact(
        self,
        *,
        job_id: str,
        claim_token: str,
        report: dict,
        audit_trace: dict,
        coverage: dict,
        termination: str | None,
        artifact: dict,
    ) -> bool:
        """artifact·REPORT step·완료 상태를 현재 claim 아래에서 원자 확정한다."""
        required = {
            "html_bytes",
            "content_hash",
            "source_report_hash",
            "draft_json",
            "draft_hash",
            "generation_mode",
            "fallback_reason",
            "template_version",
            "output_schema_version",
            "provider",
            "model_id",
            "prompt_template_hash",
            "usage",
            "audit_summary",
        }
        missing = required.difference(artifact)
        if missing:
            raise ValueError(f"artifact 필드 누락: {', '.join(sorted(missing))}")
        html_bytes = artifact["html_bytes"]
        if not isinstance(html_bytes, bytes):
            raise TypeError("artifact html_bytes는 bytes여야 합니다")
        if len(html_bytes) > 1024 * 1024:
            raise ValueError("artifact HTML은 1 MiB를 초과할 수 없습니다")
        mode = artifact["generation_mode"]
        reason = artifact["fallback_reason"]
        if mode not in REPORT_GENERATION_MODES:
            raise ValueError(f"지원하지 않는 report generation_mode: {mode}")
        if reason not in REPORT_FALLBACK_REASONS | {None}:
            raise ValueError(f"지원하지 않는 fallback_reason: {reason}")
        if (mode == "llm_assisted") != (reason is None):
            raise ValueError("generation_mode과 fallback_reason이 일치하지 않습니다")
        draft_json = artifact["draft_json"]
        if not isinstance(draft_json, dict):
            raise ValueError("artifact draft_json은 object여야 합니다")
        expected_hashes = {
            "content_hash": _sha256(html_bytes),
            "source_report_hash": _sha256(_canonical_json_bytes({
                "report": report,
                "audit_trace": audit_trace,
            })),
            "draft_hash": _sha256(_canonical_json_bytes(draft_json)),
        }
        for field, expected in expected_hashes.items():
            if artifact[field] != expected:
                raise ValueError(f"artifact {field} 무결성 검증에 실패했습니다")


        try:
            with self._conn.transaction():
                cur = self._conn.cursor()
                cur.execute(
                    f'''SELECT j.investigation_id, i.version_tuple, i.correlation_id,
                               i.report_profile
                        FROM "{self.jobs_table}" j
                        JOIN "{self.investigations_table}" i USING (investigation_id)
                        WHERE j.job_id = %s AND j.status = 'running'
                          AND j.claim_token = %s AND j.cancel_requested = false
                          AND i.status = 'running'
                        FOR UPDATE OF j, i''',
                    (job_id, claim_token),
                )
                row = cur.fetchone()
                if row is None:
                    raise _CompletionRejected
                investigation_id, version_tuple, correlation_id, report_profile = row
                if not isinstance(report_profile, dict):
                    raise ValueError("active investigation report_profile이 없습니다")
                for field in (
                    "template_version",
                    "output_schema_version",
                    "prompt_template_hash",
                ):
                    if artifact[field] != report_profile.get(field):
                        raise ValueError(f"artifact {field} pin이 investigation과 다릅니다")
                cur.execute(
                    f'''INSERT INTO "{self.report_artifacts_table}"
                        (artifact_id, investigation_id, media_type, html_bytes,
                         byte_length, content_hash, source_report_hash, draft_json,
                         draft_hash, generation_mode, fallback_reason, template_version,
                         output_schema_version, provider, model_id, prompt_template_hash,
                         usage, audit_summary, version_tuple, correlation_id)
                        VALUES (%s, %s, 'text/html; charset=utf-8', %s, %s, %s, %s,
                                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
                    (
                        new_ulid("rpt"),
                        investigation_id,
                        html_bytes,
                        len(html_bytes),
                        artifact["content_hash"],
                        artifact["source_report_hash"],
                        json.dumps(draft_json),
                        artifact["draft_hash"],
                        mode,
                        reason,
                        artifact["template_version"],
                        artifact["output_schema_version"],
                        artifact["provider"],
                        artifact["model_id"],
                        artifact["prompt_template_hash"],
                        json.dumps(artifact["usage"]),
                        json.dumps(artifact["audit_summary"]),
                        json.dumps(version_tuple),
                        correlation_id,
                    ),
                )
                cur.execute(
                    f'''INSERT INTO "{self.steps_table}"
                        (investigation_id, step_id, stage, payload, correlation_id)
                        VALUES (%s, 'step-005', 'REPORT', %s, %s)''',
                    (
                        investigation_id,
                        json.dumps({
                            "generation_mode": mode,
                            "content_hash": artifact["content_hash"],
                            "source_report_hash": artifact["source_report_hash"],
                            "template_version": artifact["template_version"],
                        }),
                        correlation_id,
                    ),
                )
                cur.execute(
                    f'''UPDATE "{self.investigations_table}"
                        SET status = 'completed', coverage = %s, termination = %s,
                            report = %s, audit_trace = %s, updated_at = now(),
                            completed_at = now()
                        WHERE investigation_id = %s AND status = 'running' ''',
                    (
                        json.dumps(coverage),
                        termination,
                        json.dumps(report),
                        json.dumps(audit_trace),
                        investigation_id,
                    ),
                )
                if cur.rowcount != 1:
                    raise _CompletionRejected
                cur.execute(
                    f'''UPDATE "{self.jobs_table}"
                        SET status = 'succeeded', lease_expires_at = NULL,
                            updated_at = now(), finished_at = now()
                        WHERE job_id = %s AND status = 'running' AND claim_token = %s
                          AND cancel_requested = false''',
                    (job_id, claim_token),
                )
                if cur.rowcount != 1:
                    raise _CompletionRejected
        except _CompletionRejected:
            return False
        except Exception as exc:
            if getattr(exc, "sqlstate", None) == "23505":
                return False
            raise
        return True

    def fail(self, *, job_id: str, claim_token: str, error: dict) -> bool:
        """현재 claim의 실행 오류를 영속한다. 취소 요청은 failure로 덮지 않는다."""
        with self._conn.transaction():
            cur = self._conn.cursor()
            cur.execute(
                f'''UPDATE "{self.jobs_table}"
                    SET status = 'failed', lease_expires_at = NULL, error_json = %s,
                        updated_at = now(), finished_at = now()
                    WHERE job_id = %s AND status = 'running' AND claim_token = %s
                      AND cancel_requested = false
                    RETURNING investigation_id''',
                (json.dumps(error), job_id, claim_token),
            )
            row = cur.fetchone()
            if row is None:
                return False
            cur.execute(
                f'''UPDATE "{self.investigations_table}"
                    SET status = 'failed', updated_at = now(), completed_at = now()
                    WHERE investigation_id = %s AND status = 'running' ''',
                row,
            )
            return cur.rowcount == 1

    def cancel(self, investigation_id: str) -> dict | None:
        """취소를 멱등 처리한다. running job은 worker stage 경계에서 종료한다."""
        with self._conn.transaction():
            cur = self._conn.cursor()
            cur.execute(
                f'''SELECT i.status, j.job_id, j.status, j.cancel_requested
                    FROM "{self.investigations_table}" i
                    JOIN "{self.jobs_table}" j USING (investigation_id)
                    WHERE i.investigation_id = %s
                    FOR UPDATE OF i, j''',
                (investigation_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            investigation_status, job_id, job_status, cancel_requested = row
            if job_status == "queued":
                cur.execute(
                    f'''UPDATE "{self.jobs_table}"
                        SET status = 'cancelled', cancel_requested = true, updated_at = now(),
                            finished_at = now()
                        WHERE job_id = %s''',
                    (job_id,),
                )
                cur.execute(
                    f'''UPDATE "{self.investigations_table}"
                        SET status = 'cancelled', updated_at = now(), completed_at = now()
                        WHERE investigation_id = %s''',
                    (investigation_id,),
                )
                investigation_status, job_status = "cancelled", "cancelled"
                cancel_requested = True
            elif job_status == "running":
                cur.execute(
                    f'''UPDATE "{self.jobs_table}"
                        SET cancel_requested = true, updated_at = now()
                        WHERE job_id = %s''',
                    (job_id,),
                )
                cancel_requested = True
            return {
                "investigation_id": investigation_id,
                "status": investigation_status,
                "job": {
                    "job_id": job_id,
                    "status": job_status,
                    "cancel_requested": cancel_requested,
                },
            }

    def is_cancel_requested(self, job_id: str, claim_token: str) -> bool:
        cur = self._conn.cursor()
        cur.execute(
            f'''SELECT cancel_requested FROM "{self.jobs_table}"
                WHERE job_id = %s AND claim_token = %s''',
            (job_id, claim_token),
        )
        row = cur.fetchone()
        return bool(row and row[0])

    def mark_cancelled(self, *, job_id: str, claim_token: str) -> bool:
        """running worker가 관찰한 cancel request를 최종 cancelled 상태로 전이한다."""
        with self._conn.transaction():
            cur = self._conn.cursor()
            cur.execute(
                f'''UPDATE "{self.jobs_table}"
                    SET status = 'cancelled', lease_expires_at = NULL, updated_at = now(),
                        finished_at = now()
                    WHERE job_id = %s AND claim_token = %s AND status = 'running'
                      AND cancel_requested = true
                    RETURNING investigation_id''',
                (job_id, claim_token),
            )
            row = cur.fetchone()
            if row is None:
                return False
            cur.execute(
                f'''UPDATE "{self.investigations_table}"
                    SET status = 'cancelled', updated_at = now(), completed_at = now()
                    WHERE investigation_id = %s AND status = 'running' ''',
                row,
            )
            return cur.rowcount == 1

    def get_job(self, job_id: str) -> dict | None:
        cur = self._conn.cursor()
        cur.execute(
            f'''SELECT job_id, investigation_id, kind, status, cancel_requested, worker_id,
                       error_json, created_at, started_at, updated_at, finished_at
                FROM "{self.jobs_table}" WHERE job_id = %s''',
            (job_id,),
        )
        return self._as_dict(cur)

    def get_job_for_investigation(self, investigation_id: str) -> dict | None:
        cur = self._conn.cursor()
        cur.execute(
            f'''SELECT job_id, investigation_id, kind, status, cancel_requested, worker_id,
                       error_json, created_at, started_at, updated_at, finished_at
                FROM "{self.jobs_table}" WHERE investigation_id = %s''',
            (investigation_id,),
        )
        return self._as_dict(cur)

    def get_latest_step(self, investigation_id: str) -> dict | None:
        cur = self._conn.cursor()
        cur.execute(
            f'''SELECT step_id, stage, payload, correlation_id, created_at
                FROM "{self.steps_table}" WHERE investigation_id = %s
                ORDER BY created_at DESC, step_id DESC LIMIT 1''',
            (investigation_id,),
        )
        return self._as_dict(cur)

    def get_investigation(self, investigation_id: str) -> dict | None:
        cur = self._conn.cursor()
        cur.execute(
            f'''SELECT investigation_id, question, subject_id, scope, mode, owner,
                       version_tuple, correlation_id, report_profile, status, coverage,
                       termination, created_at, updated_at, completed_at
                FROM "{self.investigations_table}" WHERE investigation_id = %s''',
            (investigation_id,),
        )
        return self._as_dict(cur)

    def list_investigations(
        self,
        *,
        status: str | None = None,
        limit: int = 25,
        cursor: str | None = None,
    ) -> dict:
        """HTML 본문을 읽지 않는 newest-first keyset 목록을 반환한다."""
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit은 1 이상 100 이하 정수여야 합니다")
        grouped = {
            "active": ("queued", "running"),
            "unsuccessful": ("failed", "cancelled"),
        }
        if status is not None and status not in INVESTIGATION_STATUSES | grouped.keys():
            raise ValueError(f"지원하지 않는 status: {status}")

        conditions = []
        params: list = []
        if status in grouped:
            conditions.append("i.status = ANY(%s)")
            params.append(list(grouped[status]))
        elif status is not None:
            conditions.append("i.status = %s")
            params.append(status)
        if cursor is not None:
            created_at, investigation_id = self._decode_cursor(cursor)
            conditions.append("(i.created_at, i.investigation_id) < (%s, %s)")
            params.extend((created_at, investigation_id))
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit + 1)
        cur = self._conn.cursor()
        cur.execute(
            f'''SELECT i.investigation_id, i.question, i.subject_id, i.scope, i.mode,
                       i.owner, i.report_profile, i.status, i.coverage, i.termination,
                       i.created_at, i.updated_at, i.completed_at,
                       a.artifact_id,
                       a.generation_mode AS artifact_generation_mode,
                       a.fallback_reason, a.content_hash, a.source_report_hash,
                       a.template_version AS artifact_template_version,
                       a.output_schema_version, a.provider, a.model_id,
                       a.prompt_template_hash, a.byte_length, a.audit_summary,
                       a.created_at AS artifact_created_at
                FROM "{self.investigations_table}" i
                LEFT JOIN "{self.report_artifacts_table}" a USING (investigation_id)
                {where}
                ORDER BY i.created_at DESC, i.investigation_id DESC
                LIMIT %s''',
            params,
        )
        names = [column.name for column in cur.description]
        rows = [dict(zip(names, row)) for row in cur.fetchall()]
        has_more = len(rows) > limit
        rows = rows[:limit]
        items = [self._list_item(row) for row in rows]
        next_cursor = None
        if has_more:
            last = rows[-1]
            next_cursor = self._encode_cursor(
                last["created_at"], last["investigation_id"]
            )
        return {"items": items, "page": {"next_cursor": next_cursor, "limit": limit}}

    @staticmethod
    def _list_item(row: dict) -> dict:
        artifact_id = row.pop("artifact_id")
        if artifact_id is None:
            artifact = None
            if row["status"] == "completed":
                artifact_state = (
                    "legacy_json_only"
                    if row["report_profile"] is None
                    else "missing"
                )
            elif row["status"] in {"queued", "running"}:
                artifact_state = "pending"
            else:
                artifact_state = "unavailable"
        else:
            artifact_state = "ready"
            artifact = {
                "artifact_id": artifact_id,
                "generation_mode": row.pop("artifact_generation_mode"),
                "fallback_reason": row.pop("fallback_reason"),
                "content_hash": row.pop("content_hash"),
                "source_report_hash": row.pop("source_report_hash"),
                "template_version": row.pop("artifact_template_version"),
                "output_schema_version": row.pop("output_schema_version"),
                "provider": row.pop("provider"),
                "model_id": row.pop("model_id"),
                "prompt_template_hash": row.pop("prompt_template_hash"),
                "byte_length": row.pop("byte_length"),
                "audit_summary": row.pop("audit_summary"),
                "created_at": row.pop("artifact_created_at"),
                "html_url": (
                    f"/api/investigations/{row['investigation_id']}/report.html"
                ),
            }
        if artifact is None:
            for key in (
                "artifact_generation_mode",
                "fallback_reason",
                "content_hash",
                "source_report_hash",
                "artifact_template_version",
                "output_schema_version",
                "provider",
                "model_id",
                "prompt_template_hash",
                "byte_length",
                "audit_summary",
                "artifact_created_at",
            ):
                row.pop(key)
        row["artifact"] = artifact
        row["artifact_state"] = artifact_state
        row["json_url"] = f"/api/investigations/{row['investigation_id']}/report"
        return row

    @staticmethod
    def _encode_cursor(created_at: datetime, investigation_id: str) -> str:
        payload = json.dumps(
            {"created_at": created_at.isoformat(), "investigation_id": investigation_id},
            separators=(",", ":"),
        ).encode()
        return base64.urlsafe_b64encode(payload).decode().rstrip("=")

    @staticmethod
    def _decode_cursor(cursor: str) -> tuple[datetime, str]:
        try:
            encoded = cursor.encode("ascii")
            encoded += b"=" * (-len(encoded) % 4)
            payload = json.loads(
                base64.b64decode(encoded, altchars=b"-_", validate=True)
            )
            created_at = datetime.fromisoformat(payload["created_at"])
            investigation_id = payload["investigation_id"]
            if created_at.tzinfo is None or not isinstance(investigation_id, str):
                raise ValueError
            return created_at, investigation_id
        except (
            binascii.Error,
            UnicodeEncodeError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            raise ValueError("유효하지 않은 cursor입니다") from exc

    def get_report_artifact(
        self, investigation_id: str, *, include_html: bool = False
    ) -> dict | None:
        """artifact metadata를 반환하며 HTML은 명시적으로 요청할 때만 읽는다."""
        html_column = ", html_bytes" if include_html else ""
        cur = self._conn.cursor()
        cur.execute(
            f'''SELECT artifact_id, investigation_id, media_type, byte_length,
                       content_hash, source_report_hash, draft_json, draft_hash,
                       generation_mode, fallback_reason, template_version,
                       output_schema_version, provider, model_id, prompt_template_hash,
                       usage, audit_summary, version_tuple, correlation_id, created_at
                       {html_column}
                FROM "{self.report_artifacts_table}"
                WHERE investigation_id = %s''',
            (investigation_id,),
        )
        artifact = self._as_dict(cur)
        if artifact is not None and include_html:
            artifact["html_bytes"] = bytes(artifact["html_bytes"])
        return artifact

    def get_report(self, investigation_id: str) -> dict | None:
        cur = self._conn.cursor()
        cur.execute(
            f'''SELECT report, audit_trace FROM "{self.investigations_table}"
                WHERE investigation_id = %s AND status = 'completed' ''',
            (investigation_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {"report": row[0], "audit_trace": row[1]}

    @staticmethod
    def _as_dict(cur) -> dict | None:
        row = cur.fetchone()
        if row is None:
            return None
        return {column.name: value for column, value in zip(cur.description, row)}
