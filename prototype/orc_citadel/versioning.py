"""S40 5축 version 유틸 (설계 03 §7.1, 10 §3.1, README §2.3).

version 5축 tuple (ontology_version/schema_version/prompt_template_hash/model_id/
extraction_code_version)을 승격 baseline 키·판정에 반영.

- fingerprint: 5축 dict → 결정적 `vt-` ID (순서 무관).
- ontology_major_bump: 02 §6.3 — major(타입 제거·의미 변경)면 전량 재평가 필요.
- same_axis: 특정 축만 변경 여부 (10 §3.1 부분 재평가 감지).
"""
from __future__ import annotations

import hashlib

# 5축 키 — version_tuple 정본 (03 §7.1, README §2.3).
VERSION_AXES = ("ontology_version", "schema_version", "prompt_template_hash",
                "model_id", "extraction_code_version")


def fingerprint(vt: dict) -> str:
    """5축 dict → 결정적 `vt-` ID (키 순서 무관)."""
    key = "|".join(f"{k}={vt.get(k, '')}" for k in VERSION_AXES)
    return "vt-" + hashlib.sha256(key.encode()).hexdigest()[:24]


def _parts(v: str) -> tuple:
    try:
        return tuple(int(p) for p in v.split(".")[:2])  # major, minor.
    except (ValueError, AttributeError):
        return (0, 0)


def ontology_major_bump(prev: str, cur: str) -> bool:
    """semver major 증가(2.0.0 vs 1.0.0) — 전량 재평가 필요 (02 §6.3, ADR-1005)."""
    return _parts(cur)[0] > _parts(prev)[0]


def same_axis(prev: dict, cur: dict, axis: str) -> bool:
    """prev→cur 에서 해당 축만 변경됐는지 (부분 재평가 감지, 10 §3.1)."""
    if axis not in VERSION_AXES:
        return False
    changed = {k for k in VERSION_AXES if prev.get(k) != cur.get(k)}
    return changed == {axis}
