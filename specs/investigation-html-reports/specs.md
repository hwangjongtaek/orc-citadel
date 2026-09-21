# Specs: 조사 완료 HTML 리포트와 Campaign Ledger

> Created: 2026-09-20
> Updated: 2026-09-20
> Status: Stable
> Requirements: [requirements.md](./requirements.md)

## Overview

Durable investigation worker의 성공 경로에 `REPORT` 단계를 추가한다. 입력은 `AUDIT`가 확정한 report/audit trace뿐이다. 연결된 LLM은 raw HTML이 아니라 제한된 `ReportDraft` JSON을 만들고, 기존 claim whitelist와 `Audit.trace`로 다시 검증한다. 마지막 HTML은 stdlib 기반 deterministic renderer가 escape·allowlist를 적용해 생성한다. LLM이 없거나 산출이 유효하지 않으면 동일 renderer가 감사된 원본 문장으로 fallback 문서를 만든다.

PostgreSQL에는 `investigation_report_artifacts`를 추가한다. artifact insert와 신규 `InvestigationStore.complete_with_report_artifact()`의 REPORT step/investigation/job 완료 갱신을 한 transaction으로 묶어 cutover 이후 `completed`가 곧 “JSON + audit + HTML 모두 조회 가능”을 뜻하게 한다. 별도 Vite MPA `/reports`는 investigation 목록 API와 HTML endpoint를 소비한다. 앱 viewer는 report를 sandboxed iframe으로 격리하고, 목업은 동일한 정보구조를 정적 fixture로 보여준다.

## Technical Specifications

### TS-1: 완료 트리거와 원자적 artifact 확정 (from FR-1, FR-2)

- **Components Involved**: `investigation_job.InvestigationWorker`, `investigation_store.InvestigationStore`, 신규 `investigation_report.py`.
- **State flow**:

```text
queued
  → PLAN → RUN → SYNTHESIZE → AUDIT
  → REPORT (LLM ReportDraft 시도 → 검증 → deterministic render;
            실패 시 audited JSON fallback → deterministic render)
  → transaction {
       VERIFY active claim + cancel_requested=false
       INSERT report_artifact
       INSERT step-005 / REPORT
       UPDATE investigation = completed + report/audit
       UPDATE job = succeeded
     }

cancel/lease loss at any stage boundary → no artifact, no completion
renderer/storage failure             → job/investigation failed, no partial row
```

- **Implementation Approach**:
  1. investigation 생성 시 `report_profile={generation_mode:"llm_assisted", template_version, output_schema_version, prompt_template_hash}`를 불변 값으로 고정한다. 기존 investigation `mode`와 섞지 않는다.
  2. `AUDIT` 후 현재 claim 소유와 cancel 여부를 다시 확인하고 REPORT generation 중에도 기존 heartbeat/lease를 유지한다.
  3. `HtmlReportGenerator.generate(result, investigation_meta, report_profile)`가 LLM draft를 시도하고 검증된 `RenderedArtifact`를 반환한다. 이때 durable REPORT step은 아직 쓰지 않는다.
  4. `InvestigationStore.complete_with_report_artifact(...)`가 transaction 안에서 claim/cancel fence를 다시 검증하고 artifact insert, `step-005/REPORT` insert, investigation/job update를 모두 처리한다.
  5. job update의 `status='running' AND claim_token=? AND cancel_requested=false`가 0행이거나 REPORT step/artifact uniqueness가 깨지면 transaction 전체를 rollback한다.
- **Idempotency**:
  - `UNIQUE(investigation_id)`로 artifact 1개를 강제한다.
  - 정상 transaction은 전부 commit되거나 전부 rollback되므로 “artifact만 있고 job은 running”인 중간 상태가 없다.
  - stale worker의 late result는 기존 claim token 조건으로 거부한다.
  - 최초 범위에서는 재생성/교체를 제공하지 않는다. template 변경은 새 investigation에만 적용한다.
- **Completion semantics**: `investigation.status=completed`와 `job.status=succeeded`는 HTML artifact가 저장된 뒤에만 보인다. LLM 실패는 deterministic fallback으로 흡수하지만 renderer/DB 실패는 가짜 성공으로 숨기지 않는다.

### TS-2: LLM ReportDraft와 evidence 재감사 (from FR-1)

- **Input boundary**: question, scope, conclusion, 이미 audit된 canonical statements, open questions, coverage/termination, independence summary, timeline 참조, audit summary, version tuple. 각 canonical statement에는 기존 `audit_trace.statement_ref`를 부착한다. raw document 본문·비감사 retrieved span·비밀 환경값은 전달하지 않는다.
- **LLM role**: 이미 감사된 문장을 **선택·정렬·그룹화**하는 편집자다. 새 evidentiary prose, 섹션 제목, 증거 판정, confidence 계산, claim 추가, HTML/CSS 생성 권한은 없다. renderer가 ref를 canonical 문장으로 치환하므로 “근거 ID만 그럴듯하게 붙인 새 사실” 경로 자체가 없다.
- **Strict output** (`ReportDraft`, schema `report-draft/1.0.0`):

```json
{
  "draft_schema_version": "1.0.0",
  "investigation_id": "inv-…",
  "template_version": "citadel-report-1",
  "source_report_hash": "sha256:…",
  "summary_statement_refs": ["statement-001", "statement-004"],
  "sections": [
    {
      "section_key": "findings|counter_evidence|timeline|limitations",
      "statement_refs": ["statement-002", "statement-003"]
    }
  ]
}
```

- **Schema validation**:
  - strict JSON object만 허용한다. 모든 필드는 required, `additionalProperties=false`; markdown fence·설명 prose·raw HTML은 거부한다.
  - `draft_schema_version`, investigation ID, template version, source report hash는 서버가 준 값과 정확히 같아야 한다.
  - summary ref는 최대 5개, section은 1–8개, `section_key`는 닫힌 enum이며 중복될 수 없다. ref는 summary/section 전체에서 중복될 수 없다.
- **Semantic validation**:
  - 모든 ref는 입력 report에 존재하고 `audit_trace.verified=true`여야 한다.
  - canonical `fact|asserted` 문장은 원래 `claim_ref`와 source span을 그대로 보존한다. `opinion|prediction`의 null-ref 규칙도 원본에서 바꾸지 않는다.
  - LLM이 선택하지 않은 verified statement는 누락 방지를 위해 canonical 순서로 `findings`에 결정적으로 append한다.
  - conclusion, confidence, counter-evidence summary, open questions, audit limitations, provenance IDs, version tuple은 LLM 선택과 무관하게 renderer가 항상 출력한다.
  - provider error, timeout, JSON/schema 실패, hash 불일치, unknown/blocked ref, 중복/상한 위반 중 하나라도 있으면 draft 전체를 폐기한다. 일부 필드를 salvage하지 않는다.
- **Fallback**: 같은 `ReportDraft` schema를 verified statement의 canonical 순서로 결정적 생성한다. `generation_mode=deterministic_fallback`, `fallback_reason`은 `llm_unavailable|llm_provider_error|invalid_draft|audit_rejected` 중 하나다.
- **Versioning**: validated `draft_json`/hash와 `provider`, `model_id`, `prompt_template_hash`, `output_schema_version`, `template_version`, inference params, usage를 artifact metadata에 저장한다. chain-of-thought/tool trace는 저장하지 않는다.

### TS-3: 결정적 HTML renderer (from FR-2, FR-4)

- **Document policy**:
  - `<!doctype html>`, `lang="ko"`, semantic `header/main/section/article/table/footer`.
  - script, form, iframe, object, embed, remote font/image, inline event handler 없음.
  - CSS는 문서 내 `<style>` 1개. Citadel Nightwatch 색상과 system font fallback을 사용하며 `@media print`를 포함한다.
  - 모든 text/attribute는 `html.escape(..., quote=True)`. renderer가 만드는 내부 anchor 외 사용자/LLM URL을 받지 않는다.
  - evidence link는 `/witnesses?claim=<percent-encoded-id>`만 허용한다. graph link는 `/table?subject=<id>`, 원본 JSON은 `/api/investigations/<id>/report`로 renderer가 조립한다.
- **Size guard**: UTF-8 HTML 최대 1 MiB. 입력 상한을 적용한 뒤 초과하면 renderer failure로 처리하며 무음 truncation하지 않는다.
- **Integrity**:
  - `source_report_hash = sha256(canonical_json(report+audit_trace))`.
  - `content_hash = sha256(html_bytes)`.
  - footer에 investigation ID, correlation ID, generated_at, template version, content hash 앞 12자를 표시한다.
- **Report information architecture**:
  1. Cover — `Investigation Report`, question, status, scope, generated/as-of time, mode/fallback badge.
  2. Executive Summary — audit된 핵심 문장.
  3. Confidence — value + evidence count + independent source count + basis + dimension 표. 단일 gauge 금지.
  4. Findings — modality badge, statement, claim/evidence link.
  5. Supporting & Contradicting Evidence — relation·source·span 요약·provenance 진입.
  6. Timeline — valid/observed/change/supersedes.
  7. Gaps & Open Questions — reason/coverage, budget 종료 시 명시.
  8. Method & Audit — coverage, termination, LLM/fallback, linked/verifiable/blocked, model/prompt/template/version tuple.
  9. Footer — IDs/hash/“Evidence first · generated from audited investigation data”.
- **Print**: navigation controls 숨김, 배경은 흰색/짙은 글자, 링크 URL은 필요한 내부 ref만 각주형으로, page break는 section/table row 중간을 피한다.

### TS-4: 저장 모델 (from FR-2)

#### `investigation_report_artifacts` (PostgreSQL)

| Field | Type | Constraints | Description |
|---|---|---|---|
| `artifact_id` | varchar | PK, `rpt-<ULID>` | artifact 식별자 |
| `investigation_id` | varchar | UNIQUE, FK investigations | 조사당 artifact 1개 |
| `media_type` | varchar | `text/html; charset=utf-8` | 응답 MIME |
| `html_bytes` | bytea | NOT NULL, ≤1 MiB app guard | 정확히 저장·서빙할 UTF-8 bytes |
| `byte_length` | bigint | CHECK = `octet_length(html_bytes)` | 크기 무결성 |
| `content_hash` | varchar | NOT NULL, `sha256:<hex>` | exact HTML bytes integrity |
| `source_report_hash` | varchar | NOT NULL | canonical JSON(report+audit) integrity |
| `draft_json` | jsonb | NOT NULL | 검증된 reference-only presentation plan |
| `draft_hash` | varchar | NOT NULL | canonical ReportDraft integrity |
| `generation_mode` | varchar | `llm_assisted|deterministic_fallback` | 실제 생성 경로 |
| `fallback_reason` | varchar | nullable enum | fallback 사유 |
| `template_version` | varchar | NOT NULL | renderer template |
| `output_schema_version` | varchar | NOT NULL | ReportDraft schema |
| `provider` / `model_id` | varchar | nullable | 실제 연결 LLM |
| `prompt_template_hash` | varchar | nullable | prompt pin |
| `usage` | jsonb | NOT NULL default `{}` | 실제 token/call usage |
| `audit_summary` | jsonb | NOT NULL | linked/verifiable/blocked |
| `version_tuple` | jsonb | NOT NULL | 5축 재현 메타 |
| `correlation_id` | varchar | NOT NULL | end-to-end 추적 |
| `created_at` | timestamptz | NOT NULL | UTC 생성 시각 |

- HTML을 기존 `investigations.report` JSONB에 섞지 않는다. 목록 query가 대형 text를 읽지 않도록 artifact metadata만 join한다.
- 최초 migration은 `CREATE TABLE IF NOT EXISTS`로 현재 `ensure_tables()` 패턴을 따른다. HTML은 절대 graph/curated SoT가 아니며 조사 표현 artifact다.
- `investigations.report_profile jsonb`를 추가한다. cutover 이후 생성 row에는 requested generation mode와 template/schema/prompt hash가 필수이며 immutable이다. 기존 row는 `NULL`로 남겨 legacy JSON-only 상태를 구분하고 자동 backfill하지 않는다.

### TS-5: API / Interface Design (from FR-3, FR-4)

#### `GET /api/investigations`

- **Query**: `status` optional enum, `limit` default 25/max 100, `cursor` opaque.
- **Ordering**: `(created_at DESC, investigation_id DESC)` 고정. cursor는 이 두 값을 서버에서 encode한 opaque token이다.
- **Output**:

```json
{
  "items": [
    {
      "investigation_id": "inv-…",
      "question": "…",
      "subject_id": "org-…",
      "scope": {},
      "mode": "llm",
      "status": "completed",
      "coverage": {"ratio": 0.83, "gaps": []},
      "termination": "coverage",
      "created_at": "…",
      "completed_at": "…",
      "artifact": {
        "artifact_id": "rpt-…",
        "generation_mode": "llm_assisted",
        "content_hash": "sha256:…",
        "created_at": "…",
        "html_url": "/api/investigations/inv-…/report.html"
      }
    }
  ],
  "page": {"next_cursor": null, "limit": 25}
}
```

- `artifact=null`은 queued/running/failed/cancelled와 cutover 이전 completed legacy row에 대해 정직한 상태다. legacy completed item은 `artifact_state="legacy_json_only"`와 기존 JSON link를 노출한다. cutover 이후 `report_profile`이 있는 completed row에서만 null을 무결성 위반으로 처리한다.

#### `GET /api/investigations/{id}/report-artifact`

- HTML을 제외한 artifact metadata를 반환한다. UI detail metadata와 ETag 사전 확인에 사용한다.
- unknown ID `404 investigation_not_found`; non-completed `409 investigation_not_completed`; post-cutover invariant break `500 report_artifact_missing`; legacy JSON-only `404 report_artifact_not_found`; store unavailable `503`.

#### `GET /api/investigations/{id}/report.html`

- **Success**: raw HTML bytes. JSON envelope로 감싸지 않는다.
- **Headers**:
  - `Content-Type: text/html; charset=utf-8`
  - `Content-Security-Policy: default-src 'none'; style-src 'sha256-<template-style-hash>'; img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'self'`
  - `X-Content-Type-Options: nosniff`
  - `Referrer-Policy: no-referrer`
  - `ETag: "<content_hash>"`
  - `Cache-Control: private, no-cache`
  - `Content-Disposition: inline; filename="investigation-<safe-id>.html"`
- **Conditional request**: `If-None-Match` 일치 시 `304` body 없음.
- **Compatibility**: 기존 `GET /api/investigations/{id}/report` JSON 응답은 변경하지 않는다.

### TS-6: Campaign Ledger 페이지 콘셉트 (from FR-3, FR-5)

- **World/technical name**: `Campaign Ledger · Investigation Reports` / `조사 기록 · 리포트`.
- **Route**: canonical `/reports`, Vite entry `reports.html`, mockup `campaign-ledger.html`.
- **IA position**: Council Chamber의 “완료 리포트 보기” action과 Gate의 최근 조사/리포트 진입으로 접근한다. 기존 `SPACES` 8개에는 넣지 않으며 shell의 1·2차 공간 탭 수를 바꾸지 않는다.
- **Desktop layout (1200px)**:

```text
┌ masthead: Campaign Ledger · 조사 기록 / flat band until banner asset exists ┐
├─────────────── 392 ────────────────┬────────────── remaining ──────────────┤
│ Filters + Investigation List       │ Selected Summary + Trusted Actions    │
│ status, cursor pagination          │ Sandboxed Report Preview              │
│ status cards                       │ Artifact Metadata + Audit Integrity    │
└────────────────────────────────────┴────────────────────────────────────────┘
```

- **Mobile behavior**: list view는 page title → status filter → investigation cards 순이다. item 선택 시 list를 detail view로 교체하고 selected summary/actions → report document → audit details를 선형 표시한다. back control은 list selection과 scroll을 복원하고 detail heading으로 focus를 이동한다.
- **List card**: status badge + question(2 lines) + inv ID + mode + created/completed time + coverage `covered/planned` + artifact `LLM|fallback|not ready` badge. 색만으로 상태를 전달하지 않는다.
- **Filters**: All / In progress / Completed / Failed & Cancelled. 사용자 요청 범위를 넘는 mode filter·full-text search·sort chooser는 넣지 않는다.
- **Preview states**:
  - initial/no selection: “리포트를 선택하면 감사된 HTML 문서를 엽니다.”
  - loading: skeleton + `aria-busy`.
  - queued/running: current step, coverage, cancel은 Council에서만 제공.
  - failed/cancelled: error/termination과 JSON/HTML 부재를 명시.
  - not found: 반입된 `empty-report-not-found.png`를 132px spot illustration으로 표시한다. asset 로드 실패 시 제목·설명만 남는 EmptyState여야 한다.
  - API error: “저장소 연결 실패” + retry. empty list와 혼동 금지.
- **Preview security**: `<iframe title="조사 리포트: …" sandbox src="…/report.html">`; `srcdoc` 금지. 새 창 열기는 iframe 밖의 trusted control만 제공한다.
- **Hero policy**: 반입된 `campaign-ledger-hero.png`를 shared shell의 8:3, 최대 300px band로 표시한다. 제목은 하단 scrim 위에 두며 이미지 로드 실패 시 배경색과 텍스트가 유지된다.

### TS-7: HTML Report 목업 콘셉트 (from FR-4, FR-5)

- **Output**: `docs/mockups/investigation-report.html`. 앱 shell이 아닌 저장 artifact 자체를 대표하되 mockup index와 검토 편의를 위해 theme-citadel CSS를 사용한다.
- **Fixture**: “2024년 이후 A사의 AI 가속기 공급망 다변화가 실제로 진행되었는가?” 한 건. 모든 조직/ID/수치는 `Mock fixture · 실제 조사 결과 아님` 배지와 함께 제시한다.
- **Visible content**:
  - cover meta strip: completed, LLM assisted, as-of, investigation ID.
  - conclusion + confidence value/evidence 7/independent 2/basis. coverage 63%는 Method에 표시한다.
  - evidence-first summary statements with `asserted`/`prediction` badges.
  - supporting vs contradicting table and “Hall of Witnesses에서 근거 열기” links.
  - timeline, open questions, Audit `linked 5/5`, generation metadata, version tuple, hash footer.
- **Document controls** are outside artifact in Campaign Ledger. The artifact itself has no JS buttons.

### TS-8: Illustration Prompts (from FR-6)

#### Banner — `docs/mockups/assets/campaign-ledger-hero.png`

- **Alt**: `완료된 조사 두루마리가 정돈된 Campaign Ledger 기록실`
- **Generation prompt**:

```text
Detailed 16-bit pixel art (dot art), rich retro-RPG key-art banner for "Orc Citadel", a temporal evidence intelligence platform. Crisp visible pixels, strong but controlled dithering, careful shading, high detail. Original design — do NOT imitate Warcraft or any existing game IP.

A wide night interior of the Citadel's Campaign Ledger: a disciplined basalt record hall where completed investigation reports are stored as a small row of parchment folios and black-iron index plaques. In the center, an open ledger on a low archival desk shows a restrained evidence map: only a few verified nodes connected by thin emerald #45E06F lines. To one side, a closed crimson #7B2833 report folio bears a simple abstract tusk-and-shield mark with no runes. A narrow amber #FFB13B lamp indicates one report still in progress; all completed records remain calm and unlit. No battle, no mysticism — the scene communicates durable investigation history, auditability, and readable reports.

Palette: near-black navy void #07111C and night #0D1B2A, basalt #111820 / #26313A, muted stone #D6CCB8, parchment #C8B58E, restrained crimson #7B2833. Emerald #45E06F is reserved ONLY for verified evidence links and occupies less than 8% of the frame. Warm ember #E97824 and signal amber #FFB13B are tiny status accents only.

Composition: 1920x720, 8:3 wide banner, opaque PNG. Keep the upper 35% dark and low-detail for overlaid page title. Place the open ledger and evidence links in the lower center-right so the title remains readable. Strong silhouette at thumbnail size, 2–3 primary masses despite the detailed texture.

Negative constraints: no neon dashboard, no excessive green glow, no fire particles, no combat weapons, no cheering characters, no magical prophecy orb, no glowing runes, no ornate gold frame, no noisy stone texture, no readable generated text, no logos from existing franchises, no UI chrome baked into the image.
```

#### Not found — `docs/mockups/assets/empty-report-not-found.png`

- **Alt**: `비어 있는 리포트 보관 슬롯과 닫힌 인덱스 표찰`
- **Generation prompt**:

```text
Detailed 16-bit pixel art (dot art), restrained retro-RPG spot illustration for "Orc Citadel", a temporal evidence intelligence platform. Crisp visible pixels, controlled dithering, careful shading, transparent background. Original design — do NOT imitate Warcraft or any existing game IP.

A small black-iron archive rack with one clearly empty report slot between two closed parchment #C8B58E folios. A simple iron index tag hangs below the empty slot with no readable text. A tiny magnifying lens rests beside it, angled toward the missing space. One faint, disconnected emerald #45E06F pixel node is present but NOT glowing, indicating that no report artifact was found. Quiet, precise, non-comedic "report not found" mood.

Palette: basalt #111820 / #26313A, muted stone #D6CCB8, parchment #C8B58E, near-black navy shadows #07111C. Emerald #45E06F may appear only as one tiny inactive accent; no amber alarm is needed.

Composition: centered transparent PNG, approximately 360x360 at 1x or 720x720 at 2x, readable at 132px display size, only 2–3 primary shapes, generous transparent padding, no cast background rectangle.

Negative constraints: no sad character, no broken data gag, no skull, no warning explosion, no excessive glow, no fire, no runes, no ornate frame, no readable text, no existing game faction symbol, no photorealism, no antialiased vector style.
```

## Architecture

### Component Design

```text
prototype/orc_citadel/
├── investigation_job.py       add REPORT stage; pass artifact to complete
├── investigation_report.py    ReportDraft schema/validator + generator + renderer
├── investigation_store.py     artifact table, atomic complete, list, artifact reads
└── viewer.py                  list/metadata/html endpoints + headers

design-system/ui/
└── reports.mjs                props-only list card, report meta/audit panels

design-system/mockups/
└── src/pages/
    ├── campaign-ledger.mjs
    └── investigation-report.mjs

frontend/
├── reports.html
└── src/pages/reports/main.jsx  list/poll/select/iframe; no report HTML parsing
```

### Data Flow

1. Worker computes deterministic investigation result and current optional LLM synthesis.
2. Audit removes/unmarks unsupported statements.
3. Report generator receives only audited result + safe metadata.
4. Connected LLM produces strict ReportDraft; validator + Audit recheck it. Failure selects fallback.
5. Deterministic renderer escapes values and generates script-free HTML + hashes.
6. Store atomically inserts artifact and completes investigation/job.
7. `/reports` fetches metadata list; selected ready item loads `/report.html` in sandbox.
8. User follows the trusted outer-page control for full view; evidence links point to existing Witnesses/War Table routes.

### Integration Points

- `InvestigationStore.complete_with_report_artifact()` is the sole successful completion boundary; no alternate `complete()` or second “after commit” hook remains after cutover.
- `llm_providers.build_llm_client()` supplies the linked LLM through existing provider config.
- `synthesis.Audit` remains the provenance authority and is reused after ReportDraft generation.
- `viewer_static` gains only the new Vite entry through current `/app/*` path; dynamic report HTML is served by `viewer.py`, not written into `frontend/dist`.
- `shell.mjs` keeps the 8-space arrays unchanged. Council/Gate add ordinary links to `/reports`.

## Error Handling

| Scenario | Handling Strategy | User Impact |
|---|---|---|
| LLM unavailable/timeout/provider error | audited deterministic fallback; reason persisted | 리포트는 생성되며 “deterministic fallback” 배지 |
| LLM invalid schema/unknown claim | draft 전체 폐기 + fallback | 지어낸 문장 유입 없음 |
| ReportDraft Audit rejection | draft 전체 폐기 + fallback, blocked count | 리포트 생성 성공, 감사 메타에 차단 수 |
| Renderer size/encoding failure | complete transaction 미실행, job/investigation failed | 목록에 failed; HTML 없음 |
| DB insert/update failure | transaction rollback | 부분 artifact 없음, 503/failed |
| Cancel during REPORT | stage boundary cancel wins; completion 거부 | cancelled, HTML 없음 |
| Unknown investigation | JSON/HTML 404 + not-found state | 다른 오류와 구분 |
| Not completed | 409 + Retry-After for queued/running | preview가 진행 상태 표시 |
| Post-cutover completed row without artifact | 500 invariant error + 운영 로그 | 가짜 빈 report 금지 |
| Legacy completed row without artifact | `legacy_json_only`, HTML 404, 기존 JSON link | backfill을 가장하지 않음 |
| Browser blocks iframe/CSP | outer page에 “새 창에서 열기” 제공 | 리포트 접근 경로 유지 |

## Security Considerations
- 사용자 question/scope, canonical statement surface, claim ID는 모두 untrusted input으로 취급한다. LLM 출력은 ref/schema 검증 전에는 어떤 렌더링 문맥에도 들어가지 않는다.
- LLM은 마크업을 쓰지 않는다. `ReportDraft` 자유 문자열도 renderer escape 전에는 HTML 문맥에 들어가지 않는다.
- ID는 URL percent-encoding 후 allowlisted internal route에만 연결한다. 외부 source URL은 최초 범위에서 artifact에 직접 링크하지 않고 Hall of Witnesses provenance를 경유한다.
- CSP와 iframe sandbox는 defense in depth다. HTML이 deterministic renderer를 통과했다는 사실만으로 sandbox를 생략하지 않는다.
- DB/API 로그에 HTML 본문, API key, raw prompt, chain-of-thought를 남기지 않는다.
- owner/auth가 도입되면 design 09의 investigation resource ownership 규칙을 목록·artifact endpoint에 동일 적용한다. 현재 prototype의 loopback/SSH 접근 모델은 변경하지 않는다.

## Performance Considerations

- 목록 query는 artifact metadata만 join하고 `html_bytes` column을 SELECT하지 않는다.
- `(created_at DESC, investigation_id DESC)` 및 `status, created_at DESC` index를 둔다.
- HTML endpoint는 bytes를 한 번 읽어 전송하고 ETag 304를 지원한다. artifact 최대 1 MiB.
- iframe은 선택된 ready item 하나만 `loading="lazy"`로 로드한다.
- polling은 terminal item이 하나라도 아니라 “현재 화면에 queued/running item이 있을 때”만 1–5초 backoff로 수행한다.

## Traceability

| Requirement | Specification | Primary Verification |
|---|---|---|
| FR-1 | TS-1, TS-2 | worker completion/fallback/cancel/lease regression |
| FR-2 | TS-1, TS-4 | transaction rollback, uniqueness, hash verification |
| FR-3 | TS-5, TS-6 | list cursor/filter API + browser master-detail scenario |
| FR-4 | TS-3, TS-5, TS-7 | header/CSP/ETag tests + sandbox/browser/print check |
| FR-5 | TS-6, TS-7 | SSG build + actual Chromium visual check |
| FR-6 | TS-8 | prompt checklist against DESIGN.md and asset policy |

## Open Questions

- 없음. 최초 버전의 주요 선택은 아래 Clarification Log로 고정한다. 사용자 리뷰에서 변경되면 requirements부터 cascade한다.

## Clarification Log

| # | Question | Answer | Date |
|---|---|---|---|
| 1 | LLM이 raw HTML을 생성하는가? | 아니오. strict ReportDraft JSON만 생성하고 stdlib renderer가 HTML을 만든다. | 2026-09-20 |
| 2 | LLM 실패 시 조사를 실패시키는가? | 아니오. audited deterministic fallback HTML을 저장하고 실패 사유를 메타데이터에 남긴다. | 2026-09-20 |
| 3 | 조사 완료와 HTML 저장 사이의 부분 상태를 허용하는가? | 아니오. artifact insert와 job/investigation 완료를 한 transaction으로 확정한다. | 2026-09-20 |
| 4 | `/reports`는 아홉 번째 공간인가? | 아니오. Council utility page이며 기존 8공간 IA를 유지한다. | 2026-09-20 |
| 5 | artifact를 파일 시스템에 쓰는가? | 아니오. PostgreSQL `bytea` + hash로 영속하고 HTTP에서 inline 제공한다. | 2026-09-20 |
| 6 | generated image가 오기 전 mockup은 어떻게 보이는가? | 깨진 placeholder 없이 flat masthead와 icon 없는 EmptyState를 사용한다. | 2026-09-20 |
