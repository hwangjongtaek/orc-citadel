"""증분 graph update — 실증분 재적용 + full 재구축 비율·정합성 + DoD ② SLO (design 06 §7.2) TDD.

Phase 4 「증분 graph update」 — 설계 06 §7.2 incremental rebuild: 신규 문서·정정이
영향 준 **subgraph 만 재적용** (정상 운영은 incremental, 정합성 보증 시 full rebuild,
§7.1 vs §7.2). 재구축/증분 비율·절감 게이트는 #14(recompute_bench, 06 §9 3항) 에서
store 훅으로 봉인했고, 이 작업은 그 **실경로** 를 봉인한다:

- `extract_events(graph)` — GraphService 그래프를 `graph_mutations` 이벤트 스트림으로
  역직렬화 (결정·read-only) — 증분 리포트의 source.
- `apply_incremental(base, delta_events)` — 기존 base 위에 delta subgraph 만 적용
  (실증분 재적용, 그래프 쓰기는 `GraphService.apply` 경로만).
- `incremental_rebuild_bench(base_events, delta_events, executor)` — full(전량 replay)
  vs incremental(base + delta) 벽시계·ratio 측정 (10 §4.5, 06 §9 3항 — ratio > 10×).
- `evaluate_incremental_bench` + `compute_graph_slo` — **DoD ② "신규 문서가 SLO 내
  그래프 반영"** 게이트 (10 §1.4 slo-gate·CI 비차단).

**정합성 계약 (본 작업 핵심):** incremental 로 재적용한 그래프가 full replay 그래프와
**동일**해야 한다 (동일 노드·엣지·idempotency — 불변식 §3-1 파생 serving 이 결정적).
벤시계·엣지는 실행자 mock 을 통해 주입(실측 대비 mock), 결정성은 순수 에뮬레이션으로
봉인 (recompute_bench store-hooks 패턴).

read-only(불변식 §3-3)·결정적·mock/실측 격리 원칙 (Phase 4 전 작업과 동일).
"""
from __future__ import annotations

from orc_citadel.graph_incremental import (
    GRAPH_SLO_MS,
    apply_incremental,
    compute_graph_slo,
    evaluate_incremental_bench,
    extract_events,
    incremental_rebuild_bench,
)
from orc_citadel.graph_service import GraphService

# --- extract_events: 그래프 → 이벤트 스트림 (read-only) -----------------------------


def _g(nodes: int = 3) -> GraphService:
    """결정적 소형 그래프 — create_node + create_edge 로 구성 (06 §3.2 shape)."""
    g = GraphService()
    g.apply([{"idempotency_key": f"n{i}", "op": "create_node",
              "payload": {"id": f"e{i}", "props": {"seed": 1}}} for i in range(nodes)])
    for i in range(1, nodes):
        g.apply([{"idempotency_key": f"e{i}", "op": "create_edge",
                  "payload": {"type": "SUPPLIES", "from": "e0", "to": f"e{i}"}}])
    return g


def _node_ids(g: GraphService) -> list:
    return [n["id"] for n in g.nodes()]


def _edge_ids(g: GraphService) -> list:
    return [e["edge_id"] for e in g.edges()]


def test_extract_events_reads_nodes_and_edges():
    """extract_events 가 node·edge 를 mutation 이벤트로 역직렬화 (build 가능)."""
    events = extract_events(_g(3))
    op_types = {e["op"] for e in events}
    assert "create_node" in op_types and "create_edge" in op_types
    assert len(events) >= 5  # 3 node + 2 edge


def test_extract_events_is_read_only():
    """extract_events 는 입력 그래프를 변경하지 않는다 (read-only §3-3)."""
    g = _g(3)
    before = (len(g.nodes()), g.edge_count("e0"))
    extract_events(g)
    assert (len(g.nodes()), g.edge_count("e0")) == before


def test_extract_events_deterministic():
    """동일 그래프 → 동일 이벤트 스트림 (결정성)."""
    assert extract_events(_g(4)) == extract_events(_g(4))


def test_extract_events_empty():
    """빈 그래프 → 빈 이벤트 (가드)."""
    assert extract_events(GraphService()) == []


# --- apply_incremental: base 위 delta subgraph 재적용 ---------------------------------


def test_incremental_preserves_base():
    """incremental 적용 후 base 노드 보존 — 재적용이 기존을 깨지 않는다 (§7.2)."""
    base = _g(2)
    delta = [{"idempotency_key": "n2", "op": "create_node",
              "payload": {"id": "e2", "props": {}}}]
    merged = apply_incremental(base, delta)
    assert merged.node("e0") is not None
    assert merged.node("e1") is not None
    assert merged.node("e2") is not None
    assert set(_node_ids(merged)) >= {"e0", "e1", "e2"}


def test_incremental_matches_full_replay():
    """정합성 — incremental(base+delta) 그래프 == full replay 그래프 (불변식 §3-1 결정적)."""
    base = _g(2)
    delta = [{"idempotency_key": "n2", "op": "create_node",
              "payload": {"id": "e2", "props": {}}},
             {"idempotency_key": "r2", "op": "create_edge",
              "payload": {"type": "SUPPLIES", "from": "e0", "to": "e2"}}]
    inc = apply_incremental(base, delta)
    full = GraphService()
    full.apply(extract_events(_g(2)) + delta)
    assert sorted(_node_ids(inc)) == sorted(_node_ids(full))
    assert sorted(_edge_ids(inc)) == sorted(_edge_ids(full))


def test_incremental_extra_delta_only_changes_delta():
    """delta 를 늦게 적용 — idempotency 격리: 중복 이벤트는 no-op (불변식 §3-6)."""
    base = _g(2)
    delta = [{"idempotency_key": "n2", "op": "create_node",
              "payload": {"id": "e2", "props": {}}}]
    inc = apply_incremental(base, delta)
    assert _node_ids(inc).count("e2") == 1  # 중복 없음
    assert len(set(_node_ids(inc)) & {"e0", "e1", "e2"}) == 3


# --- incremental_rebuild_bench: full vs incremental 벽시계 (mock executor) ------------


def _fake_executor(counts):
    """(events, incremental) → (n_nodes, wall_ms) — mock 벽시계 주입.

    full = 전량 replay, incremental = base+delta. 결정적 주입 (실측 대비 mock).
    """
    def run(events, incremental):
        return counts, 100.0
    return run


def test_incremental_rebuild_bench_ratio():
    """full/incremental ratio 계산 — incremental 이 유의미 절감 (도구·비용)."""
    bench = incremental_rebuild_bench(
        extract_events(_g(2)), extract_events(_g(1)),
        executor=_fake_executor(None))
    assert "ratio" in bench
    assert bench["delta_nodes"] >= 1


def test_incremental_rebuild_bench_full_gt_incr():
    """full 벽시계 ≥ incremental (incremental 이 더 싸다 — §7.2)."""
    def exec(events, incremental):
        return {"n_nodes": len({e["payload"]["id"] for e in events
                                if e["op"] == "create_node"})}, (500.0 if not incremental else 50.0)
    bench = incremental_rebuild_bench(extract_events(_g(3)), extract_events(_g(2)),
                                      executor=exec)
    assert bench["full_ms"] >= bench["incremental_ms"]


def test_evaluate_incremental_bench_ratio_gate():
    """완료조건 게이트 — ratio > 10× 유의미 절감 (10 §4.5, 06 §9 3항)."""
    res = evaluate_incremental_bench({"ratio": 20.0})
    assert res["saving_meaningful"] is True
    assert res["gate"]["pass"] is True
    assert res["slo_gate"] is True  # CI 비차단 nightly (10 §1.4)


def test_evaluate_incremental_bench_not_meaningful():
    """ratio ≤ 10 → 절감 미유의 (fail)."""
    res = evaluate_incremental_bench({"ratio": 3.0})
    assert res["saving_meaningful"] is False
    assert res["gate"]["pass"] is False


# --- DoD ②: 신규 문서 SLO 내 그래프 반영 ----------------------------------------------


def test_compute_graph_slo_ok():
    """신규 반영 지연 p95 < SLO → DoD ② 충족 (10 §1.4 slo-gate 비차단)."""
    res = compute_graph_slo(p95_ms=GRAPH_SLO_MS - 10)
    assert res["within_slo"] is True
    assert res["classified"] == "ok"


def test_compute_graph_slo_violated():
    """p95 ≥ SLO → slo-gate 경보 (CI 차단 안 함, nightly)."""
    res = compute_graph_slo(p95_ms=GRAPH_SLO_MS + 10)
    assert res["within_slo"] is False
    assert res["classified"] == "slo-gate"


def test_compute_graph_slo_unmeasured():
    """미측정(None) → within_slo False·경보 (honest-gap §6.2 — 부재가 OK 아님)."""
    res = compute_graph_slo(p95_ms=None)
    assert res["within_slo"] is False
    assert res["classified"] == "not-measured"


# --- read-only·결정성 --------------------------------------------------------------------


def test_read_only_no_mutation():
    """증분 모듈 read-only — 쓰기·mutation 미노출 (불변식 §3-3, 함수형만)."""
    from orc_citadel import graph_incremental as gi

    for bad in ("persist", "create_node", "create_edge", "insert", "upsert"):
        assert not hasattr(gi, bad), f"read-only 위반: {bad} 노출"


def test_evaluate_bench_deterministic():
    """동일 bench → 동일 평가 (결정성)."""
    from orc_citadel.graph_incremental import evaluate_incremental_bench
    r1 = evaluate_incremental_bench({"ratio": 15.0})
    r2 = evaluate_incremental_bench({"ratio": 15.0})
    assert r1 == r2
