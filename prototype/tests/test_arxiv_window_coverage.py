"""arXiv 윈도우 커버리지 결함 2건 — 계약 TDD (handoff §9 잔여 항목).

cutover handoff 가 "범위 밖" 으로 남겨둔 결함이다. 둘 다 **조용히** 문서를 잃는다:

① **상한이 하드코딩**돼 있었다 — `_arxiv_date_windows(start="202608112359")`. 윈도우는
   항상 2026-08 에서 과거로만 후진하므로 **그 이후 제출된 논문은 언제 실행해도
   도달하지 못한다.** 달력이 넘어갈수록 구멍이 커지는데 아무 신호가 없다.

② **월이 예산·10k 벽을 넘으면 말없이 다음 윈도우로 넘어갔다.** arXiv 는
   `start>~10k` 에서 500 을 준다(S50). 윈도우가 소진되지 않았는데도 실행은 정상
   종료로 끝나고, 그 달의 나머지가 몇 건인지 기록이 없다.

②의 계약은 이미 있다 — `result_cap_reached`(S1 terminal)가 `collect_paged_api`
에서 쓰이고 있다. 같은 계약을 arXiv 경로에 배선한다. 다만 **중단하지는 않는다**:
paged_api 는 커서가 하나라 상한에 걸리면 이어갈 수 없지만, arXiv 윈도우는 서로
독립이라 한 달이 잘렸다고 나머지 달을 버릴 이유가 없다.

오프라인 — 결정적 모의 connector 로 계획·이벤트만 검증한다.
"""
from __future__ import annotations

import datetime as dt

import pytest

import orc_citadel.collect_large as cl


class _Producer:
    def __init__(self):
        self.published = []

    def publish(self, envelope, route="primary"):
        self.published.append((envelope, route))


def _caps(producer):
    return [env for env, _ in producer.published
            if env.event_type == "result_cap_reached"]


# ---- ① 상한이 달력을 따라간다 ----

def test_windows_start_from_the_given_month(monkeypatch):
    wins = cl._arxiv_date_windows(2, today=dt.date(2027, 3, 15))

    assert wins[0][0].startswith("202703")
    assert wins[1][0].startswith("202702")


def test_windows_track_the_clock_instead_of_a_frozen_literal():
    """하드코딩 상한이면 달력이 넘어가도 같은 달만 본다 — 그 구멍이 결함이다."""
    first = cl._arxiv_date_windows(1)[0][0]

    assert first[:6] == dt.date.today().strftime("%Y%m")


def test_window_upper_bound_covers_the_month_it_starts_in():
    wins = cl._arxiv_date_windows(1, today=dt.date(2026, 9, 27))

    start, end = wins[0]
    assert start == "202609010000" and end == "202609302359"


# ---- ② 잘린 윈도우는 알린다 ----

def _full_page_connector(monkeypatch, *, exhaust_after: int | None = None):
    """항상 가득 찬 페이지를 주는 connector — 월이 소진되지 않는 형태."""
    calls = {"n": 0}

    class _Conn:
        def discover_entries(self, config, cursor):
            calls["n"] += 1
            if exhaust_after is not None and calls["n"] > exhaust_after:
                return []          # 소진 — _EmptyPage 경로
            start = int(cursor or 0)
            return [(f"https://arxiv.org/abs/{calls['n']}-{start}",
                     f"<e>{calls['n']}-{start}</e>".encode())]

    monkeypatch.setattr(cl.time, "sleep", lambda _s: None)
    monkeypatch.setattr(cl, "ArxivConnector", _Conn)
    return calls


def test_window_cut_short_by_its_budget_announces_the_gap(monkeypatch, tmp_path):
    """예산이 끝났는데 월은 안 끝났다 — 이게 조용히 넘어가던 지점이다."""
    monkeypatch.setattr(cl, "RAW", tmp_path / "raw")
    monkeypatch.setattr(cl, "_SHARD_STORES", {})
    _full_page_connector(monkeypatch)
    monkeypatch.setattr(cl, "arxiv_windows",
                        lambda total, windows=1, page=1000: [(0, 1)])
    producer = _Producer()

    cl.collect_arxiv(2, windows=2, event_producer=producer)

    caps = _caps(producer)
    assert caps, "잘린 윈도우가 아무 신호도 남기지 않았다"
    window = caps[0].payload["window"]
    assert "/" in window, f"어느 달이 잘렸는지 알 수 없다: {window}"
    assert caps[0].status == "terminal" and caps[0].stage == "S1"


def test_exhausted_window_announces_nothing(monkeypatch, tmp_path):
    """월이 실제로 소진되면 경보가 아니다 — 잡음을 만들면 신호가 죽는다."""
    monkeypatch.setattr(cl, "RAW", tmp_path / "raw")
    monkeypatch.setattr(cl, "_SHARD_STORES", {})
    _full_page_connector(monkeypatch, exhaust_after=1)
    monkeypatch.setattr(cl, "arxiv_windows",
                        lambda total, windows=1, page=1000: [(0, 1), (1, 1)])
    producer = _Producer()

    cl.collect_arxiv(50, windows=1, event_producer=producer)

    assert _caps(producer) == []


def test_a_truncated_window_does_not_abort_the_remaining_windows(monkeypatch, tmp_path):
    """paged_api 와 다른 점 — 윈도우는 독립이므로 한 달이 잘려도 계속한다."""
    monkeypatch.setattr(cl, "RAW", tmp_path / "raw")
    monkeypatch.setattr(cl, "_SHARD_STORES", {})
    _full_page_connector(monkeypatch)
    monkeypatch.setattr(cl, "arxiv_windows",
                        lambda total, windows=1, page=1000: [(0, 1)])
    producer = _Producer()

    counts = cl.collect_arxiv(3, windows=3, event_producer=producer)

    windows_seen = {env.payload["window"] for env in _caps(producer)}
    assert len(windows_seen) >= 2, "첫 윈도우가 잘리자 나머지를 버렸다"
    assert counts["saved"] + counts["skipped"] >= 2
