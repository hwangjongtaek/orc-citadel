# S16 그래프 서비스 — authoritative materialize (06, 03 §7 replay)

> 권장안 3 선택. curated의 승격 이벤트(mutation)를 소비해 **authoritative 노드-엣지
> 그래프를 재구축**(replay)하는 Applier를 구현한다. 물리 Neo4j가 아니라 prototype은
> 자체 그래프(노드·엣지 저장 + 인접/AS-OF 조회)로 확장 가능하게. 대상:
> [06-graph-service](../../docs/design/06-graph-service.md) §2·§3, 03 §7(Append-only 재구축).

## 배경·범위

| 결정 | 근거 |
| --- | --- |
| **Applier: graph_mutations 이벤트를 순서대로 소비해 그래프 재구축** | 06 §3: 그래프의 유일한 쓰기 경로, 불변식 §3-3(append-only replay) |
| **op 지원**: create_node / create_edge(최소) — 본 prototype gate가 발행하는 이벤트 | 06 §3.2. merge/unmerge/supersede/delete는 후속 (본 세션 게이트는 create_*) |
| **idempotency** — 적용한 idempotency_key 기록, 중복 no-op | 06 §3.1, 03 §7.2 (불변식 §3-6) |
| **게이트 라벨** — :Authoritative/:Quarantine | 06 §3.2·§4 — prototype 게이트 결과 반영 |
| **create_edge reference 무결성** — 미존재 노드 → quarantine | 06 §3.2, 02 §4-3 |
| **조회**: 노드(by id/type), 엣지(인접), AS-OF(bitetemporal은 후속, 최소 버전 반영) | 06 §2·§8 — prototype 최소 |

## 구현 계획

- **`graph_service.py`** (신규): `GraphService` — in-memory/DuckDB 그래프 저장 + `apply(events)`.
  - `apply(evt)` : idempotency check → op별 적용(create_node: merge + 라벨, create_edge:
    양끝 존재 확인) → mark_applied. 06 §3.3 pseudo-code 정합.
  - `nodes()` / `edges()` / `neighbors(id)` / AS-OF 비트emporal은 후속.
- **`curated_zone.py`** (수정): gate 승격 이벤트를 `graph_mutations` 계열로 노출
  (이미 gate.mutations()가 append-only 이벤트 — GraphService가 소비).
- **`graph_smoke.py`** (신규): 실수집 파이프라인 산출 → 이벤트 → GraphService 재구축 → 조회.
- **TDD**. (S13 백그라운드 수집은 병행 진행 — byzsnj0ks.)

## DoD

- gate 이벤트(create_node/create_edge)를 replay해 노드·엣지 재구축
- idempotency: 시스템 이벤트 재적용 no-op (동일 그래프)
- create_edge가 미존재 노드 참조 시 quarantine(사유)
- 노드/인접 조회, 전체 테스트 통과, code-only 커밋

## 한계 (문서화)

- 물리 Neo4j·merge_entity/unmerge/supersede/delete op·bitemporal AS-OF 질의는 후속
  (06 §3.2 전 op·§8) — prototype은 create_node/create_edge + 표준 트랜잭션/버전 필드
- quarantine 워크플로(review 전이)는 05 §8 후속
