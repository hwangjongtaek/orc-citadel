# S2→S3→S4 파이프라인 스모크 — 실수집 문서 최초 엔드투엔드 (Phase 0)

## 맥락 / 목표
커넥터 + 소량 실수집(04)은 `data/raw/`에 **실제 웹 HTML**을 모았다. 그러나 현재까지
"Orc Citadel의 가치"인 증거/프로비넌스 파이프라인(S2→S3→S4)은 **합성 픽스처**로만
유닛 증명됐다. 이 작업은 실제 수집 HTML을 정규화→세그먼트→큐레이션(claim)→provenance
resolve로 연결하는 **최초 엔드투엔드 스모크**를 만든다.

**누락된 연결고리:** S3 Parse/Normalize의 **HTML→본문(clean text) 추출** 단계
(설계 04 §3). 현재 `segment_document`는 HTML이 아닌 clean text를 입력으로 가정하며,
HTML을 그대로 넣으면 태그 노이즈·메타데이터(제목/저자/공개시각)가 분리되지 않는다.

## 설계 근거 (design 04 §3, 03 §3)
- S3은 raw `doc_id` 입력 → normalized `documents`(title/authors/publication_time/revision_time/parser_version/char_len) + `segments`(paragraph/sentence + 양방향 offset, ADR-302) 출력.
- `parser_version` = 분할·정규화 규칙 식별 (bump 시 재파싱, segment_id 안정 유지).
- 각 segment는 원문(raw) offset과 정규화 offset을 함께 보존 (provenance 왕복 근간).
- 원문은 immutable, 재작성 금지 (04 §1.3). 수집 단계에서 본문 미리 쓰지 않음.

## 구현 범위 (prototype 확장, TDD)

### 1) Red — `tests/test_pipeline_smoke.py` 실패 테스트
실제 수집 구조의 **대표 HTML 픽스처**(title/본문 문단 포함, 태그·엔티티 있음)로:
- `extract_text(html)` → 본문 clean text + `ParsedDoc(title, publication_time, ...)` (§3.1 documents 필드)
- HTML→text 후 `segment_document` 정상 분절, 원문 offset이 실제 raw HTML offset을 가리킴 (ADR-302)
- 파이썬 stdlib만으로 HTML 태그/엔티티 제거 (prototype: 외부 의존성 없음 — `html` 모듈 + regex)

### 2) Green — `orc_citadel/parse.py` 신규 모듈
- `ParsedDoc` dataclass: `text`, `title`, `publication_time`, `parser_version` (04 §3.1 최소)
- `extract_html(html_bytes, url) -> ParsedDoc`: `<title>`/`<meta>`/`<h1>`/본문 `<p>` 후보 추출,
  태그·`&nbsp;`류 엔티티 제거 (stdlib `html.unescape`), 연속 공백 축약.
- prototype 범위: `kind="paragraph"` 문단 단위 분절까지는 `normalize.segment_document` 재사용하되,
  원문 offset을 **실제 HTML 바이트 인덱스**로 역매핑하는 래퍼 제공.

### 3) 워밍업 브리지 — 수집 raw 파일 → in-memory `RawStore`
`data/raw/<source>/doc/<doc_id>/content.bin` + `fetch.json`을 읽어 `RawStore.put`에 재공급하는
작은 로더 (스모크 전용). 실제 영속화(DuckDB/Parquet)는 별개 단계로 미룬다.

### 4) E2E 스모크 — `orc_citadel/pipeline_smoke.py` (수동 스크립트)
실제 수집 NVIDIA/SemiEngineering/arXiv 문서 1~3건을:
`read raw → extract_html → segment → MutationLog.apply(create_claim, span) → resolve_claim`
로 왕복, **결과 claim.text가 원문 HTML에서 복원되는지** 확인.

## TDD / 성공 기준
- `test_pipeline_smoke.py` Green (실제 HTML 구조 픽스처로 파싱 + offset 왕복 + idempotency)
- 스모크 스크립트: 실제 수집 문서 최소 1건 provenance 왕복 성공
- 기존 테스트 16개 포함 전체 Green
- 파생 코드·데이터는 커밋, 수집 raw(prototype/data/)는 gitignore 유지

## 작업 순서 (Tidy First)
1. **Red** — parse 테스트 실패 작성
2. **Green** — `parse.py` 최소 구현 + segment offset 래퍼
3. **워밍업 브리지** — raw file → RawStore 로더
4. **E2E 스모크 스크립트** — 실수집 문서로 왕복 증명
5. **Refactor** — 구조 갈무리, `parser_version` 부착
6. **Commit** — 구조/동작 분리 (코드만)

## 범위 밖 (이 단계 아님)
- DuckDB/Parquet 영속화 (`documents`/`segments` row 저장) — 별도
- S4 Dedup(복제/출처 축소)·S5 LLM 추출 — 별도
- HTML 파서 의존성(BeautifulSoup 등) 도입 — prototype은 stdlib만
