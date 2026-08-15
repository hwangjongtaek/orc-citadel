"""impact graph 부분 재계산 — 영향 하류 재계산 범위 도출·절감 게이트 (06 §7.2·§5.2, 10 §4.5, Phase 5) TDD.

Phase 5 「impact graph 부분 재계산」 — 엔터티/claim 변경 시 **영향 하류 subgraph 를
도출**해 full 재계산 대신 **부분 재계산만 수행**하도록 범위를 봉인한다
(design 06 §7.2 — 신규/정정이 영향 준 subgraph 만 재적용; §5.2 — 재지정이 독립 증거·
모순 판정에 파급 → subgraph 재평가; 10 §4.5 — partial recomputation 이 full 대비 유의미 절감).

- `impact_scope` — 전파 엣지(ABOUT/SUPPORTS/CONTRADICTS/SUPERSEDES/SAME_AS) BFS로 변경
  target 에서 도달 가능한 **영향 노드 집합** (read-only·결정적, hops/타입 한정).
- `impact_subgraph` — 영향 범위를 **materialized subgraph**(노드+내부 엣지) 로 노출.
- `partial_recompute_events` — full 이벤트 중 영향 범위 내 노드·내부 엣지만 재적용 대상으로
  추림 (부분 재계산 이벤트 집합).
- `partial_vs_full` — full/partial 이벤트 수·ratio (부분 절감 계량). 빈 영향(partial=0) →
  ratio None + empty_scope (honest-gap §6.2 — "아무것도 안 함" 을 유의미 절감으로 오판 금지).
- `evaluate_partial_recompute` — 완료조건 게이트 ratio > gate → `saving_meaningful` +
  slo-gate(10 §1.4 CI 비차단 nightly).

read-only(불변식 §3-3)·결정적·mock/실측 격리 원칙 (Phase 4/5 전 작업과 동일).
"""
from __future__ import annotations

import pytest

from orc_citadel.graph_service import GraphService
from orc_citadel.impact_graph import (
    PROPAGATION_TYPES,
    evaluate_partial_recompute,
    impact_scope,
    impact_subgraph,
    partial_recompute_events,
    partial_vs_full,
)


def _g(nodes: list[str], edges: list[tuple]) -> GraphService:
    """편의 — GraphService 구축 (create_node + create_edge 결정적 이벤트)."""
    g = GraphService()
    events = []
    for i, nid in enumerate(nodes):
        events.append({"idempotency_key": f"n{i}", "op": "create_node",
                       "payload": {"id": nid, "props": {"claim": f"c-{nid}"}}})
    for j, (f, t, etype) in enumerate(edges):
        events.append({"idempotency_key": f"e{j}", "op": "create_edge",
                       "payload": {"type": etype, "from": f, "to": t}})
    g.apply(events)
    return g


def _events(g, prefix="all"):
    """GraphService → `graph_mutations`-shape 이벤트 (전체 raw stream)."""
    evs = []
    for nd in g.nodes():
        evs.append({"idempotency_key": f"{prefix}:n:{nd['id']}", "op": "create_node",
                    "payload": {"id": nd["id"]}})
    for ed in g.edges():
        evs.append({"idempotency_key": f"{prefix}:e:{ed['edge_id']}", "op": "create_edge",
                    "payload": {"edge_id": ed["edge_id"], "type": ed["type"],
                                "from": ed["from"], "to": ed["to"]}})
    return evs


# --- impact_scope (전파 BFS — 영향 하류 집합) --------------------------------


def test_scope_claims_evidence_chain():
    """entity→ABOUT→claim→SUPPORTS/evidence 체인 — claim 변경 시 하류 전체 도달."""
    g = _g(["ent1", "clm1", "ev1", "ev2"],
           [("ent1", "clm1", "ABOUT"), ("ev1", "clm1", "SUPPORTS"),
            ("ev2", "clm1", "CONTRADICTS")])
    scope = impact_scope(g, ["clm1"])
    assert set(scope) == {"clm1", "ev1", "ev2", "ent1"}


def test_scope_includes_target():
    """변경 target 자체가 scope 에 포함된다."""
    g = _g(["a"], [])
    assert impact_scope(g, ["a"]) == ["a"]


def test_scope_unrelated_not_reached():
    """전파 엣지로 연결되지 않은 노드는 scope 에 들지 않는다."""
    g = _g(["clm1", "ev1", "other"],
           [("ev1", "clm1", "SUPPORTS")])
    assert "other" not in impact_scope(g, ["clm1"])


def test_scope_reverse_contradicts():
    """CONTRADICTS 도 방향 무관 전파 — 양끝 상호 영향."""
    g = _g(["a", "b"], [("a", "b", "CONTRADICTS")])
    scope = impact_scope(g, ["a"])
    assert set(scope) == {"a", "b"}


def test_scope_hops_limited():
    """hops=1 → 1-hop 인접만, 심층 하류 제외 (범위 상한)."""
    g = _g(["a", "b", "c"], [("a", "b", "SUPPORTS"), ("b", "c", "SUPPORTS")])
    assert set(impact_scope(g, ["a"], hops=1)) == {"a", "b"}


def test_scope_type_filtered():
    """include_types 로 전파 엣지 제한 — 지정 엣지로만 도달."""
    g = _g(["a", "b", "c"], [("a", "b", "SUPPORTS"), ("b", "c", "SAME_AS")])
    scope = impact_scope(g, ["a"], include_types=("SUPPORTS",))
    assert set(scope) == {"a", "b"}


def test_scope_supersede_chain():
    """supersede 파급(§7.2) — 신·구 버전 체인 전파."""
    g = _g(["v1", "v2", "v3"],
           [("v2", "v1", "SUPERSEDES"), ("v3", "v2", "SUPERSEDES")])
    assert set(impact_scope(g, ["v1"])) == {"v1", "v2", "v3"}


def test_scope_merge_same_as():
    """merge 파급(§7.2, SAME_AS) — 동치류 전체 도달."""
    g = _g(["m1", "m2", "canon"],
           [("m1", "canon", "SAME_AS"), ("m2", "canon", "SAME_AS")])
    assert set(impact_scope(g, ["m1"])) == {"m1", "m2", "canon"}


def test_scope_empty_targets():
    """target 없음 → 빈 scope."""
    g = _g(["a"], [])
    assert impact_scope(g, []) == []


def test_scope_missing_target_skipped():
    """미존재 target 은 건너뛰고 반환 (안전)."""
    g = _g(["a"], [])
    assert impact_scope(g, ["ghost"]) == []


def test_scope_deterministic():
    """동일 그래프·target → 동일 scope (결정성)."""
    g = _g(["a", "b", "c"], [("a", "b", "SUPPORTS"), ("b", "c", "SUPPORTS")])
    assert impact_scope(g, ["a"]) == impact_scope(g, ["a"])


def test_scope_multi_target_union():
    """여러 target — 각 scope 의 합집합."""
    g = _g(["a", "b", "c", "d"],
           [("a", "b", "SUPPORTS"), ("c", "d", "CONTRADICTS")])
    assert set(impact_scope(g, ["a", "c"])) == {"a", "b", "c", "d"}


# --- impact_subgraph (영향 범위 materialize) ---------------------------------


def test_subgraph_nodes_and_internal_edges():
    """영향 subgraph — 연결된 증거 클러스터 전체 + 내부 엣지, 비연결 노드 제외."""
    g = _g(["clm1", "ev1", "ev2", "isolated"],
           [("ev1", "clm1", "SUPPORTS"), ("ev2", "clm1", "CONTRADICTS")])
    sub = impact_subgraph(g, ["clm1"])
    ids = {n["id"] for n in sub["nodes"]}
    assert ids == {"clm1", "ev1", "ev2"}          # isolated 는 비연결 → 미영향
    types = {e["type"] for e in sub["edges"]}
    assert types == {"SUPPORTS", "CONTRADICTS"}


def test_subgraph_excludes_unconnected_node():
    """연결되지 않은 노드는 scope·subgraph 에 들지 않는다 (부분 재계산 섬)."""
    g = _g(["a", "b", "solo"], [("a", "b", "SUPPORTS")])
    sub = impact_subgraph(g, ["a"])
    ids = {n["id"] for n in sub["nodes"]}
    assert ids == {"a", "b"}
    assert "solo" not in ids


def test_subgraph_scoped_hop():
    """hops 한정으로 subgraph 범위 축소."""
    g = _g(["a", "b", "c"], [("a", "b", "SUPPORTS"), ("b", "c", "SUPPORTS")])
    sub = impact_subgraph(g, ["a"], hops=1)
    ids = {n["id"] for n in sub["nodes"]}
    assert ids == {"a", "b"}


def test_subgraph_empty_target():
    """빈 target → 빈 subgraph."""
    g = _g(["a"], [])
    sub = impact_subgraph(g, [])
    assert sub["nodes"] == [] and sub["edges"] == []


# --- partial_recompute_events (부분 재계산 이벤트 추림) ----------------------


def test_partial_keeps_scope_events():
    """full 이벤트 중 scope 노드 + 내부 엣지만 유지, 비연결 제외."""
    g = _g(["clm1", "ev1", "isolated"],
           [("ev1", "clm1", "SUPPORTS")])
    full = _events(g)
    part = partial_recompute_events(g, full, ["clm1"])
    part_ids = set()
    for e in part:
        if e["op"] == "create_node":
            part_ids.add(e["payload"]["id"])
    assert part_ids == {"clm1", "ev1"}
    assert "isolated" not in part_ids


def test_partial_empty_scope():
    """target 미존재 → 빈 partial (부분 재계산 이벤트 0)."""
    g = _g(["a"], [])
    part = partial_recompute_events(g, _events(g), ["ghost"])
    assert part == []


def test_partial_subset_of_full():
    """partial 은 full 의 부분집합 — 비연결 노드는 제외 (이벤트 순서 보존)."""
    g = _g(["a", "b", "isolated"], [("a", "b", "ABOUT")])
    full = _events(g)
    part = partial_recompute_events(g, full, ["a"])
    assert len(part) < len(full)
    assert part[0]["op"] == "create_node"  # 순서 보존 (노드 먼저)


# --- partial_vs_full (부분 절감 계량 + honest-gap) ---------------------------


def test_partial_vs_full_ratio():
    """full vs partial 이벤트 수 → ratio = full/partial."""
    g = _g(["clm1", "ev1", "ev2", "isolated"],
           [("ev1", "clm1", "SUPPORTS"), ("ev2", "clm1", "CONTRADICTS")])
    brief = partial_vs_full(g, _events(g), ["clm1"])
    # full=4노드+2엣지=6; partial=클러스터(3노드 clm1,ev1,ev2 + 내부 2엣지)=5 → ratio=1.2
    assert brief["full_events"] == 6
    assert brief["partial_events"] == 5
    assert brief["ratio"] == pytest.approx(6 / 5)


def test_partial_empty_scope_honest():
    """partial=0 → ratio None + empty_scope (honest-gap — 오판 방지)."""
    g = _g(["a"], [])
    brief = partial_vs_full(g, _events(g), ["ghost"])
    assert brief["ratio"] is None
    assert brief["empty_scope"] is True


def test_partial_no_events_guard():
    """full 이벤트 없음 → ratio None (측정 불가)."""
    g = _g(["a"], [])
    brief = partial_vs_full(g, [], ["a"])
    assert brief["ratio"] is None


def test_partial_deterministic():
    """동일 입력 → 동일 계량 (결정성)."""
    g = _g(["a", "b"], [("a", "b", "ABOUT")])
    assert partial_vs_full(g, _events(g), ["a"]) == partial_vs_full(g, _events(g), ["a"])


# --- evaluate_partial_recompute (완료조건 게이트) ----------------------------


def test_evaluate_meaningful_saving():
    """ratio > gate → saving_meaningful + slo-gate (CI 비차단 nightly)."""
    brief = {"ratio": 8.0, "full_events": 8, "partial_events": 1, "empty_scope": False}
    r = evaluate_partial_recompute(brief)
    assert r["saving_meaningful"] is True
    assert r["classified"] == "slo-gate"  # 10 §1.4 — 성능은 nightly 경보, 차단 아님


def test_evaluate_no_saving_below_gate():
    """ratio ≤ gate → 절감 미인정."""
    brief = {"ratio": 2.0, "full_events": 6, "partial_events": 3, "empty_scope": False}
    r = evaluate_partial_recompute(brief)
    assert r["saving_meaningful"] is False


def test_evaluate_empty_scope_not_meaningful():
    """empty_scope(ratio None) → 절감 미인정 (honest — "아무것도 안 함"≠절감)."""
    brief = {"ratio": None, "full_events": 6, "partial_events": 0, "empty_scope": True}
    r = evaluate_partial_recompute(brief)
    assert r["saving_meaningful"] is False
    assert r["classified"] == "empty-scope"


def test_evaluate_custom_gate():
    """gate placeholder 조정 가능."""
    brief = {"ratio": 1.5, "full_events": 3, "partial_events": 2, "empty_scope": False}
    assert evaluate_partial_recompute(brief, gate=1.0)["saving_meaningful"] is True


def test_evaluate_deterministic():
    """동일 입력 → 동일 평가 (결정성)."""
    brief = {"ratio": 4.0, "full_events": 4, "partial_events": 1, "empty_scope": False}
    assert evaluate_partial_recompute(brief) == evaluate_partial_recompute(brief)


# --- read-only / 결정성 통합 ------------------------------------------------


def test_read_only_no_mutation():
    """impact_graph 모듈은 read-only — 쓰기·mutation 미노출 (불변식 §3-3)."""
    from orc_citadel import impact_graph as ig

    for bad in ("apply", "persist", "create_node", "create_edge", "insert",
                "write", "upsert"):
        assert not hasattr(ig, bad), f"read-only 위반: {bad} 노출"
