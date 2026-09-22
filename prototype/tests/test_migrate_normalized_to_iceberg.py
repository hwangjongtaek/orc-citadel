from __future__ import annotations

import datetime as dt

import duckdb
import pyarrow as pa
import pytest

from orc_citadel.iceberg_zone import NormalizedZone
from scripts.migrate_normalized_to_iceberg import _digest_batches, migrate


def _legacy_database(path) -> None:
    conn = duckdb.connect(str(path))
    conn.execute("""
        CREATE TABLE documents (
            doc_id VARCHAR, source_id VARCHAR, url VARCHAR, title VARCHAR,
            language VARCHAR, publication_time TIMESTAMP, revision_time TIMESTAMP,
            parser_version VARCHAR, char_len BIGINT,
            PRIMARY KEY (doc_id, parser_version))
    """)
    conn.execute("""
        CREATE TABLE segments (
            segment_id VARCHAR, doc_id VARCHAR, kind VARCHAR, text VARCHAR,
            char_start BIGINT, char_end BIGINT, norm_char_start BIGINT,
            norm_char_end BIGINT, ord BIGINT, parser_version VARCHAR,
            PRIMARY KEY (segment_id, parser_version))
    """)
    published = dt.datetime(2026, 8, 3, 12, 0)
    conn.execute("INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?)", [
        "doc-1", "official-test", "https://e/1", "title", "en", published,
        None, "p1", 4,
    ])
    conn.execute("INSERT INTO segments VALUES (?,?,?,?,?,?,?,?,?,?)", [
        "doc-1#p0.s0", "doc-1", "sentence", "text", 0, 4, 0, 4, 0, "p1",
    ])
    conn.close()


def test_content_digest_is_batch_independent_for_nested_and_nullable_values():
    schema = pa.schema([
        ("observed_at", pa.timestamp("us")),
        ("values", pa.list_(pa.int64())),
        ("payload_json", pa.string()),
        ("optional", pa.string()),
    ])
    table = pa.Table.from_pylist([
        {
            "observed_at": dt.datetime(2026, 9, 22, 10, 11, 12, 123456),
            "values": [1, 2],
            "payload_json": '{"a":1,"b":[null,true]}',
            "optional": None,
        },
        {
            "observed_at": dt.datetime(2026, 9, 22, 10, 11, 13),
            "values": [],
            "payload_json": "{}",
            "optional": "present",
        },
    ], schema=schema)
    columns = tuple(schema.names)

    one_batch = _digest_batches(table.to_batches(max_chunksize=2), columns)
    many_batches = _digest_batches(table.to_batches(max_chunksize=1), columns)
    aware_timestamps = pa.array([
        dt.datetime(2026, 9, 22, 10, 11, 12, 123456, tzinfo=dt.timezone.utc),
        dt.datetime(2026, 9, 22, 10, 11, 13, tzinfo=dt.timezone.utc),
    ], type=pa.timestamp("us", tz="UTC"))
    aware_table = table.set_column(0, "observed_at", aware_timestamps)
    timezone_equivalent = _digest_batches(aware_table.to_batches(max_chunksize=1), columns)

    assert one_batch == timezone_equivalent

    assert one_batch == many_batches


def test_migration_is_idempotent_and_propagates_segment_partitions(tmp_path):
    source, target = tmp_path / "oc.duckdb", tmp_path / "iceberg"
    _legacy_database(source)

    first = migrate(source, target)
    zone = NormalizedZone(target)
    try:
        token = tuple(
            zone._table(name).current_snapshot().snapshot_id
            for name in ("documents", "segments")
        )
        assert zone.segments("doc-1")[0]["text"] == "text"
        partition = zone.partition_metadata("segments")[0]["partition"]
        assert partition["source_id"] == "official-test"
        assert partition["publication_month"] is not None
    finally:
        zone.close()

    second = migrate(source, target)

    assert first["visible_documents"] == first["visible_segments"] == 1
    assert second["visible_documents"] == second["visible_segments"] == 1
    reopened = NormalizedZone(target)
    try:
        assert tuple(
            reopened._table(name).current_snapshot().snapshot_id
            for name in ("documents", "segments")
        ) == token
    finally:
        reopened.close()


def test_migration_rebuilds_stale_target_without_duplicates(tmp_path):
    source, target = tmp_path / "oc.duckdb", tmp_path / "iceberg"
    _legacy_database(source)
    migrate(source, target)
    conn = duckdb.connect(str(source))
    published = dt.datetime(2026, 9, 4, 12, 0)
    conn.execute("INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?)", [
        "doc-2", "official-test", "https://e/2", "second", "en", published,
        None, "p1", 6,
    ])
    conn.execute("INSERT INTO segments VALUES (?,?,?,?,?,?,?,?,?,?)", [
        "doc-2#p0.s0", "doc-2", "sentence", "second", 0, 6, 0, 6, 0, "p1",
    ])
    conn.close()

    result = migrate(source, target)

    assert result["visible_documents"] == result["visible_segments"] == 2


def test_migration_rebuilds_equal_count_target_with_divergent_content(tmp_path):
    source, target = tmp_path / "oc.duckdb", tmp_path / "iceberg"
    _legacy_database(source)
    migrate(source, target)
    conn = duckdb.connect(str(source))
    conn.execute("UPDATE documents SET title = 'corrected' WHERE doc_id = 'doc-1'")
    conn.execute("UPDATE segments SET text = 'edit' WHERE segment_id = 'doc-1#p0.s0'")
    conn.close()

    migrate(source, target)

    zone = NormalizedZone(target)
    try:
        assert zone.documents()[0]["title"] == "corrected"
        assert zone.segments("doc-1")[0]["text"] == "edit"
    finally:
        zone.close()


def test_migration_fails_when_imported_content_digest_does_not_match(
        tmp_path, monkeypatch):
    source, target = tmp_path / "oc.duckdb", tmp_path / "iceberg"
    _legacy_database(source)
    original = NormalizedZone.append_arrow

    def corrupt_document_title(zone, table_name, batch):
        data = pa.Table.from_batches([batch]) if isinstance(batch, pa.RecordBatch) else batch
        if table_name == "documents":
            index = data.schema.get_field_index("title")
            data = data.set_column(
                index, data.schema.field(index), pa.array(["CORRUPTED"] * data.num_rows))
        original(zone, table_name, data)

    monkeypatch.setattr(NormalizedZone, "append_arrow", corrupt_document_title)

    with pytest.raises(RuntimeError, match="normalized migration content mismatch"):
        migrate(source, target)
