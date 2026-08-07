"""S43 조사 루프 — evidence coverage & gap identification (설계 07 §4, 10 §1.3).

investigation loop의 evidence coverage(10 §1.3 `covered/planned`)와 graph gap 식별
(07 §4 IDENTIFY_GAPS)을 read-only로 계산한다.

- coverage   : 근거 충족 subclaim / 전체 (10 §1.3, gate ≥ 0.80).
- subclaim    : planner가 분해한 하위 주장 — subject_id 지정 시 S29 근거로 평가,
                미지정은 평가 불가 → gap.
- expected_info_gain: 미충족 subclaim의 Δcoverage 휴리스틱 (07 §2.3) — 라우팅·종료 입력.
- **read-only** (불변식 §3-3): 평가·공백 식별만 — graph mutation·영속 미노출.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from orc_citadel.assertion_evidence import AssertionEvidenceProjector


@dataclass(frozen=True)
class Subclaim:
    id: str
    text: str
    subject_id: str | None = None
    covered: bool = False
    evidence_count: int = 0
    gap_reason: str | None = None


@dataclass(frozen=True)
class CoverageResult:
    coverage: float
    subclaims: list
    gaps: list
    expected_info_gain: dict


class InvestigationCoverage:
    """조사 루프의 evidence coverage 계산 (07 §4 state B, read-only)."""

    def __init__(self, zone) -> None:
        self._evidence = AssertionEvidenceProjector(zone)

    def _evaluate(self, subclaim: Subclaim) -> Subclaim:
        if subclaim.subject_id is None:
            return Subclaim(
                id=subclaim.id, text=subclaim.text, subject_id=None,
                covered=False, evidence_count=0,
                gap_reason="no_target")
        evs = self._evidence.for_subject(subclaim.subject_id)
        # subject 어세션 근거 총합 — 근거가 1건 이상이면 covered.
        count = sum(e.evidence_count for e in evs)
        covered = count > 0
        return Subclaim(
            id=subclaim.id, text=subclaim.text, subject_id=subclaim.subject_id,
            covered=covered, evidence_count=count,
            gap_reason=None if covered else "insufficient_evidence")

    def coverage(self, subclaims) -> CoverageResult:
        evaluated = [self._evaluate(s) for s in subclaims]
        planned = len(evaluated) or 1
        covered_n = sum(1 for s in evaluated if s.covered)
        coverage = covered_n / planned
        gaps = [s.id for s in evaluated if not s.covered]
        # expected_info_gain — gap subclaim 1개 채우면 coverage가 Δ만큼 상승 예상.
        # coverage-delta 휴리스틱 (07 §2.3): Δcoverage ≈ 1/planned (1 subclaim 담당분).
        gain = {gid: round(1.0 / planned, 4) for gid in gaps}
        return CoverageResult(
            coverage=round(coverage, 4),
            subclaims=evaluated, gaps=gaps, expected_info_gain=gain)
