"""Migrate legacy MinIO raw objects to immutable source-sharded Parquet.

Legacy pairs are preserved by default.  Pass ``--delete-legacy`` only after the
command has written and byte/metadata-verified the replacement shard rows.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

_REPO = pathlib.Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from orc_citadel.identity import doc_id_for  # noqa: E402
from orc_citadel.minio_raw_store import (  # noqa: E402
    MinioRawStore,
    build_minio_client,
)


def _read_object(client, bucket: str, key: str) -> bytes:
    response = client.get_object(bucket, key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def _exists(client, bucket: str, key: str) -> bool:
    try:
        client.stat_object(bucket, key)
        return True
    except Exception:
        return False


def migrate(client, bucket: str = "raw", *, shard_size: int = 10_000,
            delete_legacy: bool = False) -> dict:
    """Stream legacy pairs into verified shards and return migration counts."""
    store = MinioRawStore(client, bucket, shard_size=shard_size)
    sources: dict[str, int] = {}
    migrated = skipped = deleted = 0
    pending: list[tuple[str, str, str, bytes, dict]] = []

    def flush_and_verify() -> None:
        nonlocal deleted
        if not pending:
            return
        store.flush()
        for content_key, fetch_key, doc_id, content, expected in pending:
            if store.get_raw(doc_id) != content:
                raise RuntimeError(f"migration byte verification failed: {doc_id}")
            actual = store.fetch_meta(doc_id)
            for field, value in expected.items():
                if actual.get(field) != value:
                    raise RuntimeError(f"migration metadata verification failed: {doc_id} {field}")
            if delete_legacy:
                client.remove_object(bucket, content_key)
                client.remove_object(bucket, fetch_key)
                deleted += 2
        pending.clear()

    for obj in client.list_objects(bucket, prefix="raw/", recursive=True):
        content_key = obj.object_name
        parts = content_key.split("/")
        if len(parts) != 4 or parts[0] != "raw" or parts[3] != "content.bin":
            continue
        source_id, legacy_doc_id = parts[1], parts[2]
        fetch_key = f"raw/{source_id}/{legacy_doc_id}/fetch.json"
        if not _exists(client, bucket, fetch_key):
            continue
        content = _read_object(client, bucket, content_key)
        actual_doc_id = doc_id_for(content)
        if legacy_doc_id != actual_doc_id:
            raise ValueError(
                f"{content_key}: key does not match content-derived doc_id {actual_doc_id}"
            )
        loaded = json.loads(_read_object(client, bucket, fetch_key))
        if not isinstance(loaded, dict):
            raise ValueError(f"{fetch_key}: fetch metadata must be an object")
        meta = dict(loaded)
        url = meta.pop("url", "")
        meta.pop("doc_id", None)
        meta.pop("source_id", None)

        existed = store.has(actual_doc_id)
        store.put(source_id, url, content, meta)
        sources.setdefault(source_id, 0)
        expected = dict(loaded)
        expected.update({"doc_id": actual_doc_id, "source_id": source_id, "url": url})
        expected.setdefault("http_status", None)
        expected.setdefault("robots_allowed", True)
        expected.setdefault("license", "unknown")
        expected["content_hash"] = "sha256:" + hashlib.sha256(content).hexdigest()
        if "fetched_at" not in loaded:
            expected.pop("fetched_at", None)
        pending.append((content_key, fetch_key, actual_doc_id, content, expected))
        if existed:
            skipped += 1
        else:
            migrated += 1
            sources[source_id] += 1
        if len(pending) >= shard_size:
            flush_and_verify()

    flush_and_verify()
    return {"sources": sources, "migrated": migrated, "skipped": skipped,
            "deleted": deleted}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", default="raw")
    parser.add_argument("--shard-size", type=int, default=10_000)
    parser.add_argument(
        "--delete-legacy", action="store_true",
        help="delete content.bin/fetch.json only after replacement rows verify",
    )
    args = parser.parse_args(argv)
    summary = migrate(build_minio_client(), args.bucket, shard_size=args.shard_size,
                      delete_legacy=args.delete_legacy)
    for source_id, count in sorted(summary["sources"].items()):
        print(f"  {source_id:<32} {count:>8,}")
    print(f"migrated {summary['migrated']:,} · skipped {summary['skipped']:,} · "
          f"legacy objects deleted {summary['deleted']:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
