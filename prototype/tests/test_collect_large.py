"""대형 수집 러너 — batch 계획·저장 멱등성 (resumable) TDD (04 §1.3/§1.4).

라이브 HTTP는 오프라인 테스트하지 않음 — 순수 계획(arxiv_batches)과 저장 멱등성
(_save_zone: content-hash 재개 무중복)만 검증한다. 진짜 대형 수집은 사용자 실행.
"""
from __future__ import annotations

import pathlib

import pytest

from orc_citadel.collect_large import _save_zone, arxiv_batches, SOURCES


def test_sources_registers_amd_official_rss():
    """실신호 확장 — AMD IR RSS(공식 2nd) 가 수집 소스로 등록 (design 04 §1.4 Phase 1+)."""
    assert "official-amd-ir" in SOURCES
    kind, url = SOURCES["official-amd-ir"]
    assert kind == "rss"
    assert url.startswith("https://ir.amd.com/")
    assert "rss" in url.lower()


def test_sources_registers_chips_nist_gov():
    """CHIPS/NIST gov RSS 가 수집 소스로 등록 (design 04 §1.4 초기 #3, gov-public)."""
    assert "gov-chips-nist" in SOURCES
    kind, url = SOURCES["gov-chips-nist"]
    assert kind == "rss"
    assert url.startswith("https://www.nist.gov/")
    assert "rss" in url.lower()


class _NoSleep:
    def sleep(self, _):
        return None


def test_arxiv_batches_full_pages():
    """total이 page 배수 → 균등 배치."""
    assert arxiv_batches(300, page=100) == [(0, 100), (100, 100), (200, 100)]


def test_arxiv_batches_partial_last():
    """마지막 페이지는 남은 만큼."""
    assert arxiv_batches(250, page=100) == [(0, 100), (100, 100), (200, 50)]


def test_arxiv_batches_smaller_than_page():
    assert arxiv_batches(10, page=100) == [(0, 10)]


def test_arxiv_batches_zero():
    assert arxiv_batches(0) == []


def test_save_zone_idempotent_resume(tmp_path):
    """동일 content 재저장 → created=False (재개 무중복, 03 §2.1)."""
    raw = tmp_path / "raw"
    doc_id, created = _save_zone("src-test", "http://x/1", b"hello", {}, raw_dir=raw)
    assert created is True
    assert doc_id.startswith("doc-")
    # 같은 bytes 다시 → 이미 존재 → 스킵.
    doc_id2, created2 = _save_zone("src-test", "http://x/1", b"hello", {}, raw_dir=raw)
    assert doc_id2 == doc_id
    assert created2 is False


def test_save_zone_diff_content_new_docid(tmp_path):
    """다른 content → 다른 doc_id, 새 저장."""
    raw = tmp_path / "raw"
    a, _ = _save_zone("s", "http://x/1", b"alpha", {}, raw_dir=raw)
    b, _ = _save_zone("s", "http://x/2", b"beta", {}, raw_dir=raw)
    assert a != b
    assert (raw / "s" / "doc" / a).exists()
    assert (raw / "s" / "doc" / b).exists()


def test_save_zone_writes_metadata(tmp_path):
    """content.bin + fetch.json 작성 (raw 3-zone 계약)."""
    raw = tmp_path / "raw"
    doc_id, _ = _save_zone("s", "http://x/1", b"data", {"http_status": 200}, raw_dir=raw)
    d = raw / "s" / "doc" / doc_id
    assert (d / "content.bin").read_bytes() == b"data"
    assert (d / "fetch.json").exists()


def _no_doc_get(url):
    raise AssertionError(f"metadata 경로는 문서당 GET이 없어야 한다: {url}")


def test_collect_arxiv_caps_at_limit(monkeypatch):
    """entries가 limit보다 많아도 total까지만 저장 + 문서당 HTTP GET 없음 (04 §1.4)."""
    import orc_citadel.collect_large as cl

    def fake_entries(self, config, cursor):
        for i in range(100):
            yield f"https://arxiv.org/abs/{i}", f"<entry><id>{i}</id></entry>".encode()

    monkeypatch.setattr(cl.ArxivConnector, "discover_entries", fake_entries)
    monkeypatch.setattr(cl, "_get", _no_doc_get)
    monkeypatch.setattr(cl, "_save_zone",
                        lambda *a, **k: (f"doc-{hash(a[1])%1000:03d}", True))
    monkeypatch.setattr(cl, "_sleep_for_arxiv", lambda: None)
    monkeypatch.setattr(cl, "time", _NoSleep())

    counts = cl.collect_arxiv(total=5)
    assert counts["saved"] == 5  # limit 5에서 정지 (100개 반환에도)
    assert counts["skipped"] == 0


def test_collect_sec_saves_gov(monkeypatch):
    """collect_sec → gov-source raw 저장 (content-hash 멱등성)."""
    import orc_citadel.collect_large as cl
    from orc_citadel.connectors.base import DiscoveredRef
    from orc_citadel.connectors.sec_edgar import SecEdgarConnector

    saved = {}

    def fake_discover(self, config, cursor):
        for i in range(2):
            yield DiscoveredRef(url=f"https://www.sec.gov/Archives/d{i}.htm")
        yield DiscoveredRef(url=f"https://www.sec.gov/Archives/d0.htm")  # 중복 예비

    class FakeFetchResult:
        http_status = 200
        response_headers = {"content-type": "application/octet-stream"}
        content = b"<html>10-Q</html>"

    monkeypatch.setattr(SecEdgarConnector, "discover", fake_discover)
    monkeypatch.setattr(SecEdgarConnector, "fetch",
                        lambda self, ref, prior_etag=None: FakeFetchResult())

    def fake_save(source_id, url, content, meta, raw_dir=None):
        if (source_id, url) in saved_keys:
            return f"doc-{hash(url)%1000:03d}", False
        saved_keys.add((source_id, url))
        saved[source_id] = saved.get(source_id, 0) + 1
        return f"doc-{hash(url)%1000:03d}", True

    saved_keys = set()
    monkeypatch.setattr(cl, "_save_zone", fake_save)
    counts = cl.collect_sec(limit=2, ciks=["1045810"])
    assert counts["saved"] == 2
    assert "gov-sec-edgar" in saved


# --- S48: 429/5xx transient 실패 재시도 (01 §4 retry 경로) ---

import urllib.error


def _http_error(code: int, hdrs: dict | None = None) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("http://x", code, "err", hdrs or {}, None)


def test_with_retry_429_then_success(monkeypatch):
    """429 두 번 후 성공 → 지수 backoff(30, 60) 후 값 반환."""
    import orc_citadel.collect_large as cl

    sleeps: list[float] = []
    monkeypatch.setattr(cl.time, "sleep", lambda s: sleeps.append(s))
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _http_error(429)
        return "ok"

    assert cl._with_retry(fn) == "ok"
    assert calls["n"] == 3
    assert sleeps == [30.0, 60.0]


def test_with_retry_honors_retry_after(monkeypatch):
    """Retry-After 헤더가 있으면 그 값(초)만큼 대기."""
    import orc_citadel.collect_large as cl

    sleeps: list[float] = []
    monkeypatch.setattr(cl.time, "sleep", lambda s: sleeps.append(s))
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] == 1:
            raise _http_error(429, {"Retry-After": "7"})
        return "ok"

    assert cl._with_retry(fn) == "ok"
    assert sleeps == [7.0]


def test_with_retry_non_retryable_raises(monkeypatch):
    """404는 transient가 아님 → 즉시 전파, 재시도 없음."""
    import orc_citadel.collect_large as cl

    monkeypatch.setattr(cl.time, "sleep", lambda s: (_ for _ in ()).throw(AssertionError("no sleep")))
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise _http_error(404)

    with pytest.raises(urllib.error.HTTPError):
        cl._with_retry(fn)
    assert calls["n"] == 1


def test_with_retry_exhausts_then_raises(monkeypatch):
    """계속 429 → retries 소진 후 전파."""
    import orc_citadel.collect_large as cl

    sleeps: list[float] = []
    monkeypatch.setattr(cl.time, "sleep", lambda s: sleeps.append(s))

    def fn():
        raise _http_error(429)

    with pytest.raises(urllib.error.HTTPError):
        cl._with_retry(fn, retries=3)
    assert len(sleeps) == 2  # 마지막 시도 후에는 대기 없이 전파


def test_collect_arxiv_retries_discover_429(monkeypatch):
    """페이지 API가 429로 죽지 않고 재시도 후 계속 (크래시 재현/방지)."""
    import orc_citadel.collect_large as cl

    calls = {"n": 0}

    def fake_entries(self, config, cursor):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _http_error(429)
        yield "https://arxiv.org/abs/1", b"<entry><id>1</id></entry>"

    monkeypatch.setattr(cl.ArxivConnector, "discover_entries", fake_entries)
    monkeypatch.setattr(cl, "_save_zone", lambda *a, **k: ("doc-1", True))
    monkeypatch.setattr(cl, "_sleep_for_arxiv", lambda: None)
    monkeypatch.setattr(cl.time, "sleep", lambda s: None)

    counts = cl.collect_arxiv(total=1)
    assert counts["saved"] == 1
    assert calls["n"] == 2


def test_collect_arxiv_empty_page_retries_then_stops(monkeypatch):
    """빈 페이지는 transient로 재시도하되, 계속 비면 결과 소진으로 보고 정상 종료."""
    import orc_citadel.collect_large as cl

    calls = {"n": 0}

    def fake_entries(self, config, cursor):
        calls["n"] += 1
        return iter(())  # 항상 빈 페이지

    monkeypatch.setattr(cl.ArxivConnector, "discover_entries", fake_entries)
    monkeypatch.setattr(cl, "_sleep_for_arxiv", lambda: None)
    monkeypatch.setattr(cl.time, "sleep", lambda s: None)

    counts = cl.collect_arxiv(total=200)  # 2 페이지 계획이지만 첫 페이지에서 소진
    assert counts == {"saved": 0, "skipped": 0, "errors": 0}
    assert calls["n"] >= 2  # 빈 페이지를 최소 한 번은 재시도했다


def test_with_retry_timeout_then_success(monkeypatch):
    """SSL/socket read timeout은 transient → backoff 후 재시도 (크래시 재현/방지)."""
    import orc_citadel.collect_large as cl

    sleeps: list[float] = []
    monkeypatch.setattr(cl.time, "sleep", lambda s: sleeps.append(s))
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("The read operation timed out")
        return "ok"

    assert cl._with_retry(fn) == "ok"
    assert sleeps == [30.0]


def test_with_retry_urlerror_then_success(monkeypatch):
    """URLError(DNS·연결 거부 등)도 transient → 재시도."""
    import orc_citadel.collect_large as cl

    sleeps: list[float] = []
    monkeypatch.setattr(cl.time, "sleep", lambda s: sleeps.append(s))
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.URLError("conn refused")
        return "ok"

    assert cl._with_retry(fn) == "ok"
    assert calls["n"] == 2


def test_with_retry_network_error_exhausts(monkeypatch):
    """네트워크 예외도 retries 소진 시 전파 (영구 장애는 숨기지 않음)."""
    import orc_citadel.collect_large as cl

    monkeypatch.setattr(cl.time, "sleep", lambda s: None)

    def fn():
        raise TimeoutError("timeout")

    with pytest.raises(TimeoutError):
        cl._with_retry(fn, retries=3)


def test_collect_arxiv_uses_page_size_in_config(monkeypatch):
    """collect_arxiv는 배치 크기(mx)를 max_results로 커넥터에 전달한다."""
    import orc_citadel.collect_large as cl

    seen: list[dict] = []

    def fake_entries(self, config, cursor):
        seen.append(dict(config))
        for i in range(int(config["max_results"])):
            yield f"https://arxiv.org/abs/{cursor}-{i}", b"<entry><id>x</id></entry>"

    monkeypatch.setattr(cl.ArxivConnector, "discover_entries", fake_entries)
    monkeypatch.setattr(cl, "_save_zone", lambda *a, **k: ("doc-x", True))
    monkeypatch.setattr(cl, "_sleep_for_arxiv", lambda: None)
    monkeypatch.setattr(cl.time, "sleep", lambda s: None)

    counts = cl.collect_arxiv(total=cl.ARXIV_PAGE + 5)  # 2 페이지: full + partial
    assert counts["saved"] == cl.ARXIV_PAGE + 5
    assert seen[0]["max_results"] == cl.ARXIV_PAGE
    assert seen[1]["max_results"] == 5




# --- arXiv 날짜 회전 쿼리 계획 (10k 페이징 한계 우회, S50) ---------------------

def test_arxiv_windows_partitions_total():
    """날짜 윈도우 별 쿼리 계획 — 각 윈도우가 max_results 한도 내(start<10k)로 쪼갠다.

    단일 arXiv 쿼리는 start>~10k 에서 500 → 날짜 윈도우로 나눠 각각 <10k 페이징.
    순수 함수: (total, per_window_queries) 계획.
    """
    from orc_citadel.collect_large import arxiv_windows

    # 3 윈도우 * 각 2페이지 = 6 페이지 (total=6, windows=3, page=1 → 각 윈도우 2건).
    wins = arxiv_windows(total=6, windows=3, page=1)
    assert len(wins) == 6
    # 각 배치가 (start, max_results) — start 는 항상 < 10k (페이징 한계 준수).
    for start, mx in wins:
        assert start < 10_000
    # 각 윈도우는 page=1 → start 는 0/1 두 번씩 (같은 start 가 다른 윈도우에 재사용).
    assert wins.count((0, 1)) == 3  # 3 윈도우 각각의 첫 페이지.


def test_arxiv_windows_respect_page_cap_per_window():
    """각 윈도우는 독립 쿼리 — 윈도우 내 페이지만 start 를 올린다."""
    from orc_citadel.collect_large import arxiv_windows

    # windows=2, page=100 → 각 윈도우는 start 0 하나씩 (작은 total).
    wins = arxiv_windows(total=10, windows=2, page=100)
    assert len(wins) == 2
    assert all(start == 0 for start, _ in wins)
    assert wins[0][1] == 5 and wins[1][1] == 5  # total 을 절반씩 배분.


def test_arxiv_date_windows_returns_months_recent_first():
    """날짜 윈도우 — 최신 월부터 내림차순, 각 (start_ym, end_ym) 月 경계."""
    from orc_citadel.collect_large import _arxiv_date_windows

    wins = _arxiv_date_windows(3)
    assert len(wins) == 3
    # 최신 달부터 — 각 start < end, 월 경계.
    for i in range(1, len(wins)):
        assert wins[i - 1][0] > wins[i][0]  # 내림차순
    # 형식: YYYYMMDDHHMM
    import re as _re
    for s, e in wins:
        assert _re.fullmatch(r"\d{12}", s) and _re.fullmatch(r"\d{12}", e)
        assert s < e


# --- Phase 6: SLO-05 관측 로그 배선 (design 11 §2.3, slo_observation_log) ---


def test_collect_arxiv_feeds_slo05_log(monkeypatch):
    """collect_arxiv → SLO-05 시도/성공 로그 기록 (문서별 저장 성공)."""
    import orc_citadel.collect_large as cl
    from orc_citadel.slo_observation_log import SloObservationLog

    def fake_entries(self, config, cursor):
        for i in range(3):
            yield f"https://arxiv.org/abs/{i}", f"<entry><id>{i}</id></entry>".encode()

    monkeypatch.setattr(cl.ArxivConnector, "discover_entries", fake_entries)
    monkeypatch.setattr(cl, "_get", _no_doc_get)
    monkeypatch.setattr(cl, "_save_zone", lambda *a, **k: ("doc-x", True))
    monkeypatch.setattr(cl, "_sleep_for_arxiv", lambda: None)
    monkeypatch.setattr(cl, "time", _NoSleep())

    log = SloObservationLog()
    counts = cl.collect_arxiv(total=3, slo_log=log)
    assert counts["saved"] == 3
    # SLO-05 — 3건 성공 시도 기록 → 하니스 성공률 1.0 measured.
    from orc_citadel.slo_metrics_harness import collect_success_rate
    res = collect_success_rate(log.success_results())
    assert res["measured"] is True
    assert res["n_attempt"] == 3 and res["success_rate"] == 1.0


def test_collect_rss_feeds_slo05_success_and_failure(monkeypatch):
    """collect_rss → 성공·실패 모두 SLO-05 로그 (ok True/False 구분)."""
    import orc_citadel.collect_large as cl
    from orc_citadel.connectors.base import DiscoveredRef
    from orc_citadel.slo_observation_log import SloObservationLog
    from orc_citadel.slo_metrics_harness import collect_success_rate

    def fake_discover(self, feed_url, cursor):
        yield DiscoveredRef(url="https://ok.example/1")
        yield DiscoveredRef(url="https://fail.example/2")

    originals = {}
    def fake_get(url):
        if url.startswith("https://fail"):
            raise RuntimeError("boom")
        return b"<rss/>", {"Content-Type": "application/rss+xml"}

    monkeypatch.setattr(cl.RssConnector, "discover", fake_discover)
    monkeypatch.setattr(cl, "_get", fake_get)
    monkeypatch.setattr(cl, "_save_zone", lambda *a, **k: ("doc-x", True))

    log = SloObservationLog()
    counts = cl.collect_rss("http://feed", "src-x", slo_log=log)
    assert counts["saved"] == 1 and counts["errors"] == 1
    res = collect_success_rate(log.success_results())
    assert res["n_attempt"] == 2 and res["success_rate"] == 0.5


def test_collect_sec_feeds_slo05_log(monkeypatch):
    """collect_sec → SLO-05 시도/성공 로그 기록."""
    import orc_citadel.collect_large as cl
    from orc_citadel.connectors.base import DiscoveredRef
    from orc_citadel.connectors.sec_edgar import SecEdgarConnector
    from orc_citadel.slo_observation_log import SloObservationLog
    from orc_citadel.slo_metrics_harness import collect_success_rate

    def fake_discover(self, config, cursor):
        yield DiscoveredRef(url="https://www.sec.gov/Archives/d1.htm")

    class FakeFetchResult:
        http_status = 200
        response_headers = {"content-type": "application/octet-stream"}
        content = b"<html>10-Q</html>"

    monkeypatch.setattr(SecEdgarConnector, "discover", fake_discover)
    monkeypatch.setattr(SecEdgarConnector, "fetch",
                        lambda self, ref, prior_etag=None: FakeFetchResult())
    monkeypatch.setattr(cl, "_save_zone", lambda *a, **k: ("doc-x", True))

    log = SloObservationLog()
    cl.collect_sec(limit=1, ciks=["1045810"], slo_log=log)
    res = collect_success_rate(log.success_results())
    assert res["measured"] is True and res["n_attempt"] == 1


def test_collectors_work_without_slo_log():
    """slo_log 기본 None — 기존 동작 무변경 (선택 주입, Spec 1.0.0)."""
    import orc_citadel.collect_large as cl
    # 시그니처가 선택 인자로 None 기본을 가지는지 확인.
    import inspect
    assert inspect.signature(cl.collect_arxiv).parameters["slo_log"].default is None
    assert inspect.signature(cl.collect_rss).parameters["slo_log"].default is None
    assert inspect.signature(cl.collect_sec).parameters["slo_log"].default is None
