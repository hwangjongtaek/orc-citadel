"""P1 저장 계층 키스톤 ① — PostgreSQL `graph_mutations` SoT (design 03 §7, ADR-304/307).

append-only `graph_mutations` 이벤트 로그가 in-memory `list`가 아니라 **postgres에 영속**
되고, 신규 인스턴스에서 **replay로 동일 materialized graph를 재구축**할 수 있음을 검증한다.

이벤트 계약 (§7.2):
- **Append-only** — 이벤트 수정·삭제 금지.
- **Replay** — 기록 순서대로 적용 시 동일 결과 (ADR-304).
- **Idempotency** — 동일 `idempotency_key` 재수신 시 no-op (불변식 §3-6).

테스트는 전용 테이블명(`graph_mutations_test`)을 사용해 실행마다 DROP+CREATE로 격리한다.
postgres 드라이버·연결 불가(오프라인) 시 전체 skip — 기존 스위트 424 유지.
"""
from __future__ import annotations

import os

import pytest

from orc_citadel.mutation_log import Mutation
from orc_citadel.postgres_mutation_log import (
    PostgresMutationLog,
    build_dsn,
    graph_mutations_ddl,
)

psycopg = pytest.importorskip("psycopg")

# 전용 격리 테이블명 (실제 운영 테이블과 분리 — CI/로컬 안전).
TEST_TABLE = "graph_mutations_test"


@pytest.fixture()
def pg():
    """실 postgres에 연결해 전용 테이블을 DROP+CREATE로 격리 생성."""
    dsn = build_dsn()
    try:
        conn = psycopg.connect(dsn)
    except Exception as exc:  # 오프라인/드라이버 부재 — 전체 skip
        pytest.skip(f"postgres 연결 불가: {exc}")
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(f'DROP TABLE IF EXISTS "{TEST_TABLE}"')
    cur.execute(graph_mutations_ddl(TEST_TABLE))
    yield conn
    cur.execute(f'DROP TABLE IF EXISTS "{TEST_TABLE}"')
    conn.close()


def _mutation_log(conn) -> PostgresMutationLog:
    return PostgresMutationLog(conn, table=TEST_TABLE)


def test_ddl_matches_design_column_contract(pg):
    """§7.1 정본 컬럼이 모두 존재해야 한다."""
    cur = pg.cursor()
    cur.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = %s ORDER BY ordinal_position
        """,
        (TEST_TABLE,),
    )
    cols = {row[0] for row in cur.fetchall()}
    expected = {
        "mutation_id", "idempotency_key", "op", "payload",
        "resolution_ref", "actor", "version_tuple", "correlation_id", "tx_time",
    }
    assert expected <= cols


def test_apply_persists_and_roundtrip(pg):
    """append 후 재조회로 왕복 persist 확인 (§7.1 필드 보존)."""
    log = _mutation_log(pg)
    mut_id = log.apply(
        doc_id="doc-abc",
        idempotency_key="k1",
        op="create_node",
        source_span=("doc-abc#p1.s1", 0, 10),
        payload={"claim_id": "clm-1", "label": "Organization"},
        actor="pipeline",
        version_tuple={
            "ontology_version": "1.0.0", "schema_version": "0.1.0",
            "prompt_template_hash": "h", "model_id": "det", "extraction_code_version": "1",
        },
        correlation_id="corr-1",
    )
    assert mut_id.startswith("mut-")
    # 새 인스턴스로 재조회 — 영속 확인
    log2 = _mutation_log(pg)
    rows = log2.all_mutations()
    assert len(rows) == 1
    m = rows[0]
    assert m.mutation_id == mut_id
    assert m.idempotency_key == "k1"
    assert m.op == "create_node"
    assert m.doc_id == "doc-abc"
    assert m.source_span == ("doc-abc#p1.s1", 0, 10)
    assert m.payload == {"claim_id": "clm-1", "label": "Organization"}
    assert m.tx_time is not None


def test_apply_append_only_keeps_order(pg):
    """여러 이벤트가 기록 순서대로 영속되고 replay 시 그 순서 보존 (ADR-304)."""
    log = _mutation_log(pg)
    ids = [
        log.apply(doc_id="d", idempotency_key=f"k{i}", op="create_node",
                  source_span=("d#s", i, i + 1), payload={"n": i})
        for i in range(3)
    ]
    # 신규 인스턴스 replay
    log2 = _mutation_log(pg)
    mutated = log2.all_mutations()
    assert [m.mutation_id for m in mutated] == ids
    assert [m.doc_id for m in mutated] == ["d", "d", "d"]


def test_idempotency_same_key_is_noop(pg):
    """동일 idempotency_key 재적용 시 중복 행 없음 + 기존 mutation_id 반환 (§3-6)."""
    log = _mutation_log(pg)
    first = log.apply(doc_id="d", idempotency_key="same", op="create_node",
                      source_span=("d#s", 0, 1), payload={})
    second = log.apply(doc_id="d", idempotency_key="same", op="create_node",
                       source_span=("d#s", 0, 1), payload={})
    assert second == first
    log2 = _mutation_log(pg)
    assert len(log2.all_mutations()) == 1


def test_actor_version_and_correlation_roundtrip(pg):
    """§7.1 actor/version_tuple/correlation_id round-trip."""
    log = _mutation_log(pg)
    vtuple = {"ontology_version": "1.0.0", "schema_version": "0.1.0",
              "prompt_template_hash": "p", "model_id": "claude-opus-4-8",
              "extraction_code_version": "3"}
    log.apply(doc_id="d", idempotency_key="k", op="merge_entity",
              source_span=("d#s", 0, 1), payload={"e": 1},
              actor="llm:claude-opus-4-8", version_tuple=vtuple, correlation_id="corr-9")
    log2 = _mutation_log(pg)
    (m,) = log2.all_mutations()
    assert m.actor == "llm:claude-opus-4-8"
    assert m.version_tuple == vtuple
    assert m.correlation_id == "corr-9"


def test_default_dsn_reads_env():
    """build_dsn()이 .env/환경의 POSTGRES_* 값을 반영한다."""
    dsn = build_dsn()
    assert "dbname=citadel" in dsn
    assert "user=citadel" in dsn
