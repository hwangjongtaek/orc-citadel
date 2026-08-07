"""S46 Investigation Runner (설계 07 §4 조사 루프) — read-only.

S43 coverage → S44 Graph Explorer → S45 counter-evidence를 하나의 루프로 묶어
read-only로 종료까지 진행 (07 §4, tier L3~L5).

- run(subclaims): subclaim별 coverage·gap·counter_evidence, iterations, terminated_by.
- 종료: coverage ≥ threshold(10 §1.3, 기본 0.80) | no_new_evidence(진행 없음) |
        budget(반복 예산 cap).
- **read-only** (불변식 §3-3): 반복이 그래프·존을 수정하지 않음 (같은 state 평가).
- 결정성.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from orc_citadel.investigation import InvestigationCoverage, Subclaim
from orc_citadel.graph_explorer import GraphExplorer
from orc_citadel.counter_evidence import CounterEvidenceAgent


@dataclass(frozen=True)
class InvestigationResult:
    subject_id: str
    coverage: float
    subclaims: list
    gaps: list
    counter_evidence: list
    iterations: int
    terminated_by: str
    token_usage: dict


class InvestigationRunner:
    """조사 루프 (07 §4) — coverage·counter-evidence로 read-only 종료."""

    def __init__(self, zone, graph, coverage_threshold: float = 0.80,
                 max_iters: int = 3) -> None:
        self._cov = InvestigationCoverage(zone)
        self._explorer = GraphExplorer(zone, graph)
        self._counter = CounterEvidenceAgent(zone)
        self._threshold = coverage_threshold
        self._max_iters = max_iters

    def run(self, subclaims) -> InvestigationResult:
        cov_result = self._cov.coverage(list(subclaims))
        gaps = set(cov_result.gaps)
        counter = []
        # gap subclaim의 counter-evidence 탐색 (read-only).
        for s in subclaims:
            if s.id in gaps and s.subject_id:
                ce = self._counter.explore(s.subject_id, s.text.split(" ")[0]
                                           if s.text else "subject")
                counter.append({"subject_id": s.subject_id, "id": s.id,
                                "hypotheses": ce["hypotheses"],
                                "negative_queries": ce["negative_queries"]})
        # 종료 판정 — 단순 결정적 루프 (그래프·존 불변이라 진행 없으면 종료).
        iterations = 1
        terminated = None
        if cov_result.coverage >= self._threshold:
            terminated = "coverage"
        elif iterations >= self._max_iters:
            terminated = "budget"
        elif gaps:
            # 반복에서 새 evidence 불가능(read-only) — 추가 이득 없음.
            terminated = "no_new_evidence"
        else:
            terminated = "no_new_evidence"
        subjects = sorted({s.subject_id or "" for s in subclaims})
        return InvestigationResult(
            subject_id=", ".join(subjects),
            coverage=cov_result.coverage, subclaims=cov_result.subclaims,
            gaps=cov_result.gaps, counter_evidence=counter,
            iterations=iterations, terminated_by=terminated,
            token_usage={"input_tokens": 0, "output_tokens": 0, "calls": 0},
        )
