"""P1 후속 ② — 파이프라인 → postgres SoT 배선 (design 03 §7, ADR-604·602).

`run_pipeline` 이 승격된 claim 의 그래프 mutation 을 in-memory `Gate` 에만 두지 않고,
①의 postgres `graph_mutations` SoT 에 **create_node** 로 기록하고, 그래프 재구축을
`replay_graph`(postgres 로그)로 수행한다. 이로써 파이프라인 산출이 append-only
로그에 영속되고 ADR-304 DoD(재생 재구축)가 실제 파이프라인 경로에서 성립한다.

기존 in-memory 경로(`_build_graph(gate)`)는 `mutation_log` 미제공 시 그대로 유지
(파괴 없음).

전용 테이블명 격리, 연결 불가 skip — 기존 스위트 450 유지.
"""
from __future__ import annotations

import pytest

from orc_citadel.graph_replay import replay_graph
from orc_citadel.pipeline_runner import run_pipeline
from orc_citadel.curated_zone import CuratedZone
from orc_citadel.postgres_mutation_log import (
    PostgresMutationLog,
    build_dsn,
    graph_mutations_ddl,
)

psycopg = pytest.importorskip("psycopg")
# offline-safe: postgres 테스트 전환용으로만 사용

TEST_TABLE = "graph_mutations_test"


# 기존 파이프라인 테스트가 쓰는 대표 NVIDIA HTML — 결정적 체인이 claim/승격을 생성한다.
NVIDIA_HTML = b"""<html><head>
<title>NVIDIA Conference Call</title>
<meta property="article:published_time" content="2026-08-01T14:00:00+00:00"/>
</head><body><article>
<h1>NVIDIA Sets Conference Call</h1>
<p>NVIDIA will host a conference call on Wednesday, August 26.</p>
<p>NVIDIA powers the data center and announces new accelerator products.</p>
</article></body></html>"""


def _metas():
    return [{
        "source_id": "src-t", "url": "https://test.example/nvidia",
        "doc_id": "doc-test0000000000000000", "content": NVIDIA_HTML,
    }]


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


def test_run_pipeline_writes_promoted_nodes_to_postgres(pg):
    """파이프라인이 승격 claim 을 postgres graph_mutations(create_node) 로 기록."""
    log = PostgresMutationLog(pg, table=TEST_TABLE)
    zone = CuratedZone(); zone.initialize()
    res = run_pipeline(_metas(), zone, mutation_log=log)

    rows = log.all_mutations()
    assert res.promoted_claims > 0
    assert len(rows) >= res.promoted_claims  # 승격 claim 수만큼 create_node 로그
    create_nodes = [m for m in rows if m.op == "create_node"]
    assert len(create_nodes) >= 1
    assert all(isinstance(m.payload, dict) and "id" in m.payload for m in create_nodes)
    # idempotency_key 유일
    keys = [m.idempotency_key for m in rows]
    assert len(keys) == len(set(keys))


def test_run_pipeline_replays_graph_from_postgres(pg):
    """파이프라인 그래프가 postgres 로그 재생으로 재구축 (ADR-304 실제 경로)."""
    log = PostgresMutationLog(pg, table=TEST_TABLE)
    zone = CuratedZone(); zone.initialize()
    res = run_pipeline(_metas(), zone, mutation_log=log)

    # 새 인스턴스 로그에서 replay 로 그래프 재구축 → 결과 nodes 와 일치
    log2 = PostgresMutationLog(pg, table=TEST_TABLE)
    g = replay_graph(log2.all_mutations())
    assert res.nodes > 0
    assert res.nodes == len(g.nodes())


def test_inmemory_path_unchanged_without_mutation_log():
    """mutation_log 미제공 시 기존 in-memory `_build_graph` 경로 유지 (파괴 없음)."""
    zone = CuratedZone(); zone.initialize()
    res = run_pipeline(_metas(), zone)
    assert res.promoted_claims > 0
    assert res.nodes > 0
