"""S5 최소 추출 — L1 deterministic parser (설계 05 §1.1).

L1은 gazetteer·식별자(ticker·URL)·대문자 표면형에서 **강한 식별자/후보 mention**을
결정적으로 추출한다. 해소(§2)·claim(§3)·canonicalization(§4)은 이 mention을 입력으로
쓰는 후속 단계로, 여기선 L1만 구현한다 (설계 §5 "deterministic-first" 원칙 — LLM·
embedding은 이후 단계).

- span 축: `char_start/char_end`는 **clean text** 기준 (03 §3.2, 04 §3.4 — segment
  offset과 동일 축). raw HTML 축 역매핑은 일반 케이스에서 후속 (04 §3.4).
- mention_id는 결정적: (doc_id, char_start, char_end, surface_text) hash → 재실행
  동일 mention이 동일 ID (idempotency, 03 §5).
- 중복: span이 겹치면 더 긴(우선) mention 하나만 유지 — 결정적 precision 우선.
- span 없는 mention은 만들지 않는다 (설계 05 §1.1·§3.2, provenance 원칙).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from .normalize import Segment

# L1 규칙·gazetteer 식별 — 변경 시 bump (04 §3.3 방식, 설계 05 §1.2 extraction_version).
EXTRACTION_VERSION = "e1"
MODEL_ID = "rule-l1-1"
SCHEMA_VERSION = "0.1.0"

# 주변 문맥 반경 (캐릭터) — 설계 05 §1.2 context_window.
CONTEXT_RADIUS = 96

# gazetteer: 정확 대문자 표면형 → mention_type. 도메인 조직·기술명 사전.
# (prototype 배정 — 확장 시 도메인 전문화, 설계 05 §1.1 L1.)
GAZETTEER: dict[str, str] = {
    "NVIDIA": "Organization",
    "TSMC": "Organization",
    "SEMI": "Organization",
    "RTX": "Technology",
    "GeForce NOW": "Technology",
}

# 팔호 감싼 ticker: (NYSE:XXX | NASDAQ:XXX | OTC:XXX)
_TICKER = re.compile(r"\b(?:NYSE|NASDAQ|OTC):([A-Z]{1,5})\b")
# URL 도메인 (www 접두 무시, 도메인 그대로 surface)
_URL = re.compile(r"\bhttps?://(?:www\.)?([a-zA-Z0-9.-]+\.[a-z]{2,})")
_PUNCT = re.compile(r"[,.;:!?()\]]")
# NOTE: 일반 대문자 연속 토큰(PT·ET·MIT·Sarah Guo 등)은 여기서 뽑지 않는다.
# 이는 설계 05 §1.1 L2(NER·모델) 영역이며, prototype 정밀도 유지(§5 precision 우선,
# 실수집 스모크에서 사이드바 크롬·약어 오탐 확인)에 따라 제외 — 순수 L1(강한 식별자/
# gazetteer)만 담당한다.


@dataclass(frozen=True)
class Mention:
    mention_id: str
    doc_id: str
    segment_id: str
    surface_text: str
    mention_type: str
    char_start: int
    char_end: int
    context_window: str = ""
    identifiers: dict = field(default_factory=dict)
    resolved_entity_id: str | None = None
    extraction_version: dict = field(default_factory=dict)

    def to_row(self) -> dict:
        """curated_zone mentions 테이블(row)로 변환 (설계 03 §4.1)."""
        return {
            "mention_id": self.mention_id,
            "doc_id": self.doc_id,
            "segment_id": self.segment_id,
            "surface_text": self.surface_text,
            "mention_type": self.mention_type,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "context_window": self.context_window,
            "resolved_entity_id": self.resolved_entity_id,
            "extraction_version": self.extraction_version,
        }


def mention_id_for(doc_id: str, char_start: int, char_end: int, surface: str) -> str:
    """결정적 mention_id — (doc_id, span, surface) hash (03 §5, idempotency)."""
    key = f"{doc_id}:{char_start}:{char_end}:{surface}"
    return "men-" + hashlib.sha256(key.encode()).hexdigest()[:24]


def _context_of(text: str, start: int, end: int, radius: int = CONTEXT_RADIUS) -> str:
    """mention 주위 ±radius 문맥 (설계 05 §1.2 context_window)."""
    lo = max(0, start - radius)
    hi = min(len(text), end + radius)
    return text[lo:hi]


def _clean_surface(surface: str) -> str:
    """표면형에서 앞뒤 구두점/괄호 제거 (설계 05 §1.2 surface_text 정제)."""
    return _PUNCT.sub("", surface).strip()


def extract_mentions(
    doc_id: str,
    doc,
    segments: list[Segment],
) -> list[Mention]:
    """L1 결정적 mention 추출.

    - segments의 **정규화 문장 위치**(norm_char_start)가 not그대로 쓰이지 않고, clean
      text(=`doc.text`)의 절대 span을 재계산해 결정적 ID에 쓴다.
    - 중복 span은 제거하고, gazetteer 타입이 우선이다.
    """
    text = doc.text
    # 1) 모든 규칙에서 (surface, start, end, mention_type, identifiers) 후보 수집.
    candidates: list[tuple[str, int, int, str, dict]] = []

    for m in _TICKER.finditer(text):
        surface = _clean_surface(m.group(1))
        if surface:
            candidates.append((surface, m.start(1), m.end(1), "Organization",
                               {"ticker": m.group(1)}))

    for m in _URL.finditer(text):
        surface = _clean_surface(m.group(1))
        if surface:
            candidates.append((surface, m.start(1), m.end(1), "Organization",
                               {"url": m.group(0)}))

    # gazetteer — 정확 표면형 매칭 (강함).
    for surface, mtype in GAZETTEER.items():
        for m in re.finditer(re.escape(surface), text):
            candidates.append((surface, m.start(), m.end(), mtype, {}))

    # 2) span 겹침 제거 — 결정적 precision 우선: 더 긴 surface·우선 타입 유지.
    #    정렬 후 greedy: 남은 span과 겹치면 폐기.
    candidates.sort(key=lambda c: (c[1], -(c[2] - c[1])))
    kept: list[tuple[str, int, int, str, dict]] = []
    for c in candidates:
        if _overlaps_any(c, kept):
            continue
        kept.append(c)

    # 3) mention 최종화 — 결정적 ID + 문맥.
    mentions: list[Mention] = []
    for surface, start, end, mtype, identifiers in kept:
        mid = mention_id_for(doc_id, start, end, surface)
        mentions.append(Mention(
            mention_id=mid,
            doc_id=doc_id,
            segment_id="",  # segment 매핑은 curated_zone에서 (span 기반).
            surface_text=surface,
            mention_type=mtype,
            char_start=start,
            char_end=end,
            context_window=_context_of(text, start, end),
            identifiers=identifiers,
            resolved_entity_id=None,
            extraction_version={
                "model_id": MODEL_ID,
                "schema_version": SCHEMA_VERSION,
                "extraction_code_version": f"l1:{EXTRACTION_VERSION}",
            },
        ))
    return mentions


def _overlaps_any(c, kept) -> bool:
    """c의 [start,end)가 kept 중 하나와 span 겹침 여부."""
    s, e = c[1], c[2]
    for _, ks, ke, _, _ in kept:
        if s < ke and ks < e:
            return True
    return False
