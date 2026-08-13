"""파이프라인 측정 — throughput·문서당 시간·LLM 비용 (design 10 §1.4, MVP #9) TDD.

MVP 최종 성공 기준 #9「문서당 비용·전체 처리 시간 측정」을 계측·보고한다. design 10
§1.4 지표:
- 수집/파싱 throughput = `docs_processed / elapsed_sec` (target ≥ 50 docs/s)
- 문서당 처리 시간 = per-doc 벽시계 분위수
- 문서당 LLM 비용 = `sum(llm_cost) / docs_processed` (결정적 체인은 0)

전체 벽시계(`elapsed_ms`)는 이미 존재 — 본 모듈은 **문서당 시간·throughput·비용**을
순수 함수로 계산하고, 파이프라인이 각 문서 처리 시간을 수집하게 배선한다.
"""
from __future__ import annotations

from orc_citadel.pipeline_bench import (
    llm_cost_per_doc,
    per_doc_stats,
    throughput,
)

TARGET_DOCS_PER_SEC = 50.0  # design 10 §1.4 — 수집/파싱 throughput MVP 목표.


def test_throughput_computes_docs_per_sec():
    """throughput = docs_processed / elapsed_sec (design 10 §1.4)."""
    assert throughput(100, 2.0) == 50.0


def test_throughput_meets_mvp_target():
    """목표 50 docs/s 대비 판정 — 절대·상대 비교 (부동소수 안전)."""
    assert throughput(250, 5.0) >= TARGET_DOCS_PER_SEC


def test_throughput_zero_elapsed_is_zero():
    """elapsed 0 (보호) → 0.0 — ZeroDivision 방지."""
    assert throughput(100, 0.0) == 0.0


def test_throughput_negative_elapsed_is_zero():
    """음수 elapsed (보호) → 0.0."""
    assert throughput(100, -1.0) == 0.0


def test_per_doc_stats_reports_p50_avg_max():
    """문서당 처리 시간 분위수: avg·p50·max·n (design 10 §1.4 latency)."""
    stats = per_doc_stats([10, 20, 30, 40, 50])
    assert stats["n"] == 5
    assert stats["avg_ms"] == 30.0
    assert stats["p50_ms"] == 30.0  # [10,20,30,40,50] 중앙값
    assert stats["max_ms"] == 50.0


def test_per_doc_stats_empty():
    """문서 없음 → 빈 통계 (분모 부재 가드)."""
    assert per_doc_stats([]) == {"n": 0}


def test_llm_cost_per_doc_zero_for_deterministic():
    """결정적 체인(LLM 미사용) → 문서당 LLM 비용 0 (design 10 §1.4)."""
    assert llm_cost_per_doc(0.0, 128) == 0.0


def test_llm_cost_per_doc_divides():
    """sum(llm_cost)/docs — LLM 사용 시 문서당 환산."""
    assert abs(llm_cost_per_doc(1.28, 128) - 0.01) < 1e-12


def test_llm_cost_per_doc_zero_docs_guard():
    """문서 0 → 0 (분모 부재 가드)."""
    assert llm_cost_per_doc(0.5, 0) == 0.0
