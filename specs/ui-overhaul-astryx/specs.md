# Specs: Astryx 기반 UI 전면 개편 (목업↔실UI 갭 해소 + 사용성/브리핑 최적화)

> Created: 2026-09-08
> Updated: 2026-09-08
> Status: Draft
> Requirements: [requirements.md](./requirements.md)

## Overview

Python 뷰어의 인라인 HTML 표시 계층(약 4,600줄)을 **Astryx React 프런트엔드로 전면 대체**한다. 컴포넌트는 `design-system/ui/`(신설) 1벌로 통합해 목업 SSG와 앱 CSR이 같은 코드를 소비하고, 홈을 브리핑 대시보드로 재설계한다. 뷰어는 API 서버 + 정적 서빙으로 축소되고, 파이프라인 모니터링은 Grafana 사이드카(postgres datasource)로 부착한다. 백엔드 계약은 무변경이 원칙이며 예외는 두 가지 — `/api/search` scope 확장(읽기 투영)과 run 메트릭 postgres flush 배선(운영 로그 계층).

## Technical Specifications

### TS-1: 프런트엔드 아키텍처 — Vite MPA + React 19 CSR (from FR-1)

- **Description**: `frontend/` 신설. **SPA가 아니라 Vite 멀티엔트리 MPA** — 공간당 HTML 엔트리 1개(총 9: 8공간 + index는 Gate로 통합). 클라이언트 라우터를 도입하지 않는다: stdlib 서버에 history fallback 로직이 불필요하고, 딥링크가 자연히 동작하며, 공간 이동은 현행과 같은 풀 페이지 로드다(공유 청크는 브라우저 캐시).
- **Components Involved**: `frontend/`(신설), `viewer.py`(라우트 매핑 축소), `viewer_static.py`(dist 서빙 추가), `viewer_pages.py`·`*_ext.py`(단계적 제거).
- **Data Flow**: 브라우저 → `GET /<space>` → 뷰어가 `frontend/dist/<space>.html` 서빙 → 페이지 JS가 `fetch('/api/…')` → 렌더. 하이드레이션 프레임워크 없음(순수 CSR 마운트).
- **Implementation Approach**:
  - `frontend/dist/`는 **리포에 커밋**(theme-citadel·목업과 동일 정책 — 런타임·배포·원격 호스트에 node 배제, rsync·compose 무변경). 재빌드는 저작 시점만.
  - 라우트 이관은 공간별 커밋: 이관된 공간은 canonical 경로가 dist를 서빙하고, 기존 인라인 페이지는 `/legacy/<space>`로 존치. **8공간 전부 이관 완료 시 legacy 일괄 제거 커밋**(2체계 공존 기간의 명시적 종료).
  - 이관 순서(확정): Gate → Witnesses → War Table → Archive → Spire → Council → Watchtower → Chronicle.
  - JSX·TypeScript는 `frontend/` 내부에서만 허용. 공유 컴포넌트(TS-2)는 no-JSX 규약 유지.
- **Constraints**: `stdlib only` 불변식 개정 필요(런타임은 여전히 stdlib — 개정 내용은 "표시 계층 저작 도구로 node 허용"). 3단계 기록(design 09 §1.3 → design README → ROADMAP §5) 선행. Astryx `@astryxdesign/*` 0.5.x 고정.

### TS-2: 컴포넌트 단일 소스 — `design-system/ui/` (from FR-2)

- **Description**: 목업 소스(`design-system/mockups/src/`)의 셸·페이지·도메인 컴포넌트를 `design-system/ui/`(신설 패키지)로 승격한다. 컴포넌트는 **데이터 무지(props-only)·프레젠테이셔널**로 저작하고, 소비자 둘 — 목업 빌드(SSG, 하드코딩 fixture)와 `frontend/`(CSR, `/api/*` 데이터) — 가 같은 모듈을 import 한다.
- **Components Involved**: `design-system/ui/`(신설: `shell.mjs`·`components/*.mjs`·`svg/*`·`fixtures/*.mjs`), `design-system/mockups/`(얇은 wrapper로 축소), `frontend/src/`(데이터 바인딩 + 상호작용 계층).
- **Implementation Approach**:
  - `design-system/ui/`는 **no-JSX(`React.createElement`)·번들러 무관** 규약 유지 — 목업 빌드(`node build.mjs`)가 번들러 없이 소비해야 하기 때문. Vite는 `.mjs`를 그대로 소비 가능.
  - 상호작용(탭 전환·팔레트·drawer·fetch)은 `frontend/` 쪽 컨테이너 컴포넌트가 소유. `ui/`의 프레젠테이셔널 컴포넌트는 콜백 props만 받는다(목업에선 미배선 → 클라이언트 JS 0 유지).
  - `mockups/src/pages/*.mjs`는 `ui/` 컴포넌트 + `ui/fixtures/` 샘플 데이터 결합만 남긴다.
- **회귀 가드(렌더 동등성)**: 목업 빌드 시 각 공간의 핵심 구조 마커(3열 그리드·패널 헤더·카드 구조)를 `test_mockups_build.py`가 검증(기존) + 신설 `test_frontend_dist.py`가 커밋된 dist HTML/JS에서 같은 구조 마커·컴포넌트 클래스(`astryx-*`)를 검증 — 두 산출물이 같은 컴포넌트에서 나왔음을 node 없이 확인.
- **Constraints**: `ui/`에 새 스타일 발명 금지(theme-citadel 토큰만 참조 — 기존 목업 규약 승계). 도메인 SVG(그래프·bitemporal plane·엣지 범례)는 Astryx 대응물이 없어 `ui/svg/` 직접 저작 유지.

### TS-3: 브리핑-우선 IA (from FR-3)

- **Description**: 진입·이동 구조를 주요 작업 4종(결론 조회 · 근거 추적 · 변화 확인 · 검색) 중심으로 재설계.
- **Implementation Approach**:
  - **내비 2계층**: 1차 = Gate(브리핑 홈) · War Table · Hall of Witnesses · Signal Spire + 전역 검색. 2차("운영·감사" 드롭다운) = Grand Archive · Council · Watchtower · Chronicle. 모든 URL·기능 유지, 배치만 강등. 세계관 명칭 + 기능명 병기 규칙(DESIGN.md) 유지.
  - **Gate = 브리핑 대시보드** (소비 API: `/api/gate`·`/api/rank`·`/api/spire`·`/api/watchtower`):
    1. 상단: 신규 lockup 로고 + 태그라인 + KPI 타일 4(문서·entity·claim·최근 수집).
    2. 중앙: **주요 subject 결론 카드** — 결론 요약 + confidence(값+근거 수+독립 출처 수 병기, 단일 게이지 금지) + War Table/Witnesses 딥링크.
    3. 우측/하단: 최근 변화 피드(alert 0건 → 정직 빈 상태) + New Campaign **비활성 카드**("read-only 프로토타입" 배지) + 프로세스 3단계 스트립.
  - **전역 검색 팔레트**: 헤더 검색 + `Cmd+K`. `/api/search?scope=` 확장(TS-계약 아래) 소비, 결과 그룹 = subjects/claims/documents, 각 결과에 공간별 딥링크. ILIKE contains임을 라벨로 정직 표기(BM25 아님).
  - **evidence 왕복 일관화**: 공용 `<ClaimCard>`(ui/)가 전 공간에서 동일 — modality 배지 + confidence 병기 + 액션 2종 고정: "근거 열기"(인라인 provenance drawer — `/api/evidence`→`/api/provenance`→`/api/document` 3-hop) + "Hall of Witnesses에서 보기"(딥링크). 화면별 상이한 클릭 경로 금지.
  - **브리핑 수락 시나리오**(수동 시연 체크리스트로 plans에 포함): 홈 진입 → 결론 카드 확인(1) → "근거 열기"로 원문 스팬 도달(2) → Spire/변화 피드 확인(3). 3클릭 이내.
- **Constraints**: 별도 프레젠테이션 뷰 없음(확정). 픽셀 폰트는 배지·워드마크 한정.

### TS-4: 브랜드 로고 교체 (from FR-4)

- **Description**: 신규 픽셀아트 로고 2종 반입·파생·전면 교체.
- **Implementation Approach**:
  - 반입(사용자 제공 파일): `docs/mockups/assets/logo-lockup.png`(가로: crest+레터링 통합 원본), `docs/mockups/assets/logo-crest.png`(세로: 엠블럼+하단 레터링). 투명 배경 유지.
  - **lockup은 분리해서 사용한다(확정)**: 가로 원본에서 투명 경계를 기준으로 `logo-mark.png`(crest 부분)와 `logo-title.png`(ORC CITADEL 레터링 부분)를 크롭 파생 — 헤더는 공간이 좁으므로 mark 단독 또는 mark+title 조합을 맥락별로 쓴다.
  - 파생(스크립트 `scripts/derive_brand_assets.sh`, macOS `sips` 사용 — node·외부 도구 불요): 분리 크롭 2종 + 헤더용 축소본(높이 40px@1x·80px@2x), 파비콘(`favicon-32.png`·`apple-touch-180.png`는 crest 정방형에서).
  - 교체 지점: ① 셸 헤더 워드마크(텍스트 "ORC CITADEL" → mark+title 이미지 + `alt`) ② Gate 브랜드 블록(기존 `crest-hero.png` 96px 자리) ③ 목업 index 마크 ④ favicon `<link>`(현행 부재 시 신설). ⑤ **리포 대표 `orc-citadel-hero.png`·README 배너는 교체하지 않는다(확정)**.
  - 기존 `crest-hero.png`는 삭제하지 않고 참조만 제거(자산 이력 보존, 갭 분석 기준선과 동일 정책).
- **Constraints**: 로고 표시는 전부 원본(621·1129px)보다 작은 **다운스케일**이므로 `image-rendering: pixelated`를 쓰지 않는다(픽셀레이티드는 업스케일용 — 다운스케일에선 앨리어싱 유발, 브라우저 기본 스무딩 사용). 히어로 크기 정책(8:3·상한)은 lockup에 적용하지 않는다(로고는 히어로가 아님).
- **구현 기록 (2026-09-08, 목업 레벨 완료)**: 원본에 알파가 없고 near-white 배경이 구워져 있어 `scripts/brand_logo_intake.py`(Pillow — sips 계획 대체)로 배경 제거·mark/title 분리·favicon 파생. 산출 5종 커밋: `logo-lockup.png`(1787×716)·`logo-mark.png`(621×716)·`logo-title.png`(1129×376)·`favicon-32.png`·`apple-touch-180.png`. 셸 워드마크(mark 30px + title 22px)·Gate 브랜드 블록(mark 96 + title 46)·index(mark 56)·favicon `<link>` 배선 완료, `crest-hero.png` 참조 0건 가드 추가. **세로 crest 원본은 미도착**(첨부 2건이 동일 lockup) — 정방형 쓰임새는 mark 크롭으로 충당 중이며 세로판(레터링 하단 배치)이 필요해지면 추가 반입.

### TS-5: 공간별 정보구조 — L2 갭 소진 (from FR-5)

- **Description**: 각 공간을 대응 목업 정보구조 그대로 구현. 잔여 갭 명세는 [handoff-viewer-mockup-gap.md](../../docs/handoff-viewer-mockup-gap.md) §2가 정본이며, 여기서는 구현 결정만 확정한다.
- **Implementation Approach** (공간별 핵심 결정):
  - **Gate**: TS-3 대시보드 구성이 목업 구성을 대체·상회(목업의 New Campaign은 비활성으로 반영).
  - **Witnesses**: 3-hop 왕복은 L3 재적재로 해소율 100% — modality 필터(fact/asserted/opinion/prediction), Contradicting Evidence 섹션(0건 → 정직 빈 자리), 독립성 보정 블록(`dup_cluster` 근거 N→독립 M).
  - **War Table**: 그래프는 **subject 중심 서브그래프 기본 + `/api/graph_expand` 단계 확장**(hairball 가드, 확정). 레이아웃은 결정적(시드 고정) 방사형 + 라벨 충돌 회피(겹침 시 우선순위: 선택 노드 > 고 coverage) — 외부 그래프 라이브러리 도입 없이 SVG 직접 렌더(ui/svg 저작 규약 승계). 100+ 노드 렌더 금지(DESIGN.md). panel-head 겹침은 Astryx `LayoutPanel`로 구조 해소. Chronicle rail 하단 고정 3행.
  - **Archive**: 3열(Sifter 300 | Stacks 1fr | Codex 380) 통합, facet·페이징·contains 검색은 **서버 축 유지**(`/api/archive` — aea7965). dedup lineage 뱃지(● root/○ derived/◆ independent)는 dup_clusters 528건 실데이터로 표시.
  - **Spire**: 3열(288 | 1fr | 340) + 필터·탭·알림 카드 골격 + Subscriptions. alert 영속 부재 → 카드 구조만 만들고 정직 빈 유지.
  - **Council**: 단일 3열 그리드(중복 패널 결함은 재작성으로 자연 소멸), 8 Agent 카드(초상 `char-*.png`·모델 라우팅 칩), 조사 루프 12스텝 다이어그램(ui/svg), 발언 타임라인 카드. Cost 미영속 → `—` 정직 표기.
  - **Watchtower**: KPI 5타일(Backlog·실패율·Dead-letter는 데이터 원천 없으면 not-measured 표기), Stage Throughput·Failure 패널은 **FR-6 메트릭 테이블을 소스로 렌더**(Grafana와 동일 원천) — dead-letter 백엔드 부재는 명시적 범위 밖 선언 유지. **Grafana 딥링크 카드** 추가.
  - **Chronicle**: Bitemporal Plane(2축 SVG) 최상단, "두 축이 답하는 질문" 3카드, AS-OF 대비 패널. valid_time 전부 null → X축 정직 빈 라벨.
- **Constraints**: 데이터 없는 축은 전부 honest-gap(§6.2) — 구조는 만들되 가짜 데이터 금지.

### TS-6: Grafana 사이드카 + run 메트릭 영속 (from FR-6)

- **Description**: design 11 §2.2 확정 구성(PostgreSQL + Grafana)을 compose에 실현. 병목인 메트릭 영속을 최소 배선으로 해소.
- **Components Involved**: `docker-compose.yml`·`docker-compose.prod.yml`(grafana 서비스), `deploy/grafana/provisioning/`(신설 — datasource·dashboard JSON), `prototype/orc_citadel/run_metrics.py`(신설 — flush 배선), `scripts/scheduler_runner.py`(런 종료 훅).
- **Data Flow**: scheduler nightly 런 → 런 종료 시 `run_metrics.flush(slo_log, run_summary)` → postgres `pipeline_run_metrics`·`pipeline_slo_observations` → Grafana(postgres datasource) 대시보드 / 뷰어 `/api/watchtower`(동일 테이블 조회로 Stage Throughput 패널 공급).
- **Implementation Approach**:
  - Grafana OSS 이미지(버전 핀), loopback 바인딩 + SSH 터널(viewer 접근 정책 동일), 익명 read-only org(`GF_AUTH_ANONYMOUS_ENABLED` + Viewer role), 플러그인 설치 없음(코어 postgres datasource만 — 오프라인 런타임 유지, 이미지 pull은 배포 1회).
  - provisioning as code: `datasources/postgres.yml` + `dashboards/pipeline.json` 커밋. 수동 클릭 설정 금지.
  - flush는 **런 단위 append-only**(UPSERT 없음, correlation_id·version_tuple 컬럼 포함 — ADR-1102 drill-down 정합). 파이프라인 로직 무변경 — scheduler 훅에서만 호출, 실패해도 런은 성공(경고 로그).
  - 로컬(compose 미사용, launchd venv)은 flush 대상 postgres가 없으면 skip(선택 주입 규약 승계 — `slo_log=None` 패턴과 동일).
- **Constraints**: Grafana는 관측 전용(그래프 SoT 접근 없음, read-only DB 계정). 대시보드 패널은 데이터 부재 시 No data 그대로(honest-gap).

### TS-7: 데이터 존 브라우징 사이드카 (from FR-7)

- **Description**: 존 계층별 저장 형식을 그대로 브라우징하는 체험 도구. 신규 구축 최소화 — MinIO Console(기존)·Grafana Explore(FR-6 겸용)·Neo4j Browser/Dashboards(내장)는 접근 절차만, 신규는 **parquet export 배선 + DuckDB UI 사이드카** 둘뿐.
- **Components Involved**: `docker-compose.yml`·`prod.yml`(duckdb-ui 서비스), `deploy/duckdb-ui/Dockerfile`(duckdb CLI + `INSTALL ui` — 빌드 시 1회 네트워크), `scripts/scheduler_runner.py`(export 훅 — run_metrics flush와 동일 지점), `docs/operating/data-browsing.md`(신설 가이드).
- **Data Flow**: scheduler 런 종료 → `export_parquet()`(기존 메서드) → `data/parquet/<zone>/*.parquet` → duckdb-ui 컨테이너가 read-only 마운트로 `read_parquet` 질의. raw는 MinIO Console이 버킷 직접 열람.
- **Implementation Approach**:
  - **잠금 회피가 설계의 핵심**: 뷰어 `_build()`가 `curated.duckdb`·`oc.duckdb`에 쓰기 잠금을 쥔다(실측 — arxiv-collection-gotchas). 외부 도구는 `.duckdb`를 절대 직접 열지 않고 parquet 스냅샷만 읽는다. 이 규칙을 가이드 문서에 명문화.
  - export는 `.new` 디렉터리 생성 후 원자 교체(rebuild_zones 패턴 승계) — UI가 읽는 중 파일 반쯤 교체되는 상태 방지. 비차단(실패해도 런 성공).
  - DuckDB UI는 loopback 바인딩 + SSH 터널(viewer·Grafana와 동일 정책). 예제 쿼리는 가이드 문서에 복붙 가능한 형태로(segments 조인, dedup cluster 조회, as-of, correlation drill-down).
  - 신선도: nightly 스냅샷이면 체험 목적에 충분 — 즉시 재수출은 컨테이너에서 export 스크립트 수동 1회로 문서화.
- **Constraints**: DuckDB `ui` 확장은 로컬 단일 사용자 도구(인증 없음) — loopback 한정 유지. parquet 디렉터리는 read-only 마운트(사이드카가 존을 오염시킬 수 없음 — §3-3 정합).

## Architecture

### Component Design

```
design-system/
├── theme-citadel/        (기존) 토큰 SSOT 발행본
├── fonts/                (기존) 폰트 vendoring
├── ui/                   (신설) 공용 컴포넌트 — no-JSX·props-only·theme 토큰만
│   ├── shell.mjs         헤더(내비 2계층·검색 트리거)·히어로·푸터
│   ├── components/*.mjs  ClaimCard·EvidenceDrawer 프레젠테이션·AlertCard·KpiTile·…
│   ├── svg/              war-table-graph·bitemporal-plane·edge-legend·council-loop
│   └── fixtures/*.mjs    목업용 샘플 데이터 (앱은 미사용)
├── mockups/              (축소) ui/ + fixtures 결합 wrapper → docs/mockups/ SSG
frontend/                 (신설) Vite MPA — 데이터 바인딩·상호작용
├── src/pages/<space>/    엔트리 9종: main.tsx가 ui/ 컴포넌트에 /api/* 데이터 주입
├── src/lib/              api client·팔레트(Cmd+K)·drawer 상태
└── dist/                 (커밋) 뷰어가 서빙하는 산출물
prototype/orc_citadel/
├── viewer.py             /api/* 19종 유지 + /api/search scope 확장
├── viewer_static.py      /assets/* (기존) + dist 서빙 (신설)
├── run_metrics.py        (신설) postgres flush
└── viewer_pages.py·*_ext.py  → /legacy/* 존치 후 일괄 제거
deploy/grafana/provisioning/   (신설) datasource·dashboard as code
```

### Data Flow

1. **앱**: 정적 HTML+JS(dist, 커밋됨) → CSR 마운트 → `/api/*` fetch → ui/ 컴포넌트 렌더.
2. **목업**: 같은 ui/ 컴포넌트 + fixtures → `renderToStaticMarkup` → `docs/mockups/`(클라이언트 JS 0 불변).
3. **모니터링**: scheduler 런 → run_metrics flush → postgres → Grafana + `/api/watchtower`.
4. **데이터 브라우징**: scheduler 런 → parquet 스냅샷(원자 교체) → DuckDB UI(read-only) / raw → MinIO Console / SoT·메트릭 → Grafana Explore.

### Integration Points

- 뷰어 라우트: 이관된 공간 = dist HTML, 미이관 = 기존 인라인(이관 기간 한정), `/legacy/<space>` 롤백 경로.
- theme-citadel: frontend는 React `<Theme theme={citadelTheme}>`로, 목업·legacy는 CSS 링크로 — 같은 토큰 두 소비 경로(theme-citadel README 계약 그대로).
- 배포: rsync에 `frontend/dist/`·`design-system/ui/` 포함(코드 트리라 자동), compose 무변경 + grafana 서비스 1개 추가.

## Data Models

### `pipeline_run_metrics` (신설, postgres, append-only)

| Field | Type | Description | Constraints |
|-------|------|-------------|-------------|
| run_id | text | 스케줄러 런 식별자 | PK 구성(run_id, stage) |
| started_at / finished_at | timestamptz | 런 구간 | not null |
| stage | text | fetch/parse/dedup/extract/promote | not null |
| docs_in / docs_out / failures | bigint | stage 처리량·실패 | ≥0 |
| duration_ms | bigint | stage 소요 | ≥0 |
| correlation_sample | text[] | drill-down용 correlation_id 표본 | ADR-1102 |
| version_tuple | jsonb | 5축 버전 | design 03 §7.1 |

### `pipeline_slo_observations` (신설, postgres, append-only)

| Field | Type | Description | Constraints |
|-------|------|-------------|-------------|
| run_id | text | 런 식별자 | FK 성격(강제 없음) |
| slo | text | slo-05/06/07 | not null |
| measured | boolean | honest-gap 유지 | not null |
| value / n / detail | numeric / bigint / jsonb | 관측치 | measured=false면 value null |

## API / Interface Design

### `/api/search` — 변경 불필요로 판명 (2026-09-08 구현 시 확인)

- 계획했던 scope 확장은 **불필요** — 기존 `/api/search?q=` 가 이미 `{entities, claims, documents, counts}` cross-zone 을 반환한다(각 ≤10, 결정적 정렬). 팔레트가 그대로 소비하고 딥링크는 기존 URL 부트스트랩(`/table?subject=`·`/witnesses?claim=`·`/archive?doc=`)을 쓴다. **API 계약 변경 0건 → Spec 1.1.0 유지 확정.**

### 기타 소비 계약

- 페이지별 소비 API는 기존 19종 그대로(TS-3·TS-5에 명기). `/api/watchtower`만 FR-6 테이블 조회 필드가 추가된다(표시용 필드 추가 — requirements 예외 조항).
- Grafana는 `/api/*`를 쓰지 않고 postgres를 직접 읽는다(read-only 계정).

## Error Handling

| Scenario | Handling Strategy | User Impact |
|----------|-------------------|-------------|
| `/api/*` fetch 실패 | 공용 ErrorPanel(재시도 버튼) — 빈 상태와 시각적으로 구분 | 페이지 골격은 유지, 실패 패널만 표시 |
| 데이터 0건 | `EmptyState` + 빈상태 일러스트(기존 6종) — honest-gap 문구 | "미수집/미영속" 사유 명시 |
| JS 비활성 브라우저 | `<noscript>` 안내 + legacy 링크(이관 기간) | 브리핑 환경은 JS 가정 |
| dist 부재/오염 | `test_frontend_dist.py`가 커밋 시점 차단 + 뷰어는 404 | 발생 전 차단 |
| Grafana 미기동/메트릭 0 | Watchtower 딥링크 카드에 상태 표기, 패널 No data | 뷰어 기능 무영향 |
| metrics flush 실패 | 경고 로그 후 런 계속(비차단) | 파이프라인 무영향 |
| parquet export 실패/부분 산출 | `.new` 원자 교체 — 실패 시 직전 스냅샷 유지, 경고 로그 | DuckDB UI는 항상 완결 스냅샷만 봄 |
| 외부 도구가 `.duckdb` 직접 attach | 금지 규칙 문서화 + read-only 마운트에 `.duckdb` 미포함(parquet만) | 잠금 충돌 원천 차단 |

## Dependencies

### External (전부 저작·빌드 시점 한정, 런타임 배제)

- `@astryxdesign/core` 0.5.x (핀): 컴포넌트. 정본 스코프 `@astryxdesign/*`만 — `astryx`·`astryx-ui`는 무관 패키지.
- `react`/`react-dom` 19, `vite`(버전 핀): frontend 빌드.
- `vitest`: frontend 컴포넌트 테스트(저작 도구).
- Grafana OSS 이미지(버전 핀): compose 사이드카. 플러그인 없음.
- DuckDB CLI + `ui` 확장(버전 핀): duckdb-ui 사이드카 이미지. 확장 설치는 빌드 시 1회, 런타임 오프라인.

### Internal

- `theme-citadel`(dist 커밋) — 토큰. `design-system/fonts/` — 폰트. `docs/mockups/assets/` — 일러스트·신규 로고.
- `/api/*` 파사드 19종 — 무변경 원칙(search scope만 추가).
- `slo_observation_log`·scheduler — flush 훅 접점.

## Security Considerations

- 접근 모델 무변경: loopback 바인딩 + SSH 터널(viewer·Grafana 동일). 인증 신설 없음.
- Grafana postgres 계정은 read-only(메트릭 테이블 SELECT 한정) — 그래프 SoT 테이블 권한 없음.
- dist 서빙은 기존 `viewer_static.py` 경로 이스케이프 방어 규약 승계.
- 외부 CDN·원격 폰트·analytics 없음(전 자산 로컬).

## Performance Considerations

- **번들 예산**: 공간당 초기 JS ≤ 300KB gzip(공유 청크 포함 실측치를 이관 첫 공간에서 기록, 초과 시 코드 스플릿). 로컬 LCP < 1s 목표.
- 10만+ 문서 축은 서버사이드 페이징 유지(aea7965) — 클라이언트 전량 로딩 금지.
- War Table 렌더 상한 100노드(DESIGN.md) — 서브그래프 + 단계 확장.
- dist 커밋 diff 소음: 빌드 해시 고정(`build.rollupOptions` 청크 이름 안정화)으로 무의미 diff 최소화.
- 메트릭 테이블은 append-only nightly(런당 수 행) — 인덱스 (run_id, stage)면 충분.

## Open Questions

- ~~로고 원본 파일 반입 대기~~ → **가로 lockup 반입·처리 완료** (2026-09-08). 잔여: 세로 crest 원본(첨부 2건이 동일 lockup이라 미도착) — mark 크롭으로 충당 중, 필요 시 추가 반입.
- ~~README·리포 대표 이미지 교체 여부~~ → **교체하지 않음 확정** (2026-09-08).

## Clarification Log

| # | Question | Answer | Date |
|---|----------|--------|------|
| 1 | frontend dist 배포 정책 | 리포에 커밋 (theme-citadel 방식, 런타임·원격 node 배제) | 2026-09-08 |
| 2 | 8공간 이관 순서 | 브리핑 가치 순: Gate → Witnesses → War Table → Archive → Spire → Council → Watchtower → Chronicle | 2026-09-08 |
| 3 | 쓰기 UI(New Campaign) 처리 | 비활성 자리만 — "read-only 프로토타입" 표시, §3-3 불변 | 2026-09-08 |
| 4 | 브리핑 모드 형태 | 홈 대시보드 + 딥링크 (별도 프레젠테이션 뷰 없음) | 2026-09-08 |
| 5 | War Table hairball 가드 | subject 중심 서브그래프 기본 + `/api/graph_expand` 단계 확장, 결정적 SVG 레이아웃 | 2026-09-08 |
| 6 | 파이프라인 모니터링 UI 부착 가능? | 가능·설계 정합 — design 11 §2.2가 "PostgreSQL + Grafana" 기확정. 병목은 메트릭 영속(in-memory slo_log) → FR-6 flush 배선으로 해소 | 2026-09-08 |
| 7 | 존 데이터 브라우징 UI(DuckDB·Lakehouse 체험) | raw=MinIO Console(기존 활성), DuckDB 존=**parquet 스냅샷 + DuckDB UI 사이드카**(뷰어 쓰기 잠금 실측 함정 때문에 `.duckdb` 직접 attach 금지 — parquet 경유가 lakehouse 체험에도 정합), postgres=Grafana Explore 겸용, neo4j/opensearch=내장 UI 문서화만 | 2026-09-08 |
| 8 | 로고 사용 방식·README 배너 | 가로 lockup은 mark/title **분리 크롭**해 사용, README 배너(`orc-citadel-hero.png`)는 **교체하지 않음** | 2026-09-08 |
| 9 | 진행 방식 | **목업 선행(mockup-first)** — 각 공간은 목업을 먼저 저작·확인한 뒤 frontend 구현에 착수 (바로 구현 금지) | 2026-09-08 |
| 10 | Step 6 API 판단 | `/api/search` 기구현이 팔레트 요건 충족 — scope 확장 폐기, **Spec 1.1.0 유지** | 2026-09-08 |
