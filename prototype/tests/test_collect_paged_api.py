"""`paged_api` 커넥터 — 계약 TDD (04 §1.2 discover/fetch, 블로커 ④).

현재 kind 는 rss/sitemap/urls + arXiv 전용 경로뿐이다. 2026-09-20 도메인 조사에서
AI·경제·과학 3분야가 독립적으로 같은 결론에 도달했다 — **커서/오프셋 JSON API**
하나면 HF Hub·NVD·Federal Register·Europe PMC·ClinicalTrials.gov·Crossref·
OpenAlex·INSPIRE·World Bank 를 흡수한다.

계약:
- 커서형(token)·오프셋형 두 방식. 응답에서 레코드 목록을 꺼내 **레코드 1건 = 문서 1건**.
- 레코드 URL 은 provenance 축 — 응답의 URL 필드, 없으면 `{base}#{id}` 합성.
- 기수집 URL 은 건너뛴다 (S1 URL-skip, 04 §2.1).
- **결과 상한에 걸리면 조용히 끊지 않는다** — 기존 `_arxiv_date_windows` 가 10k 초과
  월을 말없이 누락하던 결함의 재발 방지 (2026-09-20 실물 확인).
"""
from __future__ import annotations

import json

import pytest

import orc_citadel.collect_large as cl
from orc_citadel.collect_large import collect_paged_api
from orc_citadel.raw_shard import RawShardStore


@pytest.fixture(autouse=True)
def _isolate_raw(tmp_path, monkeypatch):
    monkeypatch.setattr(cl, "RAW", tmp_path / "raw")
    monkeypatch.setattr(cl, "_SHARD_STORES", {})
    return tmp_path / "raw"


def _responder(pages: dict[str, dict]):
    """URL → JSON 응답 매핑을 `_get` 대역으로."""
    seen = []

    def _get(url):
        seen.append(url)
        if url not in pages:
            raise AssertionError(f"예상 밖 요청: {url}")
        return json.dumps(pages[url]).encode(), {"Content-Type": "application/json"}

    return _get, seen


def test_cursor_paging_follows_next_token(monkeypatch, _isolate_raw):
    """커서형 — 응답의 다음 토큰을 따라가며 레코드를 모은다."""
    pages = {
        "https://api/works?per_page=2": {
            "results": [{"id": "w1", "url": "https://w/1"}, {"id": "w2", "url": "https://w/2"}],
            "next": "c2"},
        "https://api/works?per_page=2&cursor=c2": {
            "results": [{"id": "w3", "url": "https://w/3"}], "next": None},
    }
    _get, seen = _responder(pages)
    monkeypatch.setattr(cl, "_get", _get)

    counts = collect_paged_api(
        {"url": "https://api/works?per_page=2", "records": "results",
         "cursor_param": "cursor", "next_field": "next", "url_field": "url"},
        "research-works")

    assert counts["saved"] == 3
    assert len(seen) == 2
    store = RawShardStore(_isolate_raw)
    assert {d["url"] for d in store.iter_docs()} == {"https://w/1", "https://w/2", "https://w/3"}


def test_offset_paging_stops_at_empty_page(monkeypatch, _isolate_raw):
    """오프셋형 — 빈 페이지에서 정지."""
    pages = {
        "https://api/items?limit=2&offset=0": {"data": [{"id": "a"}, {"id": "b"}]},
        "https://api/items?limit=2&offset=2": {"data": [{"id": "c"}]},
        "https://api/items?limit=2&offset=4": {"data": []},
    }
    _get, _seen = _responder(pages)
    monkeypatch.setattr(cl, "_get", _get)

    counts = collect_paged_api(
        {"url": "https://api/items", "records": "data", "offset_param": "offset",
         "limit_param": "limit", "page_size": 2, "id_field": "id"},
        "research-items")

    assert counts["saved"] == 3
    store = RawShardStore(_isolate_raw)
    assert {d["url"] for d in store.iter_docs()} == {
        "https://api/items#a", "https://api/items#b", "https://api/items#c"}


def test_known_urls_are_skipped(monkeypatch, _isolate_raw):
    """기수집 URL 은 재수집하지 않는다 (S1 idempotency)."""
    pages = {"https://api/works?per_page=2": {
        "results": [{"id": "w1", "url": "https://w/1"}, {"id": "w2", "url": "https://w/2"}],
        "next": None}}
    _get, _seen = _responder(pages)
    monkeypatch.setattr(cl, "_get", _get)

    counts = collect_paged_api(
        {"url": "https://api/works?per_page=2", "records": "results",
         "cursor_param": "cursor", "next_field": "next", "url_field": "url"},
        "research-works", known_urls={"https://w/1"})

    assert counts["saved"] == 1 and counts["skipped"] == 1


def test_offset_cap_raises_instead_of_truncating_silently(monkeypatch, _isolate_raw):
    """결과 상한에 닿으면 **예외**로 알린다 — 조용한 누락 금지.

    기존 arXiv 월 윈도우가 10k 초과 월을 말없이 버리던 결함과 같은 부류다.
    """
    pages = {
        "https://api/items?limit=2&offset=0": {"data": [{"id": "a"}, {"id": "b"}]},
        "https://api/items?limit=2&offset=2": {"data": [{"id": "c"}, {"id": "d"}]},
    }
    _get, _seen = _responder(pages)
    monkeypatch.setattr(cl, "_get", _get)

    with pytest.raises(cl.ResultCapReached) as err:
        collect_paged_api(
            {"url": "https://api/items", "records": "data", "offset_param": "offset",
             "limit_param": "limit", "page_size": 2, "id_field": "id", "max_offset": 4},
            "research-items")

    assert "max_offset" in str(err.value)


def test_nested_record_path_is_supported(monkeypatch, _isolate_raw):
    """레코드 목록이 중첩돼 있어도 꺼낸다 (`a.b` 표기)."""
    pages = {"https://api/x": {"payload": {"items": [{"id": "n1"}]}}}
    _get, _seen = _responder(pages)
    monkeypatch.setattr(cl, "_get", _get)

    counts = collect_paged_api(
        {"url": "https://api/x", "records": "payload.items", "id_field": "id"},
        "research-nested")

    assert counts["saved"] == 1
