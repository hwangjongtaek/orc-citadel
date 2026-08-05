"""S20 review·delete 상태 통합 영속 (06·05, 영속 골든셋·삭제 전파) — TDD.

ReviewQueue 골든셋(05 §8.2)을 DuckDB 영속·로드 왕복, :Deleted 그래프 상태가
영속/로드에서 보존, review_records parquet export.
"""
from __future__ import annotations

import pytest

from orc_citadel.graph_service import GraphService
from orc_citadel.graph_storage import GraphStorage
from orc_citadel.review import ReviewQueue


def _graph_with_deleted():
    g = GraphService()
    g.apply([
        {"op": "create_node", "idempotency_key": "k1",
         "payload": {"id": "org-a", "props": {"name": "A"}}},
        {"op": "create_node", "idempotency_key": "k2",
         "payload": {"id": "org-b", "props": {"name": "B"}}},
        {"op": "delete", "idempotency_key": "k3",
         "payload": {"id": "org-a", "deleted_at": "2026-08-03T12:00:00Z"}},
    ])
    return g


def _review_queue():
    rq = ReviewQueue()
    rq.enqueue("clm-1", original={"predicate": "supplies"}, reason="ambiguous")
    rq.assign("clm-1", "human:jane")
    rq.reject("clm-1", reviewer="human:jane", reason="문맥상 depends_on")
    rq.enqueue("clm-2", original={"predicate": "announces"}, reason="low_confidence")
    rq.assign("clm-2", "human:jane")
    rq.approve("clm-2", reviewer="human:jane")
    return rq


def test_review_golden_persist_roundtrip(tmp_path):
    """ReviewQueue 골든셋 → DuckDB → load 왕복 (원출력·결정·이유·reviewer)."""
    store = GraphStorage(str(tmp_path / "g.duckdb"))
    store.initialize()
    store.persist_reviews(_review_queue())

    recs = store.reviews()
    assert len(recs) == 2
    by_ref = {r["element_ref"]: r for r in recs}
    rejected = by_ref["clm-1"]
    assert rejected["status"] == "rejected"
    assert rejected["reviewer"] == "human:jane"
    assert rejected["original_model_output"]["predicate"] == "supplies"
    assert rejected["reason"]  # 골든셋 이유 보존 (05 §8.2)
    approved = by_ref["clm-2"]
    assert approved["status"] == "approved"
    store.close()


def test_deleted_node_persist_roundtrip(tmp_path):
    """:Deleted 노드 상태·deleted_at이 영속/로드에서 보존 (06 §3.2, S18)."""
    store = GraphStorage(str(tmp_path / "g.duckdb"))
    store.initialize()
    g = _graph_with_deleted()
    store.persist_graph(g)

    g2 = store.load_graph()
    # 기본 조회에서 :Deleted 제외.
    assert all(n["id"] != "org-a" for n in g2.nodes())
    # include_deleted로 보면 상태·deleted_at 보존.
    n = next(n for n in g2.nodes(include_deleted=True) if n["id"] == "org-a")
    assert n["deleted"] is True
    assert n["deleted_at"] == "2026-08-03T12:00:00Z"
    # 살아있는 노드는 그대로.
    assert g2.node("org-b")["name"] == "B"
    store.close()


def test_reviews_parquet_export(tmp_path):
    """review_records parquet export."""
    store = GraphStorage(str(tmp_path / "g.duckdb"))
    store.initialize()
    store.persist_reviews(_review_queue())
    out = tmp_path / "pq"
    store.export_parquet(str(out))
    assert "review_records.parquet" in sorted(p.name for p in out.glob("*.parquet"))
    store.close()


def test_persist_reviews_idempotent(tmp_path):
    """재persist → 중복 없음."""
    store = GraphStorage(str(tmp_path / "g.duckdb"))
    store.initialize()
    store.persist_reviews(_review_queue())
    store.persist_reviews(_review_queue())
    assert len(store.reviews()) == 2
    store.close()
