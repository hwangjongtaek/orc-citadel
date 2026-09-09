# Requirements: Astryx 기반 UI 전면 개편 (목업↔실UI 갭 해소 + 사용성/브리핑 최적화)

> Created: 2026-09-08
> Updated: 2026-09-08
> Status: Finalized (open questions 5/5 해소 — specs.md Clarification Log 참조)
> Ticket: N/A
> Difficulty: high
> Pipeline: full
> Source: manual

## Overview

Astryx 도입 Phase 0–2(theme-citadel 저작 · 목업 Astryx SSG 재작성 · 뷰어 셸/자산 적용)와 L3 데이터 재적재가 완료됐지만, 두 가지 문제가 남아 있다.

1. **목업↔실UI 구조적 갭.** 목업은 Astryx React 컴포넌트(SSG)로, 실UI는 Python stdlib 인라인 HTML(약 4,600줄: `viewer_pages.py` + `*_ext.py`)로 각각 저작된다. 코드베이스가 둘이라 목업의 정보구조(3열 앱셸, 알림 카드, 패널 배치)를 뷰어에 옮길 때마다 **수작업 번역**이 필요하고, L2 정보구조 갭([handoff-viewer-mockup-gap.md](../../docs/handoff-viewer-mockup-gap.md) §2 — Spire 3열 부재, Council 중복 패널, Witnesses modality 필터 등)이 계속 재발한다. 테마 토큰만 공유해서는 갭이 구조적으로 소멸하지 않는다.
2. **사용성.** 현행 UI는 8공간에 기능이 분산된 전문가용 고밀도 인터페이스다. 이 서비스는 (a) 실험적 서비스이고 (b) **타인에게 브리핑하는 용도**로도 쓰이므로, 처음 보는 사람도 주요 기능 — 결론 조회 · 근거 추적 · 변화 확인 · 검색 — 에 직관적으로 빠르게 도달할 수 있어야 한다. 전문적인 분석·브라우징 심도는 유지한다.

**개편 방향:** 목업과 앱이 **같은 Astryx 컴포넌트 코드**를 쓰도록 프런트엔드를 통합하고(갭의 구조적 소멸), 그 위에서 브리핑-우선 IA로 재설계한다. 기존 계획([plan-ui-design-system.md](../../docs/plan-ui-design-system.md))의 "Phase 3 Spire 파일럿 → Phase 4 판정" 단계적 경로를 **전면 개편으로 대체**하되, 판정 게이트 6항(번들 크기·재현도·테마 충돌·오프라인 빌드·테스트 전략·2체계 유지비)은 본 spec의 NFR/제약으로 흡수해 해소한다.

## Goals

- [ ] G1 **단일 소스**: 목업과 실UI가 같은 컴포넌트 코드를 사용, 차이는 데이터 소스뿐(하드코딩 vs `/api/*`). 목업↔UI 갭 분류 자체가 소멸.
- [ ] G2 **브리핑 사용성**: 처음 보는 사람이 안내 없이 3클릭 이내에 "지금 무슨 결론이 있고, 그 근거가 무엇인지"에 도달.
- [ ] G3 **분석 심도 유지**: 8공간의 전문 분석·브라우징 기능 동등성(기능 하향 없음) + L2 잔여 갭 전수 소진.
- [ ] G4 **브랜드 갱신**: 신규 로고 2종(가로 lockup · 세로 crest)으로 전 화면 브랜드 자산 교체.
- [ ] G5 **파이프라인 모니터링**: 데이터 엔지니어링 실습 목표에 따라, 실수집 데이터가 흐르는 파이프라인을 실시간 모니터링할 수 있는 체계(Grafana류) 부착.
- [ ] G6 **데이터 브라우징 체험**: 존 계층별 실데이터가 **어떤 형식으로 쌓이고 어떻게 활용 가능한지**(raw 오브젝트 → DuckDB/parquet → postgres SoT) 직접 브라우징·질의할 수 있는 도구 부착.

## Functional Requirements

### FR-1: 프런트엔드 아키텍처 전환 — Astryx React 프런트 단일화

- **Description**: `frontend/` 신설 — Vite + React 19 + `@astryxdesign/core` + `theme-citadel`. 기존 `/api/*` 파사드를 그대로 소비하고(백엔드 무변경, read-only §3-3 유지), Python 뷰어는 **정적 산출물 서빙 + API 서버**로 축소한다. 8공간 전부를 새 프런트로 이관하고, 인라인 HTML 페이지(`viewer_pages.py`·`*_ext.py`의 표시 계층)는 이관 완료 후 제거한다.
- **Acceptance Criteria**:
  - [ ] 8공간(라우트 8종) 전부 새 프런트로 렌더되고, 대응 목업과 정보구조가 일치한다 (아래 FR-5)
  - [ ] 백엔드 `/api/*` 계약 무변경 (기존 API 테스트 무회귀)
  - [ ] 런타임·배포에 node 불요 — 빌드 산출물 정책은 Open Question ①에서 확정 후 반영
  - [ ] 이관 기간 중 기존 페이지는 롤백 경로로 존치, 완료 시점에 제거 커밋

### FR-2: 목업 = 앱 컴포넌트 공유 (단일 소스)

- **Description**: `design-system/mockups/src/`의 셸·페이지 컴포넌트를 `frontend/` 컴포넌트로 승격한다. 목업 빌드(`docs/mockups/`)는 같은 컴포넌트에 **하드코딩 샘플 데이터**를 물려 SSG로 뽑고, 앱은 같은 컴포넌트에 `/api/*` 데이터를 물린다.
- **Acceptance Criteria**:
  - [ ] 셸(헤더·공간 탭·히어로)과 8공간 페이지 컴포넌트가 목업·앱 공용 모듈 1벌로 존재
  - [ ] 목업 빌드는 계속 클라이언트 JS 0의 정적 HTML 산출 (기존 `test_mockups_build.py` 가드 유지)
  - [ ] 컴포넌트 수정 1회가 목업·앱 양쪽에 동시에 반영됨을 확인하는 회귀 가드 존재

### FR-3: 브리핑-우선 IA 재설계

- **Description**: 8공간의 전문 심도는 유지하되, 진입·이동 구조를 "주요 작업 우선"으로 재설계한다. 주요 작업 4종 = ① 결론/현황 조회 ② 결론→근거 원문 추적 ③ 변화(알림) 확인 ④ 통합 검색.
- **Acceptance Criteria**:
  - [ ] **홈(Citadel Gate) = 브리핑 대시보드**: 핵심 지표 타일 + 주요 subject 결론 카드(confidence·근거 수 병기) + 최근 변화 피드. 각 카드에서 해당 공간으로 1클릭 딥링크
  - [ ] **1차 내비 단순화**: 주요 작업 4종이 1차 내비/홈에서 즉시 도달 가능. 나머지 공간(Watchtower·Chronicle·Council 등 운영·감사 성격)은 2차 계층으로 강등하되 URL·기능은 유지
  - [ ] **전역 검색 승격**: 헤더 검색을 entity/claim/document 통합 검색으로. 키보드 진입(Cmd+K)과 결과에서 공간별 딥링크 제공
  - [ ] **evidence 왕복 일관화**: 어느 화면의 claim/assertion 카드에서든 동일한 인터랙션으로 근거 원문(3-hop)까지 도달 — 화면마다 다른 클릭 경로 금지
  - [ ] 브리핑 시나리오 테스트: "이 도메인의 현재 결론은? → 근거는? → 최근 바뀐 것은?"을 처음 보는 사람 기준 3클릭 이내 시연 가능

### FR-4: 브랜드 로고 교체 (신규 자산 2종)

- **Description**: 사용자가 제공한 신규 픽셀아트 로고 2종으로 브랜드 자산을 교체한다 — **가로 lockup**(crest + "ORC CITADEL" 스톤 레터링, 헤더·index용)과 **세로 crest**(엠블럼 단독 + 하단 레터링, Gate 히어로·빈상태·파비콘용). 이미지 파일 반입은 사용자 작업(§Constraints 참조).
- **Acceptance Criteria**:
  - [ ] 신규 로고 원본 2종이 `docs/mockups/assets/`에 반입되고 뷰어 `/assets/*`로 서빙됨
  - [ ] 기존 `crest-hero.png` 사용처(목업 index·Gate, 뷰어 헤더/워드마크)가 신규 자산으로 전량 교체
  - [ ] 헤더용 축소본·파비콘 파생본 생성(투명 배경 유지), 레티나 대응 크기 정책 명시
  - [ ] `README.md`의 `orc-citadel-hero.png` 등 리포 대표 이미지 교체 여부 확인 후 반영

### FR-5: L2 잔여 정보구조 갭 전수 소진 (이관과 동시)

- **Description**: FR-1 이관 시 각 공간을 목업 정보구조 그대로 구현해 [handoff-viewer-mockup-gap.md](../../docs/handoff-viewer-mockup-gap.md) §2의 잔여 갭을 소진한다. 데이터가 없는 축은 정직 빈 상태(§6.2)를 유지한다.
- **Acceptance Criteria**:
  - [ ] Signal Spire: 3열(`288px 1fr 340px`) + Campaigns/Scope 필터 + Alert Feed 탭 + 알림 카드 구조 + Subscriptions (데이터 0 → 정직 빈)
  - [ ] Council: 단일 3열 그리드(중복 패널 결함 소멸) + 8 Agent 카드(초상·모델 칩) + 조사 루프 다이어그램
  - [ ] Witnesses: modality 필터 + Contradicting Evidence 자리 + 독립성 보정 블록
  - [ ] Archive: 3열(Sifter/Stacks/Codex) 통합 — 서버사이드 페이징·facet(2026-09-08 커밋 aea7965) 유지
  - [ ] Watchtower: KPI 5타일 + Stage Throughput/Failure 패널(백엔드 없는 항목은 명시적 범위 밖 선언)
  - [ ] Chronicle: Bitemporal Plane 상단 배치 + "두 축" 설명 3카드 + AS-OF 대비 패널
  - [ ] War Table: 그래프 레이아웃 판독 가능(라벨 겹침 해소) + panel-head 겹침 해소 + Chronicle rail 하단 고정

### FR-6: 파이프라인 모니터링 — Grafana 사이드카 부착 (G5)

- **Description**: 실수집 데이터가 흐르는 파이프라인(수집→파싱→dedup→추출→승격, 원격 prod scheduler nightly)을 모니터링하는 체계를 부착한다. 방향은 설계 정본이 이미 확정 — [design 11 §2.2](../../docs/design/11-observability-and-governance.md): "초기 구성은 **PostgreSQL + Grafana**, 확장 시 ClickHouse + Grafana". compose 스택(postgres 가동 중)에 Grafana OSS 서비스를 추가하고, 대시보드·데이터소스는 provisioning 파일로 커밋한다(코드로 관리, 수동 클릭 설정 금지). in-app Watchtower는 브리핑용 요약 뷰로 유지하고, 운영 drill-down은 Grafana가 담당한다.
- **선행 의존(핵심)**: 현행 SLO 관측 로그(`slo_observation_log`)는 **순수 in-memory·런 간 누적 없음**이라 Grafana가 읽을 영속 소스가 없다. 스케줄러 런 종료 시 run summary + slo_log 산출을 postgres 메트릭 테이블로 **flush하는 최소 배선**이 필요하다(관측 로그 영속화는 zone/graph 쓰기가 아니므로 §3-3 read-only 불변식과 무관한 운영 로그 계층).
- **Acceptance Criteria**:
  - [ ] `docker-compose.yml`/`prod.yml`에 `grafana` 서비스 추가 — loopback 바인딩 + SSH 터널 접근(기존 viewer 접근 정책과 동일), 익명 열람 가능한 read-only 조직 설정
  - [ ] datasource(postgres)·대시보드 JSON이 리포에 provisioning 파일로 커밋되어 재현 가능
  - [ ] 파이프라인 run 메트릭 postgres 영속 배선: run summary(시각·stage별 처리량·실패 수·소요) + SLO-05/06/07 관측치 + correlation_id 분해 가능 스키마([design 11 §2.2](../../docs/design/11-observability-and-governance.md) D1–D6 및 ADR-1102 정합)
  - [ ] 최소 대시보드 1종: 수집 성공률·freshness·stage 처리량·quarantine 추이 (데이터 없는 패널은 정직하게 No data)
  - [ ] Watchtower(FR-5)에서 Grafana로의 딥링크 제공 (운영 drill-down 이관 명시)

### FR-7: 데이터 존 브라우징 — 저장 형식 체험 도구 (G6)

- **Description**: 제품 뷰어(가공된 소비 뷰)와 별개로, **존에 쌓인 원 데이터를 저장 형식 그대로** 브라우징·질의하는 도구를 부착한다. 존 계층별로 이미 있는 것을 최대한 재사용한다:
  - **raw (lakehouse 오브젝트 층)**: 로컬 파일 트리 / prod MinIO 버킷 — **MinIO Console**(dev compose에 이미 `:9001` 활성)로 fetch.json·content.bin 오브젝트를 직접 브라우징.
  - **normalized·curated (DuckDB 존)**: 뷰어가 `.duckdb`에 **쓰기 잠금**을 쥐므로(실측 함정) 외부 도구의 직접 attach는 금지. 대신 기존 `DuckDBZone.export_parquet()`로 **parquet 스냅샷**을 내리고, **DuckDB UI 사이드카**(공식 `ui` 확장, 로컬 웹 노트북)가 `read_parquet`로 질의 — "컬럼나 파일로 쌓고 엔진은 분리"라는 lakehouse 패턴을 그대로 체험.
  - **postgres (mutation log SoT·메트릭)**: FR-6 Grafana의 **Explore**로 ad-hoc SQL 겸용 (별도 서비스 없음).
  - **neo4j·opensearch**: 자체 내장 UI(Neo4j Browser·Dashboards)가 이미 존재 — 접근 절차 문서화까지만 (신규 서비스 없음).
- **Acceptance Criteria**:
  - [ ] scheduler 런 종료 훅에서 parquet 스냅샷 export 배선 (선택 주입·비차단 — FR-6 flush와 동일 지점·규약)
  - [ ] DuckDB UI 사이드카 compose 서비스 — parquet 디렉터리 read-only 마운트, loopback + SSH 터널, 확장 설치는 이미지 빌드 시 1회(런타임 오프라인)
  - [ ] MinIO Console 접근 절차(prod SSH 터널) 문서화 — dev는 현행 유지
  - [ ] **체험 가이드 문서** `docs/operating/data-browsing.md`: 존 계층 → 저장 형식 → 브라우징 도구 → 예제 쿼리(segments 조인·dedup cluster·correlation drill-down) 매핑
  - [ ] 뷰어 `.duckdb` 파일에 대한 외부 동시 접근 금지 규칙 명문화 (잠금 함정 재발 방지)

## Non-Functional Requirements

- **Performance**: 공간당 초기 렌더가 현행 인라인 HTML 대비 체감 동등(정량 기준은 specs에서 확정 — 번들 크기 상한 포함). 10만+ 문서 축은 서버사이드 페이징 유지, 클라이언트 전량 로딩 금지.
- **Offline/의존성**: 외부 CDN 금지 — 폰트·자산·JS 전부 로컬 서빙. 런타임·배포에 node 불요. npm은 저작·빌드 시점 한정.
- **접근성/디자인**: `DESIGN.md`(SSOT) 준수 — WCAG AA 대비, 관계 상태 색+선형태+라벨 병기, 픽셀은 액센트 한정, `prefers-reduced-motion` 대응.
- **테스트**: 현행 라우트 스모크·`node --check` 가드의 SPA 대체 전략 필수 — 최소한 (a) 빌드 산출물 존재·서빙 스모크 (b) 컴포넌트 렌더 스냅샷/구조 가드 (c) 목업 빌드 가드 유지. TDD 선작성 규약 유지.
- **Maintainability**: 2체계(파이썬 페이지 + React) 공존 기간을 명시적으로 한정하고, 이관 완료 시 표시 계층 코드를 제거해 단일 체계로 수렴.

## Constraints

- **read-only 불변식(§3-3) 유지** — 그래프·존을 변경하는 쓰기 UI는 본 개편 범위 밖 (Open Question ③ 참조).
- **`stdlib only` 불변식 개정 필요** — 프런트 전면 전환은 기존 계획의 "Phase 4 확대 시 개정" 조건에 해당. 3단계 기록 절차(design 09 §1.3 → design README → ROADMAP §5)를 밟는다.
- **`DESIGN.md` = 디자인 SSOT 유지** — 색·형태 변경은 DESIGN.md 먼저, theme-citadel 재빌드로 전파. 픽셀/판타지는 자산 레이어 한정(기확정 방향).
- **Astryx beta(0.5.x) 버전 고정** — 정본은 `@astryxdesign/*` 스코프뿐(`astryx`·`astryx-ui`는 무관 패키지).
- **로고 원본 반입은 사용자 제공 필요** — 첨부 이미지 2종(가로 lockup·세로 crest)의 원본 PNG를 리포 경로에 저장하는 단계가 선행돼야 한다 (대화 첨부만으로는 파일 반입 불가).
- **원격 prod 배포 제약** — rsync → 원격 compose build 체계. 원격 호스트 npm 네트워크 접근을 가정하지 않는다.

## Out of Scope

- 백엔드·파이프라인 변경 (L3 데이터 트랙은 별도 — canonicalize O(n²) 해소, alert 영속화, valid_time 적재 등). 단 두 가지 예외: `/api/*` 응답의 **표시용 필드 추가**(specs에서 항목별 판단)와 **FR-6 메트릭 영속 flush 배선**(운영 로그 계층, 파이프라인 로직 무변경).
- New Campaign(조사 실행) 등 쓰기 UI (Open Question ③에서 별도 결정 전까지).
- BM25 전문 검색 (현행 ILIKE contains 유지, 정직 라벨링).
- 한글 웹폰트 도입 (기존 결정 유지 — 시스템 폴백. 용량·subset 전략은 별도 과제).
- 모바일 전용 최적화 (DESIGN.md의 선형 탐색 원칙만 훼손하지 않는 수준).

## Open Questions (전부 해소 — 2026-09-08)

1. **빌드 산출물 정책** → ✅ **dist 커밋** (theme-citadel·목업과 동일 방식. 런타임·배포 node 배제, rsync 무변경).
2. **이관 순서** → ✅ **브리핑 가치 순**: Gate → Witnesses → War Table → Archive → Spire → Council → Watchtower → Chronicle.
3. **쓰기 UI** → ✅ **비활성 자리만** (New Campaign 카드를 비활성 + "read-only 프로토타입" 표시로 존치. §3-3 불변).
4. **브리핑 모드** → ✅ **홈 대시보드 + 딥링크** (별도 프레젠테이션 뷰 없음).
5. **hairball 가드** → ✅ **subject 중심 서브그래프 기본 + `/api/graph_expand` 단계 확장** (기존 엔드포인트 활용, specs TS-5 상세).

## References

- [docs/plan-ui-design-system.md](../../docs/plan-ui-design-system.md) — Astryx 도입 계획 (Phase 0–2 완료, 본 spec이 Phase 3–4를 대체)
- [docs/handoff-viewer-mockup-gap.md](../../docs/handoff-viewer-mockup-gap.md) — L1/L2/L3 갭 전수 목록
- [DESIGN.md](../../DESIGN.md) — 디자인 SSOT (Citadel Nightwatch)
- [design-system/theme-citadel/README.md](../../design-system/theme-citadel/README.md) — 토큰 매핑·저작 함정
- [design-system/mockups/README.md](../../design-system/mockups/README.md) — 목업 SSG 저작 소스
- [docs/blueprint.md](../../docs/blueprint.md) §1.4 — 8공간 개념 계층
- 신규 로고 첨부 2종 (2026-09-08 대화) — 가로 lockup · 세로 crest 픽셀아트
