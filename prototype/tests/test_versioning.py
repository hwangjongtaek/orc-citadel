"""S40 5축 version-aware 승격 (설계 10 §3.1, 03 §7.1, README §2.3) TDD.

version 5축 tuple (ontology_version/schema_version/prompt_template_hash/model_id/
extraction_code_version)을 승격 baseline 키·판정에 반영.

- fingerprint: 5축 dict → 결정적 `vt-` ID (순서 무관).
- ontology_major_bump: 02 §6.3 — major(타입 제거·의미 변경)면 전량 재평가 필요.
- same_axis: 특정 축만 변경 여부 (부분 재평가 감지, 10 §3.1).

Atomic TDD: Red → Green → Refactor.
"""
from __future__ import annotations

import pytest

from orc_citadel.versioning import (fingerprint, ontology_major_bump, same_axis)


VT = {
    "ontology_version": "1.0.0",
    "schema_version": "0.1.0",
    "prompt_template_hash": "sha256:abc",
    "model_id": "claude-opus-4-8",
    "extraction_code_version": "p1",
}


# --- fingerprint -----------------------------------------------------------

def test_fingerprint_deterministic_order_independent():
    """같은 5축 dict → 같은 vt- ID (순서 무관)."""
    import json
    a = fingerprint(VT)
    b = fingerprint(dict(reversed(list(VT.items()))))
    assert a == b
    assert a.startswith("vt-")
    assert len(a) > len("vt-")


def test_fingerprint_differs_on_any_axis():
    """한 축이라도 바뀌면 다른 ID."""
    a = fingerprint(VT)
    b = fingerprint(dict(VT, model_id="claude-haiku-4-5"))
    assert a != b


def test_fingerprint_short_hash():
    """결정적 sha256·짧은 접두."""
    a = fingerprint(VT)
    b = fingerprint(VT)
    assert a == b  # 재결정.


# --- ontology_major_bump ----------------------------------------------------

def test_major_bump_true():
    """1.0.0→2.0.0 (타입 제거·의미 변경) → major."""
    assert ontology_major_bump("1.0.0", "2.0.0") is True


def test_minor_bump_false():
    """1.0.0→1.1.0 (predicate 추가 등 하위호환) → minor."""
    assert ontology_major_bump("1.0.0", "1.1.0") is False


def test_same_version_false():
    """동일 → no bump."""
    assert ontology_major_bump("1.0.0", "1.0.0") is False


def test_patch_bump_false():
    """1.0.0→1.0.1 (패치) → minor/no — major 아님."""
    assert ontology_major_bump("1.0.0", "1.0.1") is False


# --- same_axis -------------------------------------------------------------

def test_same_axis_true_when_only_that_changes():
    """model_id만 변경 → same_axis('model_id') True, 다른 축 False."""
    v2 = dict(VT, model_id="claude-haiku-4-5")
    assert same_axis(VT, v2, "model_id") is True


def test_same_axis_false_when_other_changes():
    """model_id 변경 + extraction 변경 → same_axis('model_id') False."""
    v2 = dict(VT, model_id="claude-haiku-4-5", extraction_code_version="p2")
    assert same_axis(VT, v2, "model_id") is False


def test_same_axis_identical_none():
    """동일 5축 → 변경 없음 (어떤 축도 '유일 변경' 아님)."""
    assert same_axis(VT, VT, "model_id") is False
    assert same_axis(VT, VT, "ontology_version") is False


def test_same_axis_true_single_change():
    """model_id만 변경 + 다른 축 동일 → same_axis('model_id') True."""
    v2 = dict(VT, model_id="claude-haiku-4-5")
    assert same_axis(VT, v2, "model_id") is True
    assert same_axis(VT, v2, "ontology_version") is False


# --- version 봉인 (MVP #10) ----------------------------------------------

from orc_citadel.versioning import (
    VERSION_AXES, VERSION_TUPLE, extraction_version_tuple, version_guard,
)


def test_extraction_version_tuple_matches_sealed():
    """파이프라인 버전 tuple 이 봉인 상수의 5축 전체와 일치 (03 §7.1)."""
    vt = extraction_version_tuple()
    assert set(vt) == set(VERSION_AXES)
    assert vt == VERSION_TUPLE
    assert set(vt) == {"ontology_version", "schema_version",
                       "prompt_template_hash", "model_id",
                       "extraction_code_version"}


def test_extraction_version_tuple_is_fresh_copy():
    """호출부가 상수를 변조해도 봉인이 유지 — 새 dict 반환(불변식)."""
    vt = extraction_version_tuple()
    vt["model_id"] = "tampered"
    # 상수는 변조 불가, 재호출은 원래 봉인값.
    assert VERSION_TUPLE["model_id"] != "tampered"
    assert extraction_version_tuple()["model_id"] == VERSION_TUPLE["model_id"]


def test_version_guard_accepts_sealed():
    """봉인 상수와 일치하는 5축 → 유효 (재추출·오염 없이 사용 가능)."""
    assert version_guard(extraction_version_tuple()) is True
    assert version_guard(VERSION_TUPLE) is True


def test_version_guard_rejects_drift():
    """봉인 상수에서 벗어난 축(하드코딩 파편·무단 변경) → 감지 (02 §6.3)."""
    assert version_guard({}) is False  # 빈 dict.
    assert version_guard(dict(VERSION_TUPLE, ontology_version="2.0.0")) is False
    assert version_guard(dict(VERSION_TUPLE, model_id="other")) is False
    assert version_guard({k: VERSION_TUPLE[k] for k in
                          ("ontology_version", "schema_version")}) is False


def test_version_guard_rejects_unknown_axis():
    """미등록 축 추가 → 부적절 (불완전 tuple 부착 금지)."""
    vt = dict(extraction_version_tuple(), extra_axis="x")
    assert version_guard(vt) is False
