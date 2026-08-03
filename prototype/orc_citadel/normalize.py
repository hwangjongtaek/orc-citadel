"""Normalized zone (03 §3) — segments.

원문을 문단·문장으로 분리하고, 각 segment에 결정적 segment_id와
원문 offset(char_start/char_end)·정규화 offset(norm_char_start/end)를 보존한다
(ADR-302, provenance 왕복 근간).

prototype 범위: 문장 분할(간단 규칙) 후 정규화는 공백 축약만 적용.
"""
from __future__ import annotations

from dataclasses import dataclass

import re

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Segment:
    segment_id: str
    doc_id: str
    kind: str
    text: str               # 정규화 텍스트
    char_start: int         # 원문(raw) 기준 시작 offset
    char_end: int           # 원문(raw) 기준 끝 offset
    norm_char_start: int    # 정규화 텍스트 기준 시작
    norm_char_end: int      # 정규화 텍스트 기준 끝
    order: int


def _normalize(text: str) -> str:
    """정규화: 연속 공백 축약 (03 §3.4 예시). prototype 최소."""
    return re.sub(r"\s+", " ", text).strip()


def segment_document(doc_id: str, raw_text: str) -> list[Segment]:
    """원문을 문장 단위로 분리해 segments를 생성 (결정적 ID, 03 §3.3).

    prototype: 정규화는 공백 축약(단일 공백 입력에선 no-op)이며, 원문 offset은
    정규화 문장을 원문에서 `find`로 역매핑한다. 정규화가 문자 수를 바꾸는 일반
    케이스의 구간 매핑은 이후 증분에서 다룬다 (03 §3.4).
    """
    normalized = _normalize(raw_text)
    segments: list[Segment] = []
    cursor = 0  # 정규화 텍스트 내 진행 offset
    for order, sentence in enumerate(_SENT_SPLIT.split(normalized)):
        if not sentence.strip():
            continue
        norm_start = cursor
        norm_end = cursor + len(sentence)
        cursor = norm_end
        # 원문 offset: 정규화 문장을 원문에서 찾아 매핑
        raw_start = raw_text.find(sentence)
        segments.append(
            Segment(
                segment_id=f"{doc_id}#p0.s{order}",
                doc_id=doc_id,
                kind="sentence",
                text=sentence,
                char_start=raw_start,
                char_end=raw_start + len(sentence),
                norm_char_start=norm_start,
                norm_char_end=norm_end,
                order=order,
            )
        )
    return segments
