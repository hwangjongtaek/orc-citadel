from __future__ import annotations

from datetime import datetime, timezone

import duckdb
import pyarrow as pa
import pytest

from orc_citadel.assertions import Assertion
from orc_citadel.curated_zone import CuratedZone
from orc_citadel.extract import Mention
from orc_citadel.resolve import Entity
from scripts.migrate_curated_to_iceberg import TABLES, migrate


def _legacy_source(tmp_path):
    seed = CuratedZone(tmp_path / "seed-iceberg")
    seed.initialize()
    seed.persist_mention(Mention(
        mention_id="men-1", doc_id="doc-1", segment_id="seg-1",
        surface_text="NVIDIA", mention_type="Organization", char_start=0, char_end=6,
        context_window="NVIDIA", resolved_entity_id=None,
        extraction_version={"model_id": "det", "schema_version": "1"},
    ))
    seed.persist_entity(Entity(
        entity_id="org-1", mention_type="Organization", canonical_name="NVIDIA",
        identifiers={"ticker": "NVDA"}, surface_forms=("NVIDIA", "NVDA"),
    ))
    seed.persist_signature("doc-1", [1, 2, 3], text_hash="hash-1")
    seed.persist_cluster("clus-1", "doc-1", ["doc-1"], [], "exact")
    seed.persist_assertion(Assertion(
        assertion_id="asr-1", claim_id="clm-1", subject_id="org-1",
        predicate="announces", object_id=None, object_literal="product",
        valid_from=None, valid_to=None, time_precision="unknown",
        tx_from=datetime(2026, 9, 1, tzinfo=timezone.utc), tx_to=None,
        supersedes_id=None, mutation_id="mut-1", provenance_ref=("ext-1",),
    ))
    seed.persist_canonical_llm_record(
        "clm-1", "clm-2", "same", "canonical", 0.9, "reason",
        {"model": "test"},
    )
    export = tmp_path / "legacy-parquet"
    seed.export_parquet(export)
    seed.close()

    source = tmp_path / "curated.duckdb"
    conn = duckdb.connect(str(source))
    try:
        for name in TABLES:
            path = export / f"{name}.parquet"
            conn.execute(f'CREATE TABLE "{name}" AS SELECT * FROM read_parquet(?)', [str(path)])
    finally:
        conn.close()
    return source


def test_migration_streams_all_tables_and_is_idempotent(tmp_path):
    source = _legacy_source(tmp_path)
    target = tmp_path / "iceberg"

    first = migrate(source, target)
    assert set(first["visible"]) == set(TABLES)
    assert first["visible"] == first["source"]

    zone = CuratedZone(target)
    zone.initialize()
    assert zone.entities()[0]["identifiers"] == {"ticker": "NVDA"}
    assert zone.entities()[0]["surface_forms"] == ["NVIDIA", "NVDA"]
    assert zone.assertions()[0]["provenance_ref"] == ["ext-1"]
    assert zone.assertions()[0]["tx_from"] == datetime(2026, 9, 1)
    assert zone.canonical_llm_records()[0]["version_tuple"] == {"model": "test"}
    token = zone.snapshot_token()
    zone.close()

    second = migrate(source, target)
    assert second == first
    reopened = CuratedZone(target)
    reopened.initialize()
    assert reopened.snapshot_token() == token

    # Any partial/mismatched target is rebuilt rather than mixed with source rows.
    reopened.persist_extraction_record("bogus", "doc-bogus")
    reopened.close()
    rebuilt = migrate(source, target)
    assert rebuilt["visible"] == first["source"]
    final = CuratedZone(target)
    final.initialize()
    assert not final.has_extraction_record("bogus")
    final.close()


def test_migration_rebuilds_equal_count_target_with_divergent_content(tmp_path):
    source = _legacy_source(tmp_path)
    target = tmp_path / "iceberg"
    migrate(source, target)
    zone = CuratedZone(target)
    zone.initialize()
    row = zone.entities()[0]
    row["canonical_name"] = "CORRUPTED"
    row["identifiers"] = '{"ticker": "NVDA"}'
    zone._put("entities", row, replace=True)
    zone.close()

    migrate(source, target)

    rebuilt = CuratedZone(target)
    rebuilt.initialize()
    assert rebuilt.entities()[0]["canonical_name"] == "NVIDIA"
    rebuilt.close()


def test_migration_fails_when_imported_content_digest_does_not_match(
        tmp_path, monkeypatch):
    source = _legacy_source(tmp_path)
    target = tmp_path / "iceberg"
    original = CuratedZone.append_arrow

    def corrupt_entity_name(zone, table_name, batch):
        data = pa.Table.from_batches([batch]) if isinstance(batch, pa.RecordBatch) else batch
        if table_name == "entities":
            index = data.schema.get_field_index("canonical_name")
            data = data.set_column(
                index, data.schema.field(index), pa.array(["CORRUPTED"] * data.num_rows))
        original(zone, table_name, data)

    monkeypatch.setattr(CuratedZone, "append_arrow", corrupt_entity_name)

    with pytest.raises(RuntimeError, match="curated migration content mismatch"):
        migrate(source, target)


def test_migration_treats_legacy_tables_that_were_never_created_as_empty(tmp_path):
    source = _legacy_source(tmp_path)
    conn = duckdb.connect(str(source))
    conn.execute("DROP TABLE dup_signatures")
    conn.execute("DROP TABLE dup_bands")
    conn.close()

    result = migrate(source, tmp_path / "iceberg")

    assert result["source"]["dup_signatures"] == 0
    assert result["source"]["dup_bands"] == 0
    assert result["visible"] == result["source"]
