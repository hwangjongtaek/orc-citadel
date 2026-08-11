"""P1 저장 계층 키스톤 ③ — `extraction_records` 테이블 + provenance 게이트 (design 03 §8, ADR-305).

§8.2 `extraction_records` 를 curated zone에 영속하고, authoritative graph 진입 게이트가
**provenance_ref(=extraction_id[]) 가 없으면 quarantine** 을 강제한다 (ADR-305, 불변식 §3-2).
모델이 생성한 신규 사실은 source span 없이 저장하지 않는다 (blueprint §13).

§8.2 스키마:
  extraction_id(ele), element_id, doc_id, segment_id, char_start/end,
  content_hash, fetched_at, published_at, model_id, prompt_template_hash,
  schema_version, preprocess_code_version, review_history[]
"""
from __future__ import annotations

import pytest

from orc_citadel.curated_zone import CuratedZone
from orc_citadel.extract_claims import ClaimCandidate, claim_id_for
from orc_citadel.gate import Gate


def _claim(provenance_ref: list[str] | None = None) -> ClaimCandidate:
    """기본적으로 provenance(추출 기록 1개) 존재 → promote 기대 유지."""
    return ClaimCandidate(
        claim_candidate_id=claim_id_for("doc-1", 0, 0, 12, "announces"),
        doc_id="doc-1", predicate="announces", subject_id="org-abc",
        object_id=None, object_literal=None, modality="asserted",
        polarity="positive", confidence=0.8, seg_order=0,
        char_start=0, char_end=12, surface_fragment="will host",
        event_type_hint="earnings", status="candidate",
        provenance_ref=provenance_ref if provenance_ref is not None else ["ext-1"],
    )


@pytest.fixture()
def zone():
    z = CuratedZone()
    z.initialize()
    return z


# ---- §8.2 extraction_records persist ----
def test_extraction_records_table_schema(zone):
    """§8.2 정본 컬럼이 모두 존재 (추출 기록 영속 계약)."""
    cols = {r[0] for r in zone._conn.execute("DESCRIBE extraction_records").fetchall()}
    expected = {
        "extraction_id", "element_id", "doc_id", "segment_id",
        "char_start", "char_end", "content_hash", "fetched_at",
        "published_at", "model_id", "prompt_template_hash",
        "schema_version", "preprocess_code_version",
    }
    assert expected <= cols


def test_persist_and_query_extraction_record(zone):
    """persist 후 조회 round-trip — element_id → extraction_id 매핑 (§8.1)."""
    zone.persist_extraction_record(
        element_id="clm-1", doc_id="doc-1", segment_id="doc-1#p0.s0",
        char_start=0, char_end=12, content_hash="sha256:abc",
        fetched_at="2026-08-11T00:00:00Z", model_id="det",
    )
    recs = zone.extraction_records()
    assert len(recs) == 1
    r = recs[0]
    assert r["extraction_id"].startswith("ext-")
    assert r["element_id"] == "clm-1"
    assert r["doc_id"] == "doc-1"
    assert (r["char_start"], r["char_end"]) == (0, 12)
    assert r["content_hash"] == "sha256:abc"


def test_persist_is_idempotent_same_element(zone):
    """동일 element 동일 record — 중복 행 없음 (불변식 §3-6)."""
    zone.persist_extraction_record(element_id="clm-1", doc_id="d", segment_id="s",
                                   char_start=0, char_end=1)
    zone.persist_extraction_record(element_id="clm-1", doc_id="d", segment_id="s",
                                   char_start=0, char_end=1)
    assert len(zone.extraction_records()) == 1


def test_has_extraction_record(zone):
    """has — 게이트가 extraction 기록 존재를 확인하는 근거."""
    zone.persist_extraction_record(element_id="clm-1", doc_id="d", segment_id="s",
                                   char_start=0, char_end=1)
    assert zone.has_extraction_record("clm-1")
    assert not zone.has_extraction_record("clm-missing")


# ---- §8.3 provenance 게이트 (ADR-305) ----
def test_gate_quarantines_claim_without_provenance(zone):
    """provenance_ref 없는 claim → quarantine (missing_provenance_record) (ADR-305)."""
    gate = Gate()
    c = _claim(provenance_ref=[])
    result = gate.evaluate(c)
    assert not result.promote
    assert result.status == "quarantined"
    assert "missing_provenance_record" in result.reasons


def test_gate_promotes_claim_with_provenance(zone):
    """provenance_ref(=extraction_id[]) 있는 claim → promote (불변식 §3-2 통과)."""
    gate = Gate()
    c = _claim(provenance_ref=["ext-1"])
    result = gate.evaluate(c)
    assert result.promote
    assert result.status == "promoted"
