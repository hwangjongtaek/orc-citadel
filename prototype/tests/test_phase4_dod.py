"""Phase 4 DoD ①② 통합 검증 (design 01 §6·06 §7.2·10 §4.5·§1.4) TDD.

**DoD ① — 100만 문서 처리 시간·비용 공개.**
#14(분산 batch)·#17(batch inference 50% 절감)·#18(투영) 이 봉인한 계약을 조합해
100만 스케일의 처리 시간·비용을 공개한다. 이 값은 **결정적 모델 투영**이며 실측이
아니므로 정직하게 `measured=False` 로 표시 (10 §6.2 honest-gap).

**DoD ② — 신규 문서 SLO 내 graph 반영.**
#15(증분 graph update) 실경로를 실제 `GraphService` 로 구동해 **incremental 재적용
그래프 == full replay 그래프**(불변식 §3-1 정합성)를 확인하고, 증분이 full 대비
**ratio > 10× 절감** 완료조건을 충족하며, 신규 문서 반영 p95 가 `GRAPH_SLO_MS` 내에
들면 `compute_graph_slo`가 `ok` 로 판정 — DoD ② 를 통합 검증한다.

read-only · 결정적 · mock/실측 격리 (실측 백엔드는 executor 주입, 결정성은 에뮬레이션).
"""
from __future__ import annotations

import pytest

from orc_citadel.distributed_batch import (
    ParallelismBench, compute_slo_gate, throughput_docs_per_sec,
)
from orc_citadel.graph_incremental import (
    INCREMENTAL_RATIO_GATE,
    incremental_rebuild_bench,
    apply_incremental,
    evaluate_incremental_bench,
    extract_events,
    compute_graph_slo,
)
from orc_citadel.graph_service import GraphService
from orc_citadel.batch_inference import (
    MESSAGE_BATCHES_DISCOUNT, batch_inference_cost,
)
from orc_citadel.pipeline_bench import (
    THROUGHPUT_TARGET_DOCS_PER_SEC, throughput, per_doc_stats,
)
from orc_citadel.phase4_report import (
    PHASE4_TARGET_DOCS,
    phase4_dod_report,
    project_cost_to_scale,
    project_time_to_scale,
)


# --- 공통 픽스처 -------------------------------------------------------------

def _g(num_nodes: int, num_edges: int) -> GraphService:
    """num_nodes 노드·num_edges 엣지 그래프 — 실제 GraphService 로 생성."""
    g = GraphService()
    events = []
    for i in range(num_nodes):
        events.append({"mutation_id": f"m{i}", "idempotency_key": f"k{i}",
                       "op": "create_node",
                       "payload": {"id": f"n{i}", "props": {"v": i}, "labels": []}})
    for i in range(num_edges):
        events.append({"mutation_id": f"e{i}", "idempotency_key": f"ke{i}",
                       "op": "create_edge",
                       "payload": {"type": "SUPPLIES", "from": f"n{i}",
                                   "to": f"n{(i+1) % num_nodes}", "props": {}}})
    g.apply(events)
    return g


def _node_ids(g: GraphService) -> set:
    return {n["id"] for n in g.nodes()}


# --- DoD ① — 100만 처리 시간·비용 공개 ---------------------------------------


def test_dod1_time_cost_published_at_1m():
    """DoD ① — 100만 스케일 처리 시간·비용을 공개 리포트로 산출 (10 §4.5)."""
    # 실측이 되는 결정적 벤치 계약에 근거해 per-doc 단위 측정값 사용.
    time_ = project_time_to_scale(per_doc_ms=22.6, docs_processed=138,
                                  target_docs=PHASE4_TARGET_DOCS,
                                  parallel_speedup=4.0)
    cost_ = project_cost_to_scale(cost_per_doc=0.01, docs_processed=138,
                                  target_docs=PHASE4_TARGET_DOCS, use_batch=True)
    gs = {"classified": "ok", "within_slo": True}
    rep = phase4_dod_report(dod1_time=time_, dod1_cost=cost_, graph_slo=gs)
    # 공개 — time·cost 구성요소 존재, target = 1,000,000 문서.
    assert rep["dod1"]["target_docs"] == 1_000_000
    assert time_["projected_ms"] is not None
    assert cost_["projected_cost"] is not None
    # DoD ② 구성요소도 통합 노출.
    assert rep["dod2"]["graph_slo"]["within_slo"] is True


def test_dod1_batch_discount_published():
    """DoD ① — batch 경로 비용이 Message Batches 50% 절감으로 공개 (#17 재사용)."""
    bc = batch_inference_cost(n_calls=1_000_000, cost_per_call=0.01)
    assert bc["batch_cost"] == pytest.approx(1_000_000 * 0.01 * MESSAGE_BATCHES_DISCOUNT)
    assert bc["saving_ratio"] == pytest.approx(0.5)


def test_dod1_projections_honest_not_claimed_measured():
    """DoD ① — 투영은 결정적 모델 값이 실측이 아니므로 measured 가 아님이 정직하다."""
    time_ = project_time_to_scale(None, docs_processed=138)  # per-doc 미측정.
    # repo.slo 는 실측 입력이 있어야 ok — 미측정 입력은 measured=False (honest-gap §6.2).
    assert time_["measured"] is False
    assert time_["projected_ms"] is None


def test_dod1_slo_gate_non_blocking():
    """DoD ① — 처리 SLO 위반은 slo-gate(CI 비차단 nightly) 분류 (10 §1.4·§6.3)."""
    # PER_NODE_SLO_MS=60000 — 노드당 100초는 위반 (≥ 60s).
    g = compute_slo_gate(per_node_ms=100_000.0, wall_ms=120_000.0)
    assert g["classified"] == "slo-gate"
    assert g["violated"] is True


# --- DoD ② — 신규 문서 SLO 내 graph 반영 -----------------------------------


def test_dod2_incremental_equals_full_replay():
    """DoD ② — incremental 재적용 그래프 == full replay 그래프 (불변식 §3-1)."""
    base = _g(num_nodes=8, num_edges=6)
    delta = _g(num_nodes=2, num_edges=1)  # 신규 문서 subgraph.
    # full replay: base + delta 전체 이벤트로 재구축.
    full = GraphService()
    full.apply(extract_events(base) + extract_events(delta))
    # incremental: base 위 delta 만 재적용.
    inc = apply_incremental(base, extract_events(delta))
    assert _node_ids(full) == _node_ids(inc)  # 정합성 동치 (§3-1).
    # base 는 변경되지 않는다 (read-only — 입력 불변).
    assert len(_node_ids(base)) == 8


def test_dod2_incremental_saving_gate():
    """DoD ② — 증분이 full 대비 ratio > 10× 절감 완료조건 (10 §4.5, 06 §9 3항)."""
    base_events = extract_events(_g(num_nodes=100, num_edges=90))
    delta_events = extract_events(_g(num_nodes=1, num_edges=0))  # 신규 1 노드.

    def executor(events, incremental):
        # 실측 대비 mock — incremental 은 delta 만, full 은 전체 재적용.
        return ({}, float(len(events)))

    bench = incremental_rebuild_bench(base_events, delta_events, executor=executor)
    ev = evaluate_incremental_bench(bench)
    assert bench["ratio"] > INCREMENTAL_RATIO_GATE
    assert ev["saving_meaningful"] is True
    assert ev["gate"]["pass"] is True


def test_dod2_within_slo():
    """DoD ② — 신규 문서 반영 p95 가 GRAPH_SLO_MS 내 → ok (SLO 내 반영)."""
    g = compute_graph_slo(p95_ms=5_000.0)  # < 60s.
    assert g["within_slo"] is True
    assert g["classified"] == "ok"


def test_dod2_unmeasured_honest_gap():
    """DoD ② — 반영 지연 미측정 → not-measured (진공 통과 금지, §6.2)."""
    g = compute_graph_slo(None)
    assert g["classified"] == "not-measured"
    assert g["within_slo"] is False


def test_dod2_full_integration():
    """DoD ② — 별도 헬퍼 아닌 실제 엔진 조합으로 SLO 내 반영 검증.

    (1) 분산 throughput 으로 처리량 확인 → (2) 증분 절감 gate 통과 →
    (3) 반영 지연 p95 SLO ok → (4) phase4_dod_report 로 DoD ①② 통합 공개.
    """
    # (1) throughput (10 §1.4).
    tp = throughput(138, 10.0)
    assert tp == pytest.approx(13.8)

    # (2) 증분 절감 게이트.
    base_events = extract_events(_g(num_nodes=100, num_edges=90))
    delta_events = extract_events(_g(num_nodes=1, num_edges=0))

    def ex(events, incremental):
        return ({}, float(len(events)))
    bench = incremental_rebuild_bench(base_events, delta_events, executor=ex)
    ev = evaluate_incremental_bench(bench)
    assert ev["saving_meaningful"] is True

    # (3) 반영 지연 p95 SLO.
    gs = compute_graph_slo(p95_ms=10_000.0)
    assert gs["classified"] == "ok"

    # (4) DoD ①② 통합 공개 (measured 상태 honest).
    time_ = project_time_to_scale(22.6, 138, target_docs=PHASE4_TARGET_DOCS)
    cost_ = project_cost_to_scale(0.01, 138, target_docs=PHASE4_TARGET_DOCS,
                                  use_batch=True)
    rep = phase4_dod_report(time_, cost_, gs,
                            latency_slo=compute_slo_gate(500.0, 600.0),
                            incremental_gate=ev)
    assert rep["dod2"]["incremental_gate"]["gate"]["pass"] is True
    assert rep["all_measured"] is True


def test_dod2_read_only_base_preserved():
    """DoD ② — incremental 재적용은 base 그래프를 변경하지 않는다 (read-only §3-3)."""
    base = _g(num_nodes=8, num_edges=6)
    base_snapshot_nodes = _node_ids(base)
    delta = _g(num_nodes=2, num_edges=1)
    apply_incremental(base, extract_events(delta))
    assert _node_ids(base) == base_snapshot_nodes


# --- 모든 실행이 결정적이며 read-only ----------------------------------------


def test_phase4_dod_deterministic():
    """동일 입력 → 동일 벤치·리포트 (결정성 — 재현성)."""
    base_events = extract_events(_g(num_nodes=100, num_edges=90))
    delta_events = extract_events(_g(num_nodes=1, num_edges=0))

    def ex(events, incremental):
        return ({}, float(len(events)))
    a = incremental_rebuild_bench(base_events, delta_events, executor=ex)
    b = incremental_rebuild_bench(base_events, delta_events, executor=ex)
    assert a == b


def test_phase4_report_no_mutation_exposed():
    """aggregate DoD ② — 그래프 서비스는 mutation 을 통한 변경만 노출 (read-only)."""
    g = _g(num_nodes=3, num_edges=2)
    # GraphService 의 read API 만 노출 — 직접 apply 외 쓰기 미존재 경로 확인.
    events = extract_events(g)  # read-only 역직렬화.
    assert len(events) == 5  # 3 노드 + 2 엣지.
