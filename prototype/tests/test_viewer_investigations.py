"""prototype durable investigation HTTP 계약."""
from __future__ import annotations

import http.client
import json
import threading
from contextlib import contextmanager
from http.server import ThreadingHTTPServer

import pytest

psycopg = pytest.importorskip("psycopg")

from orc_citadel.postgres_mutation_log import build_dsn
from orc_citadel.viewer import Handler

TEST_PREFIX = "investigation_api_test"


@pytest.fixture()
def server():
    conn = psycopg.connect(build_dsn())
    conn.autocommit = True
    cur = conn.cursor()
    for suffix in ("steps", "jobs", "investigations"):
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
        for suffix in ("steps", "jobs", "investigations"):
            cur.execute(f'DROP TABLE IF EXISTS "{TEST_PREFIX}_{suffix}"')
        conn.close()


def request(address, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection(*address)
    conn.request(method, path, body=body, headers=headers or {})
    response = conn.getresponse()
    data = response.read()
    headers = dict(response.getheaders())
    conn.close()
    return response.status, headers, json.loads(data)


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
    payload = json.dumps({"question": "NVIDIA 신제품 발표를 조사"})
    _, _, created = request(
        server, "POST", "/api/investigations", payload,
        {"Content-Type": "application/json", "Idempotency-Key": "api-request-cancel"},
    )

    status, _, cancelled = request(
        server, "POST", f"/api/investigations/{created['investigation_id']}:cancel",
        "{}", {"Content-Type": "application/json"},
    )

    assert status == 200
    assert cancelled["status"] == "cancelled"
    assert cancelled["job"]["status"] == "cancelled"


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