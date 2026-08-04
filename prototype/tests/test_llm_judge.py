"""S15 LLM 판정 — 구조화 I/O 계약·검증·라우팅 (05 §4.2·§5.2) TDD.

LLM 호출은 외부 의존 — 클라이언트 인터페이스·JSON schema 계약·결정적-LLM 라우팅을
구현하고 실제 호출은 결정적 스텁으로 격리(오프라인 검증). 규칙 fast-path는 LLM을
호출하지 않고, LLM 출력 검증 실패 시 후보 유지(자동 병합 금지, ADR-507).
"""
from __future__ import annotations

import pytest

from orc_citadel.llm_judge import (
    CanonicalVerdict,
    ContradictionVerdict,
    DeterministicStub,
    validate_canonical_verdict,
    validate_contradiction_verdict,
)


# --- canonicalization I/O 계약 (05 §4.2) ------------------------------------

def test_canonical_verdict_validates_7_labels():
    """7라벨 중 하나만 유효 (equivalent/more_specific/.../temporally_superseded)."""
    valid = validate_canonical_verdict({"relation": "equivalent",
                                        "canonical_text": "X", "confidence": 0.9,
                                        "rationale": "동일"})
    assert valid.relation == "equivalent"
    # invalid label → None (후보 유지).
    assert validate_canonical_verdict({"relation": "banana", "canonical_text": "X"}) is None


def test_canonical_verdict_requires_fields():
    """필수 필드(canonical_text/relation/confidence) 없으면 검증 실패."""
    assert validate_canonical_verdict({"relation": "equivalent"}) is None  # canonical_text 없음
    assert validate_canonical_verdict({"relation": "supports", "canonical_text": "Y"}) is None  # confidence 없음


def test_canonical_verdict_confidence_range():
    """confidence ∉ [0,1] → 검증 실패 (불변식4-6)."""
    assert validate_canonical_verdict(
        {"relation": "equivalent", "canonical_text": "X", "confidence": 1.5}) is None


# --- contradiction I/O 계약 (05 §5.2) ---------------------------------------

def test_contradiction_verdict_validates():
    """verdict/conflict_type/rationale/confidence 검증."""
    ok = validate_contradiction_verdict({
        "verdict": "real_conflict", "conflict_type": "value_conflict",
        "rationale": "서로 다른 값", "confidence": 0.8,
        "evidence_spans": [{"doc_id": "doc-1", "char_start": 0, "char_end": 4}],
    })
    assert ok and ok.verdict == "real_conflict" and ok.conflict_type == "value_conflict"


def test_contradiction_verdict_rejects_invalid_conflict_type():
    assert validate_contradiction_verdict({
        "verdict": "real_conflict", "conflict_type": "nonsense",
        "rationale": "x", "confidence": 0.8,
    }) is None


def test_contradiction_verdict_rejects_invalid_verdict():
    assert validate_contradiction_verdict({
        "verdict": "maybe", "conflict_type": "value_conflict",
        "rationale": "x", "confidence": 0.8,
    }) is None


def test_contradiction_verdict_requires_rationale():
    """§5.3: rationale 필수 (판정 근거를 반드시 저장)."""
    assert validate_contradiction_verdict({
        "verdict": "real_conflict", "conflict_type": "value_conflict",
        "confidence": 0.8, "evidence_spans": [],
    }) is None


# --- 스텁 LLM (외부 의존 격리) ----------------------------------------------

def test_deterministic_stub_outputs_valid():
    """결정적 스텁은 계약-유효 출력 (오프라인 E2E)."""
    stub = DeterministicStub()
    canon = stub.judge_canonicalization(("clm-a", "clm-b"))
    assert validate_canonical_verdict(canon).relation == "unrelated"  # 규칙 미결 → 무관 후보
    cont = stub.judge_contradiction(("clm-a", "clm-b"))
    assert validate_contradiction_verdict(cont).verdict == "not_conflict"


def test_stub_returns_dict_matching_schema():
    stub = DeterministicStub()
    c = stub.judge_canonicalization(("a", "b"))
    # 스키마 키 존재 (구조화 프롬프트 계약을 스텁도 준수).
    for key in ("relation", "confidence", "rationale"):
        assert key in c
    ct = stub.judge_contradiction(("a", "b"))
    for key in ("verdict", "conflict_type", "rationale", "confidence"):
        assert key in ct
