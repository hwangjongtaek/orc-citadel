# S18 그래프 영속 (DuckDB/Parquet, 재구축)

> 권장안 1. 인메모리 GraphService(노드·엣지·quarantine)를 DuckDB/Parquet에 영속·조회·재구축한다.
> 대상: [06-graph-service](../../docs/design/06-graph-service.md) §2(물리 매핑), 03 §7(replay 재구축), 기존 curated_zone 저장 계약.

## 배경·범위

| 결정 | 근거 |
| --- | --- |
| **노드·엣지·quarantine_edges를 DuckDB 테이블로 영속** | 06 §2 노드(공통 속성 id/type/created_tx/ontology_version)·관계 타입. graph는 append-only replay로 재구축 가능(03 §7) |
| **저장 계약은 curated_zone 패턴 재사용** | DuckDB + Parquet export, 결정적 PK, idempotent upsert |
| **재구축**: stored 노드/엣지 로드로 GraphService 복원 | 03 §7 — materialized graph는 로드 가능해야 (또는 이벤트 replay) |
| **`GraphStore` (graph_service.py 확장 또는 별도)** | 영속·조회·로드 계층. 인메모리 로직은 유지 |

## 구현 계획

- **`graph_storage.py`** (신규): `GraphStorage` — DuckDB `graph_nodes`, `graph_edges`, `graph_quarantine` 테이블.
  - `persist_graph(g)` : GraphService 노드/엣지/quarantine → DuckDB (idempotent upsert).
  - `load_graph()` → GraphService 재구축.
  - `nodes()/edges()` 쿼리, `export_parquet(out_dir)` (nodes/edges/quarantine parquet).
  - graph_service.py는 순수 인메모리 유지(영속은 storage가).
- **TDD** (test_graph_persist.py): persist→load 왕복, idempotent 재persist, parquet export, quarantine 포함.

## DoD

- GraphService(노드·엣지·merge/supersede 상태 포함) → DuckDB 영속 → load 재구축 왕복
- 재persist idempotent (중복 없음), Parquet export
- 전체 테스트 통과, code-only 커밋

## 한계 (문서화)

- 물리 Neo4j·트랜잭션 진정한 회복성은 후속 — prototype은 파일/Parquet 저장
- 그래프 full-rebuild는 이벤트 replay(03 §7) 대신 저장 스냅샷 로드로 (후속선택)
