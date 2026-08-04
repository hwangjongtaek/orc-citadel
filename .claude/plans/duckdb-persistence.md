# DuckDB/Parquet 영속화 — normalized zone 쿼리 가능 (Phase 0, design 03 §3)

## 맥락 / 목표
지금까지 파이프라인(parse·segment·claim)은 **in-memory `RawStore`**로만 돌았다. 모든
수집·정규화 산출물이 프로세스 종료 시 사라진다. 이 단계는 정규화 zone(normalized)을
**DuckDB로 영속화**해 쿼리 가능하게 만든다 — 1만 문서 수집 전에 필요한 기반.

- **raw zone**: 이미 파일 기반 `data/raw/<source>/doc/<doc_id>/{content.bin,fetch.json}`
  (design 03 §2.1 레이아웃과 정확히 일치). 파일로 유지.
- **normalized zone**: `documents` + `segments`를 DuckDB에 저장 (design 03 §3.1·§3.2 스키마).
- 그래프/큐레이션(mentions·claims·S4 dedup)은 **이 단계 범위 밖** — 후속.

## 설계 근거 (design 03 §3)
- `documents`: doc_id(PK), source_id, url, title, authors, language, publication_time,
  revision_time, parser_version, char_len (03 §3.1).
- `segments`: segment_id(PK), doc_id, kind, text, char_start, char_end,
  norm_char_start, norm_char_end, order (03 §3.2, ADR-302).
- `doc_id`는 내용 기반 sha256[:24] (불변식 §3-6, idempotency). 재파싱 → 재INSERT가 아닌
  **upsert**(doc_id+parser_version)여야 하며, 옛 parser_version segment는 보존한다 (04 §3.3).
- offsets는 **문자(char)** 단위 (ADR-302, 이전 UTF-8 버그 수정과 정합).

## 구현 범위 (prototype 확장, TDD)

### 1) Red — `tests/test_duckdb_zone.py` 실패 테스트
`NormalizedZone`(DuckDB 기반) 계약:
- `persist_documents(store)` / `persist_segments(store)` — ParsedDoc+segments → DuckDB rows
- `documents()` / `segments(doc_id)` 조회 (쿼리 가능)
- **idempotency**: 동일 doc 재영속화 시 중복 row 없음 (doc_id+parser_version upsert)
- **chars vs bytes**: UTF-8 포함 문서에서도 char_len/offset 정확
- ephemeral DuckDB(`:memory:` 또는 temp file)로 테스트 — 영속 파일 없이.

### 2) Green — `orc_citadel/duckdb_zone.py` 신규 모듈
- `NormalizedZone` 클래스: `connect(path=":memory:")` → `initialize()` (CREATE TABLE IF NOT EXISTS)
- `documents`/`segments` TABLE 생성 (위 스키마)
- `persist(parsed_doc, segments, source_id, url)` → upsert
- `documents()` / `segments(doc_id=...)` 조회 메서드
- `chars` 유닛: text를 `len()`(char) 기준으로 문서화, DuckDB도 UTF-8 인식하되
  offset은 우리가 char로 계산·저장.

### 3) E2E 브리지 — `orc_citadel/persist_smoke.py` (스모크)
실제 수집 문서를 `load_raw_zone → extract_html → parse_document → NormalizedZone.persist`
로 영속화하고, DuckDB에서 `documents()`/`segments()`로 돌려받아 offset 왕복과 함께
원문 HTML 연결(해시·URL)을 확인. 프로토타입 `data/ocr.duckdb`(gitignore)에 저장.

### 4) (선택) Parquet export
DuckDB에서 `COPY documents TO ... (FORMAT PARQUET)`로 documents/segments를 Parquet으로
내보내는 스모크 1건 (05 이후 쿼리/그래프 입력용). 범위 미정 — 우선 DuckDB만.

## TDD / 성공 기준
- `test_duckdb_zone.py` Green (스키마·upsert idempotency·UTF-8 char offset·조회)
- persist_smoke: 실제 수집 문서 영속화→DuckDB 조회로 offset 왕복 검증
- 기존 23개 포함 전체 Green
- `.duckdb`/`data/` 파일은 gitignore 유지 (커밋은 코드만)

## 작업 순서 (Tidy First)
1. **Red** — duckdb_zone 테스트 실패 작성
2. **Green** — `duckdb_zone.py` 최소 구현
3. **E2E persist 스모크** — 실수집 문서 영속화·조회 검증
4. **Refactor** — 구조 갈무리 (upsert·index)
5. **Commit** — 코드만 (데이터 gitignore)

## 범위 밖 (이 단계 아님)
- curated zone(mentions/claims·status) 영속화 — S5 추출 후
- S4 Dedup / `dup_clusters` — 별도
- Parquet가 메인 저장(아직 쿼리 경로 미확정) — DuckDB 우선, Parquet export는 스모크로
- raw zone을 DuckDB로 이동 — 파일로 유지(설계 §2.1 정합)
