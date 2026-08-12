"""P1 후속 ③ — Neo4j 그래프 적재 + explorer (design 06, ADR-601/602/603).

⑤ `replay_graph` 로 재구축된 GraphService 의 노드·엣지를 **Neo4j Community**(가동 중) 에
적재(MERGE)하고 조회한다. §2.3 `entity_id_unique` 제약이 idempotency 방어선 — 중복 적재 시
노드 중복 없음. Q4 부하 스트레스는 이 증분 범위 밖(적재+조회로 한정).

드라이버/연결 불가(오프라인) 시 전체 skip — 기존 스위트 453 유지.
"""
from __future__ import annotations

import pytest

from orc_citadel.graph_replay import replay_graph
from orc_citadel.graph_service import GraphService
from orc_citadel.neo4j_graph_store import Neo4jGraphStore

pytest.importorskip("neo4j")


@pytest.fixture()
def store():
    try:
        s = Neo4jGraphStore(auth=("neo4j", "citadel-local-neo4j"))
    except Exception as exc:
        pytest.skip(f"Neo4j 연결 불가: {exc}")
    s.clear()  # 전용 정리 (전체 detach delete)
    yield s
    try:
        s.clear()
    except Exception:
        pass


def _graph() -> GraphService:
    """재생 로직을 재사용한 2-노드·1-엣지 그래프."""
    from orc_citadel.postgres_mutation_log import Mutation

    return replay_graph([
        Mutation(mutation_id="m1", idempotency_key="k1", op="create_node",
                 doc_id="d", source_span=("d#s", 0, 1),
                 payload={"id": "org-nvidia", "props": {"name": "NVIDIA"}}),
        Mutation(mutation_id="m2", idempotency_key="k2", op="create_node",
                 doc_id="d", source_span=("d#s", 1, 2),
                 payload={"id": "org-tsmc", "props": {"name": "TSMC"}}),
        Mutation(mutation_id="m3", idempotency_key="k3", op="create_edge",
                 doc_id="d", source_span=("d#s", 0, 2),
                 payload={"type": "SUPPLIES", "from": "org-tsmc", "to": "org-nvidia"}),
    ])


def test_load_graph_merges_nodes_and_edges(store):
    """GraphService 노드·엣지를 Neo4j 에 적재 → 노드/관계 조회."""
    g = _graph()
    store.load_graph(g)
    assert store.node_count() == 2
    assert store.query_neighbors("org-tsmc") == ["org-nvidia"]


def test_load_idempotent_no_duplicate_nodes(store):
    """동일 그래프 재적재 → 중복 노드 없음 (§2.3 id 유일 제약)."""
    g = _graph()
    store.load_graph(g)
    store.load_graph(g)
    assert store.node_count() == 2  # MERGE — 중복 아님


def test_empty_graph_load_noop(store):
    """빈 그래프 적재는 no-op (노드 0)."""
    store.load_graph(GraphService())
    assert store.node_count() == 0
