"""Collector and raw-loader wiring for the MinIO shard backend."""
from __future__ import annotations

import pytest

from fake_minio import FakeMinio
from orc_citadel.collect_large import (
    ResultCapReached,
    _save_zone,
    collect_bulk_archive,
    collect_index_stream,
    collect_paged_api,
    collect_urls,
    flush_raw,
)
from orc_citadel.load_raw_zone import load_raw_zone_minio
from orc_citadel.minio_raw_store import MinioRawStore


@pytest.fixture()
def env():
    client = FakeMinio()
    return client, MinioRawStore(client, bucket="raw-wiring-test", shard_size=10)


def _names(client):
    return [o.object_name for o in client.list_objects("raw-wiring-test", recursive=True)]


def test_save_and_loader_see_buffered_minio_row(env):
    _client, store = env
    doc_id, created = _save_zone(
        "src-y", "https://e/y", b"<html>doc y</html>",
        {"http_status": 200}, minio_store=store,
    )

    loaded, meta = load_raw_zone_minio(store)

    assert created
    assert loaded.raw_bytes(doc_id) == b"<html>doc y</html>"
    assert meta == [{
        "source_id": "src-y",
        "url": "https://e/y",
        "doc_id": doc_id,
        "content": b"<html>doc y</html>",
    }]


def test_flush_raw_commits_injected_minio_store(env):
    client, store = env
    _save_zone("src-x", "https://e/a", b"payload", {}, minio_store=store)
    assert _names(client) == []

    flush_raw(minio_store=store)

    assert len(_names(client)) == 1
    assert _names(client)[0].endswith(".parquet")


def test_collect_urls_flushes_injected_minio_store_at_return(monkeypatch, env):
    client, store = env
    monkeypatch.setattr("orc_citadel.collect_large._get", lambda _url: (b"body", {}))

    result = collect_urls(["https://e/a"], "src-x", minio_store=store)

    assert result == {"saved": 1, "skipped": 0, "errors": 0}
    assert len(_names(client)) == 1


@pytest.mark.parametrize("collector,args", [
    (collect_index_stream, ({"url": "https://e/index", "format": "json"}, "src-x")),
    (collect_bulk_archive, ("https://e/archive.zip", "src-x")),
])
def test_early_error_return_flushes_injected_minio_store(monkeypatch, env, collector, args):
    client, store = env
    store.put("seed", "https://seed", b"pending")
    monkeypatch.setattr("orc_citadel.collect_large._get",
                        lambda _url: (_ for _ in ()).throw(OSError("offline")))
    monkeypatch.setattr(
        "orc_citadel.collect_large._download_to_file",
        lambda _url, _output: (_ for _ in ()).throw(OSError("offline")),
    )

    result = collector(*args, minio_store=store)

    assert result["errors"] == 1
    assert len(_names(client)) == 1


def test_result_cap_exception_flushes_injected_minio_store(monkeypatch, env):
    import json

    client, store = env
    pages = iter([
        {"results": [{"id": 1}]},
        {"results": [{"id": 2}]},
    ])
    monkeypatch.setattr(
        "orc_citadel.collect_large._get",
        lambda _url: (json.dumps(next(pages)).encode(), {}),
    )

    with pytest.raises(ResultCapReached):
        collect_paged_api(
            {"url": "https://e/api", "records": "results", "offset_param": "offset",
             "limit_param": "limit", "page_size": 1, "id_field": "id", "max_offset": 2},
            "src-x", minio_store=store,
        )

    assert len(_names(client)) == 1
