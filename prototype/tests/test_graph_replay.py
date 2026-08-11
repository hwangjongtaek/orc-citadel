"""P1 저장 계층 키스톤 ⑤ — postgres SoT 로그 재생 → 그래프 재구축 (ADR-304).

①의 `graph_mutations`(postgres SoT) 로그를 `GraphService`(Applier/replay, design 06 §3) 로
순서대로 재생해 동일 materialized graph 를 재구축하는 것을 검증한다 (불변식 §3-3, blueprint §21-2).

- payload 는 jsonb 로 원형 보존 → 재생 시 그대로 전달.
- idempotency_key 중복 적용 시 중복 node 없음 (불변식 §3-6 유지).

전용 테이블명 격리(① 패턴), 연결 불가(오프라인) 시 skip — 기존 스위트 442 유지.
"""
from __future__ import annotations

import pytest

from orc_citadel.graph_replay import events_from_mutations, replay_graph
from orc_citadel.graph_service import GraphService
from orc_citadel.postgres_mutation_log import (
    Mutation,
    PostgresMutationLog,
    build_dsn,
    graph_mutations_ddl,
)

psycopg = pytest.importorskip("psycopg")

TEST_TABLE = "graph_mutations_test"


@pytest.fixture()
def pg():
    dsn = build_dsn()
    try:
        conn = psycopg.connect(dsn)
    except Exception as exc:
        pytest.skip(f"postgres 연결 불가: {exc}")
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(f'DROP TABLE IF EXISTS "{TEST_TABLE}"')
    cur.execute(graph_mutations_ddl(TEST_TABLE))
    yield conn
    cur = conn.cursor()
    cur.execute(f'DROP TABLE IF EXISTS "{TEST_TABLE}"')
    conn.close()


def _log(conn) -> PostgresMutationLog:
    return PostgresMutationLog(conn, table=TEST_TABLE)


def test_events_from_mutations_preserves_payload():
    """포스트그레스 Mutation → GraphService 이벤트 변환이 payload/op/key 원형 전달."""
    m = Mutation(
        mutation_id="mut-1", idempotency_key="k1", op="create_node",
        doc_id="d", source_span=("d#s", 0, 1), payload={"id": "org-1", "props": {}},
        resolution_ref=None, actor="pipeline", correlation_id="c",
    )
    events = events_from_mutations([m])
    assert events[0]["op"] == "create_node"
    assert events[0]["payload"] == {"id": "org-1", "props": {}}
    assert events[0]["idempotency_key"] == "k1"


def test_replay_rebuilds_graph_from_postgres_log(pg):
    """postgres `graph_mutations` SoT 에서 create_node/edge 재생 → 동일 그래프 (ADR-304)."""
    log = _log(pg)
    log.apply(doc_id="d", op="create_node", source_span=("d#s", 0, 1),
              idempotency_key="k-node1", payload={"id": "org-1", "props": {}})
    log.apply(doc_id="d", op="create_node", source_span=("d#s", 1, 2),
              idempotency_key="k-node2", payload={"id": "org-2", "props": {}})
    log.apply(doc_id="d", op="create_edge", source_span=("d#s", 0, 2),
              idempotency_key="k-edge",
              payload={"type": "DEPENDS_ON", "from": "org-1", "to": "org-2"})

    # 새 인스턴스 로그 → 재생
    log2 = _log(pg)
    g = replay_graph(log2.all_mutations())

    assert len(g.nodes()) == 2
    assert g.node("org-1") is not None
    assert g.node("org-2") is not None
    assert g.edge_count("org-1") == 1  # DEPENDS_ON 엣지


def test_replay_idempotent_no_duplicate_nodes(pg):
    """동일 idempotency_key 중복 이벤트 재생 → 중복 노드 없음 (불변식 §3-6)."""
    log = _log(pg)
    # 동일 key 로 create_node 재저장 — ②의 ON CONFLICT no-op 이라 1행만 존재.
    log.apply(doc_id="d", op="create_node", source_span=("d#s", 0, 1),
              idempotency_key="dup", payload={"id": "org-1", "props": {}})
    log.apply(doc_id="d", op="create_node", source_span=("d#s", 0, 1),
              idempotency_key="dup", payload={"id": "org-1", "props": {}})

    log2 = _log(pg)
    assert len(log2.all_mutations()) == 1  # 중복 row 없음
    g = replay_graph(log2.all_mutations())
    assert len(g.nodes()) == 1  # 노드 1개만


def test_replay_type_is_graphservice():
    """replay_graph 는 GraphService 를 반환 (그래프 유일 조회 경로)."""
    g = replay_graph([])
    assert isinstance(g, GraphService)
    assert len(g.nodes()) == 0
