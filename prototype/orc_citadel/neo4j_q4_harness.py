"""Q4 한계 측정 하니스 — Neo4j 부하 지표 실측 + 게이트 판정 (design 06 §9).

Q4 게이트 (06 §9, 2026-08-03 확정): Neo4j Community 근접·교체 판정을 트리거하는 임계.
  - 노드 수 ≥ `1e6` (Community 단일 인스턴스 실용 한계)
  - 그래프 조회 p95 latency ≥ `500 ms` (SLO 게이트, 09 §2.2 조회 계약)
  - 재구축(이벤트 replay) 벽시계 > 증분 재구축의 `10×` (백필 비용 분기)

결정적 합성 그래프를 가동 Neo4j 에 적제·조회해 3개 지표를 실측한다. 그래프 생성·게이트
판정은 순수 함수(오프라인 단위검증), 측정은 통합(가동 시 실측, 오프라인 skip).
"""
from __future__ import annotations

import statistics
import time

from .graph_service import GraphService

# 06 §9 게이트 상수.
NODE_GATE = 1_000_000
LATENCY_GATE_MS = 500
REBUILD_RATIO_GATE = 10.0


def synthetic_graph(n_nodes: int, edges_per_node: int = 3,
                    seed: int = 7) -> GraphService:
    """결정적 합성 그래프 — 벤치 재현성 (동일 인자 → 동일 그래프).

    `n_nodes` 개선 Entity + 각 노드가 반복적으로 이웃을 향하는 엣지(참조 무결성 유지,
    dangling 없음 — Neo4j MERGE 전제와 정합). 엣지 type 은 controlled vocabulary.
    """
    g = GraphService()
    nodes = [f"v{n:06d}" for n in range(n_nodes)]
    for i, nid in enumerate(nodes):
        g.apply([{"idempotency_key": f"n-{i}", "op": "create_node",
                  "payload": {"id": nid, "props": {"seed": seed, "n": i}}}])
    seq = 0
    for i, nid in enumerate(nodes):
        for k in range(1, edges_per_node + 1):
            j = (i + k * seed) % n_nodes
            if j == i:
                continue
            etype = ["SUPPLIES", "PARTNERED_WITH", "COMPETES"][(i + k) % 3]
            seq += 1
            g.apply([{"idempotency_key": f"e-{seq}", "op": "create_edge",
                      "payload": {"type": etype, "from": nid, "to": nodes[j],
                                  "props": {}}}])
    return g


def measure_load(store, graph) -> dict:
    """GraphService 그래프를 Neo4j 에 MERGE 적제하고 벽시계·규모 측정."""
    t0 = time.perf_counter()
    store.load_graph(graph)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    nc = store.node_count()
    return {
        "nodes": len(graph.nodes()),
        "edges": len(graph.edges()),
        "node_count": nc,
        "load_elapsed_ms": round(elapsed_ms, 3),
    }


def measure_query_latency(store, sample_ids, repeat: int = 5) -> dict:
    """샘플 노드의 인접 조회 지연 분포 → p95 (SLO 게이트, 09 §2.2).

    `query_neighbors` 를 샘플별·반복 실행해 p95(ms)를 산출한다. 소규모 그래프면
    p95 는 게이트(500ms)를 크게 밑돌 것으로 기대 — 실측 기준선.
    """
    lat = []
    n_queries = 0
    for i in range(repeat):
        for nid in sample_ids:
            t0 = time.perf_counter()
            store.query_neighbors(nid)
            lat.append((time.perf_counter() - t0) * 1000)
            n_queries += 1
    lat.sort()
    idx = int(0.95 * (len(lat) - 1))
    return {"p95_ms": round(lat[idx], 3), "n_queries": n_queries}


def evaluate_q4(stats: dict) -> dict:
    """실측 지표를 06 §9 임계와 비교해 게이트 판정 (오프라인 순수 함수)."""
    reasons = []
    nodes = stats.get("nodes", 0)
    p95 = stats.get("p95_ms", 0)
    ratio = stats.get("rebuild_ratio", 0)
    if nodes >= NODE_GATE:
        reasons.append(f"NODE_GATE: nodes {nodes} >= {NODE_GATE}")
    if stats.get("p95_ms") is not None and p95 >= LATENCY_GATE_MS:
        reasons.append(f"LATENCY_GATE_MS: p95 {p95} >= {LATENCY_GATE_MS}")
    if stats.get("rebuild_ratio") is not None and ratio > REBUILD_RATIO_GATE:
        reasons.append(f"REBUILD_RATIO_GATE: ratio {ratio} > {REBUILD_RATIO_GATE}")
    return {"tripped": bool(reasons), "reasons": reasons}
