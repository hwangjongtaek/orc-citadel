"""등록 source 수집 지시 HTTP 계약."""
from __future__ import annotations

import http.client
import json
import threading

from http.server import ThreadingHTTPServer

from orc_citadel import viewer
from orc_citadel.viewer import Handler


def _request(address, method, path, body=None):
    conn = http.client.HTTPConnection(*address)
    conn.request(method, path, body=body, headers={"Content-Type": "application/json"})
    response = conn.getresponse()
    payload = json.loads(response.read())
    conn.close()
    return response.status, dict(response.getheaders()), payload


def test_collection_sources_and_trigger_are_allowlisted(monkeypatch):
    class FakeControl:
        def __init__(self, _):
            pass

        @staticmethod
        def sources():
            return [{"source_id": "official-nvidia-news", "kind": "rss"}]

        @staticmethod
        def status():
            return {"status": "idle"}

        @staticmethod
        def trigger(source_ids):
            if source_ids != ["official-nvidia-news"]:
                raise ValueError("등록된 source만 수집할 수 있습니다")
            return {"run_id": "collect-1", "status": "running", "source_ids": source_ids}

    monkeypatch.setattr(viewer, "CollectionControl", FakeControl)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, sources = _request(httpd.server_address, "GET", "/api/collections/sources")
        created_status, headers, created = _request(
            httpd.server_address, "POST", "/api/collections",
            json.dumps({"source_ids": ["official-nvidia-news"]}),
        )
    finally:
        httpd.shutdown()
        thread.join()

    assert status == 200 and sources["sources"] == [{"source_id": "official-nvidia-news", "kind": "rss"}]
    assert created_status == 202 and headers["Retry-After"] == "2"
    assert created["run_id"] == "collect-1"
