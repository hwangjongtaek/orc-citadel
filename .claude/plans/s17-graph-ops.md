# S17 Applier 전 op + bitemporal AS-OF (06 §3·§5·§6, 03 §6)

> 권장안 1. S16 create_node/edge에 이어 merge/unmerge/supersede op를 Applier에 추가하고
> bitemporal AS-OF 질의를 구현한다. 대상: [06-graph-service](../../docs/design/06-graph-service.md)
> §3.2·§5·§6, [03-storage](../../docs/design/03-storage-and-data-model.md) §6.

## 배경·범위

| 결정 | 근거 |
| --- | --- |
| **merge_entity**: SAME_AS 동치류 collapse + canonical 대표 1개 + member.canonical_id/:Merged | 06 §5.1 — entity id 재작성 없이 canonical 매핑 |
| **unmerge**: SAME_AS 제거 + canonical_id 원복 + :Merged 해제 — resolution_ref로 역연산 특정 | 06 §5.3, blueprint §8.5 precision-first, 가역(불변식 §3-3) |
| **supersede**: 신버전 SUPERSEDES 구버전 + 구버전 tx_to close (현재 아님 표시) | 06 §6 — bitemporal, 버전 단위는 Assertion(03 §6.2) |
| **AS-OF**: transaction(tx_to=null만)+valid(valid_from≤T_v) 질의 | 03 §6.3 — 시간 슬라이더·감사 |
| merge 미존재 노드 → quarantine(사유) | 06 §3.2 reference(02 §4-3) |
| delete 단계는 후속 (soft delete는 08 §8.4) | 이번 scope는 검토 op 중심 |

## 구현 (graph_service.py 확장)

- apply dispatch에 merge_entity/unmerge/supersede 추가 (resolution_ref 사용).
- `_apply_merge/_apply_unmerge/_apply_supersede` + `as_of(claim, valid_at)`.
- node() 디폴트 스키마(canonical_id/tx_to/merged) 정규화.

## DoD

- merge → SAME_AS 엣지 + canonical_id + :Merged (06 §5.1)
- unmerge → 가역(canonical 원복·엣지 제거), 미병합 no-op
- supersede → SUPERSEDES 엣지 + 구버전 tx_to close (06 §6)
- AS-OF: tx_to-null 현재 + valid 하한 질의 (03 §6.3)
- 전체 테스트 통과, code-only 커밋

## 한계 (문서화)

- delete·rollback(06 §3.4·§7.4)·quarantine 워크플로(review)는 후속
- AS-OF는 최소(현재 1버전) — full time-travel은 08 §8 후속
- 물리 Neo4j·트랜잭션 close 로직은 후속 (prototype은 인메모리 그래프)
