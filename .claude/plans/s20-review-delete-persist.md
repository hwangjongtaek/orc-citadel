# S20 review·delete 상태 통합 영속 (06·05, 영속 골든셋·삭제 전파)

> 권장안 1. S19의 리뷰 결정(ReviewQueue 골든셋)과 :Deleted 그래프 상태를 **영속**에
> 통합한다. 대상: [06-graph-service](../../docs/design/06-graph-service.md) §3.2(delete)·§4,
> [05-resolution](../../docs/design/05-resolution-and-extraction.md) §8.2(골든셋), 03 §8.

## 배경·범위

| 결정 | 근거 |
| --- | --- |
| **ReviewQueue 결정(골든셋)을 DuckDB 영속** | 05 §8.2: human review as data가 회귀 평가 소스 — 영속 필수 (10 §2) |
| **:Deleted 그래프 상태의 영속 반영** | 06 §3.2·S18: deleted 노드도 props로 영속(직렬화) + 조회 시 제외 |
| **삭제 전파(retention)** | 03 §8.4: raw→normalized→curated→graph 역방향 delete/quarantine (후속 훅 기록) |
| **저장 계약은 기존 GraphStorage 파생** | 신규 `review_records` 테이블 + 기존 graph_nodes(<r>deleted 포함) 재사용 |

## 구현 계획

- **`graph_storage.py`** (수정): `review_records` 테이블 + `persist_reviews(ReviewQueue)`/
  `reviews()` 조회 + parquet. (deleted 노드는 기존 props 직렬화로 이미 커버 — S18 load 왕복
  에서 deleted_at 보존 확인.)
- **`review.py`**: `all_history()` 요약 추가 (영속 입력용).
- **curation 연동 (delete 전파 훅)**: GraphStorage 로드 시 :Deleted 노드가
  normalized/curated의 해당 doc/claim과 연결 — 별도 후속 단계로 기록 (scope 유지).
- **TDD**: 리뷰 영속→로드, deleted 노드 영속 왕복, parquet.

## DoD

- ReviewQueue 골든셋 → DuckDB 영속 → load 왕복 (원출력·결정·이유·reviewer 보존)
- :Deleted 노드가 그래프 영속/로드 왕복에서 상태·deleted_at 보존
- review_records parquet export, 전체 테스트 통과, code-only 커밋

## 한계 (문서화)

- raw→graph 삭제 전파(retention, 03 §8.4) 전체 구현은 후속 — 이번은 골든셋·deleted 상태의
  영속화와 훅 계약 기록
