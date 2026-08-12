"""Q4 한계 측정 하니스 — 결정적 합성 그래프 + 부하 지표 + 게이트 판정 (design 06 §9) TDD.

Q4 게이트 (06 §9, 2026-08-03 확정): Neo4j Community 근접·교체 판정을 트리거하는 임계.
  - 노드 수 ≥ 1e6 (Community 단일 인스턴스 실용 한계)
  - 그래프 조회 p95 latency ≥ 500 ms (SLO 게이트, 09 §2.2 조회 계약)
  - 재구축(이벤트 replay) 벽시계 > 증분 재구축의 10× (백필 비용 분기)

가동 Neo4j 를 향해 결정적 합성 그래프를 적제·조회해 3개 지표를 실측하고, 임계 초과 여부를
판정한다. 그래프 생성·게이트 판정은 순수 함수(오프라인 단위검증), Neo4j 통합은
importorskip 으로 격리해 기존 스위트 보존.
"""
from __future__ import annotations

import pytest

from orc_citadel.neo4j_q4_harness import (
    evaluate_q4,
    synthetic_graph,
    NODE_GATE,
    LATENCY_GATE_MS,
    REBUILD_RATIO_GATE,
)


# --- 결정적 합성 그래프 생성 (오프라인) ---------------------------------------

def test_synthetic_graph_is_deterministic_same_seed():
    g1 = synthetic_graph(50, edges_per_node=3)
    g2 = synthetic_graph(50, edges_per_node=3)
    assert {n["id"] for n in g1.nodes()} == {n["id"] for n in g2.nodes()}
    assert len(g1.edges()) == len(g2.edges())
    assert [e["type"] for e in g1.edges()][:5] == [e["type"] for e in g2.edges()][:5]


def test_synthetic_graph_node_edge_counts():
    g = synthetic_graph(100, edges_per_node=3)
    assert len(g.nodes()) == 100
    # 충분한 엣지가 생성되었고 참조 무결성(quarantine 없음) 유지.
    assert len(g.edges()) >= 100
    assert g.quarantined_edges() == []


def test_synthetic_graph_ids_are_controlled_etype():
    g = synthetic_graph(20, edges_per_node=2)
    for e in g.edges():
        assert " " not in e["type"]
        assert e["type"].isalnum() or "_" in e["type"]


# --- Q4 게이트 판정 (오프라인 경계값) ------------------------------------------

def test_evaluate_q4_below_thresholds_is_pass():
    stats = {"nodes": 100_000, "p95_ms": 45, "rebuild_ratio": 6.0}
    verdict = evaluate_q4(stats)
    assert verdict["tripped"] is False


def _has(reasons, tag: str) -> bool:
    return any(tag in r for r in reasons)


def test_evaluate_q4_node_count_gate():
    verdict = evaluate_q4({"nodes": NODE_GATE, "p95_ms": 10, "rebuild_ratio": 1.0})
    assert verdict["tripped"] is True
    assert _has(verdict["reasons"], "NODE_GATE")


def test_evaluate_q4_latency_gate():
    verdict = evaluate_q4({"nodes": 1000, "p95_ms": LATENCY_GATE_MS, "rebuild_ratio": 1.0})
    assert verdict["tripped"] is True
    assert _has(verdict["reasons"], "LATENCY_GATE_MS")


def test_evaluate_q4_rebuild_ratio_gate_strict_greater():
    # spec 은 "재구축 > 증분 10×" (strict) — 정확히 10× 는 미트립, 초과 시 트립.
    at = evaluate_q4({"nodes": 1000, "p95_ms": 10, "rebuild_ratio": REBUILD_RATIO_GATE})
    assert at["tripped"] is False
    verdict = evaluate_q4({"nodes": 1000, "p95_ms": 10, "rebuild_ratio": REBUILD_RATIO_GATE + 0.5})
    assert verdict["tripped"] is True
    assert _has(verdict["reasons"], "REBUILD_RATIO_GATE")


def test_evaluate_q4_multiple_gates_reported():
    stats = {"nodes": NODE_GATE, "p95_ms": 600, "rebuild_ratio": 12.0}
    verdict = evaluate_q4(stats)
    assert verdict["tripped"] is True
    assert len(verdict["reasons"]) >= 2


def test_evaluate_q4_missing_metric_defaults_no_trip():
    verdict = evaluate_q4({"nodes": 1000})
    assert verdict["tripped"] is False


# --- Neo4j 통합 (가동 시 실측, 오프라인 skip) ----------------------------------

neo4j = pytest.importorskip("neo4j")

from orc_citadel.neo4j_graph_store import Neo4jGraphStore, build_neo4j_driver
from orc_citadel.neo4j_q4_harness import measure_load, measure_query_latency


@pytest.fixture()
def store():
    try:
        s = Neo4jGraphStore()
    except Exception as exc:
        pytest.skip(f"Neo4j 연결 불가: {exc}")
    s.clear()
    yield s
    try:
        s.clear()
        s.close()
    except Exception:
        pass


def test_measure_load_counts_nodes_and_edges(store):
    g = synthetic_graph(40, edges_per_node=3)
    stats = measure_load(store, g)
    assert stats["nodes"] == len(g.nodes())
    assert stats["edges"] == len(g.edges())
    assert stats["node_count"] == len(g.nodes())
    assert stats["load_elapsed_ms"] >= 0


def test_measure_query_latency_p95_at_small_scale(store):
    g = synthetic_graph(40, edges_per_node=3)
    measure_load(store, g)
    ids = [n["id"] for n in g.nodes()][:10]
    stats = measure_query_latency(store, sample_ids=ids)
    assert "p95_ms" in stats
    assert "n_queries" in stats
    # 소규모에서는 p95 가 게이트(500ms) 미만이어야 정상 스케일 확인.
    assert stats["p95_ms"] < LATENCY_GATE_MS


# --- 재구축 vs 증분 (3번째 게이트) 측정 — 통합 ---------------------------------

def test_measure_rebuild_ratio_reports_full_and_incremental(store):
    """재구축(full load) 대 증분(large delta append) 벽시계 비율 실측.

    동일 규모의 그래프를 (a) 전체 재구축(빈 상태에서 load) (b) 기존 그래프에 증분 append
    두 방식으로 적재해, '재구축 비용이 증분의 10× 내' 여부를 게이트에 공급한다 (06 §9 3항).
    """
    from orc_citadel.neo4j_q4_harness import measure_rebuild

    # 소규모에서는 full/incremental 모두 빠르며 비율도 안정 — 계약만 검증.
    stats = measure_rebuild(store, base_nodes=30, delta_nodes=20)
    assert "full_ms" in stats and "incremental_ms" in stats
    assert "ratio" in stats
    assert stats["ratio"] > 0
    # 증분이 full 보다 비싸진 않을 것 (전형적으로 full ≥ incremental).
    # 엄밀하게는 같을 수도 있어 비율 하한만 보장한다.
