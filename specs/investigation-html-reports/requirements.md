# Requirements: 조사 완료 HTML 리포트와 Campaign Ledger

> Created: 2026-09-20
> Status: Stable
> Ticket: N/A
> Difficulty: high
> Pipeline: full
> Source: manual

## Overview

현재 Orc Citadel의 durable investigation은 `queued → running → completed|failed|cancelled` 수명주기와 JSONB `report`/`audit_trace` 영속을 제공하지만, 완료된 조사들을 한곳에서 찾아보는 목록 화면과 사람이 읽고 공유할 수 있는 HTML 산출물이 없다. Council Chamber는 방금 실행한 조사만 메모리 상태로 표시하므로 페이지를 떠난 뒤 과거 결과를 다시 찾기 어렵다.

이 기능은 성공한 조사의 감사 완료 결과를 입력으로 **LLM 보조 구성 + 결정적 HTML 렌더링**을 수행하고, 결과를 PostgreSQL에 원자적으로 저장한다. 별도 `/reports` 페이지인 **Campaign Ledger · Investigation Reports**에서 전체 조사 상태를 나열하고 완료 리포트를 탐색·열람한다. 이 페이지는 Council의 영속 기록 도구이며 기존 8개 Citadel 공간에 아홉 번째 공간을 추가하지 않는다.

## Goals

- [x] G1 cutover 이후 성공한 모든 조사에 재시작 후에도 동일하게 조회 가능한 HTML 리포트 1개를 자동 생성한다.
- [x] G2 LLM이 문장 순서와 섹션을 구성하더라도 검증된 claim/provenance 밖의 사실을 도입하지 못하게 한다.
- [x] G3 조사 목록에서 queued/running/completed/failed/cancelled 상태와 리포트 가용 여부를 즉시 파악한다.
- [x] G4 완료 리포트를 앱 안에서 안전하게 읽고 독립 문서로 열 수 있게 한다.
- [x] G5 Citadel Nightwatch 디자인과 evidence-first 원칙을 반영한 페이지·리포트 목업 및 이미지 생성 프롬프트를 제공한다.

## Functional Requirements

### FR-1: 조사 완료 시 HTML 리포트 자동 생성

- **Description**: worker가 `AUDIT`를 통과한 뒤 `REPORT` 단계를 실행한다. 연결된 LLM은 감사된 JSON report만 입력받아 서술 구조를 생성하고, 애플리케이션의 결정적 renderer가 값을 escape하여 HTML을 만든다. LLM은 raw HTML을 반환하지 않는다.
- **Acceptance Criteria**:
  - [x] 조사 생성 시 HTML report용 `report_generation_mode=llm_assisted`, template/schema version, prompt hash를 investigation 종합 `mode`와 별도 축으로 고정한다.
  - [x] 성공 경로의 step은 `PLAN → RUN → SYNTHESIZE → AUDIT → REPORT` 순서로 기록된다.
  - [x] HTML의 검증 가능한 문장은 허용된 `claim_ref`에 연결되고 Audit 재검증을 통과한 문장만 포함한다.
  - [x] LLM 미설정·timeout·비스키마·감사 실패 시 감사된 원본 JSON을 사용하는 결정적 fallback HTML을 생성하고 `generation_mode=deterministic_fallback` 및 오류 사유를 기록한다.
  - [x] `investigation.status=completed`, `job.status=succeeded`, JSON report/audit trace, HTML artifact 저장은 하나의 PostgreSQL transaction에서 함께 성공하거나 함께 rollback한다.
  - [x] 성공한 investigation 하나에는 활성 HTML artifact가 정확히 하나 존재한다.

### FR-2: 리포트 artifact 무결성·재현성 영속

- **Description**: HTML 본문과 생성 메타데이터를 investigation 운영 저장소에 별도 record로 보존한다.
- **Acceptance Criteria**:
  - [x] artifact는 `artifact_id`, `investigation_id`, HTML, `content_hash`, `source_report_hash`, template/schema version, report 생성 방식, provider/model/prompt hash, usage, 생성 시각, version tuple을 가진다.
  - [x] HTML/원본 report의 SHA-256이 저장되어 조회·재현 결과를 비교할 수 있다.
  - [x] 늦게 도착한 stale worker, 취소 요청을 받은 worker, 중복 claim은 기존 완료 artifact를 덮어쓰지 못한다.
  - [x] graph와 curated zone에는 쓰지 않는다. 영속 범위는 investigation 운영 메타데이터와 report artifact뿐이다.

### FR-3: 조사 목록 API와 Campaign Ledger 페이지

- **Description**: `/reports`는 전체 durable investigation을 최신순으로 나열하고 상태·조사 mode·report 생성 mode·coverage·종료 사유·리포트 가용 여부를 보여준다.
- **Acceptance Criteria**:
  - [x] `GET /api/investigations?status=&cursor=&limit=`가 고정 정렬과 opaque cursor로 페이지를 반환한다.
  - [x] 목록 item은 question, subject, status, 조사 mode, coverage, termination, created/completed timestamps, artifact 요약과 JSON/HTML link를 포함한다.
  - [x] 기본 화면은 최근 조사와 첫 선택 가능한 item을 표시하며 URL `?investigation=<inv-id>`로 선택 상태를 복원한다.
  - [x] queued/running item이 존재할 때만 `Retry-After`에 맞춰 폴링하고 terminal 상태에서는 중단한다.
  - [x] 상태 필터는 전체/진행 중/완료/실패·취소를 제공하며 데이터가 없는 상태와 API 실패를 서로 다른 화면으로 표시한다.

### FR-4: 안전한 리포트 열람

- **Description**: 선택된 완료 리포트는 Campaign Ledger의 viewer에서 읽거나 독립 문서로 연다.
- **Acceptance Criteria**:
  - [x] `GET /api/investigations/{id}/report.html`은 `text/html; charset=utf-8`, CSP, `ETag`, `X-Content-Type-Options: nosniff`를 반환한다.
  - [x] 앱 내 viewer는 HTML을 sandboxed iframe으로 격리하며 script/form/top-navigation 권한을 부여하지 않는다.
  - [x] 리포트에는 조사 질문·범위·결론·다차원 confidence·핵심 문장·지지/반박 근거·독립성·open questions·timeline·방법론/Audit·버전 tuple이 포함된다.
  - [x] `fact`/`asserted` 문장에는 evidence 탐색 링크가 있고 `prediction`/`opinion`은 명시 라벨을 가진다.
  - [x] 존재하지 않는 ID, 미완료 조사, artifact 저장소 장애를 각각 404, 409, 503으로 구분한다.

### FR-5: 페이지 콘셉트·목업

- **Description**: 기존 Astryx SSG와 `design-system/ui` 토큰 규약으로 Campaign Ledger와 HTML Report 두 정적 목업을 만든다.
- **Acceptance Criteria**:
  - [x] `docs/mockups/campaign-ledger.html`은 조사 목록, 상태 필터, 선택 리포트 preview, metadata/action header와 대표 상태를 보여준다.
  - [x] `docs/mockups/investigation-report.html`은 실제 artifact의 문서 정보구조와 print layout을 보여준다.
  - [x] 두 목업은 클라이언트 JavaScript 0, 외부 CDN 0, Astryx/theme-citadel 토큰 사용 규약을 지킨다.
  - [x] 데스크톱 2열 master-detail과 모바일 list→detail 선형 탐색 순서가 설계 문서에 명시된다.

### FR-6: 배너·not-found 이미지 생성 프롬프트

- **Description**: 향후 생성할 Campaign Ledger banner와 report not-found spot illustration의 복사 가능한 프롬프트를 설계 문서에 포함한다.
- **Acceptance Criteria**:
  - [x] banner prompt는 `campaign-ledger-hero.png`, 1920×720 불투명 PNG, 상단 오버레이 여백과 Citadel Nightwatch 팔레트를 명시한다.
  - [x] not-found prompt는 `empty-report-not-found.png`, 약 360px 투명 PNG, 작은 크기에서 읽히는 2–3개 형태를 명시한다.
  - [x] 두 prompt 모두 기존 IP 모사 금지, 과도한 녹색/불꽃/룬/장식 프레임 금지, 데이터 중심의 절제된 톤을 포함한다.
  - [x] 자산이 아직 없을 때 목업·앱은 깨진 이미지 대신 정직한 무이미지 EmptyState를 사용한다.

## Non-Functional Requirements

- **Security**: LLM raw HTML 저장 금지. 모든 문자열 HTML escape. `href`는 내부 allowlist만 허용. script/event handler/form/remote resource 금지. iframe sandbox + CSP 이중 방어.
- **Evidence integrity**: 검증 가능한 문장 provenance 연결률 1.0. Audit 미통과 문장은 제거하고 차단 수를 artifact metadata에 기록한다.
- **Reliability**: LLM 실패가 조사 결과 유실로 이어지지 않는다. 결정적 fallback으로 성공 artifact를 보장하며 실패 원인은 숨기지 않는다.
- **Idempotency**: investigation당 artifact 1개. worker lease/claim token과 transaction 경계를 재사용해 중복 생성·late completion을 막는다.
- **Performance**: 목록 기본 `limit=25`, 최대 100. HTML 최대 1 MiB, iframe lazy load. 목록 응답에 HTML 본문을 포함하지 않는다.
- **Accessibility**: WCAG AA, 상태는 색+텍스트/아이콘 병기, semantic heading/table, iframe title, 키보드 포커스, `prefers-reduced-motion`, print 대비 보장.
- **Offline**: 외부 CDN·remote font·remote image 없음. HTML은 inline CSS와 텍스트 중심으로 독립 열람 가능해야 한다.
- **Observability**: REPORT 단계 latency, LLM/fallback mode, token usage, 차단 문장 수, artifact bytes/hash를 correlation_id로 추적한다. chain-of-thought는 저장하지 않는다.

## Constraints

- 기존 `/api/investigations/{id}/report` JSON 계약은 유지한다.
- 기존 investigation `mode=deterministic|llm`은 조사 종합 방식이며 HTML report 생성 방식과 별도 축이다.
- 기존 8공간 IA를 유지한다. `/reports`는 Council utility이고 primary/secondary space 수를 변경하지 않는다.
- runtime은 Python stdlib HTTP server + 현행 PostgreSQL client 구조를 유지한다. 신규 queue·template engine·sanitizer 의존성을 추가하지 않는다.
- 프런트는 Vite MPA, 목업은 no-JSX SSG, 공용 UI는 props-only 규약을 따른다.
- confidence는 단일 게이지로 표현하지 않고 값·근거 수·독립 출처 수·basis를 함께 표시한다.

## Out of Scope

- 조사 엔진의 신규 외부 수집, graph/curated mutation, 지속 관찰 Campaign.
- 사용자가 HTML/CSS template을 편집하는 기능.
- PDF/DOCX 변환, 이메일 전송, public share URL, 다국어 번역.
- artifact 수정 이력·다중 버전 재생성 UI. 최초 버전은 investigation당 불변 artifact 1개다.
- cutover 이전 `completed` investigation의 HTML backfill. 기존 행은 `artifact=null`인 legacy JSON-only 기록으로 정직하게 표시한다.
- 리포트 삭제·보존 기간 정책과 tenant/auth 체계 신설.
- LLM chain-of-thought·비공개 reasoning 저장 또는 표시.

## References

- [docs/design/07-llm-and-agents.md](../../docs/design/07-llm-and-agents.md) — Synthesis/Audit, evidence-first, prompt/model versioning
- [docs/design/09-api.md](../../docs/design/09-api.md) — Investigation list/report, Report schema, Job pattern
- [docs/design/03-storage-and-data-model.md](../../docs/design/03-storage-and-data-model.md) — durable investigation metadata, provenance, idempotency
- [DESIGN.md](../../DESIGN.md) — Citadel Nightwatch design SSOT
- [docs/mockups/illustration-prompts.md](../../docs/mockups/illustration-prompts.md) — illustration prompt house style
- [specs/ui-overhaul-astryx/specs.md](../ui-overhaul-astryx/specs.md) — Vite MPA, shared UI, mockup-first conventions
