"""TDD Red — Scout 커넥터 계약 (design 04 §1.2).

모의 응답으로 discover→fetch 계약, fetch 프레임워크 politeness(robots·rate limit),
idempotent 저장(raw_store 재사용)을 검증한다. 실네트워크 수집은 별도 단계.
"""
import io
from unittest import mock

import pytest

from orc_citadel.connectors.base import DiscoveredRef, FetchResult, SourceConnector
from orc_citadel.connectors.rss import RssConnector
from orc_citadel.connectors.arxiv import ArxivConnector
from orc_citadel.connectors.sec_edgar import SecEdgarConnector
from orc_citadel.fetch import FetchFramework
from orc_citadel.raw_store import RawStore


# ---- 1. SOURCE CONNECTOR 계약 (04 §1.2) ----

def test_connector_exposes_source_type():
    """각 커넥터는 source_type을 노출한다 (04 §1.2)."""
    assert RssConnector().source_type == "press"
    assert ArxivConnector().source_type == "research"
    assert SecEdgarConnector().source_type == "gov"


def test_rss_discover_yields_discovered_refs():
    """RSS discover는 DiscoveredRef(url, hint_modified)를 낸다."""
    feed_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel>
      <item><link>https://example.com/news/1</link><pubDate>Mon, 03 Aug 2026 10:00:00 GMT</pubDate></item>
      <item><link>https://example.com/news/2</link><pubDate>Tue, 04 Aug 2026 11:00:00 GMT</pubDate></item>
    </channel></rss>"""
    conn = RssConnector()
    with mock.patch.object(conn, "_http_get", return_value=feed_xml):
        refs = list(conn.discover("https://example.com/feed.xml", cursor=None))
    assert len(refs) == 2
    assert all(isinstance(r, DiscoveredRef) for r in refs)
    assert refs[0].url == "https://example.com/news/1"


def test_rss_fetch_returns_fetch_result():
    """RSS fetch는 FetchResult(content bytes, content_hash, http_status)를 낸다."""
    body = b"<html><body>chip news</body></html>"
    conn = RssConnector()
    with mock.patch.object(conn, "_http_get", return_value=body):
        res = conn.fetch(DiscoveredRef("https://example.com/news/1", None), prior_etag=None)
    assert isinstance(res, FetchResult)
    assert res.content == body
    assert res.content_hash.startswith("sha256:")
    assert res.http_status == 200


# ---- 2. 버전 대조: DiscoveredRef/FetchResult가 04 §1.2 필드 보유 ----

def test_discovered_ref_has_extra():
    """DiscoveredRef는 extra(ETag 등) 홀더를 가진다 (04 §1.2)."""
    r = DiscoveredRef("https://x", None, extra={"etag": "abc"})
    assert r.extra["etag"] == "abc"


def test_fetch_result_has_headers_and_fetched_at():
    """FetchResult는 response_headers/fetched_at 보유 (04 §1.2)."""
    r = FetchResult(url="u", content=b"x", content_hash="sha256:y",
                    http_status=200, response_headers={"content-type": "text/html"},
                    fetched_at=None)
    assert r.response_headers["content-type"] == "text/html"


# ---- 3. fetch 프레임워크 politeness (robots·rate limit, 04 §1.2) ----

def test_fetch_framework_checks_robots():
    """FetchFramework는 robots 미허용 URL을 거부한다 (politeness)."""
    fw = FetchFramework()
    with mock.patch.object(fw, "robots_allowed", return_value=False):
        with pytest.raises(RuntimeError):
            fw.fetch(DiscoveredRef("https://x/path", None))


def test_fetch_framework_rate_limits():
    """FetchFramework는 rate limit을 초과하면 throttle/거부한다 (politeness)."""
    fw = FetchFramework(rps=1)
    fw._tokens = 0  # 버킷 소진
    with mock.patch.object(fw, "robots_allowed", return_value=True):
        with pytest.raises(RuntimeError):
            fw.fetch(DiscoveredRef("https://x", None))


# ---- 4. idempotent 저장 (raw_store 재사용) ----

def test_save_is_idempotent_across_fetch():
    """같은 bytes 재저장 시 동일 doc_id, 중복 raw 없음 (03 §2.1, DoD ②)."""
    store = RawStore()
    d1 = store.put("src-01J9...", "https://x", b"same content")
    d2 = store.put("src-01J9...", "https://x", b"same content")
    assert d1 == d2
    assert len(store._raw) == 1
