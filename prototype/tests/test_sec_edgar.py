"""S14 SEC EDGAR 커넥터 (04 §1.3·§1.4 gov) — TDD.

선언형 User-Agent 강제 + CIK submissions filing index discover + fetch(idempotent).
실제 나가는 Request 헤더(UA)를 urllib.request.urlopen 패치로 캡처해 검증(403 방지).
robots_respect=True, ≤10 req/s(프레임워크), allow_redistribute=false.
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error

import pytest

from orc_citadel.connectors.base import DiscoveredRef
from orc_citadel.connectors.sec_edgar import (
    SEC_UA,
    SecEdgarConnector,
    submission_url_for,
)

NVDA_CIK = "1045810"


class _FakeResp:
    def __init__(self, body: bytes):
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _submissions_json(n_filings: int = 3) -> bytes:
    accs = [f"0001045810-26-00000{i}" for i in range(1, n_filings + 1)]
    return json.dumps({
        "cik": NVDA_CIK,
        "filings": {"recent": {
            "accessionNumber": accs,
            "primaryDocument": [f"d{i}.htm" for i in range(1, n_filings + 1)],
            "reportDate": ["2026-07-26", "2026-05-21", "2026-03-11"][:n_filings],
        }},
    }).encode()


class _Recorder:
    """urlopen 패치 — 요청(Request)의 실제 헤더를 캡처."""

    def __init__(self, body_map):
        self.captured = []  # (url, dict(headers))
        self.body_map = body_map

    def __call__(self, req, *a, **k):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        headers = dict(req.header_items())
        self.captured.append((url, headers))
        body = self.body_map(url)
        return _FakeResp(body)


def _conn_with(monkeypatch, body_map):
    rec = _Recorder(body_map)
    monkeypatch.setattr(urllib.request, "urlopen", rec)
    return SecEdgarConnector(), rec


def _header(headers: dict, name: str) -> str | None:
    """urllib는 헤더 키를 소문자로 변환 — 대소문자 무관 조회."""
    lower = name.lower()
    for k, v in headers.items():
        if k.lower() == lower:
            return v
    return None


def test_ua_constant_declared():
    """선언형 UA — Name + ContactEmail (04 §1.4 필수)."""
    parts = SEC_UA.split()
    assert len(parts) >= 2
    assert "@" in SEC_UA


def test_pad_cik():
    from orc_citadel.connectors.sec_edgar import pad_cik
    assert pad_cik("1045810") == "0001045810"  # 10자리 zero-pad (SEC 요구)


def test_submission_url():
    # 10자리 패딩 CIK로 요청 (SEC 요구 — 미패딩 시 404).
    assert submission_url_for(NVDA_CIK) == \
        "https://data.sec.gov/submissions/0001045810.json"


def test_http_get_sends_declared_ua(monkeypatch):
    """실제 나가는 Request에 선언 UA 포함 (403 방지)."""
    conn, rec = _conn_with(monkeypatch, lambda url: _submissions_json())
    list(conn.discover({"cik": [NVDA_CIK]}, cursor=None))
    assert rec.captured, "discover가 HTTP 요청을 보내야 함"
    url, headers = rec.captured[0]
    assert _header(headers, "User-Agent") == SEC_UA
    assert "data.sec.gov" in url


def test_discover_yields_filing_refs(monkeypatch):
    """submissions JSON → filing ref (URL + last_modified=reportDate)."""
    conn, rec = _conn_with(monkeypatch, lambda url: _submissions_json())
    refs = list(conn.discover({"cik": [NVDA_CIK]}, cursor=None))
    assert len(refs) == 3
    assert "sec.gov" in refs[0].url
    assert refs[0].hint_modified is not None


def test_fetch_returns_content(monkeypatch):
    """fetch → 내용 + content_hash (idempotent, 03 §2.1), UA 포함."""
    conn, rec = _conn_with(monkeypatch, lambda url: b"<html>10-Q</html>")
    ref = DiscoveredRef(url="https://www.sec.gov/Archives/x.dhtm")
    fr = conn.fetch(ref, prior_etag=None)
    assert b"10-Q" in fr.content
    assert fr.content_hash.startswith("sha256:")
    assert rec.captured and _header(rec.captured[0][1], "User-Agent") == SEC_UA


def test_unlisted_cik_no_refs(monkeypatch):
    """빈 submissions → discover 빈 결과 (안전)."""
    conn, rec = _conn_with(monkeypatch, lambda url: b"{}")
    refs = list(conn.discover({"cik": ["0"]}, cursor=None))
    assert refs == []
