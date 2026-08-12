"""대량 실행 드라이버 — 결정적 파이프라인 → postgres SoT → replay → Neo4j 적재·Q4 (design 06 §9) TDD.

`run_pipeline`(결정적 체인)의 결과를 postgres `graph_mutations` SoT 에 기록하고, 로그
replay 로 그래프를 재구축해, 가동 Neo4j Community 에 적재·Q4 지표를 실측하는 **대량 실행
드라이버**를 검증한다. Phase 1 10만 문서 기준선을 postgres→Neo4j 로 흘리는 실행 경로를
확정한다 (ADR-304/601/602: SoT=로그·그래프=파생·조립은 조합으로 격리).

- 파이프라인·재생 로직은 이미 단위검증. 여기서는 **조합(오케스트레이션)** 의 계약을 검증.
- `_sample_metas()` 는 결정적(동일 입력→동일 결과) — 벤치 재현성.
- postgres 는 전용 테이블명 격리, 연결 불가 시 skip.
"""
from __future__ import annotations

import pytest

from orc_citadel.pipeline_bulk_driver import bulk_pipeline

# --- postgres SoT 통합 (가동 시, 연결 불가 skip) -------------------------------

psycopg = pytest.importorskip("psycopg")

from orc_citadel.postgres_mutation_log import (
    PostgresMutationLog,
    build_dsn,
    graph_mutations_ddl,
)

TEST_TABLE = "graph_mutations_bulk_test"

# 기존 파이프라인 테스트의 정본 NVIDIA HTML — 결정적 체인이 claim/승격을 생성한다.
NVIDIA_HTML = b"""<html><head>
<title>NVIDIA Conference Call</title>
<meta property="article:published_time" content="2026-08-01T14:00:00+00:00"/>
</head><body><article>
<h1>NVIDIA Sets Conference Call</h1>
<p>NVIDIA will host a conference call on Wednesday, August 26.</p>
<p>NVIDIA powers the data center and announces new accelerator products.</p>
</article></body></html>"""


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


def test_bulk_pipeline_replay_from_postgres_log(pg):
    """raw → 파이프라인 → postgres 로그 → replay 그래프 → 로그 원형 보존 (ADR-304/602)."""
    from tempfile import TemporaryDirectory

    from orc_citadel.curated_zone import CuratedZone
    from orc_citadel.graph_service import GraphService

    with TemporaryDirectory() as td:
        zone = CuratedZone(f"{td}/curated.duckdb")
        zone.initialize()
        result, g = bulk_pipeline(_sample_metas(), zone, mutation_log=_log(pg))
        assert result.docs == 1
        # 그래프는 로그 replay 로 재구축 (ADR-304) — NVIDIA 대표 doc 의 승격 claim 노드.
        assert isinstance(g, GraphService)
        assert len(g.nodes()) >= 1
        # 로그의 mutation 이 실제 영속됨 (ADR-602 — 그래프 변경은 로그로만).
        assert len(_log(pg).all_mutations()) >= 1


def test_bulk_pipeline_without_log_is_empty_replay(pg):
    """mutation_log 미제공 → 빈 로그 replay (ADR-304 계약) + 로그 미기록 — log 옵션 안전 분기."""
    from tempfile import TemporaryDirectory

    from orc_citadel.curated_zone import CuratedZone

    with TemporaryDirectory() as td:
        zone = CuratedZone(f"{td}/curated.duckdb")
        zone.initialize()
        result, g = bulk_pipeline(_sample_metas(), zone, mutation_log=None)
        assert result.docs == 1
        assert len(g.nodes()) == 0  # 로그가 없어 재생할 이벤트 없음 (ADR-304 계약).
        assert len(_log(pg).all_mutations()) == 0  # 로그에 기록 없음.


def test_bulk_pipeline_returns_pipeline_result(pg):
    """반환은 (PipelineResult, GraphService) 계약 — 대량 실행 다운스트림 형식."""
    from tempfile import TemporaryDirectory

    from orc_citadel.curated_zone import CuratedZone
    from orc_citadel.graph_service import GraphService
    from orc_citadel.pipeline_runner import PipelineResult

    with TemporaryDirectory() as td:
        zone = CuratedZone(f"{td}/curated.duckdb")
        zone.initialize()
        result, g = bulk_pipeline(_sample_metas(), zone, mutation_log=_log(pg))
        assert isinstance(result, PipelineResult)
        assert isinstance(g, GraphService)


def _sample_metas():
    """결정적 소형 raw metas — NVIDIA 대표 HTML 1건 (결정적 체인이 claim/승격 생성).

    기존 파이프라인 테스트의 정본 HTML 을 재사용해, 드라이버가 실제 승격 claim → create_node
    로그 → replay 그래프 노드에 이르는 전체 경로를 검증한다.
    """
    return [{
        "source_id": "demo-nvda", "url": "https://demo/nvda",
        "doc_id": "doc-nvda", "content": NVIDIA_HTML,
    }]
