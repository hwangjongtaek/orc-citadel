"""MinIO raw storage uses immutable source-sharded Parquet objects."""
from __future__ import annotations

import hashlib
import re

import duckdb
import pytest

from fake_minio import FakeMinio
from orc_citadel.minio_raw_store import MinioRawStore


@pytest.fixture()
def client():
    return FakeMinio()


@pytest.fixture()
def store(client):
    return MinioRawStore(client, bucket="raw-test", shard_size=10)


def test_buffered_put_is_visible_before_flush(store):
    content = b"original bytes\x00\xff"
    doc_id = store.put(
        "src-test", "https://example.com/a", content,
        {"http_status": 200, "license": "public", "custom": "value"},
    )

    assert store.has(doc_id)
    assert store.get_raw(doc_id) == content
    assert store.count_docs() == 1
    assert store.fetch_meta(doc_id) == {
        "doc_id": doc_id,
        "source_id": "src-test",
        "url": "https://example.com/a",
        "fetched_at": store.fetch_meta(doc_id)["fetched_at"],
        "http_status": 200,
        "robots_allowed": True,
        "license": "public",
        "content_hash": "sha256:" + hashlib.sha256(content).hexdigest(),
        "custom": "value",
    }


def test_filesystem_and_minio_preserve_identical_fetch_metadata(client, tmp_path):
    from orc_citadel.raw_shard import RawShardStore

    content = b"response body"
    meta = {
        "response_headers": {"Content-Type": "text/html", "ETag": '"abc"'},
        "fetch_correlation_id": "corr-deterministic",
    }
    filesystem = RawShardStore(tmp_path / "raw")
    doc_id, _ = filesystem.append("src-test", "https://example.com/a", content, meta)
    filesystem.flush()
    minio = MinioRawStore(client, bucket="raw-test")
    minio.put("src-test", "https://example.com/a", content, meta)
    minio.flush()

    local_meta = filesystem.fetch_records()[0]
    remote_meta = minio.fetch_meta(doc_id)
    for field in ("content_hash", "response_headers", "fetch_correlation_id"):
        assert local_meta[field] == remote_meta[field]


def test_twenty_five_docs_make_three_zstd_parquet_shards_without_legacy_objects(
    store, client, tmp_path,
):
    expected = {}
    for i in range(25):
        content = f"bytes-{i}".encode()
        doc_id = store.put("src-a", f"https://example.com/{i}", content,
                           {"http_status": 200, "ordinal": i})
        expected[doc_id] = (content, i)
    duplicate = store.put("src-a", "https://duplicate", b"bytes-7", {"ordinal": 999})

    assert store.count_docs() == 25
    assert store.get_raw(duplicate) == b"bytes-7"
    store.flush()

    names = sorted(o.object_name for o in client.list_objects("raw-test", recursive=True))
    assert len(names) == 3
    assert all(re.fullmatch(r"raw/src-a/shard-\d{8}T\d{12}-[A-Za-z0-9]+\.parquet", n)
               for n in names)
    assert not any(n.endswith(("content.bin", "fetch.json")) for n in names)

    for doc_id, (content, ordinal) in expected.items():
        assert store.get_raw(doc_id) == content
        assert store.fetch_meta(doc_id)["ordinal"] == ordinal

    path = tmp_path / "shard.parquet"
    path.write_bytes(client.buckets["raw-test"][names[0]])
    compression = duckdb.connect().execute(
        "SELECT DISTINCT compression FROM parquet_metadata(?)", [str(path)]
    ).fetchall()
    assert compression == [("ZSTD",)]


def test_same_bytes_are_preserved_once_per_source(client):
    first = MinioRawStore(client, bucket="raw-test", shard_size=10)
    doc_id = first.put("src-a", "https://example.com/a", b"same")
    first.flush()

    reopened = MinioRawStore(client, bucket="raw-test", shard_size=10)
    assert reopened.put("src-b", "https://example.com/b", b"same") == doc_id
    reopened.flush()

    assert reopened.count_docs() == 2
    assert len(list(client.list_objects("raw-test", recursive=True))) == 2
    assert reopened.fetch_meta(doc_id, source_id="src-a")["url"] == "https://example.com/a"
    assert reopened.fetch_meta(doc_id, source_id="src-b")["url"] == "https://example.com/b"


def test_same_url_changed_bytes_preserves_both_versions(store):
    first = store.put("src-a", "https://example.com/a", b"version one")
    second = store.put("src-a", "https://example.com/a", b"version two")

    assert first != second
    assert store.get_raw(first) == b"version one"
    assert store.get_raw(second) == b"version two"
    assert store.count_docs() == 2


def test_missing_document_raises_key_error(store):
    with pytest.raises(KeyError):
        store.get_raw("doc-missing")
    with pytest.raises(KeyError):
        store.fetch_meta("doc-missing")
    assert not store.has("doc-missing")
