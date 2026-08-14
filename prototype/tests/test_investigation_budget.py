"""조사 budget·종료 조건 + LLM routing (설계 07 §2.3·§4.3, ADR-706) TDD.

budget/종료는 §4.3 조합 STOP = (A ∧ B ∧ C) ∨ D로 판정, D는 항상 hard stop.
routing은 §2.2·§2.3 세 축(expected_info_gain · uncertainty · call_cost) + ADR-706
승급 임계(τ: 0.75/0.70/0.65)·수렴 δ(0.02)로 결정적 판정.

- InvestigationBudget: step/token 예산 추적 (hung hard stop D).
- evaluate_stop: A(coverage≥0.9)·B(신규 독립 증거율<ε 0.05)·C(미해결 모순=0)
  조합 → 정상 종료; D 그냥 hard stop.
- route_llm: task별 L0..L5 + 승급 게이트(confidence < τ_tier & budget_remaining >
  cost(next) 시 1단계 승급).
- expected_info_gain/call_cost: ADR-706 추정법 (Δcoverage × var(confidence)·토큰×단가).
- **read-only** (불변식 §3-3) — 판정만, mutation 미노출.

Atomic TDD: Red → Green.
"""
from __future__ import annotations

import pytest

from orc_citadel.investigation_budget import (
    InvestigationBudget,
    evaluate_stop,
    route_llm,
    expected_info_gain,
    call_cost,
    # 축 기본값.
    COVERAGE_TERMINATION_THRESHOLD,
    NEW_EVIDENCE_RATE_EPSILON,
    CONVERGENCE_DELTA,
    TIER_TAU_L1_L3,
    TIER_TAU_L3_L4,
    TIER_TAU_L4_L5,
)


# --- budget (hard stop D) ---------------------------------------------------

def test_budget_tracks_steps_and_force_terminates_on_exhaustion():
    """budget 소진 시 hard stop (종료 reason = budget)."""
    b = InvestigationBudget(max_steps=2, max_tokens=1000)
    assert b.consume(1, 500) is False         # step 1 사용 — 아직 소진 아님.
    assert b.exhausted is False
    assert b.consume(1, 500) is True          # step 2 사용 → max_steps 도달 소진.
    assert b.exhausted is True
    assert b.remaining_steps == 0


def test_budget_hard_stop_on_token_exhaustion():
    """token 예산 소진 → hard stop."""
    b = InvestigationBudget(max_steps=100, max_tokens=1000)
    assert b.consume(1, 600) is False         # 600 < 1000, 아직 소진 아님.
    assert b.exhausted is False
    b.consume(1, 500)                         # 누적 1100 > max_tokens.
    assert b.exhausted is True


# --- evaluate_stop (A ∧ B ∧ C) ∨ D -----------------------------------------

def test_stop_normal_converged():
    """A(coverage≥0.9)∧B(신규 독립 증거율<ε)∧C(미해결 0) → 정상 종료."""
    res = evaluate_stop(coverage=0.92, new_independent_evidence_rate=0.01,
                        unresolved_contradictions=0,
                        budget=InvestigationBudget(10, 10_000),
                        steps_consumed=3)
    assert res.should_stop is True
    assert res.hard_stop is False
    assert res.reason == "coverage_converged"


def test_stop_coverage_not_met_continues():
    """A 미충족(coverage<0.9) → 계속 (D 아님)."""
    res = evaluate_stop(coverage=0.75, new_independent_evidence_rate=0.01,
                        unresolved_contradictions=0,
                        budget=InvestigationBudget(10, 10_000), steps_consumed=3)
    assert res.should_stop is False


def test_stop_hard_stop_on_budget():
    """D(budget 소진) → 항상 hard stop (A·B·C와 무관)."""
    b = InvestigationBudget(max_steps=1, max_tokens=100)
    b.consume(1, 60)                          # step 소진.
    res = evaluate_stop(coverage=0.0, new_independent_evidence_rate=1.0,
                        unresolved_contradictions=5,
                        budget=b, steps_consumed=1)
    assert res.should_stop is True
    assert res.hard_stop is True
    assert res.reason == "budget"


def test_stop_unresolved_contradiction_continues():
    """C 미충족(미해결 모순 존재) → 계속."""
    res = evaluate_stop(coverage=0.95, new_independent_evidence_rate=0.01,
                        unresolved_contradictions=2,
                        budget=InvestigationBudget(10, 10_000), steps_consumed=2)
    assert res.should_stop is False


# --- LLM routing (§2.2·§2.3) ------------------------------------------------

def test_route_deterministic_returns_l0():
    route_llm({"task": "deterministic"}) == "L0"


def test_route_structured_extraction_l3():
    """structured_extraction → L3 (batch)."""
    assert route_llm({"task": "structured_extraction"}) == "L3"


def test_route_plan_l5():
    """plan·counter_evidence·synthesize → L5 (고성능 reasoning)."""
    assert route_llm({"task": "plan"}) == "L5"
    assert route_llm({"task": "synthesize"}) == "L5"


def test_route_escalation_gate():
    """승급: confidence < τ_tier 이고 budget 잔량 > cost(next) → 1단계 승급."""
    # L4 판정 불확실성·값 낮음 → L3로 시도, confidence 0.6 < τ_L3→L4=0.70 → L4 승급.
    tier = route_llm({"task": "ambiguous_merge", "uncertainty": "low"},
                     result_confidence=0.6, budget_remaining=5000,
                     next_tier_cost=1000)
    assert tier == "L4"


def test_route_no_escalation_without_budget():
    """budget 잔량 부족 → 승급 안 함 (하위 tier 유지)."""
    tier = route_llm({"task": "ambiguous_merge", "uncertainty": "low"},
                     result_confidence=0.6, budget_remaining=500,
                     next_tier_cost=1000)
    assert tier != "L4"  # budget_remaining(500) <= cost(1000) → 승급 거부.


def test_route_high_uncertainty_goes_high():
    """contradiction_judgment: 불확실성 높음 → L4 직접."""
    assert route_llm({"task": "contradiction_judgment", "uncertainty": "high"}) == "L4"


# --- 추정법 (ADR-706 §2.3) ---------------------------------------------------

def test_expected_info_gain_coverage_delta():
    """expected_info_gain ≈ Δcoverage × var(confidence)."""
    gain = expected_info_gain(coverage_delta_est=0.25, confidence_variance=0.16)
    assert gain == pytest.approx(0.25 * 0.16)


def test_call_cost_token_estimate():
    """call_cost ≈ (input + output) × tier_단가."""
    cost = call_cost(est_input_token=1000, est_output_token=200, tier_rate=0.05)
    assert cost == pytest.approx((1000 + 200) * 0.05)


def test_determinism():
    """동일 입력 → 동일 판정."""
    a = evaluate_stop(0.95, 0.01, 0, InvestigationBudget(10, 10_000), 1)
    b = evaluate_stop(0.95, 0.01, 0, InvestigationBudget(10, 10_000), 1)
    assert a == b


def test_read_only_no_mutation():
    """budget/판정은 read-only — 쓰기·mutation 미노출."""
    for obj in (InvestigationBudget(5, 100),):
        for bad in ("apply", "persist", "create_node", "create_edge"):
            assert not hasattr(obj, bad), f"read-only 위반: {bad} 노출"
