"""S31 Subject 신뢰도 랭킹 (설계 09 §2.1 조사 목록·War Table 우선순위 재료).

S30 결론 프로젝터(`ConclusionProjector`)를 소비해 전체 subject를 신뢰도 기준으로
**정렬된 read-only 랭킹**으로 노출한다. 조사 UX가 "어떤 주체를 먼저 주목할지"를
결정하는 재료.

- rank   : value DESC 정렬. tie-breaker: independent_source_count DESC → subject_id ASC
           (완전 결정적 — 동률 순서 고정).
- signal : 주목 신호 (조회 우선순위 언어):
           `contradicted`(반박 위험 존재) / `low_evidence`(근거 미확립) /
           `high_confidence`(value ≥ 상위신뢰 임계) / `normal`.
- 09 §4 원칙: value 단일 게이지 금지 — 항목마다 결론 봉투(value/evidence_count/
  independent_source_count/basis/dimensions)를 함께 노출.
- confidence는 **증거 구조** 기반 (blueprint §11). **read-only** (불변식 §3-3) —
  쓰기·영속·그래프 mutation 미노출.
"""
from __future__ import annotations

from dataclasses import dataclass

from orc_citadel.conclusion import ConclusionProjector

DEFAULT_HIGH_CONFIDENCE = 0.8


@dataclass(frozen=True)
class RankedConclusion:
    subject_id: str
    rank: int
    confidence: dict   # S30 결론 봉투 (09 §4).
    signal: str
    predicates: dict   # S30 by_predicate 요약.


class ConclusionRanking:
    """S30 결론 프로젝터를 정렬하는 read-only subject 랭킹."""

    def __init__(self, zone, high_confidence: float = DEFAULT_HIGH_CONFIDENCE,
                 low_confidence: float | None = None) -> None:
        self._projector = ConclusionProjector(zone, low_confidence=low_confidence or 0.4)
        self._high_confidence = high_confidence

    def _signal(self, c) -> str:
        d = c.confidence["dimensions"]
        if d["contradiction"] > 0:
            return "contradicted"
        if c.confidence["independent_source_count"] == 0 or c.confidence["evidence_count"] == 0:
            return "low_evidence"
        if c.confidence["value"] >= self._high_confidence:
            return "high_confidence"
        return "normal"

    def ranked(self, signal: str | None = None,
               limit: int | None = None) -> list[RankedConclusion]:
        conclusions = [c for c in self._projector.all() if c is not None]
        # 정렬 — value DESC → indep DESC → subject_id ASC (결정적).
        conclusions.sort(
            key=lambda c: (-c.confidence["value"],
                           -c.confidence["independent_source_count"],
                           c.subject_id))
        out = []
        for i, c in enumerate(conclusions, start=1):
            sig = self._signal(c)
            if signal is not None and sig != signal:
                continue
            out.append(RankedConclusion(
                subject_id=c.subject_id, rank=i, confidence=c.confidence,
                signal=sig, predicates=c.by_predicate))
        if limit is not None:
            out = out[:limit]
        return out

    def by_signal(self) -> dict:
        groups: dict[str, list] = {}
        for item in self.ranked():
            groups.setdefault(item.signal, []).append(item.subject_id)
        return groups
