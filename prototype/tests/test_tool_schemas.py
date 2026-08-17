"""tool JSON schema — Structured Output 계약 명시·검증 (design 07 §7, blueprint §15) TDD.

Phase 6(Stable 운용) deferred 항목 해소 — 07 §7 "각 tool별 구체 JSON schema 본문은
미확정"이 실제로는 **이미 추출·판정 골든으로 검증된 코드**에 존재함을 정직히 정리
(측정 없는 확정 금지 §20 에 부합 — 골든 검증된 contract). 4 tool 계열 스키마를
**명시적 JSON Schema + 검증기**로 공개 계약으로 봉인:

- Extractor claim (05 §6·03 §4.2, provenance ADR-305)
- canonical verdict (07 §4.2 7라벨)
- contradiction verdict (07 §5.2)
- synthesis report (07 §3.8/§9)

read-only(불변식 §3-3)·결정성·honest-gap 원칙 (Phase 6 전 작업과 동일).
"""
from __future__ import annotations

from orc_citadel.tool_schemas import (
    CANONICAL_RELATIONS,
    CLAIM_CANDIDATE_SCHEMA,
    CONFLICT_TYPES,
    CONTRADICTION_VERDICTS,
    CONTRADICTION_VERDICT_SCHEMA,
    CANONICAL_VERDICT_SCHEMA,
    OUTPUT_SCHEMA_VERSION,
    SYNTHESIS_REPORT_SCHEMA,
    validate_canonical_verdict,
    validate_claim_candidate,
    validate_contradiction_verdict,
    validate_synthesis_report,
)

# --- extractor claim schema -----------------------------------------------------


def _valid_claim() -> dict:
    return {
        "claim_candidate_id": "c-1", "doc_id": "d1", "predicate": "supplies",
        "subject_id": "TSMC", "modality": "asserted", "polarity": "positive",
        "confidence": 0.85, "seg_order": 0, "char_start": 10, "char_end": 40,
        "surface_fragment": "TSMC supplies", "provenance_ref": ["rec-1"],
    }


def test_claim_valid():
    """유효 claim candidate → valid=True."""
    assert validate_claim_candidate(_valid_claim())["valid"] is True


def test_claim_missing_field():
    """필수 필드 부재 → missing 이유 (read-only·결정적)."""
    d = _valid_claim()
    del d["subject_id"]
    r = validate_claim_candidate(d)
    assert r["valid"] is False and "subject_id" in r["reason"]


def test_claim_confidence_range():
    """confidence ∉[0,1] → invalid (범위 계약)."""
    d = _valid_claim()
    d["confidence"] = 1.5
    assert validate_claim_candidate(d)["valid"] is False


def test_claim_provenance_type():
    """provenance_ref 는 list[str] (ADR-305 — authoritative 진입 전 필수)."""
    d = _valid_claim()
    d["provenance_ref"] = "rec-1"  # str 아님
    assert validate_claim_candidate(d)["valid"] is False
    d["provenance_ref"] = ["rec-1"]
    assert validate_claim_candidate(d)["valid"] is True


def test_claim_schema_version_carried():
    """공개 스키마가 output_schema_version 부착 (07 §7 버전 관리)."""
    assert CLAIM_CANDIDATE_SCHEMA["output_schema_version"] == OUTPUT_SCHEMA_VERSION


# --- canonical verdict schema ---------------------------------------------------


def test_canonical_valid():
    """유효 canonical 판정 → valid (7라벨 relation, confidence ∈[0,1])."""
    for rel in CANONICAL_RELATIONS:
        d = {"relation": rel, "canonical_text": "t", "confidence": 0.9}
        assert validate_canonical_verdict(d)["valid"] is True


def test_canonical_relation_enum():
    """relation 이 7라벨 밖 → 인식 불가 (enum 계약)."""
    d = {"relation": "not_a_relation", "canonical_text": "t", "confidence": 0.9}
    r = validate_canonical_verdict(d)
    assert r["valid"] is False and "relation" in r["reason"]


def test_canonical_confidence_range():
    """confidence ∈[0,1] 계약 (1.1 → invalid)."""
    d = {"relation": "supports", "canonical_text": "t", "confidence": 1.1}
    assert validate_canonical_verdict(d)["valid"] is False


def test_canonical_missing_required():
    """필수 필드 부재 → missing 이유."""
    d = {"relation": "supports"}
    r = validate_canonical_verdict(d)
    assert r["valid"] is False and "confidence" in r["reason"]


# --- contradiction verdict schema -----------------------------------------------


def test_contradiction_valid():
    """유효 contradiction 판정 → valid (verdict/conflict_type/rationale/confidence)."""
    for v in CONTRADICTION_VERDICTS:
        d = {"verdict": v, "conflict_type": "temporal", "rationale": "r",
             "confidence": 0.8}
        assert validate_contradiction_verdict(d)["valid"] is True


def test_contradiction_rationale_required():
    """rationale 는 필수·비어있지 않음 (07 §5.3)."""
    d = {"verdict": "real_conflict", "rationale": "   ", "confidence": 0.8}
    assert validate_contradiction_verdict(d)["valid"] is False


def test_contradiction_conflict_type_enum():
    """conflict_type 존재 시 enum (CONFLICT_TYPES) 계약."""
    d = {"verdict": "real_conflict", "conflict_type": "not_a_type",
         "rationale": "r", "confidence": 0.8}
    r = validate_contradiction_verdict(d)
    assert r["valid"] is False and "conflict_type" in r["reason"]


def test_contradiction_verdict_enum():
    """verdict enum (CONTRADICTION_VERDICTS) 계약."""
    d = {"verdict": "maybe", "rationale": "r", "confidence": 0.8}
    assert validate_contradiction_verdict(d)["valid"] is False


# --- synthesis report schema ----------------------------------------------------


def test_report_valid():
    """유효 조사 report → valid (evidence-first shape)."""
    d = {"subject_id": "TSMC",
         "conclusion": {"value": 0.8, "dimensions": {}},
         "statements": [{"text": "s", "modality": "asserted", "claim_ref": "c-1"}],
         "open_questions": [{"subquestion": "q", "reason": "증거 부족"}],
         "audit": {"passed": True}}
    assert validate_synthesis_report(d)["valid"] is True


def test_report_type_contract():
    """conclusion/statements/etc 는 dict/list 계약."""
    d = {"subject_id": "TSMC", "conclusion": [],
         "statements": [], "open_questions": []}
    r = validate_synthesis_report(d)
    assert r["valid"] is False and "conclusion" in r["reason"]


def test_report_missing_required():
    """subject_id 부재 → missing 이유."""
    d = {"conclusion": {}, "statements": [], "open_questions": []}
    r = validate_synthesis_report(d)
    assert r["valid"] is False and "subject_id" in r["reason"]


# --- 인벤토리 / read-only / 결정성 ----------------------------------------------


def test_all_schemas_inventory():
    """4 tool 스키마 인벤토리 — 각각 output_schema_version 부착."""
    from orc_citadel.tool_schemas import all_tool_schemas
    inv = all_tool_schemas()
    assert set(inv) == {"extractor_claim", "canonical_verdict",
                        "contradiction_verdict", "synthesis_report"}
    assert all(s["output_schema_version"] == OUTPUT_SCHEMA_VERSION
               for s in inv.values())


def test_tool_schemas_read_only():
    """검증기 입력 dict 를 변경하지 않음 (read-only 불변식 §3-3)."""
    d = _valid_claim()
    snap = dict(d)
    validate_claim_candidate(d)
    assert d == snap
    r = _valid_claim()
    r["object_id"] = "X"
    validate_claim_candidate(r)
    assert r["object_id"] == "X"


def test_tool_schemas_deterministic():
    """동일 입력 → 동일 판정 (결정적)."""
    d = _valid_claim()
    assert validate_claim_candidate(d) == validate_claim_candidate(d)
    c = {"relation": "supports", "canonical_text": "t", "confidence": 0.9}
    assert validate_canonical_verdict(c) == validate_canonical_verdict(c)
