"""다국어 ER — 스크립트 탐지·다국어 정규화·교차-스크립트 후보 (05 §1.2 aliases·§2, ADR-507, Phase 5) TDD.

Phase 5 「다국어 ER」 — 같은 개체(기관)가 여러 언어·스크립트로 등장(example: TSMC /
台積電)할 때, **스크립트 탐지 + 다국어 정규화**를 기반으로 교차-스크립트 개체를
**후보(POSSIBLY_SAME_AS)로만 연결**한다.

- `detect_script` — 표면형 지배 스크립트 분류 (latn/cjk/other, 결정적 codepoint).
- `norm_name` — 스크립트별 결정적 다국어 정규화 (NFKC + 대소문자/발음구분부호/공백).
- `multilingual_alias_index` — caller-curated alias bridge 를 castex indexing (결정적).
- `multilingual_block_keys` — alias bridge 를 통해 **교차-스크립트로 같은 개체**를 가리키는
  후보를 같은 blocking bucket 으로 유도 (05 §2.1 blocking key `norm_name` 의 교차-스크립트 확장).
- `propose_multilingual_candidates` — 스크립트가 다른 개체 후보를 `POSSIBLY_SAME_AS`
  (kind="multilingual-script") 로 제안.
- `multilingual_merge_status` — 교차-스크립트는 **항상 POSSIBLY_SAME_AS**
  (ADR-507 — 자동 SAME_AS 병합은 결정적 외부식별자 exact match 만).
- **honest-gap** (§6.2) — 교차-스크립트 동치는 caller alias bridge 의 신뢰만큼만 유효,
  **transliteration 추론으로 유추하지 않는다**(알리아스 없는 교차 스크립트는 후보도 안 냄).
- 미측정(스크립트 미지정·bridge 부재) → 보수적(None/빈 결과).

read-only(불변식 §3-3)·결정적·mock/실측 격리 원칙 (Phase 4/5 전 작업과 동일).
"""
from __future__ import annotations

import pytest

from orc_citadel.multilingual_er import (
    SCRIPT_CJK,
    SCRIPT_LATN,
    SCRIPT_OTHER,
    detect_script,
    multilingual_alias_index,
    multilingual_block_keys,
    multilingual_merge_status,
    norm_name,
    propose_multilingual_candidates,
)


# --- detect_script (지배 스크립트 분류, 결정적) ------------------------------


def test_detect_latin():
    """로마자 표면형 → latn."""
    assert detect_script("TSMC") == SCRIPT_LATN
    assert detect_script("Taiwan Semiconductor") == SCRIPT_LATN


def test_detect_cjk():
    """한·중·일 통합 한자 표면형 → cjk (05 §1.2 예: 台積電)."""
    assert detect_script("台積電") == SCRIPT_CJK
    assert detect_script("三星電子") == SCRIPT_CJK


def test_detect_latin_dominant_in_mixed():
    """혼합 표기가 로마자가 지배하면 latn (중문 부기 포함)."""
    assert detect_script("Taiwan Semiconductor 台灣") == SCRIPT_LATN


def test_detect_cjk_dominant_if_majority():
    """cjk 가 다수면 cjk."""
    assert detect_script("台灣積體電路製造 TSMC") == SCRIPT_CJK


def test_detect_other_for_digits_punct():
    """스크립트 문자 없는 입력 → other (가드)."""
    assert detect_script("12345") == SCRIPT_OTHER


def test_detect_script_deterministic():
    """동일 입력 → 동일 스크립트 (결정성)."""
    assert detect_script("NVIDIA") == detect_script("NVIDIA")


# --- norm_name (스크립트별 다국어 정규화, 결정적) ----------------------------


def test_norm_latin_lowercases_and_collapses():
    """로마자 — NFKC·소문자·공백 축약·구두점 제거."""
    n = norm_name("  Taiwan Semiconductor  ")
    assert n["script"] == SCRIPT_LATN
    assert n["norm"] == "taiwan semiconductor"


def test_norm_latin_strips_diacritics():
    """발음구분부호(조합 문자) 제거 — 도/오 스크립트 정규화."""
    n = norm_name("Samsungélectronics")  # é 포함
    assert "e" in n["norm"]
    assert "é" not in n["norm"]


def test_norm_cjk_strips_whitespace():
    """CJK — 공백 제거(단어 구분 없음), 대소문자 무의미."""
    n = norm_name("台積電 ")
    assert n["script"] == SCRIPT_CJK
    assert " " not in n["norm"]
    assert n["norm"] == "台積電"


def test_norm_cjk_nfc():
    """CJK — NFKC 정규화 적용 (호환 문자 결합)."""
    n = norm_name("台積電")
    assert n["norm"] == "台積電"


def test_norm_deterministic():
    """동일 입력 → 동일 정규화 (결정성)."""
    assert norm_name("TSMC") == norm_name("TSMC")


def test_norm_empty():
    """빈 입력 → other + 빈 norm (가드)."""
    n = norm_name("")
    assert n["norm"] == ""
    assert n["script"] in (SCRIPT_LATN, SCRIPT_CJK, SCRIPT_OTHER)


# --- multilingual_alias_index (caller-curated bridge index) ------------------


def _alias_index():
    """예: TSMC 라는 기관이 로마자+중문+한글 알리아스를 지님."""
    return multilingual_alias_index([
        {"entity_id": "org-tsmc", "canonical_name": "TSMC",
         "aliases": ["Taiwan Semiconductor", "台積電", "TSMC"]},
        {"entity_id": "org-amd", "canonical_name": "AMD",
         "aliases": ["超威", "AMD"]},
    ])


def test_alias_index_builds_map():
    """알리아스 norm → 엔터티 매핑 구축 (교차-스크립트 포함)."""
    idx = _alias_index()
    # 로마자 + CJK 알리아스가 모두 같은 엔터티를 가리킨다.
    assert idx["taiwan semiconductor"]["entity_id"] == "org-tsmc"
    assert idx["台積電"]["entity_id"] == "org-tsmc"


def test_alias_index_maps_canonical_itself():
    """canonical_name 도 자기 알리아스로 인덱싱."""
    idx = _alias_index()
    assert idx["tsmc"]["entity_id"] == "org-tsmc"


def test_alias_index_deterministic():
    """동일 bridge → 동일 인덱스 (결정성)."""
    assert _alias_index() == _alias_index()


def test_alias_index_empty():
    """빈 bridge → 빈 인덱스."""
    assert multilingual_alias_index([]) == {}


# --- multilingual_block_keys (교차-스크립트 blocking 유도) -------------------


def test_block_key_bridges_cross_script():
    """CJK mention 이 alias bridge 를 통해 로마자 개체와 같은 block key 를 얻는다."""
    idx = _alias_index()
    keys = multilingual_block_keys("台積電", idx)
    # 같은 개체(org-tsmc)를 가리키는 교차-스크립트 key 존재.
    assert any(k.get("entity_id") == "org-tsmc" and k.get("kind") == "multilingual"
               for k in keys)
    assert any(k.get("entity_id") == "org-tsmc" and k.get("kind") == "script"
               for k in keys)


def test_block_key_own_script():
    """스크립트 자체 key — 같은 스크립트 동일 개체 그룹."""
    keys = multilingual_block_keys("TSMC", _alias_index())
    assert any(k.get("kind") == "script" and k.get("script") == SCRIPT_LATN
               for k in keys)


def test_block_key_no_bridge_no_cross():
    """bridge 에 없는 표면형 → 교차-스크립트 key 없음(추론 안 함, honest-gap)."""
    keys = multilingual_block_keys("Samsung", _alias_index())
    multilingual = [k for k in keys if k.get("kind") == "multilingual"]
    assert multilingual == []


def test_block_keys_deterministic():
    """동일 입력 → 동일 keys (결정성)."""
    idx = _alias_index()
    assert multilingual_block_keys("台積電", idx) == multilingual_block_keys("台積電", idx)


def test_block_keys_empty_input():
    """빈 표면형 → 빈 keys (가드)."""
    assert multilingual_block_keys("", _alias_index()) == []


# --- propose_multilingual_candidates (교차-스크립트 후보 제안) ---------------


def test_propose_cross_script_candidate():
    """스크립트 다른 개체 후보 → POSSIBLY_SAME_AS(kind=multilingual-script) 제안."""
    idx = _alias_index()
    cand_tsmc = {"entity_id": "org-tsmc", "script": SCRIPT_LATN,
                 "canonical_name": "TSMC"}
    props = propose_multilingual_candidates("台積電", [cand_tsmc], idx)
    assert len(props) == 1
    p = props[0]
    assert p["entity_id"] == "org-tsmc"
    assert p["kind"] == "multilingual-script"
    assert p["decision"] == "POSSIBLY_SAME_AS"


def test_propose_same_script_not_cross():
    """같은 스크립트 개체는 교차-스크립트 제안 아님(알리아스 매칭도 아님)."""
    idx = _alias_index()
    cand_tsmc = {"entity_id": "org-tsmc", "script": SCRIPT_LATN}
    props = propose_multilingual_candidates("TSMC", [cand_tsmc], idx)
    cross = [p for p in props if p["kind"] == "multilingual-script"]
    assert cross == []


def test_propose_no_bridge_no_proposal():
    """bridge 없는 교차 스크립트 → 제안 없음 (transliteration 추론 금지)."""
    idx = _alias_index()
    cand = {"entity_id": "org-x", "script": SCRIPT_CJK}
    props = propose_multilingual_candidates("Samsung", [cand], idx)
    assert props == []


def test_propose_never_same_as():
    """교차-스크립트 제안은 절대 SAME_AS 가 아님 (ADR-507 — 자동 병합 금지)."""
    idx = _alias_index()
    cand = {"entity_id": "org-tsmc", "script": SCRIPT_LATN}
    for p in propose_multilingual_candidates("台積電", [cand], idx):
        assert p["decision"] != "SAME_AS"


def test_propose_deterministic():
    """동일 입력 → 동일 제안 (결정성)."""
    idx = _alias_index()
    cands = [{"entity_id": "org-tsmc", "script": SCRIPT_LATN}]
    assert (propose_multilingual_candidates("台積電", cands, idx)
            == propose_multilingual_candidates("台積電", cands, idx))


def test_propose_missing_input():
    """빈 mention/candidates → [] (가드)."""
    assert propose_multilingual_candidates("", [], _alias_index()) == []


# --- multilingual_merge_status (교차-스크립트는 항상 POSSIBLY) ---------------


def test_status_always_possibly():
    """교차-스크립트 개체 → POSSIBLY_SAME_AS (자동 병합 금지, ADR-507)."""
    assert multilingual_merge_status("multilingual-script") == "POSSIBLY_SAME_AS"


def test_status_unknown_kind_none():
    """알 수 없는 타입 → None (보수적, 미측정)."""
    assert multilingual_merge_status("unknown") is None


# --- read-only / 결정성 통합 ------------------------------------------------


def test_read_only_no_mutation():
    """multilingual_er 모듈은 read-only — 쓰기·mutation 미노출 (불변식 §3-3)."""
    from orc_citadel import multilingual_er as mle

    for bad in ("apply", "persist", "create_node", "create_edge", "insert",
                "write", "upsert"):
        assert not hasattr(mle, bad), f"read-only 위반: {bad} 노출"
