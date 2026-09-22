"""ADR-405 collectors publish reference events only after durable raw flush."""
from __future__ import annotations

import io
import json
import zipfile

import pytest

import orc_citadel.collect_large as cl
from orc_citadel.raw_shard import RawShardStore


class RecordingProducer:
    def __init__(self, raw_dir):
        self.raw_dir = raw_dir
        self.events = []

    def publish(self, envelope, *, route="primary"):
        doc_id = (envelope.output_ref or "").rsplit("/", 1)[-1]
        if envelope.event_type != "result_cap_reached":
            assert RawShardStore(self.raw_dir).get_content(doc_id) is not None
        self.events.append((route, envelope))


@pytest.fixture(autouse=True)
def isolated_raw(tmp_path, monkeypatch):
    raw_dir = tmp_path / "raw"
    monkeypatch.setattr(cl, "RAW", raw_dir)
    monkeypatch.setattr(cl, "_SHARD_STORES", {})
    return raw_dir


def _assert_document_boundaries(producer: RecordingProducer, source_id: str) -> None:
    assert [event.stage for _, event in producer.events] == ["S1", "S2"]
    assert [event.event_type for _, event in producer.events] == ["document_fetched", "raw_stored"]
    assert all(event.status == "succeeded" for _, event in producer.events)
    assert all(event.payload == {"source_id": source_id} for _, event in producer.events)
    assert producer.events[0][1].idempotency_key.startswith("fetch:")
    assert producer.events[0][1].idempotency_key != producer.events[1][1].idempotency_key
    assert producer.events[0][1].output_ref == producer.events[1][1].output_ref


def test_rss_publishes_s2_for_scheduled_collection(monkeypatch, isolated_raw) -> None:
    from orc_citadel.connectors.base import DiscoveredRef

    monkeypatch.setattr(
        cl.RssConnector, "discover",
        lambda self, _url, cursor=None: iter([DiscoveredRef(url="https://source/rss-a")]),
    )
    monkeypatch.setattr(cl, "_get", lambda _url: (
        b"rss document", {"Content-Type": "text/html", "ETag": '"v1"'}))
    producer = RecordingProducer(isolated_raw)

    result = cl.collect_rss(
        "https://source/feed", "rss-source", event_producer=producer,
    )

    assert result["saved"] == 1
    _assert_document_boundaries(producer, "rss-source")
    (record,) = RawShardStore(isolated_raw).fetch_records()
    assert record["response_headers"] == {
        "Content-Type": "text/html", "ETag": '"v1"',
    }
    assert record["fetch_correlation_id"] == producer.events[0][1].correlation_id


def test_known_url_still_recovers_pending_raw_events(monkeypatch, isolated_raw) -> None:
    store = RawShardStore(isolated_raw)
    doc_id, _ = store.append(
        "fixed-source", "https://source/already-raw", b"durable",
        {"fetched_at": "2026-09-22T00:00:00+00:00"},
    )
    store.flush()
    monkeypatch.setattr(
        cl, "_get",
        lambda _url: (_ for _ in ()).throw(AssertionError("known URL was fetched")),
    )
    producer = RecordingProducer(isolated_raw)

    result = cl.collect_urls(
        ["https://source/already-raw"], "fixed-source",
        known_urls={"https://source/already-raw"}, event_producer=producer,
    )

    assert result == {"saved": 0, "skipped": 1, "errors": 0}
    assert producer.events[-1][1].output_ref == f"raw://fixed-source/{doc_id}"
    _assert_document_boundaries(producer, "fixed-source")


def test_sitemap_and_urls_publish_s2(monkeypatch, isolated_raw) -> None:
    from orc_citadel.connectors.base import DiscoveredRef
    from orc_citadel.connectors.sitemap import SitemapConnector

    monkeypatch.setattr(
        SitemapConnector, "discover",
        lambda self, _url, cursor=None: iter([DiscoveredRef(url="https://source/map-a")]),
    )
    monkeypatch.setattr(cl, "_get", lambda url: (url.encode(), {"X-Origin": "actual"}))

    sitemap_producer = RecordingProducer(isolated_raw)
    assert cl.collect_sitemap(
        "https://source/sitemap.xml", "map-source",
        event_producer=sitemap_producer,
    )["saved"] == 1
    _assert_document_boundaries(sitemap_producer, "map-source")

    urls_producer = RecordingProducer(isolated_raw)
    assert cl.collect_urls(
        ["https://source/fixed"], "fixed-source", event_producer=urls_producer,
    )["saved"] == 1
    _assert_document_boundaries(urls_producer, "fixed-source")


def test_arxiv_and_sec_publish_s2(monkeypatch, isolated_raw) -> None:
    from orc_citadel.connectors.base import DiscoveredRef
    from orc_citadel.connectors.sec_edgar import SecEdgarConnector

    monkeypatch.setattr(
        cl.ArxivConnector, "discover_entries",
        lambda self, config, cursor: iter([
            ("https://arxiv.org/abs/1", b"<entry><id>1</id></entry>")]),
    )
    monkeypatch.setattr(cl, "_sleep_for_arxiv", lambda: None)
    arxiv_producer = RecordingProducer(isolated_raw)
    assert cl.collect_arxiv(1, event_producer=arxiv_producer)["saved"] == 1
    _assert_document_boundaries(arxiv_producer, "research-arxiv-cs-cr")

    monkeypatch.setattr(
        SecEdgarConnector, "discover",
        lambda self, config, cursor=None: iter([
            DiscoveredRef(url="https://sec.test/filing")]),
    )

    class Fetch:
        content = b"<html>filing</html>"
        http_status = 200
        response_headers = {"content-type": "text/html", "etag": "sec-v1"}

    monkeypatch.setattr(
        SecEdgarConnector, "fetch",
        lambda self, ref, prior_etag=None: Fetch(),
    )
    sec_producer = RecordingProducer(isolated_raw)
    assert cl.collect_sec(
        1, ciks=["1"], event_producer=sec_producer)["saved"] == 1
    _assert_document_boundaries(sec_producer, "gov-sec-edgar")


def test_index_stream_publishes_after_document_is_durable(monkeypatch, isolated_raw) -> None:
    responses = {
        "https://source/index.json": json.dumps({"items": [{"url": "https://source/a"}]}).encode(),
        "https://source/a": b"index document",
    }
    monkeypatch.setattr(cl, "_get", lambda url: (responses[url], {}))
    producer = RecordingProducer(isolated_raw)

    result = cl.collect_index_stream(
        {"url": "https://source/index.json", "format": "json", "records": "items",
         "url_field": "url"},
        "index-source", event_producer=producer,
    )

    assert result["saved"] == 1
    _assert_document_boundaries(producer, "index-source")


def test_bulk_archive_publishes_after_entry_is_durable(monkeypatch, isolated_raw) -> None:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("entry.json", b'{"archive": true}')
    def download(_url, output):
        output.write(archive.getvalue())
        return {}

    monkeypatch.setattr(cl, "_download_to_file", download)
    producer = RecordingProducer(isolated_raw)

    result = cl.collect_bulk_archive(
        "https://source/archive.zip", "archive-source", event_producer=producer,
    )

    assert result["saved"] == 1
    _assert_document_boundaries(producer, "archive-source")


def test_paged_api_publishes_after_record_is_durable(monkeypatch, isolated_raw) -> None:
    pages = iter([{"items": [{"id": "a"}]}, {"items": []}])
    monkeypatch.setattr(cl, "_get", lambda _url: (json.dumps(next(pages)).encode(), {}))
    producer = RecordingProducer(isolated_raw)

    result = cl.collect_paged_api(
        {"url": "https://source/api", "records": "items", "id_field": "id"},
        "api-source", event_producer=producer,
    )

    assert result["saved"] == 1
    _assert_document_boundaries(producer, "api-source")


def test_result_cap_publishes_terminal_context_after_flushing(monkeypatch, isolated_raw) -> None:
    pages = iter([{"items": [{"id": "a"}]}, {"items": [{"id": "b"}]}])
    monkeypatch.setattr(cl, "_get", lambda _url: (json.dumps(next(pages)).encode(), {}))
    producer = RecordingProducer(isolated_raw)

    with pytest.raises(cl.ResultCapReached):
        cl.collect_paged_api(
            {"url": "https://source/api", "records": "items", "id_field": "id",
             "offset_param": "offset", "page_size": 1, "max_offset": 2,
             "fetch_window": "2026-09"},
            "api-source", event_producer=producer,
        )

    terminal = producer.events[-1][1]
    assert terminal.stage == "S1"
    assert terminal.event_type == "result_cap_reached"
    assert terminal.status == "terminal"
    assert terminal.output_ref is None
    assert terminal.payload == {
        "source_id": "api-source", "window": "2026-09", "limit": 2, "offset": 2,
    }
