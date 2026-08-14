"""Investigation 대시보드 (설계 11 §2.2 D8) TDD.

investigation별 evidence coverage·독립 증거 수·비용·latency 를 계산해 노출
(design 11 §2.2 D8, Council Chamber; §1.4·10 §1.4 Investigation 비용/latency).

- coverage        : covered/planned subclaim + 미조사(gap) 목록.
- 독립 증거 수      : runner/subgraph의 독립 출처 수(dup 보정, 11 §1.4).
- 비용·latency     : InvestigationBudget token/step + elapsed (조사 1건당,
                     10 §1.4 cost_per_inv·latency_p95 계약).
- **read-only** (불변식 §3-3) · 결정적.
- 모든 metric — correlation·version 분해 가능 (11 §2.2, D6 전제).

Atomic TDD: Red → Green.
"""
from __future__ import annotations

import pytest

from orc_citadel.investigation_dashboard import investigation_dashboard, Coverage
from orc_citadel.investigation_budget import InvestigationBudget


def test_dashboard_coverage():
    """D8 — coverage = covered/planned + gap 목록."""
    d = investigation_dashboard(
        investigation_id="inv-1",
        coverage=Coverage(covered=3, planned=4, gaps=["sc2"]))
    assert d["investigation_id"] == "inv-1"
    assert d["evidence_coverage"]["ratio"] == pytest.approx(0.75)
    assert d["evidence_coverage"]["gaps"] == ["sc2"]


def test_dashboard_independent_evidence():
    """독립 증거 수 — dup 보정 독립 출처 노출 (11 §1.4)."""
    d = investigation_dashboard(
        investigation_id="inv-1",
        coverage=Coverage(covered=3, planned=4, gaps=[]),
        independent_evidence=2)
    assert d["independent_evidence"] == 2


def test_dashboard_budget_token_latency():
    """비용·latency — 예산 token/step + elapsed (10 §1.4 cost_per_inv)."""
    b = InvestigationBudget(max_steps=5, max_tokens=1000)
    b.consume(2, 350)
    d = investigation_dashboard(
        investigation_id="inv-1",
        coverage=Coverage(covered=3, planned=4, gaps=[]),
        budget=b, elapsed_ms=420)
    cost = d["cost"]
    assert cost["tokens_used"] == 350
    assert cost["steps_used"] == 2
    assert d["latency_ms"] == 420


def test_dashboard_honest_gap():
    """planned 0 → coverage 미측정 (10 §6.2 honest-gap, vacuous pass 금지)."""
    d = investigation_dashboard(
        investigation_id="inv-1",
        coverage=Coverage(covered=0, planned=0, gaps=[]))
    assert d["evidence_coverage"]["measured"] is False
    assert d["evidence_coverage"]["ratio"] is None


def test_read_only_no_mutation():
    """dashboard는 read-only — 쓰기·mutation 미노출."""
    d = investigation_dashboard(
        investigation_id="inv-1",
        coverage=Coverage(covered=1, planned=1, gaps=[]))
    for bad in ("apply", "persist", "create_node", "create_edge", "insert"):
        assert not hasattr(d, bad), f"read-only 위반: {bad} 노출"
