# Plans: 조사 완료 HTML 리포트와 Campaign Ledger

> Created: 2026-09-20
> Updated: 2026-09-20
> Status: Stable (implemented)
> Requirements: [requirements.md](./requirements.md)
> Specs: [specs.md](./specs.md)

## Overview

구현은 일곱 수직 증분으로 진행한다. 각 증분은 Red → Green → Refactor를 지키고, 구조 변경과 행동 변경을 분리한다. 첫 증분에서 pure ReportDraft/renderer 계약을 봉인하고, 두 번째에서 PostgreSQL artifact·원자 완료 경계를 만든 뒤 worker에 연결한다. 이후 API → 목업 → 공용 UI/frontend → 운영 검증 순서로 확장한다. 기존 JSON report와 Council 조사 실행은 전 구간에서 동작해야 한다.

목업 선행 규칙은 유지한다. Campaign Ledger와 HTML Report 정적 목업을 브라우저로 검토한 뒤 `/reports` frontend를 구현한다.

## Implementation Steps

### Step 1: ReportDraft와 deterministic renderer 계약 (TDD)

- **Goal**: LLM이 새 문장/HTML을 만들 수 없는 reference-only presentation plan과 byte-deterministic HTML renderer를 봉인한다.
- **Specs Reference**: TS-2, TS-3.
- **Tests first**:
  - 같은 source+draft+template → byte-identical HTML/hash.
  - unknown/blocked/duplicate statement ref, hash mismatch, unknown field, free-text/HTML field → draft 전체 거부.
  - `<script>`, event attribute, `&`, quote가 question/statement/ID에 있어도 text로 escape.
  - 미선택 verified statement가 canonical order로 append되고 `fact/asserted` provenance link가 유지.
  - provider failure/invalid draft → deterministic fallback과 stable reason.
- **Files**:
  - `prototype/tests/test_investigation_report.py` — Create.
  - `prototype/orc_citadel/investigation_report.py` — Create: canonical JSON/hash, schema validator, presentation planner, renderer.
- **Validation**: 신규 pure test. 같은 fixture를 두 번 실행해 bytes/hash 동일 확인.
- **Complexity**: Complex.

### Step 2: Artifact 저장소와 원자 completion (TDD)

- **Goal**: artifact와 REPORT step이 JSON report/job completion과 함께 commit되는 단일 transaction 경계를 만든다.
- **Tests first**:
  - 성공 complete → investigation completed, job succeeded, REPORT step 1개, artifact 1개.
  - artifact insert/render metadata 오류 → 세 상태 모두 rollback.
  - cancel requested/stale claim token/late worker → artifact 0개, 기존 상태 보존.
  - 같은 investigation 중복 artifact → overwrite 없이 integrity conflict.
  - restart 후 HTML bytes/hash/metadata 동일 조회.
- **Files**:
  - `prototype/tests/test_investigation_store.py` — Modify.
  - `prototype/tests/test_investigation_job.py` — Modify.
  - `prototype/orc_citadel/investigation_store.py` — Modify: table, atomic complete, list/artifact reads.
- **Migration**: 현행 `ensure_tables()`의 `CREATE TABLE IF NOT EXISTS` 패턴. graph/curated schema는 건드리지 않는다.
- **Validation**: PostgreSQL integration tests. transaction 실패 주입으로 partial state 0건 확인.
- **Complexity**: Complex.

### Step 3: Worker REPORT 단계 연결 (TDD)

- **Goal**: `AUDIT → REPORT → complete_with_report_artifact`를 worker 수명주기에 추가한다.
- **Specs Reference**: TS-1, TS-2.
- **Tests first**:
  - 성공 path의 최종 transaction에 5번째 REPORT stage가 artifact와 함께 남는다.
  - 장기 REPORT 중 heartbeat가 유지되어 경쟁 worker가 claim하지 못함.
  - REPORT 경계 취소가 late completion보다 우선.
  - LLM unavailable/provider/schema/ref 오류 각각 fallback 완료.
  - renderer/integrity 오류는 failed이고 artifact 없음.
- **Files**:
  - `prototype/tests/test_investigation_job.py` — Modify.
  - `prototype/orc_citadel/investigation_job.py` — Modify.
  - `prototype/scripts/investigation_worker.py` 또는 현행 worker bootstrap — generator client 주입.
- **Validation**: worker integration tests, 실제 연결 LLM 없이 fake client로 모든 분기 재현.
- **Complexity**: Medium.

### Step 4: 목록·artifact HTTP 계약 (TDD)

- **Goal**: 조사 목록과 안전한 HTML/metadata 조회를 stdlib viewer에 제공한다.
- **Specs Reference**: TS-5.
- **Tests first**:
  - status/limit/cursor validation, 최신순 keyset pagination, 목록에 HTML body 미포함.
  - unknown 404, non-completed 409, post-cutover missing artifact invariant 500, legacy JSON-only HTML 404, store unavailable 503.
  - HTML Content-Type/CSP/nosniff/referrer/ETag/cache/inline filename headers와 304.
  - bytes/hash 불일치면 HTML을 보내지 않고 integrity error.
  - 기존 `/api/investigations/{id}/report` JSON byte-shape 무회귀.
- **Files**:
  - `prototype/tests/test_viewer_investigations.py` — Modify.
  - `prototype/orc_citadel/viewer.py` — Modify: list dispatch, artifact metadata, raw HTML response.
  - `docs/design/09-api.md` — 구현 확정 후 `/v1` 정본 반영 및 Spec minor bump 판단.
- **Validation**: HTTP integration tests + curl smoke로 실제 headers/body 확인.
- **Complexity**: Medium.

### Step 5: Campaign Ledger·HTML Report 목업 확정

- **Goal**: 실제 앱 구현 전에 정보구조, 상태, report print 문서를 정적 목업으로 검토한다.
- **Specs Reference**: TS-6, TS-7, TS-8.
- **Files**:
  - `design-system/mockups/src/pages/campaign-ledger.mjs` — Create.
  - `design-system/mockups/src/pages/investigation-report.mjs` — Create.
  - `design-system/mockups/build.mjs` — Modify: 두 page entry.
  - `docs/mockups/campaign-ledger.html` — Generate.
  - `docs/mockups/investigation-report.html` — Generate.
  - `docs/mockups/assets/campaign-ledger-hero.png` — supplied asset.
  - `docs/mockups/assets/empty-report-not-found.png` — supplied asset.
  - `docs/mockups/illustration-prompts.md` — implementation 시 specs TS-8 prompts를 asset SSOT에 반영.
- **Details**:
  - `DEMO FIXTURE · 실제 조사 결과 아님`을 페이지와 report 양쪽에 표시.
  - 반입된 8:3 banner와 transparent not-found illustration을 연결한다. asset 로드 실패 시 배경색/텍스트 fallback을 유지한다.
  - desktop 392px master-list + report detail 2열, mobile list→detail linear drill-in, report print view 확인.
- **Validation**: SSG 두 page build; Chromium에서 desktop/mobile/print 시각 검토; 외부 request 0, console error 0, client script 0.
- **Complexity**: Medium.

### Step 6: 공용 Report UI와 `/reports` frontend (TDD + browser)

- **Goal**: 목업 승인 정보구조를 shared UI와 Vite MPA로 이관한다.
- **Specs Reference**: TS-6.
- **Structural change first**:
  - 공용 props-only component를 `design-system/ui/reports.mjs`로 추출하고 목업이 이를 소비하도록 바꾼다. 렌더 구조 무변경을 먼저 확인한다.
- **Behavioral change**:
  - `frontend/reports.html`, `frontend/src/pages/reports/main.jsx` 추가.
  - list fetch/status filter/cursor, URL selection restore, terminal-aware polling, sandboxed iframe, retry/not-found/legacy JSON-only/empty states 배선.
  - Council 완료 panel과 Gate 최근 조사 영역에서 `/reports?investigation=` 진입 링크 추가. 8-space shell arrays는 변경하지 않는다.
- **Files**:
  - `design-system/ui/reports.mjs` — Create.
  - `design-system/mockups/src/pages/campaign-ledger.mjs` — Modify to shared components.
  - `frontend/reports.html`, `frontend/src/pages/reports/main.jsx` — Create.
  - `frontend/vite.config.mjs`, `prototype/orc_citadel/viewer.py` `_MIGRATED` — Modify.
  - `frontend/dist/` — Rebuild/commit.
- **Validation**: 실제 viewer에서 list → completed report → evidence link → back, running polling stop, unknown ID not-found, keyboard navigation, mobile drill-in을 Chromium으로 실행.
- **Complexity**: Complex.

### Step 7: 운영·보안·성능 경계 검증

- **Goal**: 기능 경계를 실제 surface에서 확인하고 회귀를 정리한다.
- **Checks**:
  - 실제 연결 LLM 1회: `generation_mode=llm_assisted`, plan ref whitelist, usage/model/prompt hash 기록 확인.
  - LLM env 제거 1회: deterministic fallback artifact 생성과 표시 확인.
  - malicious fixture: script/attribute/URL injection 불발, CSP와 iframe sandbox 확인.
  - 100개 investigation 목록 keyset pagination, HTML ≤1 MiB, 목록 query가 HTML bytes를 읽지 않음 확인.
  - print preview에서 section/table 분할·대비·header/footer 확인.
- **Docs/Cleanup**:
  - `docs/ROADMAP.md` changelog, design 03 durable metadata, design 07 REPORT presentation-plan, design 09 endpoints를 구현 결과와 정확히 동기화.
  - throwaway scripts/fixtures 제거. 신규 permanent test는 실제 회귀 계약만 유지.
- **Validation**: 관련 investigation/report tests + mockup/frontend build + 실제 browser scenario. 전체 장기 suite는 제외하고 영향 범위 suite를 실행한다.
- **Complexity**: Medium.

## Task Breakdown

| # | Deliverable | Depends On | Proof |
|---|---|---|---|
| 1 | Pure ReportDraft validator/renderer | — | deterministic/security unit tests |
| 2 | Artifact table + atomic complete | 1 | PostgreSQL rollback/idempotency tests |
| 3 | Worker REPORT stage + fallback | 1–2 | worker lifecycle tests |
| 4 | List/artifact/html APIs | 2 | HTTP contract tests + curl smoke |
| 5 | Two approved static mockups | specs | SSG + browser desktop/mobile/print |
| 6 | `/reports` MPA and entry links | 4–5 | real browser end-to-end |
| 7 | SSOT/changelog/cleanup | 1–6 | cross-reference review + focused suite |

## Testing Strategy

- **Pure behavior**: canonical JSON/hash, strict plan validation, escaping, renderer determinism, fallback.
- **Store integration**: transaction atomicity, claim/cancel fence, unique artifact, immutable hash.
- **HTTP integration**: keyset cursor, status filter, legacy/post-cutover status semantics, security headers, ETag/304, unchanged JSON report.
- **UI proof**: actual Chromium against static mockups and running viewer. Test user-visible transitions, not implementation field copies.
- **Adversarial fixtures**: question/statement containing markup, unknown refs, duplicate refs, provider garbage, large content boundary.

## Rollback Plan

- `/reports` route와 Vite entry를 제거해도 기존 8공간과 JSON report API는 유지된다.
- worker에서 REPORT stage를 제거하기 전, 배포 중 생성된 artifact table은 읽지 않는 inert 운영 데이터로 남긴다. destructive table drop은 rollback에 포함하지 않는다.
- `InvestigationStore.complete_with_report_artifact()`와 모든 호출부를 함께 되돌려 partial compatibility shim을 남기지 않는다.
- 구현 중 migration 전후 혼재 배포를 피한다. worker/viewer를 같은 release로 배포한다.

## Progress Tracking

| Step | Status | Notes |
|---|---|---|
| 1 | Done | strict reference-only draft + deterministic renderer |
| 2 | Done | PostgreSQL artifact와 atomic completion |
| 3 | Done | REPORT heartbeat·cancel·fallback 연결 |
| 4 | Done | list/metadata/raw HTML + ETag/CSP |
| 5 | Done | 정적 목업 작성 및 SSG build 완료 |
| 6 | Done | shared UI·Vite MPA·Council/Gate 진입 |
| 7 | Done | 회귀·browser·보안 리뷰·SSOT 동기화 |
