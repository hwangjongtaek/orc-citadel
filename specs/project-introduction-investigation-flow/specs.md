# Specs: 비개발자용 프로젝트 소개 및 조사 흐름 HTML 페이지

> Created: 2026-09-20
> Updated: 2026-09-21
> Status: Stable
> Requirements: [requirements.md](./requirements.md)

## Overview

`/about`에 별도 HTML 소개 페이지 **Citadel Field Guide · 프로젝트 안내**를 추가한다. 이 페이지는 운영 화면이나 아홉 번째 Citadel 공간이 아니라, 비개발자가 Orc Citadel의 목적과 조사 흐름을 이해하는 문서형 utility page다.

핵심 설계는 두 흐름을 분리하는 것이다.

1. **Evidence preparation · 근거 준비** — 외부 자료가 수집·보존·정규화·중복 보정되어 Evidence Graph가 되는 배경 파이프라인.
2. **Investigation · 조사 실행** — 사용자의 자연어 지시를 현재 durable worker가 기존 근거 위에서 `PLAN → RUN → SYNTHESIZE → AUDIT`하는 전경 파이프라인.

현재 JSON report/audit trace와 향후 `REPORT → deterministic HTML artifact → Campaign Ledger`를 같은 선 위에 놓되, 향후 구간에는 product availability `계획 · 미구현`과 별도 설계 문서 상태 `Review`를 구분해 표시한다. 전체 설명은 정적 콘텐츠로 완결되고, `/api/watchtower`는 선택적 실험 도구 링크의 도달성 표시만 점진적으로 보강한다.

## Technical Specifications

### TS-1: 페이지 정체성·route·정보 구조 (from FR-1, FR-5)

- **World / technical name**: `Citadel Field Guide · 프로젝트 안내` / `Project Introduction`.
- **Production route**: `/about`.
- **Mockup**: `docs/mockups/project-introduction.html`.
- **IA position**:
  - `PRIMARY_SPACES`, `SECONDARY_SPACES`, `SPACES`에는 추가하지 않는다.
  - Citadel Gate의 브랜드/소개 영역에 `프로젝트 안내` 일반 링크를 둔다.
  - `MOCKUP_URLS.about='./project-introduction.html'`, `APP_URLS.about='/about'`를 추가하되 8공간 `APP_ROUTES`에는 넣지 않는다.
  - 목업 인덱스의 `참조` 영역에 별도 카드를 둔다.
  - 공용 `shell()`에 optional utility contract(`skipTarget`, `mastheadContent`, `utilityNav`)를 추가한다. 기존 호출의 기본 markup은 유지한다.
  - 소개 페이지는 `utilityNav`로 검색·Signal chip·8공간 tab row를 대체한 간결한 `Citadel Gate로 돌아가기` / `Council에서 조사 시작` nav를 사용한다. 좁은 화면에서 기존 고정 300px 검색창이 overflow를 만들지 않는다.
- **Page role**: 설명·온보딩 문서다. 검색·필터·작업 queue·데이터 편집 기능을 추가하지 않는다.
- **Primary CTA**: `조사 지시 예시 보기` → 페이지 내부 `#investigation-flow`.
- **Secondary CTA**: `Council Chamber에서 조사 시작` → `/council`.
- **Experimental CTA**: `실험 시스템 상태 보기` → `/watchtower`.

#### Section order

1. Hero — 프로젝트 정의 + `현재 제공`·`실험용 서비스` 배지 + 아래 3개 first-screen 문장.
2. Why — `결론만`, `근거만`, `시간 변화 없음`의 기존 문제와 Citadel의 해법 3개(`현재 제공`).
3. Example Directive — 자연어 조사 지시와 scope(`현재 제공`, 예시 disclaimer).
4. Two-lane Flow — 근거 준비 lane + 조사 실행 lane(`현재 제공`과 future boundary).
5. Technology Map — 단계별 현재 기술·역할과 확장 후보(`현재 제공`/`실험`/`현재 미사용 · 확장 후보`).
6. Evidence-first Trail — 결과 문장에서 원문까지의 5-step 역추적(`현재 제공`; audit gap 병기).
7. Result Triad — Report + War Table + Provenance, confidence와 open questions(`현재 제공`).
8. Now / Next — 현재·실험·계획·제품 방향 비교.
9. Experimental Tools — Watchtower 우선, 선택적 dashboard links(`실험`).
10. Honesty Strip — `실험용 서비스`, `기존 evidence read-only`, `live web 아님`, `법률·의료·투자 결정을 자동으로 대신하지 않음`, CTA(`현재 제공`).

### TS-2: 비개발자용 콘텐츠 모델과 copy 규칙 (from FR-1, FR-3)

#### Hero copy

- **Eyebrow**: `Project Guide · 실험용 서비스`
- **Title**: `질문이 결론이 되기까지, 모든 근거를 남긴다.`
- **Lead**: `Orc Citadel은 여러 문서의 주장과 반증을 연결하고, 현재 결론을 원문까지 되짚게 하는 증거 조사 실험실입니다.`
- **First-screen sentence · 해결**: `흩어진 문서의 주장과 반증을 한눈에 비교하되, 원문을 잃지 않습니다.`
- **First-screen sentence · 차이**: `일반 검색과 챗봇이 답을 먼저 보여준다면, Orc Citadel은 답과 함께 반대 근거·독립 출처·변화 시점을 연결합니다.`
- **First-screen sentence · 결과**: `조사 결과, 관계를 보여주는 Evidence Graph, 원문까지 이어지는 Provenance를 남깁니다.`
- **Tagline**: `The Camp works. The Citadel remembers.`

#### Value triad

| Plain-language heading | Meaning | Technical term |
|---|---|---|
| 원문을 잃지 않는다 | 수집 시점의 문서와 정확한 인용 구간을 보존한다. | Immutable raw + source span |
| 같은 말의 복제를 증거 수로 세지 않는다 | 중복 기사와 파생 보도를 묶고 독립 출처를 따로 계산한다. | Dedup lineage + source independence |
| 시간에 따라 바뀐 주장도 남긴다 | 주장과 관계의 유효 시점·관찰 시점을 함께 기록한다. | Bitemporal Evidence Graph |

#### Example directive

> 2024년 이후 A사의 AI 가속기 공급망 다변화가 실제로 진행되었는지 조사하라. 공식 발표와 실제 계약·공시를 구분하고 반대 증거도 포함하라.
>
> `설명용 예시 · 실제 조사 결과 아님`

scope는 `기간`, `지역`, `출처 종류`, `조사 깊이` 네 칩으로만 설명한다. API field name은 상세 disclosure 안에서만 보여준다.

#### Vocabulary rules

- 첫 등장: `Evidence Graph · 주장과 근거의 관계 지도`처럼 세계관/기술어/평이한 뜻을 함께 쓴다.
- `Agent가 진실을 판단한다` 대신 `근거 공백과 반증을 찾는다`라고 쓴다.
- `confidence 61% 확률로 참` 대신 `현재 근거 구조를 0.61로 평가; 독립 출처 2개, coverage 63%`라고 쓴다.
- `live web 검색` 표현을 금지한다. 현재 조사는 `Citadel에 이미 축적된 근거를 읽는다`라고 쓴다.
- 현재 deterministic report는 audit가 연결 실패를 **표시**하지만 완료를 차단하거나 원문 문장을 제거하지 않는다. `감사에서 막았다`·`검증된 문장만 저장한다`는 표현을 금지한다.
- optional LLM 문장 보조는 audit trace의 verified whitelist만 사용하지만 결론·근거 계산은 바꾸지 않는다고 쓴다.
- 미측정·근거 없음·unknown subject는 `gap`, `미측정`, `근거 부족`으로 표시하고 성공색을 쓰지 않는다.

### TS-3: 2-lane 조사 흐름 시각화 (from FR-2, FR-5)

시각화는 canvas나 이미지 한 장이 아니라 semantic DOM으로 만든다. `FlowMap`은 두 개의 `<ol>`을 가진다. connector와 lane bridge는 CSS/SVG 장식이며 `aria-hidden="true"`; screen reader는 제목과 단계 목록만 읽어도 전체 순서를 이해한다.

#### Lane A — Evidence preparation · 조사 전부터 준비되는 근거

| Step | User-facing label | Explanation | Destination link | Status |
|---|---|---|---|---|
| A1 | 자료가 들어온다 | 허용된 출처에서 문서와 변경 사항을 수집한다. | `/watchtower` | 현재 제공 |
| A2 | 원문을 그대로 보존한다 | 나중에 같은 문장을 다시 확인할 수 있게 문서 버전을 남긴다. | `/archive` | 현재 제공 |
| A3 | 읽기 좋은 형식으로 정리하고 같은 문서를 묶는다 | 서로 다른 문서 형식을 비교 가능한 구조로 정리한 뒤, 복제 기사와 독립 취재를 구분한다. | `/archive` | 현재 제공 |
| A4 | 주장과 근거를 연결한다 | 현재 원문 왕복은 지지 근거를 제공한다. 반박 후보는 조사에 보이지만 Witnesses 원문 왕복은 아직 확장되지 않았다. | `/witnesses` | 현재 제공 · supports only |
| A5 | 시간축 관계 지도를 만든다 | 바뀐 주장도 지우지 않고 시점과 함께 남긴다. | `/table` | 현재 제공 |

lane header에는 `현재 제공`과 `백그라운드 파이프라인 · 조사 지시가 새 live-web 수집을 시작하지 않음`을 표시한다.

#### Lane B — Investigation · 사용자가 지시한 뒤

| Step | Lifecycle marker | Plain-language result | Status |
|---|---|---|---|
| B1 | Accepted / queued | 질문과 범위를 접수하고, 다시 시작해도 이어지는 조사 기록을 만든다. | 현재 제공 |
| B2 | PLAN | 질문을 확인할 하위 질문과 이미 아는 것·모르는 것으로 나눈 기록을 남긴다. | 현재 제공 |
| B3 | RUN | 이미 모아 둔 관계 지도와 문서 구절에서 근거·반증·공백을 한 번 확인한다. | 현재 제공 |
| B4 | SYNTHESIZE | 찾은 근거 범위에서 결론과 설명을 정리했다는 marker를 남긴다. | 현재 제공 |
| B5 | AUDIT | 사실로 읽힐 문장이 원문 구절까지 연결되는지 검사하고, 연결되지 않으면 감사 결과에 표시한다. | 현재 제공 |
| B6 | JSON result | 결론·문장·공백·반증·감사 결과를 조사 기록에 저장한다. | 현재 제공 |
| B7 | REPORT → deterministic HTML → Ledger | 감사 결과를 결정적 HTML 문서와 과거 조사 목록으로 제공한다. | 계획 · 미구현 (`Review` 설계) |
| B8 | Continuous Campaign | 새 근거가 들어오면 결론 변화를 기록하고 알린다. | 제품 방향 |

- `PLAN`/`RUN`은 `_execute_claimed` 호출 전에 기록되고, 현재 Planner·Runner·Synthesizer·Audit 계산은 하나의 `RUN` work unit 안에서 수행된다. `SYNTHESIZE`/`AUDIT` row는 계산이 끝난 뒤 회고 marker로 append된다. 따라서 네 marker를 독립 실행 stage나 실시간 sub-stage progress로 설명하지 않는다.
- B3는 `현재 prototype: 이미 모아 둔 근거 · 1회 read-only 확인` 상세 설명을 가진다.
- B5는 audit failure를 `blocked/unverified`로 기록하지만 deterministic path의 완료를 차단하거나 저장 문장을 제거하지 않는다고 상세 설명한다.
- B7은 dashed connector와 `계획 · 미구현` 배지를 사용한다. 보조 metadata로 별도 설계 상태 `Review`를 표시할 수 있지만 product availability와 섞지 않는다.
- lane bridge는 `B3 RUN이 A5 Evidence Graph와 A2–A4 저장 근거를 읽음` 한 곳만 강조한다.

#### Technology Map — 단계별 기술 활용

기술 이름을 제품 기능처럼 나열하지 않고, `어느 단계에서 무엇을 맡는가`와 `정본인지 파생물인지`를 함께 설명한다.

| Flow stage | Technology | Role | Availability / truth boundary |
|---|---|---|---|
| 수집·원본 보존 | Python connectors, source별 Parquet shard, optional MinIO backend | 허용된 자료와 fetch metadata를 content-hash 기준으로 불변 보존 | 현재 사용; MinIO는 선택 backend이며 raw 기본 경로를 과장하지 않음 |
| 정규화·중복 보정 | Python, Parquet, DuckDB | 문장·source span·dedup lineage 생성, Parquet 직접 분석 | 현재 사용 |
| 작업 큐·감사 원장 | PostgreSQL | investigation/job/step, `SKIP LOCKED` queue, append-only graph mutation log | 현재 사용 · SoT |
| 검색 후보 | OpenSearch | segment/claim BM25·vector 파생 인덱스 | 실험 · curated에서 재구축 가능 |
| 시간축 관계 지도 | Neo4j Community | mutation log replay로 만든 materialized graph를 탐색 | 현재 사용 · 파생 그래프, SoT 아님 |
| 조사 실행·API | Python worker, FastAPI, optional LLM | 기존 evidence read-only 조사; LLM은 문장 표현만 보조 | 현재 사용; 결론·근거 계산 불변 |
| 운영 관측 | Grafana, DuckDB UI | PostgreSQL run metric과 exported Parquet snapshot 점검 | 실험 도구 · read-only 조건 병기 |
| 확장 | Apache Iceberg/S3, Kafka/Redpanda, Ray/Spark | schema evolution, 대규모 증분 table, queue/batch 처리량 확장 | **현재 미사용 · 확장 후보** |

Iceberg는 현재 사용 기술로 표현하지 않는다. 현재 기준은 Parquet + DuckDB + PostgreSQL queue이며, `100만 문서 규모의 증분 처리`, `수천만 row 또는 schema evolution`, `queue throughput`, `재처리 SLO` 같은 측정된 승격 조건이 성립할 때만 검토한다. 검색 인덱스와 Neo4j 그래프는 정본이 아니라 raw/curated/mutation log에서 재구축 가능한 파생물이라는 문장을 section lead에 둔다.

#### Investigation status ribbon

```text
접수됨 queued → 조사 중 running → 완료 completed
                         ├→ 실패 failed
                         └→ 취소 cancelled
```

job의 `succeeded`와 investigation의 `completed`를 섞지 않는다. 사용자 화면에는 조사 상태를 우선 표시하고, 실행 job 용어는 상세 설명에서만 쓴다.

### TS-4: Provenance·결과·미래 리포트 시각화 (from FR-2, FR-3)

#### Evidence trail

```text
[결과 문장]
  → [Claim · 검증할 수 있는 주장]
  → [Supports evidence · 현재 원문 왕복 제공]
  → [Source span · 원문의 정확한 구절]
  → [문서 버전 · 출처 URL]
```

- section header에 `현재 제공 · supports only` 배지를 둔다.
- 현재 `supports evidence → source span → document`만 3회 이내 원문 왕복을 제공한다.
- `contradicts`는 조사 결과에 후보/빈 상태로 보일 수 있지만 claim-evidence facade 원문 왕복은 미확장이다. `uncertain`/`superseded`는 현재 evidence trail에서 제공하지 않는다.
- 네 관계의 선 모양·색 legend를 교육용으로 보여줄 경우 `contradicts · 원문 왕복 미확장`, `uncertain/superseded · 제품 방향` availability text를 각각 붙인다.
- 현재 audit에서 연결 실패가 존재할 수 있음을 `연결됨 / 연결 안 됨` 두 상태로 함께 보여준다.
- demo 문장에는 항상 `설명용 예시 · 실제 조사 결과 아님`을 붙이고 실제 측정값처럼 보이는 실시간 timestamp를 넣지 않는다.

#### Result triad cards

세 카드 group header에 `현재 제공` 배지를 둔다.

1. **Investigation Result · 조사 결과** — 결론, modality가 구분된 문장, open questions. audit 실패 문장은 결과에 남을 수 있으므로 `검증되지 않음` 상태를 숨기지 않는다.
2. **War Table · Evidence Graph** — 주장 관계와 시간 정보를 보여준다. 반박 후보가 있어도 현재 Witnesses의 원문 왕복은 supports only임을 병기한다.
3. **Trail · 원문 계보** — 현재 supports evidence의 source span, 문서 버전, 수집 시각, 추출 버전. `contradicts` 원문 왕복 미확장을 빈 상태로 표시한다.

confidence example은 한 gauge가 아니라 다음 4-cell과 basis 문장을 사용한다.

| Evidence structure | Demo value |
|---|---|
| confidence | `0.61 · 근거 구조 평가` |
| evidence | `7건` |
| independent sources | `2개` |
| coverage | `63%` |

> `설명용 예시 · 실제 조사 결과 아님`  
> 동일 보도자료 파생 문서는 독립 근거로 중복 계산하지 않는다.

#### Now / Next matrix

| 사용자가 보는 기능 | Badge | Plain-language copy |
|---|---|---|
| 재시작 후에도 이어지는 조사 | 현재 제공 | 접수·조사 중·완료 상태와 결과 기록을 다시 볼 수 있다. 세부 실행 marker는 독립 단계가 아니다. |
| 확인된 근거 안에서 문장 표현 보조 | 실험 | 선택 기능이며 결론과 근거 계산은 바꾸지 않는다. |
| 읽기 쉬운 HTML 조사 문서와 과거 조사 목록 | 계획 · 미구현 | 설계는 검토 중이지만 아직 제품에서 열거나 내려받을 수 없다. |
| 새 근거에 따른 결론 변화 알림 | 제품 방향 | 앞으로 새 자료가 들어왔을 때 중요한 변화를 기록하고 알리는 방향이다. |

### TS-5: 실험 도구 링크와 runtime enhancement (from FR-4)

핵심 콘텐츠는 정적이다. production page만 mount 후 `/api/watchtower`를 fetch해 도구 카드의 상태와 link를 보강한다. 별도 API는 만들지 않는다.

#### Existing interface

```ts
type ComponentStatus = {
  id: 'postgres' | 'minio' | 'neo4j' | 'opensearch' | 'grafana' | 'duckdb-ui';
  name: string;
  layer: string;
  port: number;
  ui_port: number | null;
  ui_path: string | null;
  requires_localhost: boolean;
  note: string | null;
  reachable: boolean; // viewer process TCP reachability only
};
```

#### Link policy

| Tier | Target | Runtime href policy | Label / caveat |
|---|---|---|---|
| Primary | Watchtower | same-origin `/watchtower` | 시스템 상태·모든 구성요소 보기 |
| Promoted experimental | Grafana | current URL clone → current hostname, port `3000`, path `/d/citadel-pipeline` | read-only dashboard; local/SSH tunnel 필요; No data 가능 |
| Promoted experimental | DuckDB UI | current URL clone → protocol `http:`, hostname `localhost`, port `4213`, path `/` | read-only parquet snapshot; 반드시 localhost; remote는 SSH tunnel 필요; snapshot 지연 및 remote UI asset network 필요 |
| Advanced | Neo4j Browser | current URL clone → current hostname, port `7474`, path `/` | 로그인 필요; `7687` tunnel도 필요; 제공 계정에 따라 write 가능 |
| Advanced | MinIO Console | current URL clone → current hostname, port `9001`, path `/` | credentials·write 주의; 현재 prod nightly raw는 filesystem mirror에 있어 Console bucket은 비어 있음 |
| Advanced | OpenSearch diagnostic | current URL clone → current hostname, port `9200`, path `/_cluster/health?pretty` | dashboard가 아닌 GET 진단; base compose security plugin disabled이므로 tunnel/API는 read-only가 아님 |
| No browser CTA | PostgreSQL / Bolt / MinIO API | 없음 | Grafana 또는 해당 UI를 안내 |

target builder는 `frontend/src/lib/component-link.js`에 한 벌로 두고 Watchtower와 About이 함께 사용한다. DuckDB의 `http:` 강제와 나머지 current-protocol 규칙을 여기서 allowlist한다. 완성된 remote origin literal은 source/bundle에 굽지 않는다.

#### State behavior

- section header에 `실험` 배지를 둔다.
- loading: 도구 제목 아래 `상태 확인 중` 텍스트만 표시. layout shift가 없도록 카드 높이를 고정하지 않는다.
- `reachable=false`: anchor 대신 `미가동 · local compose 또는 SSH tunnel 필요`.
- `reachable=true`: `viewer에서 TCP 연결됨` badge + link. 이는 UI asset availability, dataset 존재, 인증, read-only enforcement, browser tunnel을 보장하지 않는다.
- API error: `운영 도구 상태를 확인할 수 없음` + Watchtower 링크. 핵심 본문에는 영향 없음.
- static mockup: 모든 live-looking row에 정확히 `DEMO · 설명용 상태`를 표시하고, 추가 설명으로 `실제 연결 상태 아님`을 쓴다. anchor는 만들지 않는다.
- `target="_blank" rel="noopener noreferrer"`; credential query·internal IP literal 금지.

### TS-6: HTML 목업·responsive·accessibility (from FR-5, FR-6)

#### Source and generated boundary

```text
design-system/ui/shell.mjs
  └─ optional skipTarget / mastheadContent / utilityNav; 기존 호출 기본 markup 불변
design-system/ui/project-introduction.mjs
  └─ props-only IntroHero, ValueTriad, FlowMap, EvidenceTrail,
     ResultTriad, CapabilityMatrix, ToolCards, HonestyStrip
design-system/ui/gate.mjs + design-system/ui/shell.mjs URL spaces
  └─ `urls.about` utility link; 8-space arrays 불변

design-system/mockups/src/pages/project-introduction.mjs
  └─ demo fixture + MOCKUP_URLS + static tool states
design-system/mockups/build.mjs
  └─ register `project-introduction`
docs/mockups/project-introduction.html
  └─ generated artifact; never hand-edit

frontend/about.html
frontend/src/pages/about/main.jsx
  └─ APP_URLS + optional `/api/watchtower` fetch only
frontend/src/lib/component-link.js
  └─ Watchtower/About shared allowlisted URL builder
frontend/src/pages/watchtower/main.jsx
  └─ use shared builder; DuckDB `http://localhost` rule corrected
frontend/vite.config.mjs
prototype/orc_citadel/viewer.py::_MIGRATED
  └─ `/about` → `about.html`

prototype/tests/test_frontend_dist.py
  └─ ENTRIES/MIGRATED에 `about`; bundle/content/tool-link contract
prototype/tests/test_mockups_build.py
  └─ PAGES/REQUIRED에 `project-introduction`; no-JS/theme/핵심 블록
frontend/dist/about.html + frontend/dist/js/about.js + affected shared chunks
  └─ Vite build generated artifacts; never hand-edit
```

#### Desktop mockup — 1200px content

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ ORC CITADEL · Project Guide                         [현재 제공] [실험용]   │
├────────────────────────── hero banner 8:3 ──────────────────────────────────┤
│ 질문이 결론이 되기까지, 모든 근거를 남긴다.                                │
│ [해결 1문장] [검색/챗봇과 차이 1문장] [결과 3요소 1문장]                   │
│ [조사 흐름 보기] [Council에서 조사 시작]                                   │
├──────────────────────────────────────────────────────────────────────────────┤
│ [원문 보존]                 [독립성 보정]               [시간축 기록]     │
├─────────────────────────────── example directive ───────────────────────────┤
│ “2024년 이후 A사의 … 반대 증거도 포함하라.”                                │
│ [설명용 예시 · 실제 조사 결과 아님]                                        │
├──────────────────────────── two-lane flow ──────────────────────────────────┤
│ 근거 준비 [현재 제공] A1 자료 → A2 원문 → A3 정규화·중복 → A4 근거 → A5 Graph │
│                                      │ RUN이 기존 근거를 읽음               │
│ 조사 실행 [현재 제공] B1 접수 → B2 PLAN → B3 RUN → B4 종합 → B5 감사      │
│                                  감사 실패는 표시 ┈→ B7 HTML [계획·미구현] │
├──────────────────────────── provenance trail ───────────────────────────────┤
│ [현재 제공·supports only] 결과 문장 → Claim → 지지 근거 → Source span → 원문│
├──────────────────────────────────────────────────────────────────────────────┤
│ [현재 제공] [Investigation Result]       [War Table]       [Trail]           │
│ [설명용 예시 · 실제 조사 결과 아님] confidence + evidence + coverage       │
├──────────────────────────── current / next ─────────────────────────────────┤
│ 현재 제공 · 실험                         계획 · 미구현 · 제품 방향          │
├────────────────────────── experimental tools ───────────────────────────────┤
│ [실험] [Watchtower] [Grafana] [DuckDB UI]       <details>고급 도구</details>│
├──────────────────────────── honesty + CTA ──────────────────────────────────┤
│ [현재 제공] 실험용 서비스 · 기존 evidence read-only · live web 아님        │
│ 법률·의료·투자 결정을 자동으로 대신하지 않음                              │
│ [Council Chamber에서 조사 시작]                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

#### Mobile mockup — 390px

```text
Hero → Value cards(1열) → Example directive
→ Lane A 세로 stepper → “현재 조사는 이 근거를 읽음” bridge
→ Lane B 세로 stepper → Planned boundary
→ Evidence trail 세로 목록 → Result cards(1열)
→ Current/Next cards → Watchtower → Experimental tools accordion
→ Honesty strip → CTA
```

#### Responsive rules

- `> 960px`: two-lane 5/8-column CSS grid, result/value 3 columns.
- `721–960px`: 각 lane은 가로 스크롤이 아니라 2열 wrap; bridge text는 독립 row.
- `≤ 720px`: 모든 flow를 한 열의 vertical stepper로 전환. connector는 세로선이며 DOM 순서는 바꾸지 않는다.
- utility shell은 검색창·Signal chip·8공간 tab row를 렌더하지 않고, wordmark/context와 wrap 가능한 `utilityNav`만 렌더한다. 320 CSS px에서 shell 자체도 viewport overflow를 만들지 않는다.
- text flex child에는 `min-width: 0`; URL/code는 `overflow-wrap: anywhere`.
- 전체 페이지는 320 CSS px까지 가로 overflow가 없어야 한다.
- desktop hero는 `aspect-ratio:8/3`, `object-fit:cover`, `object-position:center`; HTML title/CTA를 overlay한다.
- mobile `≤720px` hero image box는 `aspect-ratio:4/3`, `object-fit:cover`, `object-position:center`다. title/CTA는 이미지 위 overlay가 아니라 바로 앞의 HTML block으로 이동한다. 이 crop은 원본 가로 중앙 50%를 사용한다.
- main hero는 `<picture>`의 `project-introduction-hero-960.png 960w`와 `project-introduction-hero.png 1920w`, `sizes=\"100vw\"`, `loading=\"eager\"`, `fetchpriority=\"high\"`, `decoding=\"async\"`로 제공한다. 960px 파생본은 1920px 원본을 nearest-neighbor로 축소한다.

#### Accessibility

- WCAG 2.2 AA를 수용 기준으로 삼고 일반 텍스트는 실제 배경 대비 `≥4.5:1`을 측정한다.
- 필수 본문·상태·caveat에는 `on-surface #D6CCB8` 또는 `parchment #C8B58E` 계열을 사용한다. `on-surface-muted #59636A`는 `#111820` 위 대비가 약 `2.91:1`이라 큰 텍스트에도 AA를 충족하지 못하므로 정보성 텍스트·상태 라벨에는 사용하지 않고 비텍스트 장식/비활성 표현에만 제한한다.
- skip link는 `shell({skipTarget:'main-content'})`가 `Layout`보다 먼저 렌더하고, content root는 `id=\"main-content\"`와 `tabIndex=\"-1\"`을 가진다.
- 문서에는 하나의 `h1`만 두고 9개 section은 `h2`, 내부 카드 group은 필요할 때 `h3`를 사용한다.
- `main`, `nav`, `section`, `ol`, `article`, `details/summary` semantic 구조를 사용한다.
- flow section의 visible title과 `aria-describedby` 요약을 연결한다.
- decorative connector/icon은 `aria-hidden`; 상태 badge는 텍스트를 포함한다.
- external link accessible name에 대상과 새 창을 포함한다.
- focus-visible은 기존 2px accent + 3px offset을 유지한다.
- 200% zoom에서 section 순서와 CTA가 유지된다.
- motion은 요구하지 않는다. 추가 시 reduced-motion에서 transition/animation을 `none`으로 만든다.

### TS-7: 배너 이미지 생성 프롬프트 (from FR-6)

- **Target path**: `docs/mockups/assets/project-introduction-hero.png`
- **Alt**: `조사 지시 두루마리에서 검증된 근거 지도를 지나 감사된 리포트로 이어지는 Citadel 안내 홀`
- **Generation workflow**: 가능하면 480×180 native pixel grid에서 제작 후 nearest-neighbor 4×로 1920×720 export한다. 서비스가 native grid를 제어하지 못하면 1920×720에서 crisp pixel clusters와 no anti-alias를 명시하고 후처리 검수한다.

#### Copyable generation prompt

```text
Detailed original 16-bit pixel art (dot art) wide banner for “Orc Citadel”, a temporal evidence intelligence experiment. This is an orientation scene that a non-technical visitor can understand without reading labels. Crisp deliberate pixel clusters, hard pixel edges, controlled dithering, restrained retro-RPG key-art detail. Do not imitate Warcraft or any existing game IP.

Scene: the interior of a dark basalt Citadel orientation hall at night, showing one clear left-to-right journey with only three major visual masses. On the left, a simple parchment investigation directive rests at the Citadel Gate, marked only by an abstract question seal with no readable text. In the center, the directive reaches a low War Table where a small, legible network of source fragments and evidence nodes is being checked: a few emerald #45E06F solid links for verified support, one muted crimson #E05252 double-line contradiction, and parchment source cards feeding the graph. On the right, an archivist’s desk holds one completed, closed report folio connected back to the evidence table by a thin visible provenance trail. Behind it, two dim unlit folio slots suggest future reports without implying they already exist.

The visual story must read as: question → gathered evidence → verification and contradiction check → auditable report. Calm analytical work, not prophecy or battle. One or two small orc silhouettes may guide the eye, but data artifacts and the evidence trail are the focus. No character faces in close-up.

Palette: near-black navy #07111C and night #0D1B2A, basalt #111820 and #26313A, muted stone #D6CCB8, parchment #C8B58E, restrained crimson #7B2833. Emerald #45E06F is reserved only for verified evidence connections and occupies less than 8% of the frame. Amber #FFB13B and ember #E97824 are tiny status accents only.

Composition and export: exact 1920×720, 8:3, fully opaque sRGB PNG. Prefer artwork composed on a 480×180 native pixel grid and enlarged 4× with nearest-neighbor. Keep the upper-left 42% dark and low-detail as a safe area for an HTML title and two CTA buttons. Place all three essential story masses inside the lower-center 46% of the frame so the defined mobile 4:3 `cover` crop (the source image’s center 50%) still shows the directive, evidence table, and report trail. Use 2–3 strong silhouettes at thumbnail size. No baked-in title, labels, letters, numbers, logos, or UI controls.

Negative constraints: no readable generated text, no neon dashboard, no holographic screen, no excessive green glow, no magical prophecy orb, no glowing runes, no combat, no weapons, no cheering crowd, no fire particles, no ornate gold frame, no noisy stone texture, no photorealism, no smooth vector gradients, no anti-aliased edges, no existing franchise insignia, no browser chrome or dashboard cards baked into the image.
```

#### Post-generation acceptance

- exact `1920×720`, opaque alpha, sRGB PNG; derive exact `960×360` nearest-neighbor responsive copy.
- no readable pseudo-text, franchise mark, baked UI, or title.
- desktop 8:3 overlay safe area and mobile 4:3 center-50% crop both keep question → graph → report legible.
- emerald area remains restrained and corresponds only to verified links.
- thumbnail at 320×120 still shows question → graph → report as three masses.
- asset 부재 시 build/runtime props에서 hero reference 자체를 생략해 기존 flat 132px masthead를 사용한다. 깨진 placeholder URL을 만들지 않는다.

## Architecture

### Component Design

```text
shared shell contract                  shared presentation (no fetch/state)
  shell.mjs optional utility props       project-introduction.mjs
      ↓                                    ↓ fixture              ↓ runtime props
mockup SSG                                             frontend MPA
  project-introduction.mjs                               about/main.jsx
      ↓ renderToStaticMarkup                                 ↓ createRoot
  docs/mockups/project-introduction.html                 frontend/dist/about.html
                                                               ↓
                                                      viewer `/about`

frontend/src/lib/component-link.js
  └─ Watchtower/About allowlisted runtime URLs
```

`shell.mjs`의 optional props는 기존 8공간 호출의 기본 markup을 바꾸지 않는다. `mastheadContent`가 있으면 기본 `masthead()` 대신 caller의 단일 `h1` hero를 넣고, `utilityNav`가 있으면 고정 검색/Signal/8-space tabs 대신 wrap 가능한 utility nav를 렌더한다. `skipTarget`은 `Layout` 앞의 skip anchor를 만든다.

`design-system/ui/project-introduction.mjs` owns all copy-visible component structures. Mockup and production may provide different URL spaces and tool states, but cannot fork the section order or flow labels.

### Data Flow

1. `/about` loads committed `frontend/dist/about.html` and bundle.
2. Static explanatory content renders immediately from local constants and shared components.
3. After mount, the page optionally fetches `/api/watchtower`.
4. `components[]` is mapped by allowlisted ID into tool cards; no raw payload is rendered.
5. shared target builder creates each URL by cloning `location.href` and assigning allowlisted protocol/hostname/port/path. DuckDB alone forces `http:` + `localhost`; no complete remote origin literal is accepted from API or config.
6. Fetch failure changes only the tool section to neutral unavailable copy.

### Integration Points

- `design-system/ui/shell.mjs` — optional utility shell props + `MOCKUP_URLS.about` / `APP_URLS.about`; 8-space arrays unchanged.
- `design-system/ui/gate.mjs` / Gate page — `urls.about` utility link; mockup/production 모두 같은 presenter를 사용한다.
- `design-system/mockups/src/pages/index.mjs` — reference card.
- `frontend/src/lib/component-link.js` / Watchtower page — one allowlisted link policy.
- `prototype/tests/test_frontend_dist.py` / `test_mockups_build.py` — 새 entry·route·정적 핵심 블록을 수동 registry에 추가한다.
- `/api/watchtower` — optional component reachability only.
- `/council`, `/table`, `/witnesses`, `/archive`, `/watchtower` — contextual internal links.
- `specs/investigation-html-reports` — future HTML report design status `Review`, product availability `계획 · 미구현`.

## Data Models

### Static `IntroStage`

| Field | Type | Description | Constraints |
|---|---|---|---|
| `id` | string | stable stage key | unique within lane |
| `lane` | `evidence\|investigation` | flow lane | required |
| `label` | string | plain-language heading | no implementation jargon |
| `technical` | string | optional stage/term | visible as secondary text |
| `description` | string | user outcome | ≤2 sentences |
| `availability` | `current\|experimental\|planned\|direction` | truth badge | required |
| `href` | string/null | contextual internal link | allowlisted route only |

### Runtime `ToolCard`

Derived from `ComponentStatus`; no new persisted model. It adds presentation-only `tier`, `warning`, and computed `href`. Credentials and arbitrary URLs are never accepted as input.

## API / Interface Design

### Existing `GET /api/watchtower`

- **Method**: `GET`
- **Use in this feature**: consume only `components[]`.
- **Output dependency**: `id`, `name`, `layer`, `ui_port`, `ui_path`, `requires_localhost`, `note`, `reachable`.
- **Failure behavior**: render neutral unavailable copy; do not retry automatically and do not fail the page.

No new backend endpoint, persistence, query parameter, or report contract is introduced.

## Error Handling

| Scenario | Handling Strategy | User Impact |
|---|---|---|
| `/api/watchtower` loading | static content first; neutral inline status | core explanation immediately readable |
| API error/invalid shape | hide direct tool anchors; keep Watchtower CTA | no false availability claim |
| component unreachable | non-anchor status copy | no dead link |
| component reachable but browser tunnel/assets/data absent | permanent TCP-only and target-specific caveat | reachability를 usability로 오해하지 않음 |
| hero missing | asset prop/reference 자체를 생략; flat 132px masthead | no broken image |
| demo data mistaken for real | 모든 질문·결론·수치에 exact `설명용 예시 · 실제 조사 결과 아님` | no fabricated result claim |
| narrow viewport/zoom | utility shell + vertical DOM stepper + defined hero crop | no clipped flow |
| JavaScript disabled | production tool enhancement absent; mockup/content structure remains the design baseline | explanation still available where pre-rendered mockup is used |

## Dependencies

### External

- 신규 dependency 없음.
- Astryx, React, Vite는 기존 pinned project dependency를 그대로 사용한다.

### Internal

- `DESIGN.md` / theme-citadel tokens.
- `design-system/ui/components.mjs`, `shell.mjs`.
- `frontend/src/lib/component-link.js` — Watchtower/About shared target policy.
- `/api/watchtower` component status shape.
- `docs/mockups/illustration-prompts.md` house style.
- `prototype/tests/test_frontend_dist.py`, `test_mockups_build.py` generated-artifact registries.

## Security Considerations

- runtime component metadata만 allowlisted ID에 매핑한다. API가 임의 URL을 돌려줘도 사용하지 않는다.
- URL은 current `location` clone의 fields를 target allowlist로 덮어쓴다. DuckDB만 `http:` + `localhost`; complete remote origin literal과 credential query를 받지 않는다.
- `target="_blank"`는 `rel="noopener noreferrer"`와 함께 쓴다.
- MinIO·Neo4j·OpenSearch는 read-only라고 주장하지 않는다. OpenSearch base compose는 security plugin disabled임을 고급 도구 경고에 표시한다.
- static mockup은 live external tool anchor를 만들지 않는다.
- 페이지는 사용자 입력, report HTML, remote iframe을 렌더링하지 않는다.

## Performance Considerations

- tool status fetch는 한 번만 수행하고 polling하지 않는다.
- 새 대형 chart library, animation runtime, graph layout engine을 추가하지 않는다.
- feature budget은 구현 전 baseline Vite build와 구현 후 build의 `about.html` + `about` entry JS + 영향받은 shared chunk gzip 합계 차이로 측정하며 hero 제외 `≤150 KiB gzip`을 acceptance로 둔다.
- hero는 960w/1920w PNG `srcset`을 사용하고 first-screen 자산으로 eager/high priority를 확정한다. hero prop이 없으면 preload/request도 없다.
- flow는 CSS grid/list와 작은 inline SVG connector만 사용한다.
- mockup은 client JS 0을 유지한다.

## Open Questions

- 없음. route는 `/about`, 페이지는 8공간 밖 utility, 현재/계획 구분, 도구 link 정책, mockup·banner 산출 경계를 본 사양에서 확정한다.

## Clarification Log

| # | Question | Answer | Date |
|---|---|---|---|
| 1 | 기존 `investigation-html-reports` spec을 이 요청의 기반으로 사용할 것인가? | 아니오. 해당 문서는 report artifact/Campaign Ledger라는 별도 future feature이며 보존한다. 이 소개 페이지는 새 spec으로 분리한다. | 2026-09-20 |
| 2 | dirty `main`에서 branch를 새로 만들 것인가? | 사용자가 현재 branch에 새 specs 디렉터리만 추가하도록 선택했다. | 2026-09-20 |
| 3 | 소개 페이지를 아홉 번째 Citadel 공간으로 만들 것인가? | 아니오. `/about` utility page로 두고 Gate와 목업 index에서 연결한다. | 2026-09-20 |
| 4 | 외부 도구 링크를 정적 HTML에 항상 노출할 것인가? | 아니오. production에서 `/api/watchtower`로 보강하며 정적 목업은 demo/비활성 상태만 표시한다. | 2026-09-20 |
| 5 | 현재 audit를 “검증 실패 시 차단”으로 설명할 수 있는가? | 아니오. deterministic path는 unverified/blocked를 기록하지만 완료와 문장 저장을 차단하지 않는다. 소개 페이지는 이 한계를 명시한다. | 2026-09-20 |
| 6 | 요구사항 변경: 어느 단계에서 어떤 기술을 어떻게 활용하는지 설명을 추가할 것인가? | Technology Map을 2-lane flow 뒤에 추가하고 현재 기술의 역할·정본/파생 경계를 설명한다. Iceberg 등은 측정된 병목 뒤에 검토하는 현재 미사용 확장 후보로 분리한다. | 2026-09-21 |
