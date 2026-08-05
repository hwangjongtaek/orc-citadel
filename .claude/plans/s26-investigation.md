# S26 Investigation subgraph 질의 — canonical view-rewrite + progressive (06 §8.1·§8.3)

> 권장안: GraphService 위에 **Investigation subgraph 조회**를 구현한다. canonical
> view-rewrite(SAME_AS 동치류 fold)는 필수 wrapper(§5.2), hop 제한 프로그래시브(§8.3).

## 배경·범위

조사 중심 그래프 조회 계약(06 §8). S25는 bitemporal AS-OF(§8.2) 완료. 나머지 §8.1
(Investigation subgraph)과 §8.3(progressive disclosure)을 구현한다.

| 결정 | 근거 |
| --- | --- |
| `investigation_subgraph(seed, hops, limit, include)` | 06 §8.1 · §8.3 |
| canonical view-rewrite: seed→대표, 동치류(SAME_AS*0..) fold | §5.2 필수 wrapper — merged member 미노출 |
| hop 제한 BFS + relationship 타입 필터(include) | §8.3 프로그래시브, hairball 금지 |
| 기본 :Authoritative만, :Deleted 제외 | §4.1 기본 필터 |
| limit 초과 → `truncated=True` 요약 신호 | §8.3 축약 |

## 구현 계획

- **graph_service.py**: `_canonical_of`(동치류 대표, 사이클 가드) / `_equivalence_class`
  (SAME_AS*0.. 전체) / `investigation_subgraph` — entity 동치류 → ABOUT claim → SUPPORTS|
  CONTRADICTS evidence, limit/hop/관계타입 필터, deleted 제외, truncated 신호.
- **TDD**: Red→Green — fold·member seed rewrite·evidence·deleted 제외·hop 제한·limit trunc.
- **Smoke**: 병합 동치류 + ABOUT/SUPPORTS/CONTRADICTS 그래프에서 fold·rewrite·근거 조회.

## DoD

- canonical view-rewrite로 동치류 fold, merged member 별도 노출 금지
- member seed도 canonical 대표로 rewrite
- SUPPORTS/CONTRADICTS 근거(속성 포함) 조회, :Deleted 제외
- hop·limit·관계타입 필터, truncated 신호 — 전체 테스트 통과, code-only 커밋

## 한계 (문서화)

- 실제 ABOUT/MENTIONS 등 관계 엣지는 엔티티/증거 subgraph에서 후속 단계가 채움 — 여기선
  질의 API + view-rewrite 로직 확정
- p50/p95 지연 SLO는 설계 11 — 성능 벤치 후속
