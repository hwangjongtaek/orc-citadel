"""P1 후속 ③ — Neo4j 그래프 적재 + explorer (design 06, ADR-601/602/603).

⑤ `replay_graph`/파이프라인 그래프로 재구축된 `GraphService` 의 authoritative 노드·엣지를
**Neo4j Community**(가동 중) 에 적재(MERGE)하고 조회한다.

- 노드  : `:Entity` 라벨, 공통 속성 `id` + props (design 06 §2.1 단순화 — 세부 라벨/Provenance 등 후속).
- 엣지  : 양끝 :Entity 노드 간 `(:Entity)-[:ETYPE {props}]->(:Entity)`.
- idempotency : §2.3 `entity_id_unique` 제약(전역 id 유일)이 MERGE 의 최종 방어선 — 중복 적재 시
  노드 중복 없음 (불변식 §3-6).
- Q4 부하 스트레스 측정은 이 증분 범위 밖 (적재+조회).

드라이버 `neo4j` 는 선택 의존성 — 없으면 모듈 import 유지, 테스트는 importorskip 으로 skip.
"""
from __future__ import annotations

import os

try:
    from neo4j import GraphDatabase
except Exception:  # pragma: no cover
    GraphDatabase = None


def build_neo4j_driver(uri: str | None = None, auth: tuple | None = None):
    """Neo4j 드라이버. .env(환경)의 NEO4J_HOST/PORT/NEO4J_PASSWORD 사용.

    auth 미주입 시 기본 neo4j/user + NEO4J_PASSWORD.
    """
    if GraphDatabase is None:
        raise RuntimeError("neo4j 드라이버 미설치")
    uri = uri or os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    if auth is None:
        user = os.environ.get("NEO4J_USER", "neo4j")
        password = os.environ.get("NEO4J_PASSWORD", "citadel-local-neo4j")
        auth = (user, password)
    return GraphDatabase.driver(uri, auth=auth)


class Neo4jGraphStore:
    """GraphService 재구축 그래프를 Neo4j 에 적재·조회하는 explorer 스토어."""

    def __init__(self, uri: str | None = None, auth: tuple | None = None) -> None:
        self._driver = build_neo4j_driver(uri=uri, auth=auth)
        # §2.3 전역 id 유일 제약 — MERGE idempotency 방어선 (존재하지 않으면 생성).
        self._ensure_constraints()

    def _ensure_constraints(self) -> None:
        with self._driver.session() as s:
            s.run(
                "CREATE CONSTRAINT entity_id_unique IF NOT EXISTS "
                "FOR (n:Entity) REQUIRE n.id IS UNIQUE"
            )

    def load_graph(self, graph) -> None:
        """GraphService 의 노드·엣지를 MERGE 로 적재 (idempotent)."""
        with self._driver.session() as s:
            for nid, node in graph._nodes.items():
                props = dict(node.props)
                props["id"] = nid
                s.run("MERGE (n:Entity {id: $id}) SET n += $props",
                      id=nid, props=props)
            for e in graph._edges:
                if e.fro not in graph._nodes or e.to not in graph._nodes:
                    continue  # dangling ref 는 적재 생략
                # etype 는 파이프라인 controlled vocabulary(GraphService 쓰기 경로) —
                # 관계 타입은 파라미터화 불가하므로 유효 문자만 허용해 주입 방지.
                if not e.etype.isalnum() and "_" not in e.etype:
                    continue
                s.run(
                    "MATCH (a:Entity {id:$from}), (b:Entity {id:$to}) "
                    "MERGE (a)-[r:%s]->(b) SET r += $props" % e.etype,
                    **{"from": e.fro, "to": e.to, "props": e.props},
                )

    def node_count(self) -> int:
        with self._driver.session() as s:
            r = s.run("MATCH (n:Entity) RETURN count(n) AS c")
            return r.single()["c"]

    def query_neighbors(self, node_id: str) -> list:
        """탐색(explorer): node 의 인접 이웃 id 목록."""
        with self._driver.session() as s:
            r = s.run(
                "MATCH (n:Entity {id:$id})-[r]-(m:Entity) RETURN DISTINCT m.id AS nid",
                id=node_id,
            )
            return [rec["nid"] for rec in r]

    def clear(self) -> None:
        """전용 정리 — 전체 그래프 삭제 (격리·테스트 teardown)."""
        with self._driver.session() as s:
            s.run("MATCH (n) DETACH DELETE n")

    def close(self) -> None:
        self._driver.close()
