"""Phase 4 DoD ①② 통합 공개 리포트 (design 10 §4.5·§1.4 → 01·06, Phase 4 완결).

#14–#17 이 봉인한 계약을 **DoD ①② 측에서 통합 공개** 한다 (10 §1.4 지표·§4.5).

- **DoD ① — 100만 문서 처리 시간·비용 공개.** `project_time_to_scale`·`project_cost_to_scale`
  으로 100만 스케일의 처리 시간·비용을 **투영(projection)** 한다. 이 값은 결정적 모델
  (분산 batch #14·batch inference #17 의 50% 절감)에서 계산한 **추정치**이지 실측이
  아니므로 `measured=False` 로 명시 (honest-gap §6.2 — 실측 부재가 공개 값의 근거).
- **DoD ② — 신규 문서 SLO 내 graph 반영.** `compute_graph_slo`(#15, p95 ≤ GRAPH_SLO_MS)
  + 증분 완료조건(`INCREMENTAL_RATIO_GATE > 10×`) 을 통합 판정한다. 미측정은
  `not-measured` (진공 통과 금지, §6.2).

각 구성요소는 #14–#17 이 봉인한 **결정적·read-only 계약을 재사용** (중복 구현 없음).
read-only(불변식 §3-3)·결정적·mock/실측 격리 원칙 유지.
"""
from __future__ import annotations

from .batch_inference import batch_inference_cost, MESSAGE_BATCHES_DISCOUNT
from .graph_incremental import (
    GRAPH_SLO_MS,
    INCREMENTAL_RATIO_GATE,
    compute_graph_slo,
)
from .pipeline_bench import throughput, llm_cost_per_doc  # 10 §1.4 재사용.
from .distributed_batch import compute_slo_gate  # 10 §1.4 재사용.

# blueprint §21-2 / 10 §1.4·§4.5 — 100만 문서 확장 목표.
PHASE4_TARGET_DOCS = 1_000_000


def project_time_to_scale(per_doc_ms: float | None, docs_processed: int,
                          target_docs: int = PHASE4_TARGET_DOCS,
                          parallel_speedup: float = 1.0) -> dict:
    """100만 문서 처리 시간 투영 — DoD ① (10 §4.5, 결정적·honest projection).

    벽시계(seq) = `per_doc_ms × target_docs`; 병렬 시 `÷ parallel_speedup`.
    `per_doc_ms` 미측정(None) 또는 target ≤ 0 → `measured=False` + 값 None —
    honest projection: 추정 값이지 실측이 아니며, 미측정 입력은 투영도 못한다(§6.2).
    반환 `{measured, docs, target_docs, per_doc_ms, parallel_speedup, projected_ms}`.
    """
    if per_doc_ms is None or docs_processed <= 0 or target_docs <= 0:
        return {"measured": False,
                "docs": docs_processed, "target_docs": target_docs,
                "per_doc_ms": per_doc_ms,
                "parallel_speedup": parallel_speedup,
                "projected_ms": None}
    seq_ms = per_doc_ms * target_docs
    effective = max(parallel_speedup, 1.0)
    projected_ms = seq_ms / effective
    return {"measured": True,
            "docs": docs_processed, "target_docs": target_docs,
            "per_doc_ms": per_doc_ms,
            "parallel_speedup": parallel_speedup,
            "projected_ms": round(projected_ms, 3)}


def project_cost_to_scale(cost_per_doc: float | None, docs_processed: int,
                          target_docs: int = PHASE4_TARGET_DOCS,
                          use_batch: bool = True) -> dict:
    """100만 문서 LLM 비용 투영 — DoD ① · 문서당 총비용 (10 §1.4, 07 §2.2).

    순차 = `cost_per_doc × target_docs`; `use_batch` 면 `batch_inference_cost`
    (MESSAGE_BATCHES_DISCOUNT 0.5 — L3 Message Batches) 의 batch 비용으로 절감.
    `cost_per_doc` 미측정(None) 또는 target ≤ 0 → `measured=False` + 값 None (honest).
    반환 `{measured, docs, target_docs, cost_per_doc, use_batch,
           sequential_cost, projected_cost, batch_cost?}`.
    """
    if cost_per_doc is None or docs_processed <= 0 or target_docs <= 0:
        return {"measured": False,
                "docs": docs_processed, "target_docs": target_docs,
                "cost_per_doc": cost_per_doc, "use_batch": use_batch,
                "sequential_cost": None, "projected_cost": None}
    sequential = cost_per_doc * target_docs
    out = {"measured": True,
           "docs": docs_processed, "target_docs": target_docs,
           "cost_per_doc": cost_per_doc, "use_batch": use_batch,
           "sequential_cost": round(sequential, 6),
           "projected_cost": round(sequential, 6)}
    if use_batch:
        bc = batch_inference_cost(n_calls=target_docs, cost_per_call=cost_per_doc)
        out["batch_cost"] = bc["batch_cost"]
        out["projected_cost"] = bc["batch_cost"]
        out["batch_discount"] = MESSAGE_BATCHES_DISCOUNT
    return out


def graph_reflect_slo(graph: dict, latency: dict | None = None,
                      incremental: dict | None = None) -> dict:
    """DoD ② — 신규 문서 SLO 내 graph 반영 통합 판정 (10 §1.4, 06 §7.2/#15).

    - `graph` = `compute_graph_slo` 결과(직접 전달).
    - `latency` (선택) = `distributed_batch.compute_slo_gate` — 노드당 벽시계 SLO.
    - `incremental` (선택) = `evaluate_incremental_bench` — 증분 완료조건 ratio>10×.
    각각의 `measured`/분류를 그대로 재노출 (중복 계산 없음). read-only·결정적.
    """
    graph_copy = dict(graph)
    out = {"graph_slo": graph_copy}
    if latency is not None:
        out["node_slo"] = dict(latency)
    if incremental is not None:
        out["incremental_gate"] = dict(incremental)
    return out


def phase4_dod_report(dod1_time: dict, dod1_cost: dict,
                      graph_slo: dict, latency_slo: dict | None = None,
                      incremental_gate: dict | None = None) -> dict:
    """Phase 4 DoD ①② 통합 공개 리포트 — 의사결정·운영 SLO 관점.

    - DoD ①: `dod1_time`(project_time_to_scale)·`dod1_cost`(project_cost_to_scale)
      — 각 `measured` 플래그로 실측/투영 구분 공개 (honest-gap §6.2).
    - DoD ②: `_graph_reflect` — `graph_slo`(필수)·`latency_slo`·`incremental_gate`
      분류 재노출 (각 `measured`·`classified`: ok/slo-gate/not-measured).
    - `all_measured` — DoD ①·② 전 구성요소가 실측인지 (부분 미측정 시 False — honest).
    """
    reflect = graph_reflect_slo(graph_slo, latency_slo, incremental_gate)
    measured_flags = [
        dod1_time.get("measured"), dod1_cost.get("measured"),
        graph_slo.get("classified") != "not-measured",
    ]
    all_measured = measured_flags and all(measured_flags)
    return {
        "phase": "Phase 4",
        "dod1": {
            "target_docs": PHASE4_TARGET_DOCS,
            "processing_time": dod1_time,
            "cost": dod1_cost,
        },
        "dod2": reflect,
        "all_measured": bool(all_measured),
    }
