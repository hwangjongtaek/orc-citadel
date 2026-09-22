"""Normalized-zone Iceberg tables (design 03 §3).

Both local and production paths use PyIceberg. Local callers supply a directory
containing a persistent SQLite catalog plus file warehouse; production selects the
REST catalog through environment configuration.
"""
from __future__ import annotations

import heapq
import pathlib
import sqlite3
import tempfile
from datetime import datetime, timezone
from typing import Iterable, Iterator

import pyarrow as pa
import pyarrow.parquet as pq
from pyiceberg.expressions import AlwaysTrue, And, EqualTo, In, Or
from pyiceberg.partitioning import PartitionField, PartitionSpec
from pyiceberg.schema import Schema
from pyiceberg.table.sorting import SortField, SortOrder
from pyiceberg.transforms import IdentityTransform, MonthTransform
from pyiceberg.types import LongType, NestedField, StringType, TimestampType

from .iceberg_catalog import open_catalog
from .identity import doc_id_for
from .parse import ParsedDoc, parse_document

_NAMESPACE = "normalized"
_DOCUMENTS = f"{_NAMESPACE}.documents"
_SEGMENTS = f"{_NAMESPACE}.segments"

_DOCUMENT_SCHEMA = Schema(
    NestedField(1, "doc_id", StringType(), required=True),
    NestedField(2, "source_id", StringType(), required=True),
    NestedField(3, "url", StringType(), required=True),
    NestedField(4, "title", StringType(), required=False),
    NestedField(5, "language", StringType(), required=False),
    NestedField(6, "publication_time", TimestampType(), required=False),
    NestedField(7, "revision_time", TimestampType(), required=False),
    NestedField(8, "parser_version", StringType(), required=True),
    NestedField(9, "char_len", LongType(), required=False),
    identifier_field_ids=[1, 8],
)
_SEGMENT_SCHEMA = Schema(
    NestedField(1, "segment_id", StringType(), required=True),
    NestedField(2, "doc_id", StringType(), required=True),
    NestedField(3, "kind", StringType(), required=True),
    NestedField(4, "text", StringType(), required=True),
    NestedField(5, "char_start", LongType(), required=True),
    NestedField(6, "char_end", LongType(), required=True),
    NestedField(7, "norm_char_start", LongType(), required=True),
    NestedField(8, "norm_char_end", LongType(), required=True),
    NestedField(9, "ord", LongType(), required=True),
    NestedField(10, "parser_version", StringType(), required=True),
    # Physical partition columns are deliberately hidden from the public segment API.
    NestedField(11, "source_id", StringType(), required=True),
    NestedField(12, "publication_time", TimestampType(), required=False),
    identifier_field_ids=[1, 10],
)


def _partition_spec(source_field_id: int, publication_field_id: int) -> PartitionSpec:
    return PartitionSpec(
        PartitionField(source_field_id, 1000, IdentityTransform(), "source_id"),
        PartitionField(publication_field_id, 1001, MonthTransform(), "publication_month"),
    )


def _utc_naive(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _rows(table, *, selected_fields: tuple[str, ...] | None = None,
          row_filter=AlwaysTrue()) -> Iterator[dict]:
    scan = table.scan(row_filter=row_filter, selected_fields=selected_fields or ("*",))
    for batch in scan.to_arrow_batch_reader():
        yield from batch.to_pylist()


def _and(filters: list):
    expression = AlwaysTrue()
    for candidate in filters:
        expression = And(expression, candidate)
    return expression


def _or(filters: list):
    if not filters:
        return AlwaysTrue()
    expression = filters[0]
    for item in filters[1:]:
        expression = Or(expression, item)
    return expression


class NormalizedZone:
    """Normalized documents and segments stored as Iceberg tables."""

    def __init__(self, root: str | pathlib.Path = ":memory:") -> None:
        self._handle = open_catalog(root)
        self._catalog = self._handle.catalog

    def initialize(self) -> None:
        self._catalog.create_namespace_if_not_exists(_NAMESPACE)
        self._catalog.create_table_if_not_exists(
            _DOCUMENTS,
            schema=_DOCUMENT_SCHEMA,
            partition_spec=_partition_spec(2, 6),
            sort_order=SortOrder(SortField(1, transform=IdentityTransform())),
            properties={"write.parquet.compression-codec": "zstd"},
        )
        self._catalog.create_table_if_not_exists(
            _SEGMENTS,
            schema=_SEGMENT_SCHEMA,
            partition_spec=_partition_spec(11, 12),
            sort_order=SortOrder(SortField(2, transform=IdentityTransform())),
            properties={"write.parquet.compression-codec": "zstd"},
        )


    def reset(self) -> None:
        """Recreate normalized tables from their source-of-truth during migration."""
        for identifier in (_SEGMENTS, _DOCUMENTS):
            if self._catalog.table_exists(identifier):
                self._catalog.purge_table(identifier)
        self.initialize()
    def tables(self) -> list[str]:
        return sorted(identifier[-1] for identifier in self._catalog.list_tables(_NAMESPACE))

    def _table(self, name: str):
        return self._catalog.load_table(f"{_NAMESPACE}.{name}")

    def persist(self, source_id: str, url: str, raw_html: bytes, doc: ParsedDoc) -> str:
        return self.persist_many([(source_id, url, raw_html, doc)])[0]

    def persist_many(self, items: Iterable[tuple[str, str, bytes, ParsedDoc]]) -> list[str]:
        """Commit one bounded batch, upserting each identifier tuple exactly once."""
        document_rows: list[dict] = []
        segment_rows: list[dict] = []
        doc_ids: list[str] = []
        for source_id, url, raw_html, doc in items:
            doc_id = doc_id_for(raw_html)
            published = _utc_naive(doc.publication_time)
            doc_ids.append(doc_id)
            document_rows.append({
                "doc_id": doc_id, "source_id": source_id, "url": url,
                "title": doc.title, "language": "en", "publication_time": published,
                "revision_time": None, "parser_version": doc.parser_version,
                "char_len": len(doc.text),
            })
            for segment in parse_document(doc_id, doc):
                segment_rows.append({
                    "segment_id": segment.segment_id, "doc_id": doc_id,
                    "kind": segment.kind, "text": segment.text,
                    "char_start": segment.char_start, "char_end": segment.char_end,
                    "norm_char_start": segment.norm_char_start,
                    "norm_char_end": segment.norm_char_end, "ord": segment.order,
                    "parser_version": doc.parser_version, "source_id": source_id,
                    "publication_time": published,
                })
        if not document_rows:
            return []
        documents = self._table("documents")
        segments = self._table("segments")
        documents.upsert(pa.Table.from_pylist(document_rows, schema=documents.schema().as_arrow()))
        replace_filter = _or([
            And(EqualTo("doc_id", row["doc_id"]),
                EqualTo("parser_version", row["parser_version"]))
            for row in document_rows
        ])
        existing = _rows(segments, selected_fields=("segment_id",),
                         row_filter=replace_filter)
        if next(existing, None) is not None:
            segments.delete(replace_filter)
        if segment_rows:
            segments.append(pa.Table.from_pylist(
                segment_rows, schema=segments.schema().as_arrow()))
        return doc_ids

    def upsert_arrow(self, table_name: str, batch: pa.Table | pa.RecordBatch) -> None:
        """Bounded migration entry point using the table identifier fields."""
        table = self._table(table_name)
        data = pa.Table.from_batches([batch]) if isinstance(batch, pa.RecordBatch) else batch
        if data.num_rows:
            table.upsert(data.cast(table.schema().as_arrow()))

    def append_arrow(self, table_name: str, batch: pa.Table | pa.RecordBatch) -> None:
        """Append a source-unique migration batch without an equality scan."""
        table = self._table(table_name)
        data = pa.Table.from_batches([batch]) if isinstance(batch, pa.RecordBatch) else batch
        if data.num_rows:
            table.append(data.cast(table.schema().as_arrow()))

    def iter_document_ids(self) -> Iterator[str]:
        for row in _rows(self._table("documents"), selected_fields=("doc_id",)):
            yield row["doc_id"]

    def documents(self, doc_ids: Iterable[str] | None = None) -> list[dict]:
        filters = []
        if doc_ids is not None:
            values = sorted(set(doc_ids))
            if not values:
                return []
            filters.append(In("doc_id", values))
        rows = list(_rows(self._table("documents"), row_filter=_and(filters)))
        return sorted(rows, key=lambda row: (row["doc_id"], row["parser_version"]))

    def segments(self, doc_id: str) -> list[dict]:
        public = ("segment_id", "doc_id", "kind", "text", "char_start", "char_end",
                  "norm_char_start", "norm_char_end", "ord", "parser_version")
        rows = list(_rows(self._table("segments"), selected_fields=public,
                          row_filter=EqualTo("doc_id", doc_id)))
        return sorted(rows, key=lambda row: (row["ord"], row["parser_version"]))

    def counts(self) -> dict[str, int]:
        return {name: self._record_count(self._table(name))
                for name in ("documents", "segments")}

    @staticmethod
    def _record_count(table) -> int:
        snapshot = table.current_snapshot()
        return int(snapshot.summary.get("total-records", 0)) if snapshot else 0

    def freshness(self) -> dict:
        now = datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory(prefix="orc-citadel-freshness-") as scratch:
            conn = sqlite3.connect(pathlib.Path(scratch) / "ages.sqlite")
            conn.execute("CREATE TABLE ages(value REAL NOT NULL)")
            rows = (
                ((now - (value.replace(tzinfo=timezone.utc)
                         if value.tzinfo is None else value)).total_seconds() / 60.0,)
                for row in _rows(
                    self._table("documents"),
                    selected_fields=("publication_time",))
                if (value := row["publication_time"]) is not None
            )
            conn.executemany("INSERT INTO ages VALUES (?)", rows)
            count, minimum, maximum = conn.execute(
                "SELECT COUNT(*), MIN(value), MAX(value) FROM ages").fetchone()
            if not count:
                conn.close()
                return {"measured": False,
                        "note": "publication_time 없음 → 지연 미측정 (honest-gap §6.2)"}
            median = conn.execute(
                "SELECT value FROM ages ORDER BY value LIMIT 1 OFFSET ?",
                [count // 2],
            ).fetchone()[0]
            conn.close()
        return {"measured": True, "n": count, "min_age_min": round(minimum, 1),
                "median_age_min": round(median, 1), "max_age_min": round(maximum, 1)}

    @staticmethod
    def _source_type(source_id: str) -> str:
        head = source_id.split("-", 1)[0]
        return head if head in {"official", "press", "gov", "research", "exchange"} else "source"

    @staticmethod
    def _matches(row: dict, *, source_type=None, source=None, language=None, q=None,
                 doc_ids: set[str] | None = None) -> bool:
        if source_type and NormalizedZone._source_type(row["source_id"]) != source_type:
            return False
        if source and row["source_id"] != source:
            return False
        actual_language = row.get("language") or "unknown"
        if language and actual_language != language:
            return False
        if doc_ids is not None and row["doc_id"] not in doc_ids:
            return False
        if q:
            needle = q.casefold()
            if not any(needle in str(row.get(key) or "").casefold()
                       for key in ("title", "url", "doc_id")):
                return False
        return True

    def archive_page(self, *, limit: int, offset: int, source_type=None, source=None,
                     language=None, q=None, doc_ids=None, sort="doc_id"):
        ids = set(doc_ids) if doc_ids is not None else None
        table = self._table("documents")
        all_counts = self.counts()
        total = 0

        def matched_rows():
            nonlocal total
            for row in _rows(table):
                if self._matches(row, source_type=source_type, source=source,
                                 language=language, q=q, doc_ids=ids):
                    total += 1
                    yield row

        def publication_key(row):
            published = row["publication_time"]
            return ((0, -published.timestamp(), row["doc_id"], row["parser_version"])
                    if published is not None
                    else (1, 0, row["doc_id"], row["parser_version"]))

        key = publication_key if sort == "publication" else (
            lambda row: (row["doc_id"], row["parser_version"]))
        page_rows = heapq.nsmallest(offset + limit, matched_rows(), key=key)
        docs = page_rows[offset:offset + limit]
        segment_counts = self.segment_counts({row["doc_id"] for row in docs})
        for row in docs:
            row["segments"] = segment_counts.get(row["doc_id"], 0)

        source_facets: dict[str, int] = {}
        language_facets: dict[str, int] = {}
        for row in _rows(table):
            if not self._matches(row, q=q, doc_ids=ids):
                continue
            source_key = self._source_type(row["source_id"])
            language_key = row.get("language") or "unknown"
            source_facets[source_key] = source_facets.get(source_key, 0) + 1
            language_facets[language_key] = language_facets.get(language_key, 0) + 1
        return docs, all_counts, {"limit": limit, "offset": offset, "total": total,
                                  "sort": sort}, {
                                      "source_type": dict(sorted(source_facets.items())),
                                      "language": dict(sorted(language_facets.items())),
                                  }

    def segment_counts(self, doc_ids: set[str]) -> dict[str, int]:
        if not doc_ids:
            return {}
        counts: dict[str, int] = {}
        for row in _rows(self._table("segments"), selected_fields=("doc_id",),
                         row_filter=In("doc_id", sorted(doc_ids))):
            doc_id = row["doc_id"]
            counts[doc_id] = counts.get(doc_id, 0) + 1
        return counts

    def archive_facets(self) -> tuple[dict[str, int], list[dict]]:
        kinds: dict[str, int] = {}
        for row in _rows(self._table("segments"), selected_fields=("kind",)):
            kinds[row["kind"]] = kinds.get(row["kind"], 0) + 1
        with tempfile.TemporaryDirectory(prefix="orc-citadel-facets-") as scratch:
            conn = sqlite3.connect(pathlib.Path(scratch) / "urls.sqlite")
            conn.execute("CREATE TABLE urls(url TEXT PRIMARY KEY, n INTEGER, ids TEXT)")
            for row in _rows(self._table("documents"), selected_fields=("url", "doc_id")):
                conn.execute(
                    "INSERT INTO urls VALUES (?, 1, ?) ON CONFLICT(url) DO UPDATE SET "
                    "n=n+1, ids=CASE WHEN n<5 THEN ids || char(10) || excluded.ids ELSE ids END",
                    (row["url"], row["doc_id"]),
                )
            groups = [{"url": url, "count": n, "doc_ids": ids.split("\n")}
                      for url, n, ids in conn.execute(
                          "SELECT url,n,ids FROM urls WHERE n>=2 ORDER BY url LIMIT 20")]
            conn.close()
        return dict(sorted(kinds.items())), groups

    def search_documents(self, query: str, limit: int = 10) -> tuple[list[dict], int]:
        total = 0

        def hits():
            nonlocal total
            for row in _rows(
                    self._table("documents"),
                    selected_fields=("doc_id", "title", "source_id", "url")):
                if (query.casefold() in str(row.get("title") or "").casefold()
                        or query.casefold() in str(row.get("url") or "").casefold()):
                    total += 1
                    yield row

        chosen = heapq.nsmallest(limit, hits(), key=lambda row: row["doc_id"])
        return [{key: row[key] for key in ("doc_id", "title", "source_id")}
                for row in chosen], total

    def document(self, doc_id: str) -> dict:
        docs = self.documents([doc_id])
        return {"doc_id": doc_id, "available": True, "documents": docs,
                "segments": [{key: row[key] for key in
                              ("segment_id", "ord", "kind", "text", "char_start", "char_end")}
                             for row in self.segments(doc_id)]}

    def export_parquet(self, out_dir: str | pathlib.Path) -> None:
        out = pathlib.Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        for name in ("documents", "segments"):
            table = self._table(name)
            writer = pq.ParquetWriter(out / f"{name}.parquet", table.schema().as_arrow(),
                                      compression="zstd")
            try:
                for batch in table.scan().to_arrow_batch_reader():
                    writer.write_batch(batch)
            finally:
                writer.close()

    def partition_metadata(self, table_name: str = "documents") -> list[dict]:
        return self._table(table_name).inspect.partitions().to_pylist()

    def close(self) -> None:
        self._handle.close()
