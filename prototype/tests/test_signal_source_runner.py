"""실신호 본문 Q4 재현 러너 — 전용 반도체 언론 본문 → SoT → replay → Neo4j → Q4 (design 06 §9) TDD.

실신호(비합성) 그래프에서 Q4 판정(조회 p95 · 노드 수)을 **재현 가능**하게 실측하는 러너를
검증한다. 설계 06 §9 판정 유보("실신호 본문 소스 확보 후 재판정")에 대응해, 결정적 extractor
가 object 를 바인딩해 **공급망 엣지가 실존**하는 본문 그래프에서 Q4 를 잰다.

- 러너 조립(파이프라인→postgres SoT→replay→Neo4j→Q4)은 pipeline_bulk_driver 已검증 조합.
- 여기서는 **전용 신호 소스 선택** + **엣지 생존** + **빈 그래프 skip** 의 계약을 검증:
  결정적 소형 HTML(공급망 문장)에서 러너가 source 선택·엣지 배선을 거쳐 그래프에 엣지가
  생기고, 빈 그래프는 Q4 실측을 건너뜀(빈 dict).
- postgres/Neo4j 연결 불가(오프라인) 시 해당 통합은 skip — 기존 스위트 보존.
"""
from __future__ import annotations

import pytest

from orc_citadel.signal_source_runner import (
    SIGNAL_SOURCE_IDS,
    load_q4_report,
    run_signal_q4,
    select_signal_metas,
)

# --- 신호 소스 선택 (순수 함수 — 오프라인) --------------------------------------

def test_signal_source_ids_are_the_verified_signal_sources():
    """실신호가 집중된 전용 반도체/공급망 언론 소스만 선택 (메모리 확증)."""
    assert "official-nvidia-news" in SIGNAL_SOURCE_IDS
    assert "press-semiengineering" in SIGNAL_SOURCE_IDS


def test_select_signal_metas_filters_to_signal_sources():
    """select_signal_metas 는 비신호 소스(arxiv 등) 를 제외한다."""
    metas = [
        {"source_id": "official-nvidia-news", "doc_id": "a", "content": b"x"},
        {"source_id": "press-semiengineering", "doc_id": "b", "content": b"y"},
        {"source_id": "research-arxiv-cs-cr", "doc_id": "c", "content": b"z"},
    ]
    out = select_signal_metas(metas)
    assert {m["doc_id"] for m in out} == {"a", "b"}


def test_run_signal_q4_empty_metas_yields_empty_replay_graph():
    """빈 metas → authoritative 그래프는 빈 로그 replay (ADR-304, 노드 없음)."""
    res, g = run_signal_q4([], zone_path=":memory:")
    assert g.nodes() == []  # 로그 재생할 이벤트 없음 → 빈 그래프 (Q4 실측 대상 아님).


def test_load_q4_report_empty_graph_returns_empty_dict():
    """빈 그래프 는 Q4 실측을 건너뛰고 빈 dict 반환 — 노이즈 없는 명시적 분기."""
    from orc_citadel.graph_service import GraphService

    out = load_q4_report(GraphService(), store=None, sample_k=200)
    assert out == {}


# --- postgres SoT 통합 (실 postgres — 연결 불가 skip) ---------------------------

psycopg = pytest.importorskip("psycopg")

from orc_citadel.postgres_mutation_log import (
    PostgresMutationLog,
    build_dsn,
    graph_mutations_ddl,
)

TEST_TABLE = "graph_mutations_signal_test"


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


SUPPLY_HTML = b"""<html><head><title>Supply Report</title>
<meta property="article:published_time" content="2026-08-01T14:00:00+00:00"/>
</head><body><article>
<h1>Supply Chain</h1>
<p>TSMC supplies NVIDIA with advanced silicon.</p>
</article></body></html>"""


def test_run_signal_q4_persists_signal_edges_to_log(pg):
    """실신호 소스 HTML → 파이프라인 → postgres SoT 로그에 create_edge 기록 (엣지 배선)."""
    from tempfile import TemporaryDirectory

    from orc_citadel.curated_zone import CuratedZone

    with TemporaryDirectory() as td:
        zone = CuratedZone(f"{td}/curated.duckdb")
        zone.initialize()
        metas = [{
            "source_id": "official-nvidia-news", "url": "https://demo/supply",
            "doc_id": "doc-supply", "content": SUPPLY_HTML,
        }]
        res, g = run_signal_q4(metas, zone_path=f"{td}/curated.duckdb",
                               mutation_log=_log(pg))
        # 로그 replay 그래프에 공급망 엣지가 실존 (object 바인딩, quarantine 0).
        assert len(g.edges()) >= 1
        assert g.quarantined_edges() == []
