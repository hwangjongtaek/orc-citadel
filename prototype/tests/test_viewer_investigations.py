"""prototype durable investigation HTTP 계약."""
from __future__ import annotations

import hashlib
import http.client
import json
import threading
from http.server import ThreadingHTTPServer
from urllib.parse import urlencode

import pytest

psycopg = pytest.importorskip("psycopg")

from orc_citadel.investigation_report import (
    default_report_profile,
    style_csp_hash,
)
from orc_citadel.investigation_store import InvestigationStore
from orc_citadel.postgres_mutation_log import build_dsn
from orc_citadel.viewer import Handler

TEST_PREFIX = "investigation_api_test"


@pytest.fixture()
def server():
    conn = psycopg.connect(build_dsn())
    conn.autocommit = True
    cur = conn.cursor()
    for suffix in ("report_artifacts", "steps", "jobs", "investigations"):
        cur.execute(f'DROP TABLE IF EXISTS "{TEST_PREFIX}_{suffix}"')

    class TestHandler(Handler):
        investigation_table_prefix = TEST_PREFIX

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd.server_address
    finally:
        httpd.shutdown()
        thread.join()
        for suffix in ("report_artifacts", "steps", "jobs", "investigations"):
            cur.execute(f'DROP TABLE IF EXISTS "{TEST_PREFIX}_{suffix}"')
        conn.close()


def raw_request(address, method, path, body=None, headers=None):
    """HTTP response body를 JSON 변환 없이 exact bytes로 돌려준다."""
    conn = http.client.HTTPConnection(*address)
    conn.request(method, path, body=body, headers=headers or {})
    response = conn.getresponse()
    data = response.read()
    response_headers = dict(response.getheaders())
    conn.close()
    return response.status, response_headers, data


def request(address, method, path, body=None, headers=None):
    status, response_headers, data = raw_request(address, method, path, body, headers)
    return status, response_headers, json.loads(data)


def _store_connection():
    conn = psycopg.connect(build_dsn())
    conn.autocommit = True
    return conn, InvestigationStore(conn, table_prefix=TEST_PREFIX)


def _create_completed_artifact(*, key: str, html_bytes: bytes = b"<!doctype html><p>ok</p>"):
    conn, store = _store_connection()
    try:
        profile = default_report_profile()
        created = store.create(
            question=f"완료 조사 {key}",
            subject_id="org-test",
            scope={"as_of": "2026-09-20"},
            mode="deterministic",
            idempotency_key=key,
            report_profile=profile,
        )
        claimed = store.claim_next(worker_id="viewer-test")
        report = {"statements": [{"statement": "감사된 문장", "claim_ref": "clm-1"}]}
        audit_trace = {"linked": 1, "verifiable": 1, "trace": []}
        canonical = lambda value: json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        source_hash = "sha256:" + hashlib.sha256(canonical({
            "report": report,
            "audit_trace": audit_trace,
        })).hexdigest()
        draft = {
            "draft_schema_version": "1.0.0",
            "investigation_id": created["investigation_id"],
            "template_version": profile["template_version"],
            "source_report_hash": source_hash,
            "summary_statement_refs": [],
            "sections": [],
        }
        artifact = {
            "html_bytes": html_bytes,
            "content_hash": f"sha256:{hashlib.sha256(html_bytes).hexdigest()}",
            "source_report_hash": source_hash,
            "draft_json": draft,
            "draft_hash": "sha256:" + hashlib.sha256(canonical(draft)).hexdigest(),
            "generation_mode": "deterministic_fallback",
            "fallback_reason": "llm_unavailable",
            "template_version": profile["template_version"],
            "output_schema_version": profile["output_schema_version"],
            "provider": None,
            "model_id": None,
            "prompt_template_hash": profile["prompt_template_hash"],
            "usage": {},
            "audit_summary": {"linked": 1, "verifiable": 1, "blocked": 0},
        }
        assert store.complete_with_report_artifact(
            job_id=claimed["job_id"],
            claim_token=claimed["claim_token"],
            report=report,
            audit_trace=audit_trace,
            coverage={"ratio": 1.0},
            termination="coverage",
            artifact=artifact,
        )
        return created["investigation_id"], report, audit_trace, artifact
    finally:
        conn.close()


def _create_via_http(server, key: str):
    status, _, created = request(
        server,
        "POST",
        "/api/investigations",
        json.dumps({"question": f"조사 {key}"}),
        {"Content-Type": "application/json", "Idempotency-Key": key},
    )
    assert status == 202
    return created


def test_create_investigation_returns_202_location_and_idempotent_job(server):
    """POST는 즉시 queued job을 만들고 같은 키에는 같은 응답을 돌려준다."""
    payload = json.dumps({"question": "NVIDIA 신제품 발표를 조사", "mode": "deterministic"})
    headers = {"Content-Type": "application/json", "Idempotency-Key": "api-request-1"}

    status, response_headers, first = request(server, "POST", "/api/investigations", payload, headers)
    _, _, second = request(server, "POST", "/api/investigations", payload, headers)

    assert status == 202
    assert response_headers["Content-Type"] == "application/json; charset=utf-8"
    assert response_headers["Location"] == f"/api/jobs/{first['job']['job_id']}"
    assert response_headers["Retry-After"] == "1"
    assert second == first
    assert first["job"]["status"] == "queued"


def test_create_pins_default_report_profile(server):
    created = _create_via_http(server, "api-request-profile")

    status, _, investigation = request(
        server, "GET", f"/api/investigations/{created['investigation_id']}",
    )

    assert status == 200
    assert investigation["report_profile"] == default_report_profile()


def test_create_rejects_oversized_json_before_reading_body(server):
    status, _, body = request(
        server,
        "POST",
        "/api/investigations",
        "{}",
        {
            "Content-Type": "application/json",
            "Content-Length": str(1024 * 1024 + 1),
            "Idempotency-Key": "oversized-request",
        },
    )

    assert status == 413
    assert body["error"]["code"] == "request_too_large"


def test_investigation_and_job_status_are_polled_separately(server):
    """job 실행 수명과 investigation 진행 상태는 별도 GET으로 조회한다."""
    payload = json.dumps({"question": "NVIDIA 신제품 발표를 조사"})
    _, _, created = request(
        server, "POST", "/api/investigations", payload,
        {"Content-Type": "application/json", "Idempotency-Key": "api-request-status"},
    )
    investigation_id = created["investigation_id"]
    job_id = created["job"]["job_id"]

    job_status, _, job = request(server, "GET", f"/api/jobs/{job_id}")
    inv_status, _, investigation = request(server, "GET", f"/api/investigations/{investigation_id}")
    progress_status, _, progress = request(
        server, "GET", f"/api/investigations/{investigation_id}/status",
    )

    assert job_status == inv_status == progress_status == 200
    assert job["status"] == "queued"
    assert "T" in job["created_at"] and job["created_at"].endswith("+00:00")
    assert investigation["status"] == "queued"
    assert set(investigation["version_tuple"]) == {
        "ontology_version", "schema_version", "prompt_template_hash",
        "model_id", "extraction_code_version",
    }
    assert progress == {
        "investigation_id": investigation_id,
        "status": "queued",
        "current_step": None,
        "evidence_coverage": {},
    }


def test_cancel_endpoint_transitions_queued_investigation(server):
    """POST :cancel은 Idempotency-Key 없이 queued job을 멱등 취소한다."""
    created = _create_via_http(server, "api-request-cancel")

    status, _, cancelled = request(
        server, "POST", f"/api/investigations/{created['investigation_id']}:cancel",
        "{}", {"Content-Type": "application/json"},
    )

    assert status == 200
    assert cancelled["status"] == "cancelled"
    assert cancelled["job"]["status"] == "cancelled"


def test_list_paginates_without_html_and_retries_only_for_active_items(server):
    completed_id, _, _, _ = _create_completed_artifact(key="list-completed")
    queued = _create_via_http(server, "list-queued")

    status, headers, first_page = request(
        server, "GET", "/api/investigations?limit=1",
    )
    next_cursor = first_page["page"]["next_cursor"]
    second_status, second_headers, second_page = request(
        server,
        "GET",
        "/api/investigations?" + urlencode({"limit": 1, "cursor": next_cursor}),
    )
    completed_status, completed_headers, completed = request(
        server, "GET", "/api/investigations?status=completed",
    )

    assert status == second_status == completed_status == 200
    assert first_page["page"]["limit"] == second_page["page"]["limit"] == 1
    assert {first_page["items"][0]["investigation_id"], second_page["items"][0]["investigation_id"]} == {
        completed_id, queued["investigation_id"],
    }
    assert headers.get("Retry-After") == (
        "1" if first_page["items"][0]["status"] in {"queued", "running"} else None
    )
    assert second_headers.get("Retry-After") == (
        "1" if second_page["items"][0]["status"] in {"queued", "running"} else None
    )
    assert "Retry-After" not in completed_headers
    assert completed["items"][0]["artifact"]["html_url"].endswith("/report.html")
    assert "html_bytes" not in completed["items"][0]["artifact"]


def test_list_supports_exact_and_grouped_status_filters(server):
    queued = _create_via_http(server, "filter-queued")
    running = _create_via_http(server, "filter-running")
    failed = _create_via_http(server, "filter-failed")
    cancelled = _create_via_http(server, "filter-cancelled")
    conn, store = _store_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f'''UPDATE "{store.investigations_table}" SET status = 'running'
                WHERE investigation_id = %s''',
            (running["investigation_id"],),
        )
        cur.execute(
            f'''UPDATE "{store.investigations_table}" SET status = 'failed'
                WHERE investigation_id = %s''',
            (failed["investigation_id"],),
        )
        cur.execute(
            f'''UPDATE "{store.investigations_table}" SET status = 'cancelled'
                WHERE investigation_id = %s''',
            (cancelled["investigation_id"],),
        )
    finally:
        conn.close()

    _, active_headers, active = request(
        server, "GET", "/api/investigations?status=active",
    )
    _, unsuccessful_headers, unsuccessful = request(
        server, "GET", "/api/investigations?status=unsuccessful",
    )
    _, _, exact = request(server, "GET", "/api/investigations?status=queued")

    assert {item["investigation_id"] for item in active["items"]} == {
        queued["investigation_id"], running["investigation_id"],
    }
    assert {item["status"] for item in unsuccessful["items"]} == {"failed", "cancelled"}
    assert [item["investigation_id"] for item in exact["items"]] == [queued["investigation_id"]]
    assert active_headers["Retry-After"] == "1"
    assert "Retry-After" not in unsuccessful_headers


@pytest.mark.parametrize(
    "query",
    [
        "status=unknown",
        "status=queued&status=running",
        "limit=0",
        "limit=101",
        "limit=one",
        "cursor=",
        "unknown=value",
        "status",
    ],
)
def test_list_rejects_invalid_query_with_structured_400(server, query):
    status, _, body = request(server, "GET", f"/api/investigations?{query}")

    assert status == 400
    assert body["error"]["code"] == "invalid_investigation_query"
    assert isinstance(body["error"]["details"], dict)


def test_report_metadata_and_html_are_served_with_integrity_headers(server):
    html = "<!doctype html><html lang=\"ko\"><p>감사됨</p></html>".encode()
    investigation_id, _, _, artifact = _create_completed_artifact(
        key="artifact-success", html_bytes=html,
    )

    metadata_status, _, metadata = request(
        server, "GET", f"/api/investigations/{investigation_id}/report-artifact",
    )
    status, headers, body = raw_request(
        server, "GET", f"/api/investigations/{investigation_id}/report.html",
    )

    assert metadata_status == status == 200
    assert metadata["investigation_id"] == investigation_id
    assert metadata["content_hash"] == artifact["content_hash"]
    assert "html_bytes" not in metadata
    assert body == html
    assert headers["Content-Type"] == "text/html; charset=utf-8"
    assert headers["Content-Security-Policy"] == (
        "default-src 'none'; "
        f"style-src 'sha256-{style_csp_hash(artifact['template_version'])}'; "
        "img-src 'self' data:; base-uri 'none'; form-action 'none'; "
        "frame-ancestors 'self'"
    )
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert headers["ETag"] == f'"{artifact["content_hash"]}"'
    assert headers["Cache-Control"] == "private, no-cache"
    assert headers["Content-Disposition"] == (
        f'inline; filename="investigation-{investigation_id}.html"'
    )
    assert headers["Content-Length"] == str(len(html))

    not_modified, cached_headers, cached_body = raw_request(
        server,
        "GET",
        f"/api/investigations/{investigation_id}/report.html",
        headers={"If-None-Match": headers["ETag"]},
    )
    assert not_modified == 304
    assert cached_headers["ETag"] == headers["ETag"]
    assert cached_body == b""


def test_report_endpoints_distinguish_state_errors(server):
    queued = _create_via_http(server, "state-queued")
    legacy = _create_via_http(server, "state-legacy")
    missing = _create_via_http(server, "state-missing")
    conn, store = _store_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f'''UPDATE "{store.investigations_table}"
                SET status = 'completed', report_profile = NULL
                WHERE investigation_id = %s''',
            (legacy["investigation_id"],),
        )
        cur.execute(
            f'''UPDATE "{store.investigations_table}"
                SET status = 'completed'
                WHERE investigation_id = %s''',
            (missing["investigation_id"],),
        )
    finally:
        conn.close()

    cases = [
        ("inv-does-not-exist", "report-artifact", 404, "investigation_not_found"),
        (queued["investigation_id"], "report-artifact", 409, "investigation_not_completed"),
        (legacy["investigation_id"], "report.html", 404, "report_artifact_not_found"),
        (missing["investigation_id"], "report.html", 500, "report_artifact_missing"),
    ]
    for investigation_id, suffix, expected_status, code in cases:
        status, headers, body = request(
            server, "GET", f"/api/investigations/{investigation_id}/{suffix}",
        )
        assert status == expected_status
        assert body["error"]["code"] == code
        if investigation_id == queued["investigation_id"]:
            assert headers["Retry-After"] == "1"


def test_report_html_refuses_stored_bytes_with_wrong_hash(server):
    investigation_id, _, _, _ = _create_completed_artifact(key="artifact-corrupt")
    conn, store = _store_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f'''UPDATE "{store.report_artifacts_table}"
                SET html_bytes = repeat('x', byte_length::integer)::bytea
                WHERE investigation_id = %s''',
            (investigation_id,),
        )
    finally:
        conn.close()

    status, _, body = request(
        server, "GET", f"/api/investigations/{investigation_id}/report.html",
    )

    assert status == 500
    assert body["error"]["code"] == "report_artifact_integrity_error"


def test_json_report_endpoint_preserves_existing_envelope(server):
    investigation_id, report, audit_trace, _ = _create_completed_artifact(
        key="legacy-json-compatible",
    )

    status, headers, body = raw_request(
        server, "GET", f"/api/investigations/{investigation_id}/report",
    )

    assert status == 200
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    assert json.loads(body) == {"report": report, "audit_trace": audit_trace}


def test_get_returns_503_without_opening_duckdb_when_postgres_is_unavailable():
    """Durable API 장애는 fake facade로 후퇴하지 않고 구조화 503을 보낸다."""
    class UnavailableHandler(Handler):
        facade = None

        def _investigation_store(self):
            raise OSError("postgres unavailable")

        @classmethod
        def _ensure_facade(cls):
            raise AssertionError("durable route must not open DuckDB")

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), UnavailableHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, body = request(
            httpd.server_address, "GET", "/api/investigations?status=active",
        )
    finally:
        httpd.shutdown()
        thread.join()

    assert status == 503
    assert body["error"]["code"] == "investigation_store_unavailable"


def test_post_returns_503_without_creating_fake_job_when_postgres_is_unavailable():
    """PostgreSQL 장애는 성공처럼 보이지 않는 구조화 503이다."""
    class UnavailableHandler(Handler):
        def _investigation_store(self):
            raise OSError("postgres unavailable")

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), UnavailableHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, body = request(
            httpd.server_address, "POST", "/api/investigations",
            json.dumps({"question": "NVIDIA 신제품 발표를 조사"}),
            {"Content-Type": "application/json", "Idempotency-Key": "unavailable"},
        )
    finally:
        httpd.shutdown()
        thread.join()

    assert status == 503
    assert body["error"]["code"] == "investigation_store_unavailable"