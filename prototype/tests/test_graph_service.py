"""S16 Graph Service — Applier(replay) (설계 06 §3, 03 §7) TDD.

graph_mutations 이벤트를 순서대로 소비해 authoritative 노드-엣지 그래프를 재구축한다.
idempotency(§3.1), create_edge reference 무결성(§3.2, 02 §4-3), 조회. 물리 Neo4j 아님
— prototype은 자체 그래프(노드·엣지·인접). bitemporal/AS-OF는 후속.
"""
from __future__ import annotations

import pytest

from orc_citadel.graph_service import GraphService


def _node_evt(evt_id, key, node_id, **props):
    return {"mutation_id": evt_id, "idempotency_key": key, "op": "create_node",
            "payload": {"id": node_id, "props": props, "labels": []}}


def _edge_evt(evt_id, key, etype, fro, to, **props):
    return {"mutation_id": evt_id, "idempotency_key": key, "op": "create_edge",
            "payload": {"type": etype, "from": fro, "to": to, "props": props}}


def test_create_nodes_rebuilt():
    """create_node 이벤트 replay → 노드 생성 (Authoritative 라벨)."""
    g = GraphService()
    g.apply([
        _node_evt("mut-1", "k1", "org-nvda", name="NVIDIA"),
        _node_evt("mut-2", "k2", "org-tsmc", name="TSMC"),
    ])
    assert g.node("org-nvda")["name"] == "NVIDIA"
    assert g.node("org-tsmc")["label"] == "Authoritative"
    assert len(g.nodes()) == 2


def test_idempotent_apply():
    """동일 idempotency_key 재적용 no-op (03 §7.2, 불변식 §3-6)."""
    g = GraphService()
    evt = _node_evt("mut-1", "k-same", "org-x", name="X")
    g.apply([evt, evt])  # 두 번
    assert len(g.nodes()) == 1


def test_edge_requires_endpoints():
    """create_edge가 미존재 노드 참조 → quarantine(사유) (02 §4-3)."""
    g = GraphService()
    g.apply([
        _node_evt("mut-1", "k1", "org-a"),
        _edge_evt("mut-2", "k2", "MENTIONS", "org-a", "org-missing"),
    ])
    # 존재하는 노드는 정상.
    assert g.node("org-a") is not None
    # dangling ref 엣지는 생성되지 않음 — quarantine 기록.
    assert g.edge_count("org-missing") == 0


def test_valid_edge_created():
    """양끝 존재 시 엣지 생성 + 인접 조회."""
    g = GraphService()
    g.apply([
        _node_evt("mut-1", "k1", "org-a"),
        _node_evt("mut-2", "k2", "org-b"),
        _edge_evt("mut-3", "k3", "SAME_AS", "org-a", "org-b"),
    ])
    nbrs = g.neighbors("org-a")
    assert any(n["id"] == "org-b" for n in nbrs)
    assert g.edge_count("org-a") == 1


def test_neighbors_empty_when_none():
    g = GraphService()
    g.apply([_node_evt("mut-1", "k1", "org-iso")])
    assert g.neighbors("org-iso") == []


def test_nodes_filter_by_label():
    """Authoritative 라벨 필터."""
    g = GraphService()
    g.apply([
        _node_evt("mut-1", "k1", "a"),
        _node_evt("mut-2", "k2", "b"),
    ])
    auth = g.nodes(label="Authoritative")
    assert {n["id"] for n in auth} == {"a", "b"}
