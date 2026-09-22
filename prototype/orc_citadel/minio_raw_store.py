"""Immutable source-sharded Parquet raw storage on MinIO.

Objects use ``raw/<source_id>/shard-<timestamp>-<id>.parquet``.  Rows have the
same logical schema as :class:`RawShardStore`; original bytes remain in the
``content`` BLOB and committed shards are never rewritten.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import tempfile
from datetime import datetime, timezone
from typing import Iterator

import duckdb

from .identity import doc_id_for, new_ulid
from .raw_shard import validate_source_id

try:
    from minio import Minio
except Exception:  # pragma: no cover - optional driver at import time
    Minio = None


_COLUMNS = ("doc_id VARCHAR, source_id VARCHAR, url VARCHAR, fetched_at VARCHAR, "
            "http_status INTEGER, robots_allowed BOOLEAN, license VARCHAR, "
            "meta_json VARCHAR, content BLOB")
_SHARD_SIZE = 10_000


def build_minio_client() -> "Minio":
    """Build the MinIO client from the established environment variables."""
    if Minio is None:
        raise RuntimeError("minio 드라이버 미설치")
    return Minio(
        f"{os.environ.get('MINIO_HOST', 'localhost')}:{os.environ.get('MINIO_PORT', '9000')}",
        access_key=os.environ.get("MINIO_ROOT_USER", "citadel"),
        secret_key=os.environ.get("MINIO_ROOT_PASSWORD", "citadel-local-minio"),
        secure=False,
    )


class MinioRawStore:
    """Append-only raw rows buffered into immutable, source-local Parquet shards."""

    def __init__(self, client, bucket: str = "raw", *, shard_size: int = _SHARD_SIZE) -> None:
        if shard_size <= 0:
            raise ValueError("shard_size must be positive")
        self.client = client
        self.bucket = bucket
        self.shard_size = shard_size
        self._buffer: dict[str, list[tuple]] = {}
        self._known: set[tuple[str, str]] | None = None
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)

    def put(self, source_id: str, url: str, content: bytes,
            meta: dict | None = None) -> str:
        """Buffer original bytes and metadata, returning their content-derived doc id."""
        validate_source_id(source_id)
        doc_id = doc_id_for(content)
        self._ensure_index()
        assert self._known is not None
        if (source_id, doc_id) in self._known:
            return doc_id

        extra = dict(meta or {})
        fetched_at = extra.pop("fetched_at", None) or datetime.now(timezone.utc).isoformat()
        http_status = extra.pop("http_status", None)
        robots_allowed = extra.pop("robots_allowed", True)
        license_name = extra.pop("license", "unknown")
        extra.pop("doc_id", None)
        extra.pop("source_id", None)
        extra.pop("url", None)
        extra["content_hash"] = "sha256:" + hashlib.sha256(content).hexdigest()
        row = (
            doc_id, source_id, url, fetched_at, http_status, robots_allowed, license_name,
            json.dumps(extra, ensure_ascii=False) if extra else None, content,
        )
        self._buffer.setdefault(source_id, []).append(row)
        self._known.add((source_id, doc_id))
        if len(self._buffer[source_id]) >= self.shard_size:
            self._write_shard(source_id)
        return doc_id

    def flush(self) -> None:
        """Commit every non-empty source buffer as a new immutable shard."""
        for source_id in list(self._buffer):
            self._write_shard(source_id)

    def has(self, doc_id: str, *, source_id: str | None = None) -> bool:
        self._ensure_index()
        assert self._known is not None
        return ((source_id, doc_id) in self._known if source_id is not None
                else any(known_doc_id == doc_id for _, known_doc_id in self._known))

    def count_docs(self) -> int:
        self._ensure_index()
        assert self._known is not None
        return len(self._known)

    def get_raw(self, doc_id: str, *, source_id: str | None = None) -> bytes:
        """Return exact original bytes from the buffer or one matching shard row."""
        row = self._buffer_row(doc_id, source_id)
        if row is not None:
            return row[-1]
        sql = "SELECT content FROM read_parquet(?) WHERE doc_id = ?"
        params = [doc_id]
        if source_id is not None:
            sql += " AND source_id = ?"
            params.append(source_id)
        for row in self._iter_persisted(sql, params, source_ids=[source_id] if source_id else None):
            return bytes(row[0])
        raise KeyError(doc_id)

    def fetch_meta(self, doc_id: str, *, source_id: str | None = None) -> dict:
        """Return Parquet core and JSON metadata for one exact source row."""
        row = self._buffer_row(doc_id, source_id)
        if row is None:
            sql = (
                "SELECT doc_id, source_id, url, fetched_at, http_status, "
                "robots_allowed, license, meta_json FROM read_parquet(?) WHERE doc_id = ?"
            )
            params = [doc_id]
            if source_id is not None:
                sql += " AND source_id = ?"
                params.append(source_id)
            row = next(self._iter_persisted(
                sql, params, source_ids=[source_id] if source_id else None), None)
        if row is None:
            raise KeyError(doc_id)
        return self._meta_from_row(row)

    def iter_docs(self, source_ids: list[str] | None = None,
                  doc_ids: list[str] | None = None) -> Iterator[dict]:
        """Stream shard rows one object at a time, then expose still-buffered rows."""
        wanted = set(doc_ids) if doc_ids is not None else None
        sql = "SELECT doc_id, source_id, url, content FROM read_parquet(?)"
        params: list = []
        if wanted is not None:
            sql += " WHERE doc_id IN (SELECT unnest(?))"
            params.append(list(wanted))
        for doc_id, source_id, url, content in self._iter_persisted(
            sql, params, source_ids=source_ids
        ):
            yield {"doc_id": doc_id, "source_id": source_id,
                   "url": url, "content": bytes(content)}
        for source_id, rows in self._buffer.items():
            if source_ids is not None and source_id not in source_ids:
                continue
            for row in rows:
                if wanted is None or row[0] in wanted:
                    yield {"doc_id": row[0], "source_id": row[1],
                           "url": row[2], "content": row[-1]}

    def iter_records(self, source_ids: list[str] | None = None) -> Iterator[dict]:
        """Stream metadata rows without materializing content or the corpus."""
        sql = (
            "SELECT doc_id, source_id, url, fetched_at, http_status, "
            "robots_allowed, license, meta_json FROM read_parquet(?)"
        )
        for row in self._iter_persisted(sql, [], source_ids=source_ids):
            yield self._meta_from_row(row)
        for source_id, rows in self._buffer.items():
            if source_ids is None or source_id in source_ids:
                for row in rows:
                    yield self._meta_from_row(row[:-1])

    def _write_shard(self, source_id: str) -> None:
        rows = self._buffer.get(source_id, [])
        if not rows:
            return
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        object_id = new_ulid("r").split("-", 1)[1]
        key = f"raw/{source_id}/shard-{stamp}-{object_id}.parquet"
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "shard.parquet"
            con = duckdb.connect()
            try:
                con.execute(f"CREATE TABLE shard({_COLUMNS})")
                con.executemany("INSERT INTO shard VALUES (?,?,?,?,?,?,?,?,?)", rows)
                con.execute("COPY shard TO ? (FORMAT PARQUET, COMPRESSION zstd)", [str(path)])
            finally:
                con.close()
            with path.open("rb") as stream:
                self.client.put_object(self.bucket, key, stream, length=path.stat().st_size)
        del self._buffer[source_id]

    def _ensure_index(self) -> None:
        if self._known is not None:
            return
        self._known = {
            (source_id, doc_id)
            for source_id, doc_id in self._iter_persisted(
                "SELECT source_id, doc_id FROM read_parquet(?)", [])
        }
        for rows in self._buffer.values():
            self._known.update((row[1], row[0]) for row in rows)

    def _shard_keys(self, source_ids: list[str] | None = None) -> Iterator[str]:
        allowed = (
            {validate_source_id(source_id) for source_id in source_ids}
            if source_ids is not None else None
        )
        for obj in self.client.list_objects(self.bucket, prefix="raw/", recursive=True):
            parts = obj.object_name.split("/")
            if (len(parts) == 3 and parts[0] == "raw"
                    and parts[2].startswith("shard-") and parts[2].endswith(".parquet")
                    and (allowed is None or parts[1] in allowed)):
                yield obj.object_name

    def _iter_persisted(self, sql: str, params: list,
                        source_ids: list[str] | None = None) -> Iterator[tuple]:
        for key in self._shard_keys(source_ids):
            with tempfile.TemporaryDirectory() as directory:
                path = pathlib.Path(directory) / "shard.parquet"
                response = self.client.get_object(self.bucket, key)
                try:
                    with path.open("wb") as output:
                        while chunk := response.read(1024 * 1024):
                            output.write(chunk)
                finally:
                    response.close()
                    response.release_conn()
                con = duckdb.connect()
                try:
                    cursor = con.execute(sql, [str(path), *params])
                    while rows := cursor.fetchmany(1_000):
                        yield from rows
                finally:
                    con.close()

    def _buffer_row(self, doc_id: str, source_id: str | None = None) -> tuple | None:
        for rows in self._buffer.values():
            for row in rows:
                if row[0] == doc_id and (source_id is None or row[1] == source_id):
                    return row
        return None

    @staticmethod
    def _meta_from_row(row: tuple) -> dict:
        (doc_id, source_id, url, fetched_at, http_status,
         robots_allowed, license_name, meta_json) = row[:8]
        meta = json.loads(meta_json) if meta_json else {}
        return {
            "doc_id": doc_id,
            "source_id": source_id,
            "url": url,
            "fetched_at": fetched_at,
            "http_status": http_status,
            "robots_allowed": robots_allowed,
            "license": license_name,
            **meta,
        }
