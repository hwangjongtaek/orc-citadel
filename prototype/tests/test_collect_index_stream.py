"""`index_stream` 커넥터 — 계약 TDD (04 §1.3, 블로커 ④).

EDGAR `master.idx`·govinfo 컬렉션 목록처럼 **URL 을 열거하는 인덱스**를 파싱해
대상 문서를 수집한다. `urls` kind 처럼 목록을 코드에 박을 수 없는 100만~1,000만
규모가 대상이다.

계약:
- 인덱스는 구분자 텍스트(`master.idx`) 또는 JSON 목록.
- 인덱스에서 뽑은 URL 이 곧 문서 URL — 기수집분은 건너뛴다 (S1 URL-skip).
- **같은 문서가 인덱스에 여러 번 실려도 한 번만 받는다** — EDGAR `master.idx` 는
  공동제출을 CIK 별로 중복 수록해 2025Q4 중복률 29.7%(2026-09-20 조사 실측)다.
- 문서 fetch 실패는 런 전체를 죽이지 않고 errors 로 집계한다.
"""
from __future__ import annotations

import json

import pytest

import orc_citadel.collect_large as cl
from orc_citadel.collect_large import collect_index_stream
from orc_citadel.raw_shard import RawShardStore

MASTER_IDX = b"""Description: Master Index
CIK|Company Name|Form Type|Date Filed|Filename
1045810|NVIDIA CORP|8-K|2026-08-01|edgar/data/1045810/0001.txt
2488|AMD INC|8-K|2026-08-02|edgar/data/2488/0002.txt
1045810|NVIDIA CORP|8-K|2026-08-01|edgar/data/1045810/0001.txt
"""


@pytest.fixture(autouse=True)
def _isolate_raw(tmp_path, monkeypatch):
    monkeypatch.setattr(cl, "RAW", tmp_path / "raw")
    monkeypatch.setattr(cl, "_SHARD_STORES", {})
    return tmp_path / "raw"


def _serve(monkeypatch, responses: dict[str, bytes], fail: set[str] = frozenset()):
    calls = []

    def _get(url):
        calls.append(url)
        if url in fail:
            raise RuntimeError(f"fetch 실패: {url}")
        return responses[url], {"Content-Type": "text/plain"}

    monkeypatch.setattr(cl, "_get", _get)
    return calls


def test_delimited_index_yields_documents(monkeypatch, _isolate_raw):
    calls = _serve(monkeypatch, {
        "https://sec/master.idx": MASTER_IDX,
        "https://sec/edgar/data/1045810/0001.txt": b"<8-K>NVDA</8-K>",
        "https://sec/edgar/data/2488/0002.txt": b"<8-K>AMD</8-K>",
    })

    counts = collect_index_stream(
        {"url": "https://sec/master.idx", "format": "delimited", "delimiter": "|",
         "field": 4, "base_url": "https://sec/", "skip_prefixes": ["Description:", "CIK|"]},
        "gov-sec-edgar")

    assert counts["saved"] == 2
    assert calls.count("https://sec/edgar/data/1045810/0001.txt") == 1, "중복 수록분을 두 번 받았다"
    store = RawShardStore(_isolate_raw)
    assert {d["url"] for d in store.iter_docs()} == {
        "https://sec/edgar/data/1045810/0001.txt", "https://sec/edgar/data/2488/0002.txt"}


def test_json_index_yields_documents(monkeypatch, _isolate_raw):
    payload = json.dumps({"packages": [{"link": "https://gov/a.xml"},
                                       {"link": "https://gov/b.xml"}]}).encode()
    _serve(monkeypatch, {"https://gov/index.json": payload,
                         "https://gov/a.xml": b"<a/>", "https://gov/b.xml": b"<b/>"})

    counts = collect_index_stream(
        {"url": "https://gov/index.json", "format": "json",
         "records": "packages", "url_field": "link"},
        "gov-bulk")

    assert counts["saved"] == 2


def test_known_urls_are_not_refetched(monkeypatch, _isolate_raw):
    calls = _serve(monkeypatch, {
        "https://sec/master.idx": MASTER_IDX,
        "https://sec/edgar/data/2488/0002.txt": b"<8-K>AMD</8-K>"})

    counts = collect_index_stream(
        {"url": "https://sec/master.idx", "format": "delimited", "delimiter": "|",
         "field": 4, "base_url": "https://sec/", "skip_prefixes": ["Description:", "CIK|"]},
        "gov-sec-edgar",
        known_urls={"https://sec/edgar/data/1045810/0001.txt"})

    assert counts["saved"] == 1 and counts["skipped"] == 1
    assert "https://sec/edgar/data/1045810/0001.txt" not in calls


def test_document_fetch_failure_is_counted_not_fatal(monkeypatch, _isolate_raw):
    _serve(monkeypatch, {
        "https://sec/master.idx": MASTER_IDX,
        "https://sec/edgar/data/2488/0002.txt": b"<8-K>AMD</8-K>"},
        fail={"https://sec/edgar/data/1045810/0001.txt"})

    counts = collect_index_stream(
        {"url": "https://sec/master.idx", "format": "delimited", "delimiter": "|",
         "field": 4, "base_url": "https://sec/", "skip_prefixes": ["Description:", "CIK|"]},
        "gov-sec-edgar")

    assert counts["saved"] == 1 and counts["errors"] == 1


def test_index_fetch_failure_reports_error(monkeypatch, _isolate_raw):
    _serve(monkeypatch, {}, fail={"https://sec/master.idx"})

    counts = collect_index_stream(
        {"url": "https://sec/master.idx", "format": "delimited", "delimiter": "|",
         "field": 4, "base_url": "https://sec/"},
        "gov-sec-edgar")

    assert counts == {"saved": 0, "skipped": 0, "errors": 1}
