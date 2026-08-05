"""S23 LLM 판정 영속화 (설계 03 §4.2, 07 §6.1) TDD.

결정적 체인이 `ClaudeJudge`(LLM)로 미결 쌍을 판정한 결과를 version tuple과 함께
curated zone에 영속해, provenance·재실행(replay)·추적이 가능하게 한다 (불변식, 03 §7).

- `canonical_llm_records` — canonicalization 7라벨 판정 근거 + version tuple.
- `conflict_verdicts` — contradiction verdict 실체 + version tuple.
- idempotent upsert (결정적 (a,b) 쌍 PK), Parquet export 포함.
"""
from __future__ import annotations

from orc_citadel.curated_zone import CuratedZone

VERSION_TUPLE = {
    "ontology_version": "1.0.0",
    "schema_version": "0.1.0",
    "prompt_template_hash": "ph-abc123",
    "model_id": "claude-opus-4-8",
    "extraction_code_version": "c1",
}


def _zone() -> CuratedZone:
    z = CuratedZone(":memory:")
    z.initialize()
    return z


# ------------------------------------------------------- canonical LLM records

def test_persist_and_read_canonical_llm_record():
    """canonical LLM 판정 근거 + version tuple을 저장·조회."""
    z = _zone()
    z.persist_canonical_llm_record(
        claim_id_a="clm-a", claim_id_b="clm-b",
        relation="equivalent", canonical_text="CoWoS 확장",
        confidence=0.9, rationale="동일 subject·predicate·의미",
        version_tuple=VERSION_TUPLE, judged_by="llm",
    )
    rows = z.canonical_llm_records()
    assert len(rows) == 1
    r = rows[0]
    assert r["claim_id_a"] == "clm-a" and r["claim_id_b"] == "clm-b"
    assert r["relation"] == "equivalent"
    assert r["confidence"] == 0.9
    assert r["judged_by"] == "llm"
    # version tuple이 JSON으로 왕복 (dict 복원).
    assert r["version_tuple"] == VERSION_TUPLE


def test_canonical_llm_idempotent_upsert():
    """동일 (a,b) 쌍 재저장 → 1행 유지 (결정적 PK, 03 §5)."""
    z = _zone()
    z.persist_canonical_llm_record("clm-a", "clm-b", "equivalent", "t",
                                   0.9, "r", VERSION_TUPLE, "llm")
    z.persist_canonical_llm_record("clm-a", "clm-b", "unrelated", "t",
                                   0.1, "r2", VERSION_TUPLE, "llm")
    rows = z.canonical_llm_records()
    assert len(rows) == 1
    assert rows[0]["relation"] == "unrelated"  # upsert로 갱신


def test_canonical_llm_preserves_non_equivalent():
    """비-equivalent(예: unrelated)도 근거로 저장 — 병합 안 된 쌍 추적 (05 §4.2)."""
    z = _zone()
    z.persist_canonical_llm_record("clm-a", "clm-b", "unrelated", "",
                                   0.1, "무관 판정", VERSION_TUPLE, "llm")
    rows = z.canonical_llm_records()
    assert len(rows) == 1
    assert rows[0]["relation"] == "unrelated"


# --------------------------------------------------------------- conflict verdicts

def test_persist_and_read_conflict_verdict():
    """contradiction LLM verdict + version tuple 저장·조회."""
    z = _zone()
    z.persist_conflict_verdict(
        claim_id_a="clm-a", claim_id_b="clm-b",
        verdict="real_conflict", conflict_type="value_conflict",
        rationale="서로 다른 값", confidence=0.8,
        version_tuple=VERSION_TUPLE, judged_by="llm",
    )
    rows = z.conflict_verdicts()
    assert len(rows) == 1
    r = rows[0]
    assert r["verdict"] == "real_conflict"
    assert r["conflict_type"] == "value_conflict"
    assert r["judged_by"] == "llm"
    assert r["version_tuple"] == VERSION_TUPLE


def test_conflict_verdict_idempotent_upsert():
    """동일 (a,b) 쌍 재저장 → 1행 (verdict 갱신)."""
    z = _zone()
    z.persist_conflict_verdict("clm-a", "clm-b", "not_conflict", None,
                               "모순 아님", 0.85, VERSION_TUPLE, "llm")
    z.persist_conflict_verdict("clm-a", "clm-b", "real_conflict", "value_conflict",
                               "실제 모순", 0.9, VERSION_TUPLE, "llm")
    rows = z.conflict_verdicts()
    assert len(rows) == 1
    assert rows[0]["verdict"] == "real_conflict"


def test_tables_registered_and_parquet_export():
    """신규 테이블 2개 등록 + Parquet export 포함."""
    import tempfile, pathlib
    z = _zone()
    z.persist_canonical_llm_record("clm-a", "clm-b", "equivalent", "t",
                                   0.9, "r", VERSION_TUPLE, "llm")
    z.persist_conflict_verdict("clm-a", "clm-b", "real_conflict", "value_conflict",
                               "충돌", 0.8, VERSION_TUPLE, "llm")
    ts = z.tables()
    assert "canonical_llm_records" in ts
    assert "conflict_verdicts" in ts

    with tempfile.TemporaryDirectory() as d:
        z.export_parquet(d)
        files = sorted(str(p.name) for p in pathlib.Path(d).iterdir())
    assert "canonical_llm_records.parquet" in files
    assert "conflict_verdicts.parquet" in files
