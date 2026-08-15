"""다국어 ER — 스크립트 탐지·다국어 정규화·교차-스크립트 후보 (design 05 §1.2 aliases·§2, ADR-507, Phase 5).

Phase 5 「다국어 ER」 — 같은 개체(기관)가 여러 언어·스크립트로 등장하는 사례
(example: TSMC / 台積電, 05 §1.2 `aliases`)를, **스크립트 탐지 + 다국어 정규화**를
기반으로 **교차-스크립트 개체를 후보(POSSIBLY_SAME_AS)로만 연결**한다.

설계 근거: 05 §1.2 mentions 가 교차-스크립트 alias(`aliases: [TSMC, 台積電]`) 를 carry,
§2.1 blocking key `norm_name` 은 기본적으로 같은 스크립트만 비교. Phase 5 는 그
`norm_name` blocking 의 **교차-스크립트 확장**을 봉인한다.

**precision-first (ADR-507 정합):** 결정적 외부식별자 exact match 만 자동 `SAME_AS`
병합. **교차-스크립트 동치는 항상 `POSSIBLY_SAME_AS`** — transliteration 추론으로
병합하지 않는다.

**honest-gap (§6.2):** 교차-스크립트 동치는 **caller-curated alias bridge**의 신뢰만큼만
유효하다. bridge 에 없는 표면형은 교차-스크립트 후보를 **추론하지 않는다**
(transliteration 은 모호 — 비결정적). 스크립트 미지정/미측정은 보수적(None/빈 결과).

원칙 (Phase 4/5 전 작업과 동일): 결정적·read-only(불변식 §3-3)·mock/실측 격리.
실제 병합·SAME_AS 이벤트 발행은 호출자(ER 캐스케이드) 몫 — 본 모듈은 후보·상태 산출만.
"""
from __future__ import annotations

import unicodedata

# 스크립트 상수.
SCRIPT_LATN = "latn"
SCRIPT_CJK = "cjk"
SCRIPT_OTHER = "other"

# CJK 통합 한자 + 한글 범위 (스크립트 분류에 쓰는 주요 블록).
_CJK_RANGES = (
    (0x4E00, 0x9FFF),   # CJK Unified Ideographs
    (0xAC00, 0xD7AF),   # Hangul Syllables
    (0x3040, 0x30FF),   # Hiragana + Katakana
)
_LATN_UPPER = (0x0041, 0x005A)
_LATN_LOWER = (0x0061, 0x007A)
# 조합 발음구분부호 (diacritic combining marks) — 정규화에서 제거.
_COMBINING_START = 0x0300
_COMBINING_END = 0x036F


def _script_class(cp: int) -> str:
    """단일 codepoint 의 스크립트 클래스 (latn/cjk/other)."""
    for lo, hi in _CJK_RANGES:
        if lo <= cp <= hi:
            return SCRIPT_CJK
    if (_LATN_UPPER[0] <= cp <= _LATN_UPPER[1]
            or _LATN_LOWER[0] <= cp <= _LATN_LOWER[1]):
        return SCRIPT_LATN
    return SCRIPT_OTHER


def detect_script(surface: str) -> str:
    """표면형의 **지배 스크립트** 분류 (결정적 — codepoint 다수결).

    - latn/cjk/other — 05 §1.2 교차-스크립트 alias 의 기준축.
    - 스크립트 문자 없는 입력(숫자·구두점) → `other` (가드).
    """
    counts = {SCRIPT_LATN: 0, SCRIPT_CJK: 0, SCRIPT_OTHER: 0}
    for ch in surface:
        for c in unicodedata.normalize("NFKD", ch):
            if unicodedata.combining(c):
                continue  # 조합 부호는 스크립트 분류에서 제외
            counts[_script_class(ord(c))] += 1
    best = max(counts, key=lambda k: counts[k])
    return best if counts[best] > 0 else SCRIPT_OTHER


def norm_name(surface: str) -> dict:
    """스크립트별 **결정적 다국어 정규화** (NFKC 기반).

    - NFKC 정규화 (호환 문자 결합) + 조합 발음구분부호 제거(도/오 스크립트 재결합).
    - 로마자: 소문자·공백 축약·구두점 제거.
    - CJK: 공백 제거(단어 구분 없음), 대소문자 무의미.
    - 반환 `{script, norm}` — blocking key `norm_name`(05 §2.1) 의 교차-스크립트 변형 기반.
    """
    nfkd = unicodedata.normalize("NFKD", surface)
    stripped = "".join(c for c in nfkd
                       if not (_COMBINING_START <= ord(c) <= _COMBINING_END))
    nfc = unicodedata.normalize("NFC", stripped)
    script = detect_script(surface)
    if script == SCRIPT_CJK:
        norm = "".join(ch for ch in nfc if not ch.isspace())
    else:
        norm = " ".join(nfc.lower().split())
        norm = "".join(ch for ch in norm if not _is_punct(ch))
    return {"script": script, "norm": norm}


def _is_punct(ch: str) -> bool:
    return unicodedata.category(ch).startswith("P")


def multilingual_alias_index(entities: list[dict]) -> dict:
    """caller-curated alias bridge 를 **norm → entity** 인덱스로 구축 (결정적).

    - `entities[i]` = `{entity_id, canonical_name, aliases}`.
    - 각 엔터티의 canonical_name·aliases 를 `norm_name(...)["norm"]` 으로 인덱싱 —
      교차-스크립트 alias(TSMC ↔ 台積電)가 같은 entity_id 로 연결된다.
    - 중복 key 는 최초 등장 보존 (결정적). 빈 bridge → 빈 인덱스.
    """
    index: dict = {}
    for ent in entities:
        surfaces = [ent.get("canonical_name")] + list(ent.get("aliases", []))
        for s in surfaces:
            nm = norm_name(s or "")["norm"]
            if not nm:
                continue
            index.setdefault(nm, {"entity_id": ent["entity_id"],
                                  "script": detect_script(s or ""),
                                  "canonical_name": ent.get("canonical_name")})
    return index


def multilingual_block_keys(surface: str, alias_index: dict) -> list[dict]:
    """표면형의 blocking key 가져오기 — **교차-스크립트 bridge 포함** (05 §2.1 확장).

    - script key: `{kind:"script", script, norm}` (같은 스크립트·같은 정규형 그룹).
    - bridge hit 시: script key 에 `entity_id` 부여 + `{kind:"multilingual",
      entity_id}` key 추가 — **로마자·CJK 표면형이 같은 교차-스크립트 개체로 bucket**.
    - bridge 없는 표면형 → 교차 key 없음 (transliteration 추론 금지, honest-gap).
    """
    nm = norm_name(surface)
    if not nm["norm"]:
        return []
    keys = [{"kind": "script", "script": nm["script"], "norm": nm["norm"]}]
    hit = alias_index.get(nm["norm"])
    if hit:
        keys[0]["entity_id"] = hit["entity_id"]
        keys.append({"kind": "multilingual", "entity_id": hit["entity_id"]})
    return keys


def propose_multilingual_candidates(surface: str, candidates: list[dict],
                                    alias_index: dict) -> list[dict]:
    """스크립트가 다른 개체 후보를 `POSSIBLY_SAME_AS` 로 제안 (교차-스크립트 후보).

    - bridge -> 표면형 norm 이 특정 entity_id 를 가리킬 때, 그와 **스크립트가 다른**
      candidate 만 제안 — `{entity_id, kind:"multilingual-script", decision,
      script, candidate_script}`.
    - **결정은 항상 `POSSIBLY_SAME_AS`** (ADR-507 — 자동 병합 금지).
    - bridge 에 없는 표면형 → 빈 결과 (추론 안 함). read-only·결정적.
    """
    nm = norm_name(surface)
    if not nm["norm"] or not candidates:
        return []
    hit = alias_index.get(nm["norm"])
    if not hit:
        return []
    props = []
    for c in candidates:
        c_script = c.get("script")
        if (c_script is not None and c_script != nm["script"]
                and c.get("entity_id") == hit["entity_id"]):
            props.append({
                "entity_id": c["entity_id"], "kind": "multilingual-script",
                "decision": "POSSIBLY_SAME_AS",
                "script": nm["script"], "candidate_script": c_script,
            })
    return props


def multilingual_merge_status(kind: str) -> str | None:
    """교차-스크립트 병합 상태 — **항상 `POSSIBLY_SAME_AS`** (ADR-507).

    - `kind == "multilingual-script"` → `POSSIBLY_SAME_AS` (자동 병합 금지).
    - 그 외 → None (보수적, 미측정).
    """
    if kind == "multilingual-script":
        return "POSSIBLY_SAME_AS"
    return None
