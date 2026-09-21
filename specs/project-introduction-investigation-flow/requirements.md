# Requirements: 비개발자용 프로젝트 소개 및 조사 흐름 HTML 페이지

> Created: 2026-09-20
> Updated: 2026-09-21
> Status: Stable
> Ticket: N/A
> Difficulty: high
> Pipeline: full
> Source: manual

## Overview

Orc Citadel의 현재 화면은 조사·증거·그래프 개념을 이미 아는 사용자를 전제로 한다. 처음 방문한 비개발자는 “무엇을 하는 프로젝트인지”, “질문을 입력하면 어떤 과정을 거치는지”, “결론을 왜 믿거나 의심해야 하는지”, “현재 구현과 앞으로 추가될 리포트가 무엇인지”를 한 번에 파악하기 어렵다.

이 기능은 별도 HTML 페이지 **Citadel Field Guide · 프로젝트 안내**를 추가한다. 페이지는 Orc Citadel을 “문서를 모아 답을 생성하는 챗봇”이 아니라, 원문·주장·반증·변화를 시간과 출처 계보로 연결하는 **Temporal Evidence Intelligence 실험 서비스**로 설명한다. 조사 지시부터 현재 JSON 조사 결과와 감사 경로, 향후 HTML 리포트·Campaign Ledger까지를 비개발자용 시각 흐름으로 보여준다.

서비스가 public product가 아닌 실험 환경이라는 점을 숨기지 않는다. 운영 도구는 설명을 보강하는 선택 링크로 제공하되, 링크나 도구가 없어도 본문은 완전히 이해되어야 한다. 현재 구현, 실험 기능, 계획된 기능을 시각적으로 명확히 구분한다.

## Goals

- [x] G1 비개발자가 3분 안에 프로젝트의 목적, 입력, 조사 방식, 결과물을 설명할 수 있게 한다.
- [x] G2 조사 지시부터 검증·감사된 결과와 향후 HTML 리포트까지의 흐름을 한 화면의 시각 서사로 이해시킨다.
- [x] G3 현재 제공 기능과 실험·계획 기능을 혼동 없이 구분해 과장된 제품 인상을 막는다.
- [x] G4 Neo4j, Grafana, DuckDB UI 같은 실험 도구를 맥락과 주의사항이 있는 선택 링크로 제공한다.
- [x] G5 기존 Citadel Nightwatch 디자인과 접근성 규약을 따르는 HTML 목업과 배너 이미지 생성 프롬프트를 제공한다.

## Functional Requirements

### FR-1: 비개발자용 프로젝트 소개

- **Description**: 별도 `/about` 페이지에서 전문 용어보다 사용자 관점의 문제·과정·결과를 먼저 설명한다.
- **Acceptance Criteria**:
  - [ ] 첫 화면에 “무엇을 해결하는가”, “일반 검색/챗봇과 무엇이 다른가”, “무엇을 결과로 남기는가”가 각각 한 문장으로 보인다.
  - [ ] 핵심 결과를 `조사 결과 + Evidence Graph + 원문까지의 Provenance` 3요소로 설명한다.
  - [ ] 세계관 명칭과 기술 용어를 함께 표기하되, 처음 등장할 때 평이한 한국어 설명을 병기한다.
  - [ ] hash, JSONB, claim_ref, worker lease 같은 구현 용어는 주요 본문에 노출하지 않고 선택적 상세 설명으로만 둔다.
  - [ ] 이 서비스가 실험용이며 법률·의료·투자 결정을 자동으로 대신하지 않는다는 한계를 명시한다.

### FR-2: 조사 지시부터 결과까지의 시각 흐름

- **Description**: “데이터가 준비되는 배경 흐름”과 “사용자가 조사를 지시한 뒤의 전경 흐름”을 분리해 설명한다.
- **Acceptance Criteria**:
  - [ ] 배경 흐름은 `외부 자료 → 원문 보존 → 정규화·중복 보정 → 주장·근거 연결 → Evidence Graph` 순서로 보인다.
  - [ ] 사용자 흐름은 `자연어 조사 지시 → PLAN → RUN(기존 근거 탐색·반증·공백 확인) → SYNTHESIZE → AUDIT → 현재 조사 결과` 순서로 보인다.
  - [ ] 각 자료 처리·조사 단계에 현재 기술과 역할을 연결해 `MinIO/Parquet`, `DuckDB`, `PostgreSQL`, `OpenSearch`, `Neo4j`, `Python worker/FastAPI`, `Grafana`가 무엇을 저장·계산·조회하는지 평이한 문장으로 설명한다.
  - [ ] `Apache Iceberg`, `S3`, `Kafka/Redpanda`, `Ray/Spark`는 현재 사용 기술로 표현하지 않고, 측정된 규모·처리량 병목이 생길 때 검토하는 `현재 미사용 · 확장 후보`로 구분한다.
  - [ ] 현재 durable investigation이 live web을 새로 수집하지 않고 Citadel에 이미 축적된 근거를 read-only로 조사한다는 사실을 흐름 안에 명시한다.
  - [ ] `queued → running → completed|failed|cancelled` 조사 상태를 사용자 언어와 함께 보여준다.
  - [ ] 결론에서 원문까지 현재 제공되는 `결과 문장 → claim → supports evidence → source span → 원문` 경로를 별도 시각화하고, `contradicts` 원문 왕복은 facade 미확장, `uncertain`/`superseded`는 현재 trail 미제공이라고 정직하게 구분한다.
  - [ ] confidence는 진실 확률로 표현하지 않고 값·근거 수·독립 출처 수·계산 근거·미해결 질문을 함께 보여준다.

### FR-3: 현재·실험·계획 기능의 정직한 구분

- **Description**: 제품 비전과 현재 prototype의 범위를 같은 색의 완성 기능처럼 보이지 않게 한다.
- **Acceptance Criteria**:
  - [ ] 모든 주요 기능 블록은 `현재 제공`, `실험`, `계획`, `제품 방향` 중 하나의 텍스트 배지를 가진다.
  - [ ] 현재 제공에는 durable async 조사, `PLAN`/`RUN`/`SYNTHESIZE`/`AUDIT` step marker, JSON report/audit trace, War Table·Witnesses 탐색을 포함한다. marker는 현재 worker의 독립 실행 단계가 아니라 `RUN` 전후에 남는 진행·감사 기록임을 설명한다.
  - [ ] 향후 리포트에는 계획 중인 `REPORT` 단계, 결정적 HTML artifact, Campaign Ledger를 `계획 · 미구현`으로 표시하고, 별도 설계 문서 상태 `Review`는 보조 정보로만 표기한다.
  - [ ] 지속 관찰 Campaign과 자동 Signal Spire 알림은 현재 조사 결과와 구분된 `제품 방향`으로 표시한다.
  - [ ] HTML 리포트가 아직 구현되지 않은 상태에서 다운로드·과거 리포트 목록이 현재 기능인 것처럼 표현하지 않는다.
  - [ ] 예시 질문·결론·수치는 모두 `설명용 예시 · 실제 조사 결과 아님`으로 표시한다.

### FR-4: 실험 도구 링크

- **Description**: 설명 중간의 관련 문맥에서 실험 도구로 이동할 수 있게 하되, 운영 도구를 제품 이해의 필수 경로로 만들지 않는다.
- **Acceptance Criteria**:
  - [ ] `/watchtower`를 “실험 시스템 상태 보기”의 기본 진입점으로 제공한다.
  - [ ] Grafana와 DuckDB UI는 read-only 성격과 로컬/SSH tunnel 필요 조건을 설명한 선택 링크로 제공할 수 있다.
  - [ ] Neo4j Browser, MinIO Console, OpenSearch 진단 링크는 `고급 실험 도구`로 강등하고 인증·쓰기 가능성·데이터 부재 가능성을 경고한다.
  - [ ] PostgreSQL, Neo4j Bolt, MinIO S3 API 같은 비브라우저 엔드포인트는 CTA로 제공하지 않는다.
  - [ ] 런타임은 기존 `/api/watchtower`의 component reachability를 재사용하며 `reachable=false`에는 클릭 가능한 링크를 만들지 않는다.
  - [ ] `reachable=true`는 “viewer에서 TCP 연결됨”으로만 설명하며 앱 정상·데이터 준비·브라우저 tunnel 개통을 보장한다고 표현하지 않는다.
  - [ ] API 실패 또는 정적 목업에서는 직접 도구 링크를 비활성화하고 `/watchtower` 안내만 유지한다.
  - [ ] 새 창 링크는 의미 있는 이름과 `target="_blank" rel="noopener noreferrer"`를 사용하고 자격증명을 URL·본문에 포함하지 않는다.

### FR-5: HTML 페이지와 시각화

- **Description**: 기존 Vite MPA와 Citadel Nightwatch 디자인 시스템을 재사용해 정보 중심 HTML 페이지를 만든다.
- **Acceptance Criteria**:
  - [ ] production route는 `/about`이며 기존 8개 Citadel 공간에 아홉 번째 공간으로 추가하지 않는다.
  - [ ] Citadel Gate의 일반 링크와 목업 인덱스 `참조` 영역에서 진입할 수 있다.
  - [ ] 데스크톱 페이지에는 hero, 핵심 가치 3요소, 예시 조사 지시, 2-lane 흐름도, 단계별 기술 활용 지도, provenance 경로, 결과 3요소, 현재/향후 비교, 실험 도구, 한계·CTA가 이 순서로 나타난다.
  - [ ] 시각 흐름은 DOM의 순서 있는 목록과 텍스트만으로도 이해되며 색·이미지·connector가 없어도 의미가 유지된다.
  - [ ] 720px 이하에서는 좌우 흐름을 세로 stepper로 바꾸고 DOM 읽기 순서를 유지한다.
  - [ ] decorative animation은 필수가 아니며, 추가할 경우 `prefers-reduced-motion`에서 완전히 정지한다.
  - [ ] 외부 CDN·remote font를 쓰지 않고 기존 로컬 자산과 theme token만 사용한다.

### FR-6: 페이지 목업과 배너 프롬프트

- **Description**: 구현 전에 검토 가능한 정적 HTML 목업과 향후 배너 자산 생성을 위한 복사 가능한 프롬프트를 사양에 포함한다.
- **Acceptance Criteria**:
  - [ ] 목업 정본은 `design-system/mockups/src/pages/project-introduction.mjs`, 생성물은 `docs/mockups/project-introduction.html`이다.
  - [ ] 목업은 client JavaScript 0, 외부 request 0이며 모든 live 상태를 `DEMO · 설명용 상태`로 표기한다.
  - [ ] desktop 1440×1000, mobile 390×844, 200% zoom에서 흐름·링크·텍스트가 잘리지 않고 가로 overflow가 없다.
  - [ ] 배너 파일명은 `project-introduction-hero.png`, 최종 규격은 1920×720 opaque sRGB PNG다.
  - [ ] 배너 prompt는 조사 지시 → 근거 연결 → 감사 → 리포트의 진행을 하나의 장면으로 표현하고 제목/CTA 안전 영역과 mobile center crop을 명시한다.
  - [ ] 배너는 기존 게임 IP, 생성 텍스트, UI chrome, 과도한 녹색 광원·불꽃·룬·장식 프레임을 포함하지 않는다.
  - [ ] 이미지가 없을 때는 깨진 URL 대신 기존 132px flat masthead를 사용한다.

## Non-Functional Requirements

- **Clarity**: 핵심 본문은 한국어 중학생 수준의 짧은 문장과 1문단 3문장 이하를 기본으로 한다. 기술 용어에는 첫 등장 시 평이한 설명을 붙인다.
- **Accuracy**: 현재 코드와 계획 문서를 구분한다. 구현되지 않은 기능은 반드시 `계획` 또는 `제품 방향`으로 표시한다.
- **Accessibility**: WCAG 2.2 AA, 일반 텍스트 대비 4.5:1, semantic heading/nav/list, 키보드 탐색, 200% zoom reflow, 색 이외의 상태 라벨, 의미 있는 링크명을 충족한다.
- **Performance**: hero를 제외한 초기 HTML+JS+CSS feature 증분은 150 KiB gzip 이하를 목표로 하고, hero는 responsive image와 lazy/eager 정책을 분리한다.
- **Resilience**: `/api/watchtower` 또는 실험 도구가 없어도 핵심 소개·흐름·한계 설명은 그대로 표시된다.
- **Security**: 자격증명·내부 IP·remote host를 번들에 넣지 않는다. 직접 링크는 런타임 host로 조립하며 사용자 입력 HTML을 렌더링하지 않는다.
- **Maintainability**: 목업과 production이 공유하는 표현 컴포넌트는 `design-system/ui/`의 props-only no-JSX 패턴으로 한 벌만 유지한다.

## Constraints

- 기존 `PRIMARY_SPACES`, `SECONDARY_SPACES`, `SPACES` 8공간 배열을 변경하지 않는다.
- 기존 Vite MPA, Astryx SSG, `theme-citadel`, committed `frontend/dist/` 구조를 유지한다.
- `docs/mockups/*.html`과 `docs/mockups/astryx.css`는 생성물이므로 직접 편집하지 않는다.
- emerald는 검증된 연결과 선택 경로에만 사용하고 일반 장식색으로 남용하지 않는다.
- current prototype의 조사 실행은 기존 evidence를 read-only로 사용한다. live-web 수집·graph/curated mutation을 현재 기능으로 설명하지 않는다.
- static mockup은 `/api/watchtower`를 실제 probe하지 않는다.

## Out of Scope

- investigation worker에 `REPORT` stage를 구현하는 작업.
- HTML report artifact, PostgreSQL table, `/reports` Campaign Ledger, 다운로드 API 구현.
- 수집·추출·entity resolution·graph mutation 로직 변경.
- 신규 인증, tenant, public share, SEO/marketing analytics.
- Neo4j·Grafana·DuckDB UI 등 외부 도구의 설치·권한·가용성 보장.
- 기존 8개 제품 공간의 IA 재설계.

## References

- [README.md](../../README.md) — 프로젝트 정체성과 현재 아키텍처
- [docs/blueprint.md](../../docs/blueprint.md) — 사용자 경험, 제품 흐름, evidence-first 원칙
- [docs/design/07-llm-and-agents.md](../../docs/design/07-llm-and-agents.md) — 조사 state machine과 현재 durable read-only 구현
- [docs/design/09-api.md](../../docs/design/09-api.md) — investigation lifecycle, report, provenance 계약
- [docs/operating/data-browsing.md](../../docs/operating/data-browsing.md) — 실험 도구 링크와 tunnel 제약
- [DESIGN.md](../../DESIGN.md) — Citadel Nightwatch 디자인 SSOT
- [specs/investigation-html-reports](../investigation-html-reports/) — 향후 HTML 리포트·Campaign Ledger 설계(Review, 미구현)
- [specs/ui-overhaul-astryx/specs.md](../ui-overhaul-astryx/specs.md) — Vite MPA, shared UI, mockup-first 규약
