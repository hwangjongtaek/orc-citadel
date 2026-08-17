"""Structured Output 계약 스키마 — tool별 JSON schema 명시·검증 (design 07 §7).

07 §7 "각 tool별 구체 JSON schema 본문은 미확정"이라 했으나, 실제로 3개 tool 계열
스키마는 이미 추출·판정 goldlen 으로 검증된 코드에 존재한다 (측정 없는 확정 금지
blueprint §20 에 부합 — 골든 검증된 contract). 이 모듈은 그 스키마를 **명시적
JSON Schema 정의 + 검증기** 로 공개 계약으로 봉인한다:

- **Extractor claim schema** — `CLAIM_CANDIDATE_SCHEMA` (05 §6·03 §4.2,
  `extract_claims.ClaimCandidate.to_row`)
- **Canonical verdict schema** — `CANONICAL_VERDICT_SCHEMA` (07 §4.2 7라벨,
  `llm_judge.validate_canonical_verdict` — relation enum·confidence ∈[0,1])
- **Contradiction verdict schema** — `CONTRADICTION_VERDICT_SCHEMA` (07 §5.2,
  `llm_judge.validate_contradiction_verdict` — verdict/conflict_type/rationale/confidence)
- **Synthesis report schema** — `SYNTHESIS_REPORT_SCHEMA` (07 §3.8/§9,
  `synthesis.SynthesisReport` — subject_id/conclusion/statements/open_questions/audit)

각 계약은 `output_schema_version="1.0.0"` 으로 버전 관리 (07 §7 — 저장 스키마 [03] 과
정합, contract test 대상, blueprint §15). 검증은 read-only·결정적 — 산출 실패 시
quarantine 으로 보낸다(07 §7, → 05/06). 변경 시 Spec version 증가 + ROADMAP.
"""
from __future__ import annotations

# 07 §7 — tool 산출 스키마 버전 (확정 계약). 저장 스키마 [03] 과 정합 유지.
OUTPUT_SCHEMA_VERSION = "1.0.0"

# 07 §4.2 canonical relation 7라벨 (llm_judge.CANONICAL_RELATIONS 와 동일).
CANONICAL_RELATIONS = {
    "equivalent", "more_specific", "more_general", "supports",
    "contradicts", "unrelated", "temporally_superseded",
}
# 07 §5.2 contradiction verdict·conflict_type (llm_judge 와 동일).
CONTRADICTION_VERDICTS = {"real_conflict", "temporal", "scope", "not_conflict"}
CONFLICT_TYPES = {"value_conflict", "temporal", "scope"}
# 02 §2.2 mention_type 유효 어휘 (extract/gate 와 동일).
VALID_MENTION_TYPES = {
    "Person", "Organization", "Location", "Product", "Technology",
    "Event", "Source",
}

# --- 검증기 (read-only·결정적, 실패 시 이유 반환) -------------------------------


def _missing(required: list[str], d: dict) -> list[str]:
    return [k for k in required if k not in d or d[k] is None]


def _in_range(conf, lo: float = 0.0, hi: float = 1.0) -> bool:
    return isinstance(conf, (int, float)) and lo <= conf <= hi


def _in_enum(v, allowed: set) -> bool:
    return isinstance(v, str) and v in allowed


def validate_claim_candidate(d: dict) -> dict:
    """Extractor claim candidate 스키마 검증 (07 §7, 05 §6 — provenance 필수).

    필수: claim_candidate_id·doc_id·predicate·subject_id·modality·polarity·confidence·
    seg_order·char_start·char_end·surface_fragment. confidence ∈[0,1]. optional:
    object_id/object_literal/provenance_ref(provenance 는 ADR-305 게이트가 필수).
    반환 {valid, reason|None} — read-only·결정적.
    """
    req = ["claim_candidate_id", "doc_id", "predicate", "subject_id",
           "modality", "polarity", "confidence", "seg_order",
           "char_start", "char_end", "surface_fragment"]
    miss = _missing(req, d)
    if miss:
        return {"valid": False, "reason": f"missing: {sorted(miss)}"}
    if not _in_range(d["confidence"]):
        return {"valid": False, "reason": "confidence not in [0,1]"}
    if "provenance_ref" in d and d["provenance_ref"] is not None:
        if not isinstance(d["provenance_ref"], list) or not all(
                isinstance(x, str) for x in d["provenance_ref"]):
            return {"valid": False, "reason": "provenance_ref must be list[str]"}
    return {"valid": True, "reason": None}


def validate_canonical_verdict(d: dict) -> dict:
    """07 §4.2 canonical 판정 스키마 검증 (7라벨, confidence ∈[0,1]).

    필수: relation ∈ CANONICAL_RELATIONS·canonical_text str·confidence ∈[0,1].
    반환 {valid, reason|None}.
    """
    req = ["relation", "canonical_text", "confidence"]
    miss = _missing(req, d)
    if miss:
        return {"valid": False, "reason": f"missing: {sorted(miss)}"}
    if not _in_enum(d["relation"], CANONICAL_RELATIONS):
        return {"valid": False,
                "reason": f"relation not in {sorted(CANONICAL_RELATIONS)}"}
    if not isinstance(d["canonical_text"], str):
        return {"valid": False, "reason": "canonical_text must be str"}
    if not _in_range(d["confidence"]):
        return {"valid": False, "reason": "confidence not in [0,1]"}
    return {"valid": True, "reason": None}


def validate_contradiction_verdict(d: dict) -> dict:
    """07 §5.2 contradiction 판정 스키마 검증.

    필수: verdict ∈ CONTRADICTION_VERDICTS·rationale str(필수)·confidence ∈[0,1].
    optional: conflict_type ∈ CONFLICT_TYPES(존재 시)·evidence_spans list.
    """
    req = ["verdict", "rationale", "confidence"]
    miss = _missing(req, d)
    if miss:
        return {"valid": False, "reason": f"missing: {sorted(miss)}"}
    if not _in_enum(d["verdict"], CONTRADICTION_VERDICTS):
        return {"valid": False,
                "reason": f"verdict not in {sorted(CONTRADICTION_VERDICTS)}"}
    if not isinstance(d["rationale"], str) or not d["rationale"].strip():
        return {"valid": False, "reason": "rationale required non-empty (07 §5.3)"}
    if not _in_range(d["confidence"]):
        return {"valid": False, "reason": "confidence not in [0,1]"}
    ct = d.get("conflict_type")
    if ct is not None and not _in_enum(ct, CONFLICT_TYPES):
        return {"valid": False, "reason": f"conflict_type not in {sorted(CONFLICT_TYPES)}"}
    return {"valid": True, "reason": None}


def validate_synthesis_report(d: dict) -> dict:
    """07 §3.8/§9 조사 report 스키마 검증 (evidence-first).

    필수: subject_id str·conclusion dict·open_questions list. statements list
    (텍스트/증거 연결 — claim_ref 는 evidence 쪽이 소유, 문장은 파생). audit dict.
    """
    req = ["subject_id", "conclusion", "statements", "open_questions"]
    miss = _missing(req, d)
    if miss:
        return {"valid": False, "reason": f"missing: {sorted(miss)}"}
    for k, t in (("conclusion", dict), ("statements", list),
                 ("open_questions", list), ("audit", dict)):
        if k in d and d[k] is not None and not isinstance(d[k], t):
            return {"valid": False, "reason": f"{k} must be {t.__name__}"}
    return {"valid": True, "reason": None}


# --- 스키마 계약 (JSON Schema 형식) ----------------------------------------------
# 공개 계약 정의 — 검증기는 위 함수들(코드 골든 반영), 이 스키마는 산출 계약의
# 사람/도구 판독용 요약 (07 §7 — [03] 저장 스키마와 정합, contract test 대상).

CLAIM_CANDIDATE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "ClaimCandidate",
    "type": "object",
    "output_schema_version": OUTPUT_SCHEMA_VERSION,
    "required": ["claim_candidate_id", "doc_id", "predicate", "subject_id",
                 "modality", "polarity", "confidence", "seg_order",
                 "char_start", "char_end", "surface_fragment"],
    "properties": {
        "claim_candidate_id": {"type": "string"},
        "doc_id": {"type": "string"},
        "predicate": {"type": "string"},
        "subject_id": {"type": "string"},
        "object_id": {"type": ["string", "null"]},
        "modality": {"type": "string"},
        "polarity": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "seg_order": {"type": "integer"},
        "char_start": {"type": "integer"},
        "char_end": {"type": "integer"},
        "surface_fragment": {"type": "string"},
        "provenance_ref": {"type": ["array", "null"], "items": {"type": "string"}},
    },
    "additionalProperties": True,  # optional 확장 허용 (어세션/버전 필드 포함).
}

CANONICAL_VERDICT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "CanonicalVerdict",
    "type": "object",
    "output_schema_version": OUTPUT_SCHEMA_VERSION,
    "required": ["relation", "canonical_text", "confidence"],
    "properties": {
        "relation": {"type": "string", "enum": sorted(CANONICAL_RELATIONS)},
        "canonical_text": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
    "additionalProperties": True,
}

CONTRADICTION_VERDICT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "ContradictionVerdict",
    "type": "object",
    "output_schema_version": OUTPUT_SCHEMA_VERSION,
    "required": ["verdict", "rationale", "confidence"],
    "properties": {
        "verdict": {"type": "string", "enum": sorted(CONTRADICTION_VERDICTS)},
        "conflict_type": {"type": ["string", "null"],
                          "enum": sorted(CONFLICT_TYPES) + [None]},
        "rationale": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "evidence_spans": {"type": ["array", "null"]},
    },
    "additionalProperties": True,
}

SYNTHESIS_REPORT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "SynthesisReport",
    "type": "object",
    "output_schema_version": OUTPUT_SCHEMA_VERSION,
    "required": ["subject_id", "conclusion", "statements", "open_questions"],
    "properties": {
        "subject_id": {"type": "string"},
        "conclusion": {"type": "object"},
        "statements": {"type": "array",
                       "items": {"type": "object",
                                 "properties": {"text": {"type": "string"},
                                                "modality": {"type": "string"},
                                                "claim_ref": {"type": ["string", "null"]}}}},
        "open_questions": {"type": "array"},
        "audit": {"type": "object"},
    },
    "additionalProperties": True,
}


def all_tool_schemas() -> dict:
    """7 §7 tool 스키마 인벤토리 (output_schema_version 부착) — read-only·결정적."""
    return {
        "extractor_claim": CLAIM_CANDIDATE_SCHEMA,
        "canonical_verdict": CANONICAL_VERDICT_SCHEMA,
        "contradiction_verdict": CONTRADICTION_VERDICT_SCHEMA,
        "synthesis_report": SYNTHESIS_REPORT_SCHEMA,
    }
