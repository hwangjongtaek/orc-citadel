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
