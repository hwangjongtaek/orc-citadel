"""S18 그래프 영속 (DuckDB/Parquet, 재구축) — TDD (06 §2, 03 §7).

GraphService 노드·엣지·quarantine을 DuckDB에 영속하고 load로 재구축(왕복)한다.
idempotent 재persist, Parquet export. 결정적 PK, 저장 계약은 curated_zone 패턴.
"""
from __future__ import annotations

import pytest

from orc_citadel.graph_service import GraphService
from orc_citadel.graph_storage import GraphStorage


def _graph():
    """노드·SAME_AS·supersede·quarantine이 섞인 그래프."""
    g = GraphService()
    g.apply([
        {"idempotency_key": "k1", "op": "create_node",
         "payload": {"id": "org-nvda", "props": {"name": "NVIDIA", "type": "Entity"}}},
        {"idempotency_key": "k2", "op": "create_node",
         "payload": {"id": "org-tsmc", "props": {"name": "TSMC", "type": "Entity"}}},
        {"idempotency_key": "k3", "op": "create_edge",
         "payload": {"type": "SAME_AS", "from": "org-nvda", "to": "org-tsmc", "props": {}}},
        # dangling edge → quarantine.
        {"idempotency_key": "k4", "op": "create_edge",
         "payload": {"type": "MENTIONS", "from": "org-nvda", "to": "org-missing", "props": {}}},
        # supersede → tx_to close (노드 상태 포함 영속 확인).
        {"idempotency_key": "k5", "op": "create_node",
         "payload": {"id": "asr-old", "props": {"claim": "c"}}},
        {"idempotency_key": "k6", "op": "create_node",
         "payload": {"id": "asr-new", "props": {"claim": "c"}}},
        {"idempotency_key": "k7", "op": "supersede",
         "payload": {"new_id": "asr-new", "superseded_id": "asr-old",
                     "superseded_at": "2026-08-03T12:00:00Z", "reason": "정정"}},
    ])
    return g


def test_persist_load_roundtrip(tmp_path):
    """GraphService → DuckDB persist → load 재구축 왕복 (노드·엣지·상태)."""
    g = _graph()
    store = GraphStorage(str(tmp_path / "graph.duckdb"))
    store.initialize()
    store.persist_graph(g)

    g2 = store.load_graph()
    assert g2.node("org-nvda")["name"] == "NVIDIA"
    # merge/supersede 상태 보존.
    assert g2.node("asr-old")["tx_to"] == "2026-08-03T12:00:00Z"
    # SAME_AS 엣지 보존.
    assert any(n["id"] == "org-tsmc" and n["type"] == "SAME_AS"
               for n in g2.neighbors("org-nvda"))
    # quarantine 보존.
    assert any(e["reason"] == "dangling_ref" for e in g2.quarantined_edges())
    store.close()


def test_persist_idempotent(tmp_path):
    """재persist → 중복 없음 (결정적 PK)."""
    store = GraphStorage(str(tmp_path / "g.duckdb"))
    store.initialize()
    store.persist_graph(_graph())
    store.persist_graph(_graph())  # 두 번
    assert len(store.nodes()) == 4  # org-nvda, org-tsmc, asr-old, asr-new
    assert len(store.edges()) == 2  # SAME_AS, SUPERSEDES
    store.close()


def test_export_parquet(tmp_path):
    """Parquet export (nodes/edges/quarantine)."""
    store = GraphStorage(str(tmp_path / "g.duckdb"))
    store.initialize()
    store.persist_graph(_graph())
    out = tmp_path / "pq"
    store.export_parquet(str(out))
    names = sorted(p.name for p in out.glob("*.parquet"))
    assert "graph_nodes.parquet" in names
    assert "graph_edges.parquet" in names
    store.close()


def test_empty_graph_roundtrip(tmp_path):
    """빈 그래프 왕복 안전."""
    store = GraphStorage(str(tmp_path / "g.duckdb"))
    store.initialize()
    g = GraphService()
    store.persist_graph(g)
    g2 = store.load_graph()
    assert g2.nodes() == []
    store.close()
