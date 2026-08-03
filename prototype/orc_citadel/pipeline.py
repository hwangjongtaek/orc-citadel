"""S1→S6 파이프라인 최소 흐름 (prototype).

`process_document`: raw 저장 → segments → 추출(claim) → provenance 기록을 한 단위로.
원문 span에서 claim을 만들어 raw_store에 extraction 기록(provenance_ref 부여)한다.
"""
from __future__ import annotations

from dataclasses import dataclass

from .identity import new_ulid
from .normalize import Segment
from .raw_store import RawStore, SegmentRef


@dataclass
class Claim:
    claim_id: str
    segment_id: str
    char_start: int
    char_end: int


def process_document(
    store: RawStore,
    segments: list[Segment],
    source_span: tuple[str, int, int],
) -> Claim:
    """선택된 source_span(segment_id, char_start, char_end)에서 claim 하나를 추출·기록.

    doc_id는 claim의 segment_id(→doc_id)에서 파생하므로 별도 인자가 필요 없다.
    source_span이 실제 segment에 속하는지 검증(StopIteration → 상위 호출자 처리).
    """
    segment_id, char_start, char_end = source_span
    next(s for s in segments if s.segment_id == segment_id)  # span 유효성 검증
    claim = Claim(
        claim_id=new_ulid("clm"),
        segment_id=segment_id,
        char_start=char_start,
        char_end=char_end,
    )
    store.record_claim(claim.claim_id, SegmentRef(segment_id, char_start, char_end))
    return claim
