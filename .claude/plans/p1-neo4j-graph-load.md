# P1 · 후속 ③ — Neo4j 그래프 적재 + explorer (design 06, ADR-601/602/603)

## 배경
⑤ `replay_graph` 로 재구축된 GraphService 의 authoritative 노드·엣지를 가동 중인
**Neo4j Community**(bolt 7687)에 적재(MERGE)하고 조회한다. §2.3 `entity_id_unique`
제약이 MERGE idempotency 방어선 — 중복 적재 시 노드 중복 없음(불변식 §3-6).
Q4 부하 스트레스는 이 증분 범위 밖(적재+조회로 한정).

## 구현 (`neo4j_graph_store.py`)
- `Neo4jGraphStore(uri, auth)` — `build_neo4j_driver`(.env NEO4J_* ).
- `load_graph(graph)` — 노드 MERGE(:Entity, id+props), 엣지 MERGE(:Entity)-[:ETYPE]->(:Entity).
  dangling ref 생략, etype 유효 문자만 허용(주입 방지).
- `node_count()` / `query_neighbors(id)` / `clear()`.
- `entity_id_unique` 제약 ensure.

## TDD (`test_neo4j_graph_store.py`)
- 연결 불가시 importorskip+skip → 기존 453 유지.
- 재생 그래프(2노드·1엣지) → node_count 2, neighbors('org-tsmc')=['org-nvidia'].
- 재적재 시 중복 노드 없음 (MERGE + id 유일).
- 빈 그래프 no-op.

## 후속(미실시)
Q4 부하 측정·Memgraph 전환·세부 노드 라벨/Provenance·Cypher 서브그래프 조회 확장.
