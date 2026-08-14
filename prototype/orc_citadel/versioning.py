"""S40 5축 version 유틸 (설계 03 §7.1, 10 §3.1, README §2.3, ADR-1003·1005).

version 5축 tuple (ontology_version/schema_version/prompt_template_hash/model_id/
extraction_code_version)을 승격 baseline 키·판정에 반영.

- fingerprint: 5축 dict → 결정적 `vt-` ID (순서 무관).
- ontology_major_bump: 02 §6.3 — major(타입 제거·의미 변경)면 전량 재평가 필요.
- same_axis: 특정 축만 변경 여부 (10 §3.1 부분 재평가 감지).
- **version 봉인 (MVP #10):** 파이프라인 산출물에 부착되는 5축은 여기 한 곳에
  정의·밀봉한다. 버전 축이 바뀌면 (1) `VERSION_TUPLE`을 bump 하고 (2) 설계
  02 §6.3·10 §3 에 따라 회귀를 실행한다. 파이프라인은 이 상수를 하드코딩
  대신 참조하며, 미등록 축/불일치는 `extraction_version_tuple`·`version_guard`
  가 감지한다 (10 §3.1 재추출·재평가 트리거).
"""
from __future__ import annotations

import hashlib

# 5축 키 — version_tuple 정본 (03 §7.1, README §2.3).
VERSION_AXES = ("ontology_version", "schema_version", "prompt_template_hash",
                "model_id", "extraction_code_version")

# ── version 봉인 (MVP #10) ──────────────────────────────────────────────
# 파이프라인(결정적 추출 추적 포함) 산출물의 신뢰 version 상수. 각 축 변경 시
# bump + 회귀 (ADR-1003). 모듈 상수와 정합: extract 02 §2 ontology="1.0.0",
# parse 03 §5 schema, dedup 04 §4.2 dedup_version 은 별도 축(dedup/schema 개별).
SCHEMA_VERSION = "0.1.0"
ONTOLOGY_VERSION = "1.0.0"
PROMPT_TEMPLATE_HASH = ""
MODEL_ID = "deterministic"
EXTRACTION_CODE_VERSION = "p1"

# 파이프라인이 무결정적(LLM 미사용) 추출 산출물에 일괄 부착하는 version 5축.
VERSION_TUPLE: dict = {
    "ontology_version": ONTOLOGY_VERSION,
    "schema_version": SCHEMA_VERSION,
    "prompt_template_hash": PROMPT_TEMPLATE_HASH,
    "model_id": MODEL_ID,
    "extraction_code_version": EXTRACTION_CODE_VERSION,
}


def extraction_version_tuple() -> dict:
    """파이프라인 버전 5축 tuple (03 §7.1). 봉인 상수와 일치를 보장(불변식):
    새 dict 를 만들어 반환해 호출부가 상수를 변조하지 못하게 한다. version 변경
    시 이 함수의 반환값이 바뀌고, `fingerprint` 유일성·`version_guard` 가 이를
    감지한다 (MVP #10 봉인).
    """
    return {k: VERSION_TUPLE[k] for k in VERSION_AXES}


def version_guard(vt: dict) -> bool:
    """version 5축 유효성 검사 (02 §6.3, 10 §3): 미등록 축·누락 축이 없고
    봉인 상수와 일치해야 재추출·오염 없이 사용 가능하다 (MVP #10).

    - 누락/미등록 축: False (불완전 tuple 은 산출물에 부착 금지).
    - 봉인 상수와 불일치: False (하드코딩 파편 또는 무단 변경 감지).
    인자 없음(또는 5축 dict) — 파이프라인이 산출물 version 을 부착하기 전
    검사 게이트로 사용한다.
    """
    if not isinstance(vt, dict):
        return False
    if set(vt) != set(VERSION_AXES):
        return False
    return all(vt[k] == VERSION_TUPLE[k] for k in VERSION_AXES)


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
