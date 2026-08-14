"""조사 품질 평가 하네스 (설계 10 §1.3·§12.3) TDD.

golden question (10 §2.1 조사 질문) 대비 InvestigationRunner·Synthesis 출력을 채점.
DoD ② 증명 경로 — 반증 탐색 제거 버전 대비 점수 향상 계량.

- 하위질문 coverage      : covered/planned (gate ≥ 0.80).
- 인용 연결률             : linked/verifiable (gate = 1.0, evidence-first 불변식 §3-5).
- 인용 지지율             : supporting/total (gate ≥ 0.95, judge — LLM-as-judge 보정 §1.3).
- 독립증거 수 정확성      : 1 − mean(|reported−gold|/max(gold,1)) (target ≥ 0.90).
- 반증 발견률             : found/total_gold_counter (target ≥ 0.70).
- modality 정확도         : correct/total (gate ≥ 0.85).
- Confidence 변화 적절성  : 부호(방향) 일치율 (target ≥ 0.85).
- **honest-gap** (§6.2): 골든 미확보 축은 measured=False 미측정, vacuous pass 금지.
- **read-only** (불변식 §3-3): 채점만, 쓰기·mutation 미노출.

Atomic TDD: Red → Green.
"""
from __future__ import annotations

import pytest

from orc_citadel.investigation_quality import (
    GoldenQuestion,
    InvestigationQualityHarness,
    SUBCLAIM_COVERAGE_GATE,
    CITATION_LINKAGE_GATE,
    CITATION_SUPPORT_GATE,
    INDEPENDENT_EVIDENCE_TARGET,
    COUNTER_EVIDENCE_RECALL_TARGET,
    MODALITY_GATE,
    CONFIDENCE_SIGN_GATE,
)


# --- 하위질문 coverage ----------------------------------------------------

def test_coverage_ratio_and_gate():
    """골든 planned 4 중 covered 3 → 0.75, gate ≥0.80 FAIL."""
    h = InvestigationQualityHarness()
    res = h.coverage_metric(planned=4, covered=3)
    assert res.measured is True
    assert res.value == pytest.approx(0.75)
    assert res.gate["threshold"] == SUBCLAIM_COVERAGE_GATE
    assert res.gate["pass"] is False


def test_coverage_gate_pass():
    """covered 4/4 → 1.0, gate PASS."""
    h = InvestigationQualityHarness()
    res = h.coverage_metric(planned=4, covered=4)
    assert res.value == pytest.approx(1.0)
    assert res.gate["pass"] is True


def test_coverage_honest_gap():
    """골든 planned 0 → measured=False (vacuous pass 금지, §6.2)."""
    h = InvestigationQualityHarness()
    res = h.coverage_metric(planned=0, covered=0)
    assert res.measured is False
    assert res.value is None


# --- 인용 연결률 (evidence-first) -----------------------------------------

def test_citation_linkage_perfect():
    """모든 검증가능 문장이 claim_ref 소유 → 1.0, gate =1.0 PASS."""
    h = InvestigationQualityHarness()
    statements = [
        {"text": "a", "modality": "asserted", "claim_ref": "clm-1"},
        {"text": "b", "modality": "fact", "claim_ref": "clm-2"},
        {"text": "c", "modality": "prediction", "claim_ref": None},  # 무출처 예측은 허용.
    ]
    res = h.citation_linkage(statements)
    assert res.measured is True
    assert res.value == pytest.approx(1.0)
    assert res.gate["pass"] is True


def test_citation_linkage_unattributed_asserted():
    """asserted가 claim_ref 없음 → 연결률 0.5, gate =1.0 FAIL."""
    h = InvestigationQualityHarness()
    statements = [
        {"text": "a", "modality": "asserted", "claim_ref": "clm-1"},
        {"text": "b", "modality": "asserted", "claim_ref": None},  # 무출처.
    ]
    res = h.citation_linkage(statements)
    assert res.value == pytest.approx(0.5)
    assert res.gate["pass"] is False


def test_citation_linkage_honest_gap():
    """검증가능(asserted/fact) 문장 0 → measured=False."""
    h = InvestigationQualityHarness()
    res = h.citation_linkage([{"text": "p", "modality": "prediction", "claim_ref": None}])
    assert res.measured is False


# --- 인용 지지율 (judge) ---------------------------------------------------

def test_citation_support_gate():
    """judge 지지 3/3 → 1.0 PASS; 2/3 → 0.67 FAIL (gate ≥0.95)."""
    h = InvestigationQualityHarness()
    ok = h.citation_support([True, True, True])
    bad = h.citation_support([True, True, False])
    assert ok.value == pytest.approx(1.0) and ok.gate["pass"] is True
    assert bad.value == pytest.approx(2 / 3) and bad.gate["pass"] is False


def test_citation_support_honest_gap():
    """judge 판정 0건 → measured=False (goruden 없이 판정 금치)."""
    h = InvestigationQualityHarness()
    res = h.citation_support([])
    assert res.measured is False


# --- 독립증거 수 정확성 -----------------------------------------------------

def test_independent_evidence_accuracy():
    """reported 3 / gold 3 → 1.0 (target ≥0.90)."""
    h = InvestigationQualityHarness()
    res = h.independent_evidence_accuracy(reported=3, gold=3)
    assert res.measured is True and res.value == pytest.approx(1.0)
    assert res.gate["pass"] is True


def test_independent_evidence_gold_zero():
    """gold=0: reported=0 → 1.0, reported≠0 → 0 (10 §1.3)."""
    h = InvestigationQualityHarness()
    assert h.independent_evidence_accuracy(reported=0, gold=0).value == pytest.approx(1.0)
    assert h.independent_evidence_accuracy(reported=2, gold=0).value == pytest.approx(0.0)


def test_independent_evidence_miss():
    """reported 2 / gold 4 → 1 − 2/4 = 0.5, target 실패."""
    h = InvestigationQualityHarness()
    res = h.independent_evidence_accuracy(reported=2, gold=4)
    assert res.value == pytest.approx(0.5)
    assert res.gate["pass"] is False


# --- 반증 발견률 (DoD ② 직접 지표) ------------------------------------------

def test_counter_evidence_recall():
    """골든 반증 3 중 2 발견 → 0.67 FAIL (<0.70)."""
    h = InvestigationQualityHarness()
    res = h.counter_evidence_recall(found=2, total=3)
    assert res.measured is True and res.value == pytest.approx(2 / 3)
    assert res.gate["pass"] is False


def test_counter_evidence_recall_pass():
    """3/3 → 1.0 PASS (target ≥0.70)."""
    h = InvestigationQualityHarness()
    res = h.counter_evidence_recall(found=3, total=3)
    assert res.value == pytest.approx(1.0) and res.gate["pass"] is True


def test_counter_evidence_recall_honest_gap():
    """골든 반증 0건 → measured=False."""
    h = InvestigationQualityHarness()
    res = h.counter_evidence_recall(found=0, total=0)
    assert res.measured is False


# --- modality 정확도 --------------------------------------------------------

def test_modality_accuracy():
    """8/10 정확 → 0.8 FAIL; 9/10 → 0.9 PASS (gate ≥0.85)."""
    h = InvestigationQualityHarness()
    assert h.modality_accuracy(correct=8, total=10).gate["pass"] is False
    assert h.modality_accuracy(correct=9, total=10).gate["pass"] is True


# --- confidence 변화 적절성 (ablation 부호 일치) ----------------------------

def test_confidence_sign_agreement():
    """부호 일치 5/5 → 1.0 PASS; 4/5 → 0.8 FAIL (target ≥0.85)."""
    h = InvestigationQualityHarness()
    assert h.confidence_sign_agreement(agree=5, total=5).gate["pass"] is True
    assert h.confidence_sign_agreement(agree=4, total=5).gate["pass"] is False


# --- score_question 통합 ----------------------------------------------------

def test_score_question_all_axes():
    """골든 질문 대비 전 축 채점 — 일부는 measured, 골든 없는 축은 honest-gap."""
    q = GoldenQuestion(
        question_id="q1", question="NVDA 공급망?",
        planned_subclaims=("s1", "s2", "s3", "s4"),
        gold_independent_count=3,
        gold_counter=("생산축소", "주문취소", "확장중단"),
    )
    statements = [
        {"text": "a", "modality": "asserted", "claim_ref": "clm-1"},
        {"text": "b", "modality": "fact", "claim_ref": "clm-2"},
    ]
    # coverage 4/4, 반증 3/3, 독립 3/3, 연결 1.0 — 전 축 PASS.
    res = InvestigationQualityHarness().score_question(
        question=q,
        statements=statements,
        coverage=(4, 4),
        counter_found=3,
        reported_independent=3,
        judged_support=[True, True],
    )
    assert res["coverage"]["measured"] and res["coverage"]["gate"]["pass"] is True
    assert res["citation_linkage"]["measured"] and res["citation_linkage"]["gate"]["pass"] is True
    assert res["independent_evidence"]["gate"]["pass"] is True
    assert res["counter_evidence_recall"]["gate"]["pass"] is True


def test_score_question_honest_gap_axes():
    """골든 계획/counter/독립이 비어 있으면 해당 축 measured=False."""
    q = GoldenQuestion(question_id="q2", question="질문")
    statements = [{"text": "x", "modality": "prediction", "claim_ref": None}]
    res = InvestigationQualityHarness().score_question(
        question=q, statements=statements, coverage=(0, 0),
        counter_found=0, reported_independent=0, judged_support=[],
    )
    assert res["coverage"]["measured"] is False          # planned 0.
    assert res["independent_evidence"]["measured"] is False  # gold 0.
    assert res["counter_evidence_recall"]["measured"] is False  # total 0.
    assert res["citation_linkage"]["measured"] is False   # 검증가능 문장 0.


def test_read_only_no_mutation():
    """하네스는 read-only — 쓰기·mutation 미노출."""
    h = InvestigationQualityHarness()
    for bad in ("apply", "persist", "create_node", "create_edge", "insert"):
        assert not hasattr(h, bad), f"read-only 위반: {bad} 노출"


def test_determinism():
    """동일 입력 → 동일 채점."""
    q = GoldenQuestion(question_id="q1", question="?", planned_subclaims=("s1", "s2"))
    h = InvestigationQualityHarness()
    a = h.score_question(q, statements=[{"text": "a", "modality": "asserted",
                                         "claim_ref": "c1"}],
                         coverage=(2, 2), counter_found=1, reported_independent=1,
                         judged_support=[True])
    b = h.score_question(q, statements=[{"text": "a", "modality": "asserted",
                                         "claim_ref": "c1"}],
                         coverage=(2, 2), counter_found=1, reported_independent=1,
                         judged_support=[True])
    assert a == b
