# P1 · 저장 계층 키스톤 ① — PostgreSQL `graph_mutations` SoT + Replay (design 03 §7, ADR-304/307)

## 배경 (Phase 1 저장 계층 키스톤)

사용자가 Phase 1(10만 문서 MVP)의 **저장 계층 키스톤**을 이번 세션의 착수 지점으로 선택했다.
탐색 결과 저장 계층 최대 구조적 격차는 **append-only mutation log가 in-memory list**라는 점이다
(`mutation_log.py` → `_mutations: list[Mutation]`, 영속화 없음). design 03 §7(ADR-304/307)에서 **SoT는
append-only `graph_mutations` 이벤트 로그**이고 materialized graph/projection은 그로부터 **replay로 재구축**되어야
한다. 이번 증분은 그 SoT를 가동 중인 PostgreSQL 16 컨테이너에 영속화하고 재생 경로를 구현한다.

> 참고 — 이번 증분 범위 밖의 나머지 키스톤 조각(후속 증분으로 계획에 명시만):
> - **후속 ② MinIO raw 객체 스토어** (design 03 §2): 현재 raw는 로컬 fs + in-memory dict, `fetch.json` §2.2 미비.
>   이번 증분은 raw를 건드리지 않음.
> - **후속 ③ `extraction_records` 테이블 + provenance 게이트** (design 03 §8, ADR-305): 현재 `RawStore + in-memory
>   dict`에만 존재. 재생 SoT가 먼저 있어야 게이트를 안정적으로 강제할 수 있으므로 후속 배치.

## 현재 상태

- infra: `docker compose` postgres:16-alpine **healthy**, 5432. 크리덴셜은 gitignore `.env`(`POSTGRES_USER/PASSWORD/DB`).
- `mutation_log.py`: `MutationLog` = in-memory `list[Mutation]` + `_by_key` + `_claims_by_span`. append-only/idempotency
  계약은 이미 구형(불변식 §3-3, §3-6)돼 있으나 **영속화·재생 없음**.
- `pyproject.toml` deps: `duckdb`, `requests`만. `uv` 사용 가능(`uv pip install 'psycopg[binary]'` dry-run 확인됨).
- prototype venv + pytest 424개 Green.

## 설계 계약 (design 03 §7.1 정본)

`graph_mutations` 테이블 (컨테이너 postgres에 생성):

| 컬럼 | 타입 | 비고 |
| --- | --- | --- |
| `mutation_id` | varchar PK | `mut-<ULID>` |
| `idempotency_key` | varchar UNIQUE | stage input 해시 — 중복 방지 |
| `op` | varchar | `create_node/create_edge/merge_entity/unmerge/supersede/delete/quarantine` |
| `payload` | jsonb | 대상 element·속성 |
| `resolution_ref` | varchar NULL | → resolution decision |
| `actor` | varchar | `pipeline/llm:<model>/human:<user>` |
| `version_tuple` | jsonb | 5축 |
| `correlation_id` | varchar | end-to-end 추적 |
| `tx_time` | timestamptz | 기록 시각 |

이벤트 계약 (§7.2):
- **Append-only**: 이벤트 수정·삭제 금지. rollback은 역이벤트(`delete/supersede/unmerge`)로.
- **Replay**: `tx_time`·기록 순서대로 적용 시 동일 materialized graph 재구축 가능.
- **Idempotency**: 동일 `idempotency_key` 재수신 시 no-op (반환값은 기존 `mutation_id`).

## 구현 단계 (TDD — Red → Green)

### Step 1 — `PostgresMutationLog` (새 모듈 `postgres_mutation_log.py`)

기존 `MutationLog`의 **동일 append-only/idempotency 계약**을 유지하면서 postgres 백엔드로 교체한다.
`Mutation` dataclass는 `mutation_log.py`의 것을 재사용(계약 일치 · 뒤쪽 호환)한다.

- **Red**: `tests/test_postgres_mutation_log.py` 추가
  - 테이블 생성 스키마가 §7.1에 부합(컬럼 존재 검증, `CITADEL_TEST_*` DB/스키마 사용, 실행 시 DROP+CREATE로 격리).
  - `apply()` — ULID mutation_id, insert 후 재조회로 왕복 persist 확인.
  - append-only — 동일 `idempotency_key` 재`apply` 시 **중복 행 없음**, 기존 `mutation_id` 반환.
  - replay — 두 이벤트 `apply` → 신규 인스턴스로 `all_mutations()` 순서 재조회 → 동일 리스트 (ADR-304).
  - `actor/version_tuple/correlation_id/payload/op` round-trip.
- **Green**: `postgres_mutation_log.py` 구현 — `psycopg` 커넥션(환경변수/`.env`의 `POSTGRES_*`), 준비된 INSERT, UNIQUE(ON CONFLICT DO NOTHING), ORDER BY 기록 순서 조회.
- **Refactor**: 파라미터·접속 문자열 생성 헬퍼 추출 (작은 경우 생략 가능).

### Step 2 — idempotency no-op 계약 정합 (선택, 겹치면)

mutation_log의 `IdempotencyViolation` 예비 모델과 postgres `ON CONFLICT DO NOTHING` 결정을 일치시키는
짧은 문서 주석만 추가 — 행동 변경 아님.

### Step 3 — 설계 정본 문서 반영 (3단계 규칙)

문제 없을 시 아래 3단계 수행:
1. `docs/design/03-storage-and-data-model.md` — ADR 로그에 실제 구현 기록(예: `graph_mutations` postgres 구현, replay 검증 경로).
2. `docs/design/README.md` — Spec version 유지(0.1.0)·관련 사항 반영 여부 확인.
3. `docs/ROADMAP.md` §5 Changelog — "저장 계층 키스톤 ① — Postgres graph_mutations SoT" 기록.

### Step 4 — 회귀 확인

기존 424 테스트 Green 유지 + 신규 테스트 통과. CI 차단은 없음(이 증분은 로컬 프로토타입).

## 앤티-골(하지 않음)

- MinIO raw/`fetch.json`/`extraction_records`/provenance 게이트/Neo4j/그래프 엑스플로러 — 후속 증분.
- `curated_zone`·`graph_service`·파이프라인 재작성 — 기존 계약 유지.
- LLM budget/tiering · 병렬성 · 10만 실제 수집 — 별도 트랙.

## 성공 기준 (검증 가능)

1. `pytest tests/test_postgres_mutation_log.py` — 전 test 통과.
2. 전체 스위트 회귀 0.
3. postgres 컨테이너에 `graph_mutations` 테이블이 실제 생성되고, `apply`→재조회 round-trip,
   동일 `idempotency_key` 재적용 no-op, 신규 인스턴스 replay 동일 결과 모두 데모 확인.
4. Changlog(S5) + design 03 반영 — 3단계 규칙 준수.

## 테스트 격리 주의

- 테스트는 **전용 DB/스키마**(예: `CITADEL_TEST` 또는 `citatdel_test` 스키마)에 DROP+CREATE로 생성해
  실제 postgres에 안전하게 실행되게 한다. 크리덴셜은 `.env`(`POSTGRES_USER/PASSWORD/DB`)에서 읽는다.
- 네트워크/드라이버 불가 시(오프라인) 테스트는 명시적으로 skip — 기존 스위트 424 유지 보장.
