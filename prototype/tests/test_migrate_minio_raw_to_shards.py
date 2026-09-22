from __future__ import annotations

import io
import json

import pytest

from fake_minio import FakeMinio
from orc_citadel.identity import doc_id_for
from orc_citadel.minio_raw_store import MinioRawStore
from scripts.migrate_minio_raw_to_shards import migrate


def _legacy(client, bucket, source, content, meta=None, *, doc_id=None):
    doc_id = doc_id or doc_id_for(content)
    prefix = f"raw/{source}/{doc_id}"
    fetch = {"doc_id": doc_id, "source_id": source, "url": f"https://e/{doc_id}",
             "fetched_at": "2026-09-20T00:00:00+00:00", **(meta or {})}
    payload = json.dumps(fetch).encode()
    client.put_object(bucket, f"{prefix}/content.bin", io.BytesIO(content), len(content))
    client.put_object(bucket, f"{prefix}/fetch.json", io.BytesIO(payload), len(payload))
    return doc_id


def _client():
    client = FakeMinio()
    client.make_bucket("raw")
    return client


def test_migration_is_bounded_into_source_shards_and_idempotent():
    client = _client()
    expected = {}
    for i in range(25):
        content = f"legacy-{i}".encode()
        doc_id = _legacy(client, "raw", "src-a", content,
                         {"http_status": 200, "ordinal": i})
        expected[doc_id] = (content, i)

    first = migrate(client, "raw", shard_size=10)
    second = migrate(client, "raw", shard_size=10)

    assert first == {"sources": {"src-a": 25}, "migrated": 25, "skipped": 0,
                     "deleted": 0}
    assert second == {"sources": {"src-a": 0}, "migrated": 0, "skipped": 25,
                      "deleted": 0}
    names = [o.object_name for o in client.list_objects("raw", recursive=True)]
    assert len([n for n in names if n.endswith(".parquet")]) == 3
    assert len([n for n in names if n.endswith("content.bin")]) == 25
    assert len([n for n in names if n.endswith("fetch.json")]) == 25

    store = MinioRawStore(client, "raw")
    for doc_id, (content, ordinal) in expected.items():
        assert store.get_raw(doc_id) == content
        assert store.fetch_meta(doc_id)["ordinal"] == ordinal
        assert store.fetch_meta(doc_id)["fetched_at"] == "2026-09-20T00:00:00+00:00"


def test_destructive_flag_deletes_only_verified_legacy_pairs():
    client = _client()
    doc_ids = [_legacy(client, "raw", "src-a", f"body-{i}".encode()) for i in range(2)]
    client.put_object("raw", "unrelated/object", io.BytesIO(b"keep"), 4)

    summary = migrate(client, "raw", shard_size=10, delete_legacy=True)

    assert summary["deleted"] == 4
    names = [o.object_name for o in client.list_objects("raw", recursive=True)]
    assert len([n for n in names if n.endswith(".parquet")]) == 1
    assert not any(n.endswith(("content.bin", "fetch.json")) for n in names)
    assert "unrelated/object" in names
    store = MinioRawStore(client, "raw")
    assert {store.get_raw(doc_id) for doc_id in doc_ids} == {b"body-0", b"body-1"}


def test_migration_rejects_legacy_key_with_wrong_content_hash():
    client = _client()
    _legacy(client, "raw", "src-a", b"body", doc_id="doc-wrong")

    with pytest.raises(ValueError, match="content-derived doc_id"):
        migrate(client, "raw", shard_size=10)

    assert not any(o.object_name.endswith(".parquet")
                   for o in client.list_objects("raw", recursive=True))
