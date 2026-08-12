"""S49+ — 수집 안정화: 페이지 지속 5xx가 전체 수집을 죽이지 않음 (resumable).

S48/S49 안정화 원칙(transient 재시도 + 429 경로 전환)을 이어, **배치 단위 멱등·계속**
을 검증한다. `collect_arxiv` 가 한 페이지의 지속 5xx(재시도 소진)를 `errors` 로 세고
다음 페이지를 계속 이어가 전체 100k 실행이 한 페이지에 죽지 않음을 보장한다.

오프라인 — 실제 HTTP 를 쓰지 않고 결정적 모의 connector 로 수집 계획·재시도·계속
순서만 검증.
"""
from __future__ import annotations

import pytest

import orc_citadel.collect_large as cl


class _FakeEntries(list):
    """discover_entries 가 반환할 (url, raw) 리스트."""


def _http_error(code):
    import urllib.error

    return urllib.error.HTTPError("http://x", code, "err", {}, None)


def _persistent_500(*_a, **_k):
    """retries 회를 모두 500으로 실패시켜 `_with_retry` 소진을 유도하는 페이지."""
    raise _http_error(500)


def test_collect_arxiv_skips_persistent_5xx_page(monkeypatch):
    """지속 5xx 페이지를 errors 로 세고, 나머지 페이지는 계속 수집 (resumable)."""
    calls = {"n": 0}

    class _Conn:
        def discover_entries(self, config, cursor):
            start = int(cursor or 0)
            calls["n"] += 1
            if start == 0:
                raise _http_error(500)  # 첫 페이지 8회 재시도 모두 실패 → 소진.
            return _FakeEntries([(f"https://arxiv.org/abs/{start}", f"<e>{start}</e>".encode())])

    monkeypatch.setattr(cl.time, "sleep", lambda _s: None)  # 백오프·politeness 무시.
    monkeypatch.setattr(cl, "ArxivConnector", _Conn)
    # 3 페이지 계획 (start=0/1/2, 각 1건) — 새 날짜 윈도우 경로(arxiv_windows) 로.
    monkeypatch.setattr(cl, "arxiv_windows", lambda total, windows=1, page=1000: [(0, 1), (1, 1), (2, 1)])

    counts = cl.collect_arxiv(3)
    # 첫 페이지는 항상 실패 — _with_retry 가 마지막 예외를 재전파, collect 가 errors 로 집계.
    assert counts["errors"] >= 1
    # 이후 페이지(1, 2) 는 시도되어 실행이 계속됨 — 실제 저장은 content-hash 멱등성으로
    # 이미 존재하면 skipped 로 집계되므로, '처리된 문서' = saved + skipped 로 검증.
    assert counts["saved"] + counts["skipped"] >= 2
    # 실제로 2번째/3번째 페이지를 시도했음 (첫 페이지 한 번에 죽지 않음).
    assert calls["n"] >= 3
