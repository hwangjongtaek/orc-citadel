"""One-shot, idempotent DuckDB normalized-zone migration to Iceberg.

The legacy database is only a migration source. Both tables are streamed as Arrow
record batches; segment partition columns are propagated from the matching document
version before identifier-field upsert into Iceberg.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, time, timezone
import hashlib
import math
import pathlib
import struct
import sys

import duckdb

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from orc_citadel.iceberg_zone import NormalizedZone  # noqa: E402

BATCH_SIZE = 10_000

_DOCUMENT_COLUMNS = (
    "doc_id", "source_id", "url", "title", "language", "publication_time",
    "revision_time", "parser_version", "char_len",
)
_SEGMENT_COLUMNS = (
    "segment_id", "doc_id", "kind", "text", "char_start", "char_end",
    "norm_char_start", "norm_char_end", "ord", "parser_version", "source_id",
    "publication_time",
)

_DOCUMENTS_SQL = """
SELECT doc_id, source_id, url, title, language, publication_time, revision_time,
       parser_version, char_len
FROM documents
ORDER BY doc_id, parser_version
"""
_SEGMENTS_SQL = """
SELECT s.segment_id, s.doc_id, s.kind, s.text, s.char_start, s.char_end,
       s.norm_char_start, s.norm_char_end, s.ord, s.parser_version,
       d.source_id, d.publication_time
FROM segments s
JOIN documents d
  ON d.doc_id = s.doc_id AND d.parser_version = s.parser_version
ORDER BY s.doc_id, s.parser_version, s.ord, s.segment_id
"""


def _hash_value(digest, value) -> None:
    if value is None:
        digest.update(b"N")
    elif isinstance(value, bool):
        digest.update(b"B1" if value else b"B0")
    elif isinstance(value, int):
        encoded = str(value).encode("ascii")
        digest.update(b"I" + len(encoded).to_bytes(8, "big") + encoded)
    elif isinstance(value, float):
        if math.isnan(value):
            digest.update(b"Fnan")
        else:
            digest.update(b"F" + struct.pack(">d", value))
    elif isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        encoded = value.isoformat(timespec="microseconds").encode("ascii")
        digest.update(b"T" + len(encoded).to_bytes(8, "big") + encoded)
    elif isinstance(value, date):
        encoded = value.isoformat().encode("ascii")
        digest.update(b"D" + len(encoded).to_bytes(8, "big") + encoded)
    elif isinstance(value, time):
        encoded = value.isoformat(timespec="microseconds").encode("ascii")
        digest.update(b"C" + len(encoded).to_bytes(8, "big") + encoded)
    elif isinstance(value, str):
        encoded = value.encode("utf-8")
        digest.update(b"S" + len(encoded).to_bytes(8, "big") + encoded)
    elif isinstance(value, bytes):
        digest.update(b"Y" + len(value).to_bytes(8, "big") + value)
    elif isinstance(value, (list, tuple)):
        digest.update(b"L" + len(value).to_bytes(8, "big"))
        for item in value:
            _hash_value(digest, item)
    elif isinstance(value, dict):
        digest.update(b"M" + len(value).to_bytes(8, "big"))
        for key in sorted(value):
            _hash_value(digest, key)
            _hash_value(digest, value[key])
    else:
        _hash_value(digest, str(value))


def _digest_batches(batches, columns: tuple[str, ...]) -> tuple[int, str]:
    digest = hashlib.sha256()
    digest.update(b"orc-citadel-migration-content-v1")
    for column in columns:
        _hash_value(digest, column)
    count = 0
    for batch in batches:
        arrays = [batch.column(batch.schema.get_field_index(column)) for column in columns]
        for row_index in range(batch.num_rows):
            digest.update(b"R")
            for array in arrays:
                _hash_value(digest, array[row_index].as_py())
            count += 1
    return count, digest.hexdigest()


def _query_digest(conn, sql: str, columns: tuple[str, ...]) -> tuple[int, str]:
    return _digest_batches(conn.execute(sql).to_arrow_reader(BATCH_SIZE), columns)


def _target_digest(zone: NormalizedZone, table_name: str, columns: tuple[str, ...],
                   order_by: str) -> tuple[int, str]:
    sorter = duckdb.connect()
    try:
        sorter.execute("SET memory_limit = '128MB'")
        sorter.register(
            "migration_target",
            zone._table(table_name).scan(selected_fields=columns).to_arrow_batch_reader(),
        )
        selected = ", ".join(f'"{column}"' for column in columns)
        return _query_digest(
            sorter, f"SELECT {selected} FROM migration_target ORDER BY {order_by}", columns)
    finally:
        sorter.close()


def _source_state(conn) -> tuple[dict[str, int], dict[str, str]]:
    counts = {
        "documents": conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
        "segments": conn.execute("SELECT COUNT(*) FROM segments").fetchone()[0],
    }
    document_count, document_digest = _query_digest(conn, _DOCUMENTS_SQL, _DOCUMENT_COLUMNS)
    segment_count, segment_digest = _query_digest(conn, _SEGMENTS_SQL, _SEGMENT_COLUMNS)
    streamed = {"documents": document_count, "segments": segment_count}
    if streamed != counts:
        raise RuntimeError(
            f"normalized migration source query mismatch: source={counts}, streamed={streamed}")
    return counts, {"documents": document_digest, "segments": segment_digest}


def _target_state(zone: NormalizedZone) -> tuple[dict[str, int], dict[str, str]]:
    document_count, document_digest = _target_digest(
        zone, "documents", _DOCUMENT_COLUMNS, "doc_id, parser_version")
    segment_count, segment_digest = _target_digest(
        zone, "segments", _SEGMENT_COLUMNS, "doc_id, parser_version, ord, segment_id")
    return (
        {"documents": document_count, "segments": segment_count},
        {"documents": document_digest, "segments": segment_digest},
    )


def _import_query(conn, zone: NormalizedZone, table_name: str, sql: str) -> int:
    total = 0
    reader = conn.execute(sql).to_arrow_reader(BATCH_SIZE)
    for batch in reader:
        zone.append_arrow(table_name, batch)
        total += batch.num_rows
    return total


def migrate(source: pathlib.Path | str, target: pathlib.Path | str) -> dict[str, int]:
    source = pathlib.Path(source)
    if not source.is_file():
        raise FileNotFoundError(source)
    conn = duckdb.connect(str(source), read_only=True)
    zone = NormalizedZone(target)
    try:
        zone.initialize()
        source_counts, source_digests = _source_state(conn)
        visible = zone.counts()
        streamed_visible, visible_digests = _target_state(zone)
        if (visible == source_counts == streamed_visible
                and visible_digests == source_digests):
            return {"source_documents": source_counts["documents"],
                    "source_segments": source_counts["segments"],
                    "visible_documents": visible["documents"],
                    "visible_segments": visible["segments"]}
        if visible["documents"] or visible["segments"]:
            zone.reset()
        documents = _import_query(conn, zone, "documents", _DOCUMENTS_SQL)
        segments = _import_query(conn, zone, "segments", _SEGMENTS_SQL)
        imported = {"documents": documents, "segments": segments}
        visible = zone.counts()
        streamed_visible, visible_digests = _target_state(zone)
        if (imported != source_counts or visible != source_counts
                or streamed_visible != source_counts or visible_digests != source_digests):
            raise RuntimeError(
                "normalized migration content mismatch: "
                f"source_counts={source_counts}, imported={imported}, visible={visible}, "
                f"streamed_visible={streamed_visible}, "
                f"source_digests={source_digests}, visible_digests={visible_digests}")
        return {"source_documents": documents, "source_segments": segments,
                "visible_documents": visible["documents"],
                "visible_segments": visible["segments"]}
    finally:
        zone.close()
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=pathlib.Path, default=ROOT / "data" / "oc.duckdb")
    parser.add_argument("--target", type=pathlib.Path, default=ROOT / "data" / "iceberg")
    args = parser.parse_args()
    print(migrate(args.source, args.target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
