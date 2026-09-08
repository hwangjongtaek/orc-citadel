# Plans: Astryx 기반 UI 전면 개편 (목업↔실UI 갭 해소 + 사용성/브리핑 최적화)

> Created: 2026-09-08
> Updated: 2026-09-08
> Status: Ready
> Requirements: [requirements.md](./requirements.md)
> Specs: [specs.md](./specs.md)

## Overview

3개 트랙으로 진행한다. **A. 기반**(불변식 개정 → ui/ 승격 → frontend 스캐폴드), **B. 공간 이관**(브리핑 가치 순 8공간, 공간당 1~2커밋), **C. 모니터링**(Grafana — B와 병행 가능). 전 단계에서 리포 규약 유지: TDD 선작성 · Tidy First(구조/행위 커밋 분리) · honest-gap · 외부 CDN 금지.

**진행 규칙 — 목업 선행 (2026-09-08 사용자 확정):** 각 공간(Step 5~13)은 바로 구현하지 않고 ① 목업(`design-system/mockups`)을 새 정보구조로 먼저 저작·빌드 ② 사용자 확인 ③ frontend 구현 착수 순서를 지킨다. 목업 저작은 해당 Step의 frontend 작업보다 앞서 독립 커밋으로 진행할 수 있다. (셸 2계층 내비 + Gate 브리핑 대시보드 목업은 2026-09-08 선행 완료 — Step 5의 ①이 소진됨.)

## Prerequisites

- **로고 원본 2종 반입(사용자)**: 첨부 이미지의 원본 PNG를 `docs/mockups/assets/logo-lockup.png`(가로) · `logo-crest.png`(세로)로 저장. Step 4 선행 조건 — 미도착 시 Step 4만 뒤로 미루고 나머지 진행.
- node ≥ 20 로컬 저작 환경 (theme-citadel·mockups 빌드와 동일 — 이미 충족).
- 원격 prod에 Grafana 이미지 pull 1회 필요(Step 14 배포 시점, 네트워크 접근 확인).

## Implementation Steps

### Step 1: `stdlib only` 불변식 개정 기록 (문서)

- **Goal**: 표시 계층 저작 도구로 node·React를 허용하는 개정을 정본 3곳에 기록 — 이후 커밋의 규약 근거.
- **Specs Reference**: TS-1 Constraints
- **Files**:
  - `docs/design/09-api.md` — Modify — §1.3 뷰어 조항에 개정(런타임 stdlib 유지, 저작 도구 node 허용, dist 커밋 정책)
  - `docs/design/README.md` — Modify — 불변식 표 갱신
  - `docs/ROADMAP.md` — Modify — §5 결정 기록
- **Validation**: 3곳 상호참조 일치. Spec 버전: 문서 개정만 → 유지.
- **Complexity**: Simple

### Step 2: `design-system/ui/` 승격 (구조 커밋 — 행위 무변경)

- **Goal**: 목업 소스의 셸·컴포넌트·SVG를 공용 패키지로 이동, 목업 빌드는 wrapper+fixtures만 남김.
- **Specs Reference**: TS-2
- **Files**:
  - `design-system/ui/{package.json,shell.mjs,components/*.mjs,svg/*,fixtures/*.mjs}` — Create — mockups/src에서 이동·분해(no-JSX 규약 유지)
  - `design-system/mockups/src/pages/*.mjs` — Modify — `ui/` import + fixture 결합 wrapper로 축소
  - `design-system/mockups/build.mjs` — Modify — import 경로
- **Details**: 컴포넌트를 props-only로 정리하면서 하드코딩 데이터를 `ui/fixtures/`로 추출. 스타일 신규 발명 금지(토큰 참조만).
- **Validation**: `npm run build` 후 `docs/mockups/` diff가 **구조 동일**(무의미 차이만) + `test_mockups_build.py` 42개 통과 + `node --check` 전 파일.
- **Complexity**: Medium

### Step 3: `frontend/` 스캐폴드 + 뷰어 dist 서빙 (TDD)

- **Goal**: Vite MPA 골격 + 뷰어가 dist를 서빙하는 배선 + 회귀 가드.
- **Specs Reference**: TS-1
- **Files**:
  - `frontend/{package.json,vite.config.ts,src/lib/api.ts,src/pages/gate/main.tsx,…}` — Create — 멀티엔트리 9종(초기엔 Gate만 실엔트리, 나머지 placeholder 없이 단계 추가)
  - `frontend/dist/` — Create — 커밋 (청크 이름 안정화 설정 포함)
  - `prototype/orc_citadel/viewer_static.py` — Modify — dist HTML·자산 서빙(경로 방어 승계)
  - `prototype/orc_citadel/viewer.py` — Modify — 이관 라우트 → dist, `/legacy/<space>` 배선
  - `prototype/tests/test_frontend_dist.py` — Create — **선작성**: dist 존재·엔트리별 HTML 마커·자산 참조 실재·외부 URL 0건·이관 라우트 200/legacy 200
- **Validation**: pytest 신규 가드 + 기존 8라우트 무회귀.
- **Complexity**: Medium

### Step 4: 로고 자산 반입·파생·셸 교체 (FR-4)

- **Goal**: 신규 로고 2종 반영 — 헤더 lockup·Gate crest·favicon.
- **Specs Reference**: TS-4
- **Files**:
  - `scripts/derive_brand_assets.sh` — Create — sips 파생(헤더 40/80px, favicon 32, touch 180 — 정수배 축소)
  - `design-system/ui/shell.mjs` — Modify — 워드마크 텍스트 → lockup `<img>`(alt 유지), favicon `<link>`
  - `docs/mockups/*` — Modify — 재빌드 산출물
  - `prototype/tests/test_viewer_static.py` — Modify — 신규 자산 서빙 가드
- **Validation**: 목업·뷰어 양쪽 렌더에서 로고 표시(`image-rendering: pixelated` 확인). `crest-hero.png` 참조 0건(파일은 보존). README 대표 이미지는 사용자 확인 후 별도 커밋.
- **Complexity**: Simple

### Step 5: Gate 브리핑 대시보드 이관 (이관 1호)

- **Goal**: 홈을 브리핑 대시보드로 — KPI 4타일 · subject 결론 카드 · 변화 피드 · New Campaign 비활성 카드 · 프로세스 스트립.
- **Specs Reference**: TS-3, TS-5(Gate)
- **Files**:
  - `design-system/ui/components/{KpiTile,ConclusionCard,ProcessStrip,DisabledCampaignCard}.mjs` — Create
  - `frontend/src/pages/gate/` — Create — `/api/gate`·`/api/rank`·`/api/spire`·`/api/watchtower` 바인딩
  - `design-system/mockups/src/pages/citadel-gate.mjs` — Modify — 같은 컴포넌트 + fixture로 목업 갱신
  - `prototype/tests/test_frontend_dist.py` — Modify — Gate 구조 마커
- **Details**: confidence는 값+근거 수+독립 출처 수 병기(단일 게이지 금지). **번들 예산 실측을 이 단계에서 기록**(≤300KB gzip 게이트) — 초과 시 이후 공간 진행 전 스플릿 전략 확정.
- **Validation**: 브리핑 시나리오 1·3클릭 구간 시연 + 예산 실측 기록.
- **Complexity**: Complex

### Step 6: `/api/search` scope 확장 + 전역 검색 팔레트 (TDD)

- **Goal**: 통합 검색(subjects/claims/documents) + Cmd+K 팔레트를 셸 공통으로.
- **Specs Reference**: TS-3, API Design
- **Files**:
  - `prototype/tests/test_viewer.py`(또는 기존 검색 테스트 파일) — Modify — **선작성**: scope별 응답·하위호환(scope 생략)·400
  - `prototype/orc_citadel/viewer.py` — Modify — `_api_search` scope 분기(rank·claim 투영 재사용, read-only)
  - `frontend/src/lib/palette.tsx` — Create — Cmd+K·그룹 렌더·딥링크
  - `design-system/ui/components/SearchPalette.mjs` — Create — 프레젠테이션(목업은 정적 표기)
- **Validation**: API 테스트 + 전 이관 페이지에서 팔레트 동작. ILIKE 정직 라벨. **Spec 버전: API 추가 → minor bump**(현행 1.1.0 → 1.2.0) 기록.
- **Complexity**: Medium

### Step 7: Hall of Witnesses 이관 — evidence 왕복 확립

- **Goal**: `ClaimCard` + `EvidenceDrawer`(3-hop 인라인) 공용화 — 이후 전 공간이 재사용하는 왕복 패턴의 기준 구현.
- **Specs Reference**: TS-3(왕복 일관화), TS-5(Witnesses)
- **Files**:
  - `design-system/ui/components/{ClaimCard,EvidenceDrawer,IndependenceNote,ModalityFilter}.mjs` — Create
  - `frontend/src/pages/witnesses/` — Create — `/api/subject_claims`·`/api/claim`·`/api/evidence`·`/api/provenance`·`/api/document`
  - `design-system/mockups/src/pages/hall-of-witnesses.mjs` — Modify
- **Details**: modality 필터 4종, Contradicting Evidence 정직 빈 자리, dup_cluster 독립성 보정 블록. L3 재적재로 원문 왕복 100% — 실데이터로 검증.
- **Validation**: 결과→원문 3-hop이 drawer에서 완결. 브리핑 시나리오 2클릭 구간 시연.
- **Complexity**: Complex

### Step 8: War Table 이관 — 그래프 캔버스 재작성

- **Goal**: subject 중심 서브그래프 + 단계 확장, 판독 가능한 결정적 레이아웃.
- **Specs Reference**: TS-5(War Table)
- **Files**:
  - `design-system/ui/svg/graph.mjs` — Create — 결정적(시드 고정) 방사형 배치·라벨 충돌 회피·엣지 5종 선형태(DESIGN.md 병기 규칙)
  - `frontend/src/pages/table/` — Create — `/api/table`·`/api/graph`·`/api/graph_node`·`/api/graph_expand`
  - `design-system/mockups/src/pages/war-table.mjs` — Modify
- **Details**: 렌더 상한 100노드, 확장은 `/api/graph_expand` 클릭 단위. 선택 노드만 primary 발광. Chronicle rail 하단 고정 3행. Evidence Inspector는 Step 7의 ClaimCard 재사용.
- **Validation**: 722 claims 실데이터에서 라벨 겹침 0(수동 확인 + 노드 수 상한 단위 테스트).
- **Complexity**: Complex

### Step 9: Grand Archive 이관

- **Goal**: 3열(Sifter 300 | Stacks 1fr | Codex 380) 통합 — 서버 축(페이징·facet·contains) 유지.
- **Specs Reference**: TS-5(Archive)
- **Files**: `frontend/src/pages/archive/` — Create, `design-system/ui/components/{FacetChips,LineageBadge}.mjs` — Create, 목업 갱신
- **Details**: dedup lineage 뱃지(dup_clusters 528 실데이터), `?doc=`·`?src=` 딥링크 부트스트랩 유지(aea7965 파리티).
- **Validation**: `test_viewer_archive.py` 25개 무회귀(API 계층) + 10만 문서에서 페이지 응답 유지.
- **Complexity**: Medium

### Step 10: Signal Spire 이관

- **Goal**: 3열(288 | 1fr | 340) + Campaigns/Scope 필터 + Alert Feed 탭 + 알림 카드 골격 + Subscriptions.
- **Specs Reference**: TS-5(Spire)
- **Files**: `design-system/ui/components/AlertCard.mjs` — Create, `frontend/src/pages/spire/` — Create, 목업 갱신
- **Details**: alert 영속 부재 → 전 열 정직 빈 상태(카드 구조는 fixture로 목업에서 증명). 셸 Spire 칩은 `/api/spire` 실측치.
- **Validation**: 빈 상태 3열 렌더 + 목업 구조 일치.
- **Complexity**: Medium

### Step 11: Council Chamber 이관

- **Goal**: 단일 3열 그리드(중복 패널 결함 소멸) + 8 Agent 카드(초상·모델 칩) + 조사 루프 12스텝 다이어그램 + 발언 타임라인.
- **Specs Reference**: TS-5(Council)
- **Files**: `design-system/ui/svg/council-loop.mjs` — Create, `frontend/src/pages/council/` — Create, 목업 갱신
- **Validation**: 패널 중복 0. Cost `—` 정직 표기 유지.
- **Complexity**: Medium

### Step 12: Watchtower 이관 (+ Grafana 딥링크)

- **Goal**: KPI 5타일 + Stage Throughput/Failure 패널(FR-6 테이블 소스) + Sources 확장 컬럼 + Grafana 딥링크 카드.
- **Specs Reference**: TS-5(Watchtower), TS-6
- **Files**: `frontend/src/pages/watchtower/` — Create, `prototype/orc_citadel/viewer.py` — Modify(`/api/watchtower`에 메트릭 테이블 조회 필드 — 표시용 추가), 목업 갱신
- **Details**: Step 14a(메트릭 테이블) 이후 착수 권장 — 선행 없으면 전 패널 not-measured 렌더로 진행 가능. dead-letter는 범위 밖 명시 유지.
- **Validation**: 메트릭 유무 양쪽에서 정직 렌더.
- **Complexity**: Medium

### Step 13: Chronicle Vault 이관 (이관 마지막)

- **Goal**: Bitemporal Plane 최상단 + "두 축" 3카드 + AS-OF 대비 패널.
- **Specs Reference**: TS-5(Chronicle)
- **Files**: `frontend/src/pages/chronicle/` — Create, `design-system/ui/svg/bitemporal-plane` 재사용, 목업 갱신
- **Details**: valid_time 전부 null → X축 정직 빈 라벨. dual slider·preset은 기존 aux_ext 로직을 React로 이식.
- **Validation**: AS-OF 질의 3종 preset 동작(재료 없으면 비활성).
- **Complexity**: Medium

### Step 14: Grafana 트랙 (Step 5~13과 병행 가능)

- **14a. run 메트릭 postgres flush (TDD)** — `prototype/orc_citadel/run_metrics.py` Create(테이블 2종 DDL·append-only flush·선택 주입), `scripts/scheduler_runner.py` Modify(런 종료 훅·비차단), `prototype/tests/test_run_metrics.py` Create 선작성(스키마·correlation 분해·flush 실패 비차단·postgres 부재 skip — `importorskip` 격리 규약 준수).
- **14b. compose grafana 서비스** — `docker-compose.yml`·`docker-compose.prod.yml` Modify(이미지 핀·loopback·anonymous Viewer), `deploy/grafana/provisioning/{datasources,dashboards}/` Create. read-only DB 계정.
- **14c. 대시보드 1종** — `deploy/grafana/provisioning/dashboards/pipeline.json`: 수집 성공률·freshness·stage 처리량·quarantine 추이. `docs/operating/deployment.md`에 접근 절차(SSH 터널) 추가.
- **Specs Reference**: TS-6
- **Validation**: 로컬 compose 기동 → nightly 시뮬레이션 런 1회 → 대시보드에 실측치 표시. 데이터 없는 패널 No data.
- **Complexity**: Medium

### Step 16: 데이터 브라우징 트랙 (Step 3 이후 병행 가능 — Step 14와 독립)

- **16a. parquet 스냅샷 export 배선 (TDD)** — `scripts/scheduler_runner.py` Modify(런 종료 훅에 `export_parquet` 호출 — 14a와 동일 지점·선택 주입·비차단), export를 `.new` 디렉터리 → 원자 교체로 감싸는 헬퍼(`rebuild_zones` 패턴 승계). `prototype/tests/test_parquet_snapshot.py` Create 선작성(원자 교체·실패 시 직전 유지·비차단).
- **16b. DuckDB UI 사이드카** — `deploy/duckdb-ui/Dockerfile` Create(duckdb CLI 핀 + `INSTALL ui` 빌드 시 1회), `docker-compose.yml`·`prod.yml` Modify(parquet 디렉터리 **read-only 마운트**·loopback·`.duckdb` 미포함 — 잠금 함정 원천 차단).
- **16c. 접근 절차 + 체험 가이드** — `docs/operating/data-browsing.md` Create: 존 계층 → 저장 형식 → 도구 매핑(raw=MinIO Console·DuckDB존=parquet+DuckDB UI·SoT/메트릭=Grafana Explore·neo4j/opensearch=내장 UI), 복붙용 예제 쿼리(segments 조인·dedup cluster·correlation drill-down), prod SSH 터널 절차, `.duckdb` 직접 attach 금지 규칙 명문화. `docs/operating/deployment.md` Modify(서비스 목록).
- **Specs Reference**: TS-7
- **Validation**: 로컬 compose에서 스냅샷 export → DuckDB UI로 예제 쿼리 3종 실행 + MinIO Console에서 raw 오브젝트 열람. export 실패 시 직전 스냅샷 유지 확인.
- **Complexity**: Medium

### Step 15: legacy 일괄 제거 + 마감 기록

- **Goal**: 2체계 공존 종료 — 인라인 표시 계층 제거, 3단계 기록 완료.
- **Specs Reference**: TS-1
- **Files**:
  - `prototype/orc_citadel/viewer_pages.py`·`aux_ext.py`·`council_ext.py`·`table_ext.py`·`witnesses_ext.py` — Delete/축소(API가 참조하는 비표시 유틸만 잔존) + `/legacy/*` 라우트 제거
  - 관련 표시 계층 테스트 — Delete/이관
  - `docs/ROADMAP.md`·`docs/design/09-api.md`·`docs/design/README.md` — Modify — 완료 기록
- **Validation**: 전체 스위트 green + 8공간 실기동 확인 + 브리핑 시나리오 최종 시연.
- **Complexity**: Medium

## Task Breakdown

- [ ] **Step 1**: 불변식 개정 기록 (문서 3곳)
- [ ] **Step 2**: design-system/ui/ 승격 (구조)
- [ ] **Step 3**: frontend 스캐폴드 + dist 서빙 (TDD)
- [ ] **Step 4**: 로고 반입·파생·셸 교체 ← 로고 파일 대기
- [ ] **Step 5**: Gate 브리핑 대시보드 (+ 번들 예산 실측)
- [ ] **Step 6**: /api/search scope + Cmd+K 팔레트 (Spec 1.2.0)
- [ ] **Step 7**: Witnesses (ClaimCard·EvidenceDrawer 확립)
- [x] **Step 8**: War Table (그래프 재작성)
- [x] **Step 9**: Archive
- [x] **Step 10**: Spire
- [x] **Step 11**: Council
- [x] **Step 12**: Watchtower (+ Grafana 딥링크)
- [ ] **Step 13**: Chronicle
- [ ] **Step 14**: Grafana 트랙 (14a flush → 14b compose → 14c 대시보드)
- [ ] **Step 16**: 데이터 브라우징 트랙 (16a parquet export → 16b DuckDB UI 사이드카 → 16c 가이드 문서)
- [ ] **Step 15**: legacy 제거 + 마감 기록 (최종)
- [ ] **Final**: requirements Acceptance Criteria 전수 확인

## File Change Summary

| File | Action | Step | Description |
|------|--------|------|-------------|
| `docs/design/09-api.md` 외 정본 2 | Modify | 1, 15 | 불변식 개정·완료 기록 |
| `design-system/ui/**` | Create | 2, 5~13 | 공용 컴포넌트 패키지 |
| `design-system/mockups/src/**` | Modify | 2, 5~13 | wrapper+fixture로 축소·갱신 |
| `frontend/**` (+ dist 커밋) | Create | 3, 5~13 | Vite MPA·페이지 엔트리 |
| `prototype/orc_citadel/viewer_static.py` | Modify | 3, 4 | dist·신규 자산 서빙 |
| `prototype/orc_citadel/viewer.py` | Modify | 3, 6, 12, 15 | 라우트 매핑·search scope·watchtower 필드·legacy 제거 |
| `scripts/derive_brand_assets.sh` | Create | 4 | 로고 파생 |
| `prototype/orc_citadel/run_metrics.py` | Create | 14a | postgres flush |
| `scripts/scheduler_runner.py` | Modify | 14a | 런 종료 훅 |
| `docker-compose*.yml` + `deploy/grafana/**` | Modify/Create | 14b·c | Grafana 사이드카·provisioning |
| `deploy/duckdb-ui/Dockerfile` + `docs/operating/data-browsing.md` | Create | 16 | DuckDB UI 사이드카·체험 가이드 |
| `prototype/tests/test_frontend_dist.py` 외 | Create/Modify | 3~14 | TDD 가드 |
| `viewer_pages.py`·`*_ext.py` | Delete/축소 | 15 | 인라인 표시 계층 제거 |

## Dependencies Between Steps

```
Step 1 ── Step 2 ── Step 3 ── Step 5 ── Step 6 ── Step 7 ── Step 8 ─┬─ Step 9~11, 13 (순서 자유)
                        │                                            │
Prereq(로고) ── Step 4 ─┘ (Step 3 이후 아무 때나)                     └─ Step 12 ── Step 15
                                                                          │
Step 14a ── 14b ── 14c  (Step 3 이후 병행, 14a는 Step 12 권장 선행) ──────┘
Step 16a ── 16b ── 16c  (Step 3 이후 병행, 프런트·Grafana와 독립)
```

- Step 7의 ClaimCard가 8·9·13의 재사용 기반 — 7을 8보다 먼저 고정.
- Step 14 트랙은 프런트와 독립 — 병행 시 커밋만 분리.

## Testing Strategy

### Unit Tests (pytest — node 불요, 커밋 게이트)
- `test_frontend_dist.py`: dist 무결성·구조 마커·외부 URL 0·라우트 200 (Step 3 선작성, 공간마다 마커 추가)
- `test_viewer_*`: `/api/search` scope(선작성)·watchtower 필드·기존 API 무회귀
- `test_run_metrics.py`: flush 스키마·비차단·postgres 부재 skip(importorskip 격리 규약)
- `test_mockups_build.py`: 기존 42개 유지 — ui/ 승격 후에도 클라이언트 JS 0·토큰 하드코딩 금지

### Integration Tests (저작 도구 — vitest, 빌드 시점)
- ui/ 컴포넌트 렌더 스냅샷(fixture 입력 → 구조), 팔레트 키보드 동작, EvidenceDrawer 3-hop mock 왕복

### Manual Verification (공간 이관마다)
- 실기동 뷰어(8791)에서 해당 공간 + 목업 나란히 대조 → 정보구조 일치 확인
- 브리핑 시나리오: 홈 → 결론 카드 → 근거 원문 → 변화 피드, 3클릭 이내 (Step 5·7 후, Step 15 최종)
- Grafana: 로컬 compose에서 시뮬레이션 런 1회 후 대시보드 실측 표시

## Rollback Plan

1. **Step 2 이후**: ui/ 승격은 목업 산출물 diff 무변경이 게이트 — 실패 시 revert 1커밋.
2. **Step 5~13 각 공간**: canonical 라우트를 `/legacy/<space>` 매핑으로 되돌리는 1줄 변경(뷰어 라우트 테이블) — 공간 단위 즉시 롤백.
3. **Step 14**: grafana 서비스 제거로 원상복구(메트릭 테이블은 append-only 잔존 무해). flush 훅은 선택 주입이라 비활성화만으로 복귀.
4. **Step 15 이후**: legacy 제거 커밋 revert (그 전까지 이력 보존).

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Astryx beta(0.5.x) API 변동 | Medium | Medium | 버전 핀 + dist 커밋으로 런타임 격리(재빌드 시점에만 노출) |
| 번들 예산 초과(공유 청크 비대) | Medium | Medium | Step 5에서 조기 실측 게이트 — 초과 시 공간별 스플릿 확정 후 진행 |
| dist 커밋 diff 소음 | High | Low | 청크 이름 안정화 + 이관 커밋과 dist 커밋 분리 |
| 그래프 SVG 자작 레이아웃 품질 | Medium | Medium | 결정적 시드 + 100노드 상한 + Step 8 실데이터(722 claims) 검증. 미달 시 레이아웃만 교체(컴포넌트 계약 유지) |
| 픽셀 로고 축소 뭉개짐 | Low | Low | 정수배 축소·pixelated 렌더링 |
| Grafana 이미지 원격 pull 불가 | Low | Medium | 배포 1회 네트워크 확인, 불가 시 로컬 `docker save/load` 경로를 deployment.md에 기록 (duckdb-ui 이미지 동일) |
| 외부 도구의 `.duckdb` 직접 attach로 잠금 충돌 | Medium | Medium | 사이드카 마운트에 `.duckdb` 미포함(parquet만) + 금지 규칙 문서 명문화 |
| parquet export 소요(105k docs·823k segments) | Low | Low | nightly 비차단 훅 — 런 시간에 합산될 뿐 파이프라인 무영향. 소요 실측을 16a에서 기록 |
| 2체계 공존 장기화 | Medium | Medium | 공간별 롤백 경로 유지 + Step 15를 브리핑 가치 4공간(5~8) 완료 직후로 앞당길 수 있게 legacy 의존 최소화 |

## Progress Tracking

| Step | Status | Started | Completed | Notes |
|------|--------|---------|-----------|-------|
| Step 1 | Done | 2026-09-08 | 2026-09-08 | 09 §1.3 · design README §3 · ROADMAP §5 기록 |
| Step 2 | Done | 2026-09-08 | 2026-09-08 | ui/ 승격 + rawSvg→svg-node 분리(브라우저-안전), 산출물 diff 0. node_modules 심링크로 단일 react |
| Step 3 | Done | 2026-09-08 | 2026-09-08 | Vite MPA + /app/* 서빙 + 가드 4종. **번들 실측 69.45KB gzip** (예산 300KB 충족) — Step 5 게이트 선통과 |
| Step 4 | In Progress | 2026-09-08 | | 목업 레벨 완료 — lockup 반입·배경 투명화·mark/title 분리·favicon 파생·셸/Gate/index 배선 (`scripts/brand_logo_intake.py`). 세로 crest 원본 미도착(mark 크롭으로 충당). 뷰어 셸 교체는 frontend 이관 시 |
| Step 5 | Done | 2026-09-08 | 2026-09-08 | `/` canonical 전환 완료 (`/legacy/gate` 롤백 경로). ui/gate 추출 + 셸 URL 파라미터화(MOCKUP_URLS/APP_URLS). 번들 117KB gzip. 브라우저 실렌더·콘솔 0 검증 |
| Step 6 | Done | 2026-09-08 | 2026-09-08 | API 무변경(기존 /api/search 소비) → **Spec 1.1.0 유지**. ui/palette.mjs(공용) + frontend lib(⌘K·디바운스·키보드). 딥링크 3종 E2E 검증(TSMC→War Table). ⚠ 확장 키입력으론 ⌘K가 옴니박스로 감 — 실사용 키보드 검증은 사용자 확인 필요 |
| Step 7 | Done | 2026-09-08 | 2026-09-08 | `/witnesses` canonical 전환. ui/witnesses.mjs 확립(claimRow·claimFocus·독립성·trail·documentSegments·roundTrip). 3-hop 왕복 실데이터 E2E(하이라이트 성립). ⚠ L3 발견: extraction segment(#p1+)와 normalized 세그먼트(p0.s*) 불일치 — 표본 20건 중 매칭 3 · 미매칭 17, UI 는 접두 폴백 + "span 미매칭" 정직 표기. 세그먼트 정합 복구는 데이터 트랙 과제 |
| Step 8 | Done | 2026-09-08 | 2026-09-08 | `/table` canonical 전환. ui/graph.mjs — subject 중심 + predicate 그룹 집계 + 부채꼴 단계 확장(페이지당 12·항상 ≤100 노드·결정적 슬롯 배치로 라벨 겹침 0). truncated 정직 표기. Inspector = subject 봉투 + claim 카드 + Witnesses 딥링크. Chronicle 레일(assertion tx 실데이터). graph_expand API 는 빈 응답이라 subgraph 클라이언트 페이징으로 대체 |
| Step 9 | Done | 2026-09-08 | 2026-09-08 | `/archive` canonical 전환. ui/archive.mjs(facetChips·lineageBadge·docCard·pager·sifterSearch) — 목업·앱 공유. 서버 축 유지(facet 3축·contains q·정렬·limit/offset 페이저), `?doc=`·`?src=` 부트스트랩 파리티. Codex = lineage 뱃지 + 같은 URL 버전 히스토리(url_groups) + dedup 총계(528). footer = segment_kinds 실측. 계획의 components/{FacetChips,LineageBadge}.mjs 는 기존 관례(공간당 평면 모듈)에 맞춰 archive.mjs 로 통합 |
| Step 10 | Done | 2026-09-08 | 2026-09-08 | `/spire` canonical 전환. ui/spire.mjs(triggerRow·filterRow·feedTabs·alertCard·subscriptionCard·newSubscriptionSlot) — 알림 카드 골격은 목업 fixture 로 증명, 앱은 /api/spire 실측으로 전 열 정직 빈(트리거 카탈로그 5종 docstring·empty-spire 일러스트·fire-once 규칙 인용). 구독은 비활성 자리만(§3-3). 셸 Spire 칩 = alerts.length 실측 |
| Step 11 | Done | 2026-09-08 | 2026-09-08 | `/council` canonical 전환. 단일 3열(중복 패널 결함 소멸). ui/council.mjs — agentCard(초상 stretch 방식 승격)·loopStrip(12스텝)·turnCard·COUNCIL_ROLES(wire 판정 카탈로그). 8역할 executed/not-run 은 wire 필드 존재로, trace 는 on-request 버튼 1회(로드 자동 fetch 없음). Cost 4타일 전부 — 정직 표기, 모델 ID 미표기(wire 미영속). 계획의 ui/svg/council-loop.mjs 는 SVG 대신 loopStrip 칩 스트립으로 대체(정보 동일·의존 감소) |
| Step 12 | Done | 2026-09-08 | 2026-09-08 | `/watchtower` canonical 전환. ui/watchtower.mjs(stageCard·failureCard·sloCard·grafanaCard). /api/watchtower 에 run_metrics 표시 필드 추가(최근 런 요약 read-only·pg 미가동 정직 빈 — metrics_connect 주입 테스트 2). KPI 5타일 실측(freshness 일 단위 표기), stage·DLQ 는 wire 미영속 → not-measured/범위 밖 정직 렌더, Run Metrics 테이블(14a 실측), Grafana 카드는 14b 전까지 미배선 표기, Sources 확장 컬럼(last_fetch·governance) |
| Step 13 | Pending | | | |
| Step 14 | 14a Done | 2026-09-08 | | 14a: run_metrics.py(테이블 2종·append-only·safe_flush 비차단) + scheduler 런 종료 훅 + nightly_* slo_log 주입·요약 반환, 테스트 10(순수 5 오프라인·pg 5 격리), 기본 경로 스모크 실측. 14b·14c 남음 |
| Step 16 | Pending | | | 병행 트랙 (데이터 브라우징) |
| Step 15 | Pending | | | 최종 마감 |

## Acceptance Criteria Checklist

From requirements:
- [ ] FR-1: 8공간 전부 새 프런트 렌더 + 목업 정보구조 일치 / API 무회귀 / 런타임 node 불요 / legacy 존치 후 제거
- [ ] FR-2: 공용 컴포넌트 1벌 / 목업 클라이언트 JS 0 유지 / 동시 반영 회귀 가드
- [ ] FR-3: Gate 대시보드 / 1차 내비 4종 / Cmd+K 통합 검색 / evidence 왕복 일관화 / 3클릭 시연
- [ ] FR-4: 로고 2종 반입·서빙 / crest-hero 참조 전량 교체 / 파생본·레티나 정책 / README 확인 후 반영
- [ ] FR-5: 공간별 갭 체크리스트(Spire·Council·Witnesses·Archive·Watchtower·Chronicle·War Table) 전수
- [ ] FR-6: grafana 서비스 / provisioning 커밋 / 메트릭 영속 배선 / 대시보드 1종 / Watchtower 딥링크
- [ ] FR-7: parquet export 배선 / DuckDB UI 사이드카 / MinIO Console 절차 / 체험 가이드 문서 / `.duckdb` 직접 접근 금지 명문화
