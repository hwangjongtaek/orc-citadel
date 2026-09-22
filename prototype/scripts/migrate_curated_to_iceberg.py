"""Bounded one-shot migration from legacy curated DuckDB to curated Iceberg."""
from __future__ import annotations

import argparse
import pathlib
import sys

import duckdb
import pyarrow as pa

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from orc_citadel.curated_zone import CuratedZone  # noqa: E402
from orc_citadel.dedup import DEDUP_VERSION  # noqa: E402
from scripts.migrate_normalized_to_iceberg import _digest_batches, _query_digest  # noqa: E402

BATCH_SIZE = 10_000
TABLES = (
    "mentions", "dup_signatures", "dup_bands", "dup_clusters", "entities",
    "claim_candidates", "canonical_claims", "member_of", "conflict_candidates",
    "assertions", "authoritative_edges", "canonical_llm_records",
    "conflict_verdicts", "golden_pairs", "golden_entity_pairs",
    "golden_lineage_pairs", "promotion_baselines", "extraction_records",
)
ORDER_BY = {
    "mentions": "mention_id",
    "dup_signatures": "doc_id, dedup_version",
    "dup_bands": "doc_id, dedup_version, band_idx",
    "dup_clusters": "cluster_id",
    "entities": "entity_id",
    "claim_candidates": "claim_candidate_id",
    "canonical_claims": "canonical_claim_id",
    "member_of": "claim_id, canonical_claim_id",
    "conflict_candidates": "claim_id_a, claim_id_b",
    "assertions": "assertion_id",
    "authoritative_edges": "edge_id",
    "canonical_llm_records": "claim_id_a, claim_id_b",
    "conflict_verdicts": "claim_id_a, claim_id_b",
    "golden_pairs": "golden_id",
    "golden_entity_pairs": "golden_id",
    "golden_lineage_pairs": "golden_id",
    "promotion_baselines": "baseline_id",
    "extraction_records": "extraction_id",
}


def _source_tables(conn) -> set[str]:
    return {row[0] for row in conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
    ).fetchall()}


def _source_counts(conn, source_tables: set[str]) -> dict[str, int]:
    return {
        name: (conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
               if name in source_tables else 0)
        for name in TABLES
    }


def _source_state(conn, zone: CuratedZone,
                  source_tables: set[str]) -> tuple[dict[str, int], dict[str, str]]:
    counts = _source_counts(conn, source_tables)
    digests: dict[str, str] = {}
    streamed: dict[str, int] = {}
    for name in TABLES:
        columns = tuple(zone.columns(name))
        if name not in source_tables:
            count, digest = _digest_batches((), columns)
        else:
            selected = ", ".join(f'"{column}"' for column in columns)
            count, digest = _query_digest(
                conn,
                f'SELECT {selected} FROM "{name}" ORDER BY {ORDER_BY[name]}',
                columns,
            )
        streamed[name] = count
        digests[name] = digest
    if streamed != counts:
        raise RuntimeError(
            f"curated migration source query mismatch: source={counts}, streamed={streamed}")
    return counts, digests


def _target_state(zone: CuratedZone) -> tuple[dict[str, int], dict[str, str]]:
    counts: dict[str, int] = {}
    digests: dict[str, str] = {}
    sorter = duckdb.connect()
    try:
        sorter.execute("SET memory_limit = '128MB'")
        for name in TABLES:
            columns = tuple(zone.columns(name))
            sorter.register(
                "migration_target",
                zone._table(name).scan(selected_fields=columns).to_arrow_batch_reader(),
            )
            selected = ", ".join(f'"{column}"' for column in columns)
            count, digest = _query_digest(
                sorter,
                f"SELECT {selected} FROM migration_target ORDER BY {ORDER_BY[name]}",
                columns,
            )
            sorter.unregister("migration_target")
            counts[name] = count
            digests[name] = digest
    finally:
        sorter.close()
    return counts, digests


def _import_table(conn, zone: CuratedZone, name: str) -> int:
    columns = zone.columns(name)
    selected = ", ".join(f'"{column}"' for column in columns)
    sql = f'SELECT {selected} FROM "{name}" ORDER BY {ORDER_BY[name]}'
    total = 0
    for batch in conn.execute(sql).to_arrow_reader(BATCH_SIZE):
        data = pa.Table.from_batches([batch])
        if name == "mentions":
            data = data.append_column(
                "_dedup_version", pa.array([DEDUP_VERSION] * data.num_rows, type=pa.string()))
        zone.append_arrow(name, data)
        total += data.num_rows
    return total


def migrate(source: pathlib.Path | str, target: pathlib.Path | str) -> dict[str, dict[str, int]]:
    """Rebuild a partial/divergent target, or no-op when all table contents match."""
    source = pathlib.Path(source)
    if not source.is_file():
        raise FileNotFoundError(source)
    conn = duckdb.connect(str(source), read_only=True)
    zone = CuratedZone(target)
    try:
        zone.initialize()
        source_tables = _source_tables(conn)
        source_counts, source_digests = _source_state(conn, zone, source_tables)
        visible = zone.counts()
        streamed_visible, visible_digests = _target_state(zone)
        if (visible == source_counts == streamed_visible
                and visible_digests == source_digests):
            return {"source": source_counts, "visible": visible}
        if any(visible.values()):
            zone.reset()
        imported = {
            name: (_import_table(conn, zone, name) if name in source_tables else 0)
            for name in TABLES
        }
        visible = zone.counts()
        streamed_visible, visible_digests = _target_state(zone)
        if (imported != source_counts or visible != source_counts
                or streamed_visible != source_counts or visible_digests != source_digests):
            raise RuntimeError(
                "curated migration content mismatch: "
                f"source_counts={source_counts}, imported={imported}, visible={visible}, "
                f"streamed_visible={streamed_visible}, "
                f"source_digests={source_digests}, visible_digests={visible_digests}")
        return {"source": source_counts, "visible": visible}
    finally:
        zone.close()
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=pathlib.Path,
                        default=ROOT / "data" / "curated.duckdb")
    parser.add_argument("--target", type=pathlib.Path, default=ROOT / "data" / "iceberg")
    args = parser.parse_args()
    print(migrate(args.source, args.target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
