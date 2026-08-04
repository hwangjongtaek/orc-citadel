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
    assert "entities" in zone.tables()
    assert "claim_candidates" in zone.tables()
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
    assert "entities.parquet" in names
    assert "dup_clusters.parquet" in names


# --- 해소 영속 (S6) ----------------------------------------------------------

def test_persist_entity_query(zone):
    from orc_citadel.resolve import Entity
    e = Entity(
        entity_id="org-abc", mention_type="Organization",
        canonical_name="NVIDIA", identifiers={"ticker": "NVDA"},
        surface_forms=("NVIDIA", "NVDA"),
    )
    zone.persist_entity(e)
    rows = zone.entities()
    assert len(rows) == 1
    assert rows[0]["canonical_name"] == "NVIDIA"
    assert rows[0]["identifiers"]["ticker"] == "NVDA"
    assert rows[0]["surface_forms"] == ["NVIDIA", "NVDA"]


# --- claim_candidates (S7) ---------------------------------------------------

def test_persist_claim_query(zone):
    from orc_citadel.extract_claims import ClaimCandidate, claim_id_for
    c = ClaimCandidate(
        claim_candidate_id=claim_id_for("doc-x", 0, 0, 12, "announces"),
        doc_id="doc-x", predicate="announces", subject_id="org-abc",
        object_id=None, object_literal=None, modality="asserted",
        polarity="positive", confidence=0.8, seg_order=0, char_start=0, char_end=12,
        surface_fragment="will host", event_type_hint="earnings", status="candidate",
    )
    zone.persist_claim(c)
    rows = zone.claims("doc-x")
    assert len(rows) == 1
    r = rows[0]
    assert r["predicate"] == "announces"
    assert r["subject_id"] == "org-abc"
    assert r["event_type_hint"] == "earnings"
    assert r["status"] == "candidate"


def test_persist_claim_idempotent(zone):
    from orc_citadel.extract_claims import ClaimCandidate, claim_id_for
    mk = lambda: ClaimCandidate(
        claim_candidate_id=claim_id_for("doc-y", 1, 5, 9, "announces"),
        doc_id="doc-y", predicate="announces", subject_id="org-1",
        object_id=None, object_literal=None, modality="asserted",
        polarity="positive", confidence=0.8, seg_order=1, char_start=5, char_end=9,
        surface_fragment="webcast", event_type_hint="earnings", status="candidate",
    )
    for _ in range(2):
        zone.persist_claim(mk())
    assert len(zone.claims("doc-y")) == 1


def test_export_parquet_includes_claims(zone, tmp_path):
    from orc_citadel.extract_claims import ClaimCandidate, claim_id_for
    zone.persist_claim(ClaimCandidate(
        claim_candidate_id=claim_id_for("doc-z", 0, 0, 4, "announces"),
        doc_id="doc-z", predicate="announces", subject_id="org-z",
        object_id=None, object_literal=None, modality="asserted",
        polarity="positive", confidence=0.8, seg_order=0, char_start=0, char_end=4,
        surface_fragment="host", event_type_hint="earnings", status="candidate",
    ))
    out = tmp_path / "pq"
    zone.export_parquet(str(out))
    names = sorted(p.name for p in out.glob("*.parquet"))
    assert "claim_candidates.parquet" in names


def test_persist_resolved_updates_mentions(zone):
    """persist_resolved → mention.resolved_entity_id 반영 (설계 05 §1.2)."""
    from orc_citadel.extract import extract_mentions
    from orc_citadel.parse import ParsedDoc
    from orc_citadel.identity import doc_id_for
    from orc_citadel.resolve import EntityResolver

    text = "NVIDIA (NASDAQ: NVDA) leads."
    doc_id = doc_id_for(text.encode())
    doc = ParsedDoc(text=text, title="")
    ms = extract_mentions(doc_id, doc, parse_document(doc_id, doc))
    for m in ms:
        zone.persist_mention(m)
    entities, resolved = EntityResolver().resolve(doc_id, ms)
    for e in entities:
        zone.persist_resolved(e, resolved)

    rows = zone.mentions(doc_id)
    filled = [r for r in rows if r["resolved_entity_id"]]
    # NVIDIA(+NVDA) mention들이 모두 한 entity로 참조.
    assert filled
    ids = {r["resolved_entity_id"] for r in filled}
    assert len(ids) == 1
    assert ids == {e.entity_id for e in entities}
