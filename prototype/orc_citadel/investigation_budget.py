"""조사 budget·종료 조건 + LLM routing (설계 07 §2.2·§2.3·§4.3, ADR-706) — read-only.

- InvestigationBudget     : step/token 예산 추적 — 소진 시 **hard stop (D)**.
- evaluate_stop           : §4.3 조합 STOP = (A ∧ B ∧ C) ∨ D — A(coverage ≥ 0.9)·
                            B(신규 독립 증거율 < ε) · C(미해결 모순 = 0), D는 항상 hard stop.
- route_llm               : §2.2 task별 L0..L5 + ←승급 게이트(결과 confidence < τ_tier 이고
                            budget 잔량 > cost(next_tier) 시 1단계 승급, ADR-706 τ 0.75/0.70/0.65).
- expected_info_gain      : §2.3 coverage-delta 휴리스틱 ≈ Δcoverage × var(confidence).
- call_cost               : §2.3 토큰 추정 ≈ (input + output) × tier_단가.
- 종료 confidence 변화 폭  : §4.3 — < δ(0.02) 수렴 신호(A·B 보강 보조).

모든 판정은 결정적 (ADT-706 placeholder — 골든셋 실측으로 조정, 10 §2). 미측정 양
의존을 제거해 라우팅·종료 구현 가능화.
**read-only** (불변식 §3-3): 판정·추적만, 영속·graph mutation 미노출.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# §4.3 종료 임계 (초기 기본값).
COVERAGE_TERMINATION_THRESHOLD = 0.9
NEW_EVIDENCE_RATE_EPSILON = 0.05
CONVERGENCE_DELTA = 0.02

# §2.3·ADR-706 승급 임계.
TIER_TAU_L1_L3 = 0.75
TIER_TAU_L3_L4 = 0.70
TIER_TAU_L4_L5 = 0.65


@dataclass
class InvestigationBudget:
    """조사 step·token 예산 (hard stop D) — read-only 추적."""
    max_steps: int
    max_tokens: int
    steps_used: int = 0
    tokens_used: int = 0

    @property
    def exhausted(self) -> bool:
        # step: max_steps=0은 즉시 소진(hard stop); token: max_tokens=0은 비활성.
        return self.steps_used >= self.max_steps or (
            self.max_tokens > 0 and self.tokens_used >= self.max_tokens)

    @property
    def remaining_steps(self) -> int:
        return max(0, self.max_steps - self.steps_used)

    def consume(self, steps: int, tokens: int) -> bool:
        """예산 소모 — 소진 시 True (호출자가 hard stop)."""
        self.steps_used += steps
        self.tokens_used += tokens
        return self.exhausted


@dataclass(frozen=True)
class StopDecision:
    should_stop: bool
    hard_stop: bool
    reason: str | None


def evaluate_stop(coverage: float, new_independent_evidence_rate: float,
                  unresolved_contradictions: int, budget: InvestigationBudget,
                  steps_consumed: int) -> StopDecision:
    """§4.3 조합 종료 판정 — STOP = (A ∧ B ∧ C) ∨ D.

    D(budget 소진)는 항상 hard stop. 경과 step을 budget에 반영해 소진판정에 쓴다.
    """
    if budget.exhausted:
        return StopDecision(should_stop=True, hard_stop=True, reason="budget")
    if steps_consumed >= budget.max_steps:
        return StopDecision(should_stop=True, hard_stop=True, reason="budget")
    # A ∧ B ∧ C — 정상 종료.
    a = coverage >= COVERAGE_TERMINATION_THRESHOLD
    b = new_independent_evidence_rate < NEW_EVIDENCE_RATE_EPSILON
    c = unresolved_contradictions == 0
    if a and b and c:
        return StopDecision(should_stop=True, hard_stop=False, reason="coverage_converged")
    return StopDecision(should_stop=False, hard_stop=False, reason=None)


def _tau_for(task: str) -> float:
    """승급 시 적용 임계 — task의 하위 tier 판정 confidence 하한 (ADR-706)."""
    if task in ("classify", "ner"):
        return TIER_TAU_L1_L3
    if task in ("ambiguous_merge", "contradiction_judgment"):
        return TIER_TAU_L3_L4
    return TIER_TAU_L4_L5


def route_llm(task: dict, result_confidence: float | None = None,
              budget_remaining: int = 0, next_tier_cost: int = 0) -> str:
    """§2.2 routing + §2.3 승급 게이트 — 결정적 tier 판정."""
    kind = task.get("task", "")
    if kind == "deterministic":
        return "L0"
    if kind in ("classify", "ner"):
        base = "L1"
    elif kind in ("candidate_search",):
        base = "L2"
    elif kind == "structured_extraction":
        return "L3"  # batch.
    elif kind in ("ambiguous_merge", "contradiction_judgment"):
        uncertainty = task.get("uncertainty")
        base = "L4" if uncertainty == "high" else "L3"
    elif kind in ("plan", "counter_evidence", "synthesize", "audit"):
        return "L5"
    else:
        return "L3"
    # 승급 게이트 — 하위 tier 산출물 confidence가 임계 미만이고 예산 잔량 > 비용.
    tau = _tau_for(kind)
    escalate = (result_confidence is not None and result_confidence < tau
                and budget_remaining > next_tier_cost)
    if escalate and base == "L3":
        return "L4"
    return base


def expected_info_gain(coverage_delta_est: float,
                       confidence_variance: float) -> float:
    """§2.3 expected_info_gain ≈ Δcoverage × var(confidence)."""
    return coverage_delta_est * confidence_variance


def call_cost(est_input_token: int, est_output_token: int,
              tier_rate: float) -> float:
    """§2.3 call_cost ≈ (input + output) × tier_단가 (토큰 추정)."""
    return (est_input_token + est_output_token) * tier_rate
