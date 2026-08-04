"""S5 curated zone DuckDB 영속 (설계 03 §4.1 mentions, §4.3 dup_clusters) — TDD.

L1 추출 mention과 S4 dedup cluster를 curated zone에 영속·조회·Parquet export한다.
LLM 의존 해소/claim은 이 zone의 후속 소비 영역 (여기선 저장·조회 대상만).
"""
from __future__ import annotations

import pytest

from orc_citadel.curated_zone import CuratedZone
from orc_citadel.extract import Mention, extract_mentions
from orc_citadel.parse import ParsedDoc, parse_document
from orc_citadel.identity import doc_id_for


@pytest.fixture
def zone(tmp_path):
    z = CuratedZone(str(tmp_path / "curated.duckdb"))
    z.initialize()
    yield z
    z.close()


def _mentions(text: str) -> list[Mention]:
    doc_id, doc = doc_id_for(text.encode()), ParsedDoc(text=text, title="")
    return extract_mentions(doc_id, doc, parse_document(doc_id, doc))


def test_tables_created(zone):
    assert "mentions" in zone.tables()
    assert "dup_clusters" in zone.tables()


def test_persist_mentions_query(zone):
    ms = _mentions("NVIDIA and TSMC partner on advanced packaging.")
    for m in ms:
        zone.persist_mention(m)
    db_rows = zone.mentions(ms[0].doc_id)
    assert len(db_rows) >= 2
    surfaces = {r["surface_text"] for r in db_rows}
    assert {"NVIDIA", "TSMC"}.issubset(surfaces)


def test_mention_columns_schema(zone):
    ms = _mentions("NVIDIA (NASDAQ:NVDA) leads.")
    for m in ms:
        zone.persist_mention(m)
    db_rows = zone.mentions(ms[0].doc_id)
    nv = [r for r in db_rows if r["surface_text"] == "NVIDIA"][0]
    assert nv["mention_id"].startswith("men-")
    assert nv["mention_type"] == "Organization"
    assert nv["resolved_entity_id"] is None
    assert isinstance(nv["char_start"], int)
    ev = nv["extraction_version"]
    assert "model_id" in ev and "schema_version" in ev


def test_mention_idempotent(zone):
    """동일 mention 재persist → 중복 없음 (03 §5 idempotency)."""
    ms = _mentions("TSMC is the foundry leader.")
    for _ in range(2):
        for m in ms:
            zone.persist_mention(m)
    db_rows = zone.mentions(ms[0].doc_id)
    ids = {r["mention_id"] for r in db_rows}
    assert len(ids) == len(db_rows)  # PK 중복 없음


def test_persist_clusters_query(zone):
    zone.persist_cluster(
        cluster_id="clus-1",
        root_doc_id="doc-root",
        member_doc_ids=["doc-a"],
        independent_addition_doc_ids=["doc-a"],
        dedup_method="minhash",
    )
    rows = zone.clusters()
    assert len(rows) == 1
    c = rows[0]
    assert c["root_doc_id"] == "doc-root"
    assert c["member_doc_ids"] == ["doc-a"]
    assert c["dedup_method"] == "minhash"


def test_persist_clusters_idempotent(zone):
    for _ in range(2):
        zone.persist_cluster(
            cluster_id="clus-x", root_doc_id="r",
            member_doc_ids=["m"], independent_addition_doc_ids=[], dedup_method="exact",
        )
    assert len(zone.clusters()) == 1


def test_export_parquet(zone, tmp_path):
    for m in _mentions("NVIDIA and TSMC."):
        zone.persist_mention(m)
    zone.persist_cluster("c", "r", ["m"], [], "minhash")
    out = tmp_path / "pq"
    zone.export_parquet(str(out))
    names = sorted(p.name for p in out.glob("*.parquet"))
    assert "mentions.parquet" in names
    assert "dup_clusters.parquet" in names
