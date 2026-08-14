"""Investigation 대시보드 (설계 11 §2.2 D8) — read-only·결정적.

investigation별 **evidence coverage·독립 증거 수·비용·latency** 를 계산해
Council Chamber(11 §2.2 D8)에 노출한다. 소스는 agent runtime(→ 07),
지표 계약은 10 §1.4(Investigation 비용/latency: cost_per_inv·latency_p95)·
11 §1.4(독립 증거 수 dup 보정).

- evidence_coverage : covered/planned + 미조사(gap) 목록 — planned 0이면
  honest-gap(10 §6.2: measured=False, vacuous pass 금지).
- independent_evidence: dup 보정 독립 출처 수 (11 §1.4).
- cost              : InvestigationBudget token/step 사용량 (10 §1.4).
- latency_ms        : 조사 1건당 벽시계 지연 (10 §1.4 latency_p95 계약).
- 모든 metric 은 investigation_id 로 분해 가능 (11 §2.2 drill-down).

**read-only** (불변식 §3-3): 계산만, 쓰기·영속·graph mutation 미노출.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Coverage:
    """survey coverage 입력 — covered/planned + gap 목록."""
    covered: int
    planned: int
    gaps: list


def investigation_dashboard(investigation_id: str, coverage: Coverage,
                            independent_evidence: int = 0,
                            budget=None, elapsed_ms: int = 0) -> dict:
    """D8 보고서 — investigation별 지표 계산 (read-only·결정적).

    budget 과 elapsed_ms 는 생략 시 미보고 (비용·latency 미측정).
    """
    if coverage.planned <= 0:
        cov = {"measured": False, "ratio": None, "gaps": list(coverage.gaps)}
    else:
        cov = {"measured": True,
               "ratio": round(coverage.covered / coverage.planned, 4),
               "gaps": list(coverage.gaps)}
    cost = {}
    if budget is not None:
        cost = {"tokens_used": budget.tokens_used,
                "steps_used": budget.steps_used}
    return {
        "investigation_id": investigation_id,
        "evidence_coverage": cov,
        "independent_evidence": independent_evidence,
        "cost": cost,
        "latency_ms": elapsed_ms,
    }
