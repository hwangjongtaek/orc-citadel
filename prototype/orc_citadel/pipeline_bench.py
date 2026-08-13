"""파이프라인 측정 — throughput·문서당 시간·LLM 비용 (design 10 §1.4, MVP #9).

MVP 최종 성공 기준 #9「문서당 비용·전체 처리 시간 측정」을 계측·보고하는 순수 함수 집합.
design 10 §1.4 지표를 결정적·재현 가능하게 계산한다:

- **throughput** = `docs_processed / elapsed_sec` (수집/파싱, target ≥ 50 docs/s MVP)
- **문서당 처리 시간** = per-doc 벽시계 분위수 (avg·p50·max)
- **문서당 LLM 비용** = `sum(llm_cost) / docs_processed`

전체 벽시계(`elapsed_ms`)는 `pipeline_bulk_driver`가 이미 계측한다. 본 모듈은 그
파생 지표·문서당 단위를 순수 함수로 계산해 재현성 있게 공개한다 (원시 분→통계 변환만
담당, 측정 데이터 수집은 파이프라인/드라이버 와 해후).
"""
from __future__ import annotations

import statistics

# design 10 §1.4 — 수집/파싱 throughput MVP 목표.
THROUGHPUT_TARGET_DOCS_PER_SEC = 50.0


def throughput(docs_processed: int, elapsed_sec: float) -> float:
    """수집/파싱 throughput = `docs_processed / elapsed_sec` (design 10 §1.4).

    elapsed ≤ 0 (보호) → 0.0 — ZeroDivision·그릇된 벽시계 입력 방지.
    """
    if elapsed_sec <= 0:
        return 0.0
    return docs_processed / elapsed_sec


def per_doc_stats(per_doc_elapsed_ms: list[float]) -> dict:
    """문서당 처리 시간 통계 — avg·p50·max·n (design 10 §1.4 latency).

    문서가 없으면 분모가 없으므로 빈 통계 반환 (노이즈 없는 명시적 가드).
    """
    if not per_doc_elapsed_ms:
        return {"n": 0}
    return {
        "n": len(per_doc_elapsed_ms),
        "avg_ms": round(statistics.mean(per_doc_elapsed_ms), 3),
        "p50_ms": round(statistics.median(per_doc_elapsed_ms), 3),
        "max_ms": round(max(per_doc_elapsed_ms), 3),
    }


def llm_cost_per_doc(total_llm_cost_usd: float, docs_processed: int) -> float:
    """문서당 LLM 비용 = `sum(llm_cost) / docs_processed` (design 10 §1.4).

    결정적 체인(LLM 미사용)은 total 0 → 문서당 0. 문서 0 (분모 부재) → 0.
    """
    if docs_processed <= 0:
        return 0.0
    return total_llm_cost_usd / docs_processed
