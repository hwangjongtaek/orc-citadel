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
from orc_citadel.retrieval import RetrievalAgent


@dataclass(frozen=True)
class InvestigationResult:
    subject_id: str
    coverage: float
    subclaims: list
    gaps: list
    counter_evidence: list
    retrieved: list
    iterations: int
    terminated_by: str
    token_usage: dict


class InvestigationRunner:
    """조사 루프 (07 §4) — coverage·counter-evidence·retrieval로 read-only 종료."""

    def __init__(self, zone, graph, coverage_threshold: float = 0.80,
                 max_iters: int = 3, budget=None) -> None:
        self._cov = InvestigationCoverage(zone)
        self._explorer = GraphExplorer(zone, graph)
        self._counter = CounterEvidenceAgent(zone)
        self._retriever = RetrievalAgent(zone)
        self._threshold = coverage_threshold
        self._max_iters = max_iters
        # §4.3 예산 — 기본은 max_iters 기반 (하위 호환). 제공 시 hard stop 추적.
        if budget is not None:
            self._budget = budget
        else:
            from orc_citadel.investigation_budget import InvestigationBudget
            self._budget = InvestigationBudget(max_steps=max_iters, max_tokens=0)

    @staticmethod
    def _query_terms(text: str) -> list[str]:
        """subclaim 텍스트 → 검색 질의 용어 (결정적)."""
        import re
        return [t for t in re.split(r"[^a-z0-9가-힣]+", (text or "").lower()) if t]

    def run(self, subclaims) -> InvestigationResult:
        cov_result = self._cov.coverage(list(subclaims))
        gaps = set(cov_result.gaps)
        counter = []
        retrieved = []
        # gap subclaim의 counter-evidence 탐색 (read-only).
        for s in subclaims:
            if s.id in gaps and s.subject_id:
                ce = self._counter.explore(s.subject_id, s.text.split(" ")[0]
                                           if s.text else "subject")
                counter.append({"subject_id": s.subject_id, "id": s.id,
                                "hypotheses": ce["hypotheses"],
                                "negative_queries": ce["negative_queries"]})
                # SEARCH 스테이지 (07 §4): gap을 채울 후보 span 검색.
                terms = self._query_terms(s.text)
                if terms:
                    retrieved.extend(self._retriever.search(
                        {"terms": terms, "subject_id": s.subject_id}))
        # 종료 판정 — §4.3 조합 (A·B·C)/D + 하위 호환 기본 경로.
        # read-only 루프라 반복에서 새 evidence 불가 → 단일 step 결정.
        iterations = 1
        terminated = None
        # 이 step을 예산에 반영 — 소진 시 hard stop (D).
        self._budget.consume(1, 0)
        from orc_citadel.investigation_budget import evaluate_stop
        decision = evaluate_stop(
            coverage=cov_result.coverage,
            new_independent_evidence_rate=(
                0.0 if cov_result.coverage else 1.0),
            unresolved_contradictions=len(counter),
            budget=self._budget,
            steps_consumed=iterations)
        if decision.hard_stop:
            terminated = "budget"
        elif cov_result.coverage >= self._threshold:
            terminated = "coverage"
        elif gaps:
            # 반복에서 새 evidence 불가능(read-only) — 추가 이득 없음.
            terminated = "no_new_evidence"
        else:
            terminated = "no_new_evidence"
        subjects = sorted({s.subject_id or "" for s in subclaims})
        return InvestigationResult(
            subject_id=", ".join(subjects),
            coverage=cov_result.coverage, subclaims=cov_result.subclaims,
            gaps=cov_result.gaps, counter_evidence=counter, retrieved=retrieved,
            iterations=iterations, terminated_by=terminated,
            token_usage={"input_tokens": 0, "output_tokens": 0, "calls": 0},
        )
