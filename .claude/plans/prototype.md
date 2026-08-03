# Prototype 계획 — provenance·bitemporal 모델 (Phase 0, design 03)

## 목표
설계 `docs/design/03-storage-and-data-model.md`의 핵심을 최소 구현으로 검증, **Phase 0 DoD 2항목**을 직접 충족한다.
- DoD ① 원문 offset → segment → claim → 원문 **왕복 추적** 가능
- DoD ② 동일 문서 재처리 시 **중복 mutation 없음** (idempotency)

### 범위
- 저장 계층 **핵심만**: raw(immutable, doc_id=sha256) · normalized(segments, 양방향 offset) · curated(claim_candidates) · mutation log(append-only, idempotency_key unique)
- bitemporal·graph replay는 **이번 범위 제외** (다음 증분)
- 기술: **Python + DuckDB** (Parquet 지향, 설계 §1 "초기 로컬은 DuckDB"), `pytest`(TDD)

## 검증 가능한 목표 (TDD Red→Green)
1. **왕복 추적** — 원문 span ↔ segment ↔ claim ↔ extraction_record ↔ 원문 offset이 재현됨
2. **idempotency** — 동일 bytes(동일 doc_id) 재수집 → 같은 mutation key로 **중복 이벤트 없음**
3. (당연히) immutable raw — 동일 URL 변경분은 새 doc_id로 보존

## 구현 구조 (최소)
```
prototype/
  pyproject.toml            # deps: duckdb, pytest
  orc_citadel/
    __init__.py
    identity.py             # doc_id = sha256(bytes)[:24]; ULID 유사 순번
    raw_store.py            # raw zone: immutable content + fetch.json
    normalize.py            # segments 생성(문단·문장 분리, offset 매핑)
    pipeline.py             # S1..S6 흐름: raw → segments → claim → mutation
    mutation_log.py         # append-only, idempotency_key unique
    provenance.py           # 왕복 왕복 추적 resolver
  tests/
    test_roundtrip.py       # DoD ①
    test_idempotency.py     # DoD ②
    test_immutable_raw.py
```

## 작업 순서 (TDD)
1. **Red** — `test_roundtrip.py`·`test_idempotency.py`·`test_immutable_raw.py` 실패 테스트 작성
2. **Green** — 최소 구현으로 통과
3. **Refactor** — 구조 갈무리 (Tidy, AGENTS.md)

## 도구 제약
- `duckdb`·`pytest` 설치 필요 (pip), Python 3.11+
- 외부 네트워크 없이 로컬 DuckDB 파일로 검증

## 성공 기준
- pytest 3개 파일 전부 Green
- DoD ① ② 각각을 단언(assert)으로 검증
- 구조 변경은 Tidy First에 따라 별도 커밋
