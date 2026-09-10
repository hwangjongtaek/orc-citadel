"""PostgreSQL-backed durable investigation/job 저장소.

그래프·curated zone을 변경하지 않는다. 이 모듈은 investigation 실행의 운영
메타데이터와 결과만 영속하며, queue claim은 PostgreSQL 트랜잭션으로 직렬화한다.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from .identity import new_ulid

JOB_STATUSES = {"queued", "running", "succeeded", "failed", "cancelled"}
INVESTIGATION_STATUSES = {"queued", "running", "completed", "failed", "cancelled"}
MODES = {"deterministic", "llm"}


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

    def create(
        self,
        *,
        question: str,
        subject_id: str | None,
        scope: dict,
        mode: str,
        idempotency_key: str,
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

        self.ensure_tables()
        with self._conn.transaction():
            cur = self._conn.cursor()
            investigation_id = new_ulid("inv")
            job_id = new_ulid("job")
            correlation_id = new_ulid("corr")
            cur.execute(
                f'''INSERT INTO "{self.investigations_table}"
                    (investigation_id, idempotency_key, question, subject_id, scope, mode,
                     owner, version_tuple, correlation_id, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'queued')
                    ON CONFLICT (idempotency_key) DO NOTHING
                    RETURNING investigation_id''',
                (investigation_id, idempotency_key, question, subject_id,
                 json.dumps(scope), mode, owner, json.dumps(version_tuple or {}), correlation_id),
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
                           i.scope, i.mode, i.version_tuple, i.correlation_id
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

            job_id, investigation_id, question, subject_id, scope, mode, version_tuple, correlation_id = row
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

    def complete(
        self,
        *,
        job_id: str,
        claim_token: str,
        report: dict,
        audit_trace: dict,
        coverage: dict,
        termination: str,
    ) -> bool:
        """현재 claim만 완료할 수 있다. 취소된 job은 결과를 기록하지 않는다."""
        with self._conn.transaction():
            cur = self._conn.cursor()
            cur.execute(
                f'''UPDATE "{self.jobs_table}"
                    SET status = 'succeeded', lease_expires_at = NULL, updated_at = now(),
                        finished_at = now()
                    WHERE job_id = %s AND status = 'running' AND claim_token = %s
                      AND cancel_requested = false
                    RETURNING investigation_id''',
                (job_id, claim_token),
            )
            row = cur.fetchone()
            if row is None:
                return False
            (investigation_id,) = row
            cur.execute(
                f'''UPDATE "{self.investigations_table}"
                    SET status = 'completed', coverage = %s, termination = %s,
                        report = %s, audit_trace = %s, updated_at = now(), completed_at = now()
                    WHERE investigation_id = %s AND status = 'running' ''',
                (json.dumps(coverage), termination, json.dumps(report),
                 json.dumps(audit_trace), investigation_id),
            )
            return cur.rowcount == 1

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
                       version_tuple, correlation_id, status, coverage, termination,
                       created_at, updated_at, completed_at
                FROM "{self.investigations_table}" WHERE investigation_id = %s''',
            (investigation_id,),
        )
        return self._as_dict(cur)

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
