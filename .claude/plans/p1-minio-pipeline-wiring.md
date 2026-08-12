# P1 · 후속 ① — MinIO ↔ 파이프라인 실배선 + fetch.json 완비 (design 03 §2)

## 배경

저장 키스톤 ②에서 `MinioRawStore`가 MinIO에 raw를 영속할 수 있게 됐지만, **실제 수집
(`collect_large`)과 파이프라인 입력(`load_raw_zone`)은 여전히 로컬 fs를 쓴다**. 이 증분은
raw 저장 계약을 MinIO로 실배선해 수집→저장→파이프라인 end-to-end 를 완성한다.

## 현재 vs 목표
- `_save_zone`(collect_large): 로컬 fs `data/raw/<source>/doc/<doc_id>/{content.bin, fetch.json}`.
- `load_raw_zone`: 로컬 fs → in-memory RawStore (meta list).
- `MinioRawStore`: MinIO 객체 키 §2.1, content-hash idempotency·ADR-301 이미 구현(②).

목표: **collect_large가 MinIO에 쓰고, load_raw_zone이 MinIO로부터 읽는다** — 기존 로컬 fs 경로는
default 로 유지(파괴 없음), MinIO 는 선택 백엔드.

## 구현

### 1. `collect_large._save_zone` MinIO 백엔드 (무파괴 옵션)
- `_save_zone(source_id, url, content, meta, raw_dir=None, minio_store=None)`.
  `minio_store` 제공 시 → `MinioRawStore.put(source_id, url, content, meta)` 로 저장 (동일
  content-hash doc_id+idempotency), 반환 `(doc_id, created)`. 미제공 시 기존 로컬 fs 경로 유지.
- `collect_arxiv`·RSS/SEC 콜렉터가 `--minio` 플래그(전역 `MINIO_STORE`) 시 store 전달.

### 2. `load_raw_zone` MinIO 읽기 경로
- `load_raw_zone_minio(minio_store) -> (store, meta)` — MinIO에서 `raw/<source>/<doc>/content.bin`+
  fetch.json 읽어 동일 meta list 계약 `[{source_id,url,doc_id,content}]` 재구성 (파이프라인 재사용).
- 기존 `load_raw_zone` (fs) 는 유지.

### 3. fetch.json §2.2 완비
- `_save_zone`/MinioRawStore 가 기록하는 meta 에 **`license`·`robots_allowed`**(governance 11 필드)
  기본값 추가 (license="gov-public"/"unknown", robots_allowed=true). `.env`/source 별 덮어쓰기 여지.

## TDD (Red→Green)
`tests/test_minio_pipeline_wiring.py`:
- 전용 버킷(② `raw-test-*` 재사용) 격리, 연결 불가 skip.
- `collect_arxiv(total=2)` → `MinioRawStore` 버킷에 raw 2건 객체 존재 (객체 키 §2.1).
- `load_raw_zone_minio` → 동일 meta list (doc_id·content 왕복) → `run_pipeline` 재사용 가능.
- fetch.json 에 license/robots_allowed 존재.
- idempotent 재수집 (동일 doc_id, 중복 객체 없음).

## 앤티-골
- postgres 배선(후속 ②)·Neo4j(후속 ③) 제외.
- 실제 대량 수집(1만) 실행 제외 — 러너 구축·실증만.

## 성공 기준
1. `test_minio_pipeline_wiring.py` 통과.
2. 전체 스위트 446 회귀 0.
3. MinIO 라이브 데모: collect → MinIO 객체 → load_raw_zone_minio → 파이프라인 입력.
4. 3단계 문서 반영 (design 03 §2 구현 + ROADMAP Changelog).
