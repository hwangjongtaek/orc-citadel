# S19 delete·rollback·quarantine 워크플로 (06 §3·§7, 05 §8)

> 권장안 1. 그래프 소프트 삭제·역이벤트 rollback·quarantine review 워크플로를 구현한다.
> 대상: [06-graph-service](../../docs/design/06-graph-service.md) §3.2(delete)·§4.1(:Deleted 제외)·§7.4(rollback),
> [05-resolution](../../docs/design/05-resolution-and-extraction.md) §8(review 상태 전이·human review as data).

## 배경·범위

| 결정 | 근거 |
| --- | --- |
| **delete op**: 노드 soft-delete(`:Deleted`+deleted_at), 엣지 제거; 기본 조회서 `:Deleted` 제외 | 06 §3.2·§4.1: 원장 append-only, 물리 삭제 금지 |
| **rollback**: create_node→`delete` 역이벤트 (revert, 로그 보존) | 06 §7.4: 로그 truncation 금지, 역이벤트 발행 |
| **quarantine review 워크플로**: pending→in_review→approved/rejected/escalated + 골든셋 | 05 §8.1·§8.2: human review as data(원출력·수정·이유) |
| merge→unmerge·supersede→재정정 rollback은 이미 S17 | 06 §7.4 — unmerge/supersede op 완성 |

## 구현 계획

- **graph_service.py** (수정): `delete` op (soft-delete 라벨+deleted_at, 엣지 제거).
  `nodes()`/`neighbors()` 기본에서 `:Deleted` 제외(§4.1) (+ `include_deleted` 옵션).
- **review.py** (신규): `ReviewQueue` — 상태 전이(assign→in_review; approve/correct/reject/escalate)
  + `review_history[]`(원출력·인간 결정·이유·reviewer → 골든셋, 05 §8.2).
  quarantine된 element를 리뷰로 흘려 승격/폐기.
- **graph_storage.py**: delete 상태도 영속 반영 (deleted 노드는 props에 존재 유지).
- **TDD**.

## DoD

- delete → soft(:Deleted·deleted_at), 기본 조회 제외, rollback(revert) 가능
- review 전이: pending→in_review→approved(re-promote)/rejected(폐기)/escalated(제안)
- human review as data: 원출력·결정·이유 저장 (골든셋)
- 전체 테스트 통과, code-only 커밋

## 한계 (문서화)

- 온톨로지 proposal(escalate→02 §6.2)·전파 delete(기록 §8.4)는 후속
- quarantine 물리 그래프 분리(06 §4.1 ADR-603)는 후속 — 상태 라벨로 논리 분리
