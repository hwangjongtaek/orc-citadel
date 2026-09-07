# viewer ↔ 목업 잔여 갭 — UI 추가 작업 리스트

> 작성 2026-09-07. 근거: 로컬 viewer(8791) 8라우트 **실기동 렌더 실측** + `docs/mockups/*.html` 대조 + `viewer_pages.py`·`*_ext.py` 코드 확인.
> 선행 위임 `handoff-viewer-pages.md`(완료)·`handoff-viewer-fidelity.md`(완료, ROADMAP §5 "remaining-gaps 전수 소진") **이후에도 남아 있는** 갭만 담는다.
> 실측 데이터 기준: raw 105,252 docs / normalized 6 docs·90 segments / curated 29 assertions·7 entities·29 claims·dedup 0.

## 0. 요약 — 왜 아직 "미완성"으로 보이는가

세 층위가 겹쳐 있다. 층을 섞어서 잡으면 안 된다.

| 층 | 내용 | 성격 |
| --- | --- | --- |
| **L1 · 셸/자산** | 히어로·초상·빈상태 PNG 22종 **전부 미서빙**, 웹폰트 4종 **미로딩**, 헤더 검색 6/8 페이지 무동작 | 순수 UI. 가장 큰 "완성도" 체감차 |
| **L2 · 페이지 정보구조** | 8페이지 중 **5페이지가 목업의 다열 앱셸이 아니라 단일 컬럼 적층**(이모지 h2 나열) | 순수 UI |
| **L3 · 데이터** | curated 29건·normalized 6건뿐, object_literal 전부 null, valid_time 전부 null, alert/contradicts/dedup 0 | **UI로 못 메움**. §3 별도 트랙 |

L3 때문에 L1·L2 를 다 채워도 화면은 여전히 비어 보인다. **L3 를 먼저 또는 병행**해야 한다.

---

## 1. L1 — 전역 셸 (전 페이지 공통)

| # | 항목 | 현재 실측 | 목업 | 비고 |
| --- | --- | --- | --- | --- |
| A1 | **정적 자산 라우트 `/assets/*` 부재** | `GET /assets/gate-hero.png` → **200 + Gate HTML**(PNG 아님). 미지정 경로가 전부 Gate 로 폴백 | `docs/mockups/assets/` 22종 참조 | 라우트 신설 + `_page_for` 404 처리. 오프라인 제약과 무관(로컬 파일) |
| A2 | masthead 히어로 배경 8종 미적용 | flat gradient 108px 밴드 | `*-hero.png` center/cover | A1 선행 |
| A3 | **웹폰트 미로딩** | `--font-display:"Cinzel"` 등 4종 선언만, `@font-face`·`<link>` **0건** → 전 페이지 system-ui/Georgia 폴백 | Cinzel/Space Grotesk/Inter/JetBrains Mono | OFL 폰트 로컬 vendoring(`/assets/fonts/`) 필요. CDN 금지 규약은 유지 |
| A4 | **헤더 검색이 6/8 페이지에서 무동작** | `SEARCH_JS` 가 `/` 에만 주입. `/archive` 는 자체 contains 검색. `/table`·`/witnesses`·`/council`·`/watchtower`·`/chronicle`·`/spire` 는 입력만 있고 죽어 있음 | 전 페이지 동작 | `shell()` 레벨로 승격 |
| A5 | Signal Spire 칩 하드코딩 | `Signal Spire · 0` 문자열 고정 | 미확인 알림 수 | L3-C3 선행 |
| A6 | 앱셸 레이아웃 불일치 | `main{max-width:1200px}` 문서 스크롤 | `.app{height:100vh;grid-rows:auto 1fr auto}` 전폭 + 패널 내부 스크롤 | L2 다열화의 전제 |
| A7 | 빈 상태 일러스트 6종 미사용 | 텍스트 한 줄 | `empty-*.png` + 문구 | `empty-states.html` 패턴. A1 선행 |
| A8 | 404 없음 | 오타 경로가 Gate 200 | — | A1 과 같은 커밋 |

---

## 2. L2 — 페이지별 정보구조

우선순위는 **갭 크기 × 실데이터 가능성** 순.

### P0-1. Signal Spire `/spire` — 갭 최대, ext 미주입
`viewer_pages.py:1126–1137` 에서 **`PAGE_SPIRE` 만 `_inject` 대상에서 빠져 있다.** Wave 2 프런트 작업이 통째로 없다.

- 3열(`288px 1fr 340px`) 없음 → 트리거 카탈로그 표 + 빈 피드 두 덩이만, 화면 60% 공백
- **좌열 없음**: Campaigns 필터 · Scope 필터(안읽음/전체/material)
- **중앙 없음**: Alert Feed 탭(안읽음·전체·확인됨), 최신순 정렬
- **알림 카드 구조 없음**: confidence before→after 델타, 근거 지지/반대 증감, Cause·mutation, correlation, 독립 증거 수, `1회 점화` 배지, dedup key, `War Table에서 보기`/`Hall of Witnesses` 딥링크
- **우열 없음**: Subscriptions 패널
- ⚠️ **L3-C3 선행**: alert 영속 저장소가 없어 실데이터 0. 카드 구조는 만들되 빈 상태 유지가 정직

### P0-2. Council Chamber `/council` — **중복 패널 구조 결함**
base 3열 그리드와 ext 3열 그리드가 **병합되지 않고 세로로 적층**되어, `Stopping · Cost · Audit`(base)와 `Stopping · Audit`(ext) 두 패널이 한 화면에 동시에 보인다. Agent Catalog·Investigation Trace 도 두 번째 그리드에 따로 있다.

- 두 그리드를 목업의 단일 `320px 1fr 372px` 로 병합
- 8 Agent 카드에 오크 초상(`char-*.png`)·모델 라우팅 칩(`opus-4-8`/`sonnet-5`) 없음
- 조사 루프 12스텝 다이어그램(plan→retrieve→gaps→search→extract→resolve→update→counter→stopping→synthesize→audit) 없음
- 발언 타임라인(에이전트·시각·근거·불확실성 카드) 없음 — 현재 `조사 trace` 클릭 시 텍스트 블록
- Cost `LLM_USD`/`TOKENS` `—` (미영속, 정직 갭)

### P0-3. Hall of Witnesses `/witnesses` — **핵심 기능이 현 데이터에서 무효**
페이지 존재 이유인 **결과→원문 3-hop 왕복**이 우측 패널 `원문 미가용 · normalized 존 세그먼트 없음` 로 끝난다. curated evidence 의 `doc_id`(예: `doc-086e5a28…`, `doc-5b5b6a26…`)가 normalized 6건에 **없다**(L3-C1). 12건 중 소수만 해소된다.

- claim 목록 **29행이 전부 `announces · —`** — `object_literal` null·`surface_fragment` 가 단어 1개(`enable`)라 식별 불가 (L3-C2)
- Modality 필터(fact/asserted/opinion/prediction) 없음
- Contradicting Evidence 섹션 없음 (데이터 0 — 정직 빈으로라도 자리 확보)
- 독립성 보정 설명 블록(`dup_cluster` 로 근거 N건 → 독립 M건) 없음

### P1-1. Grand Archive `/archive`
- 목업 3열(`Sifter 300px | Stacks 1fr | Codex 380px`) → **단일 컬럼 적층**
- Sifter facet 이 두 곳으로 분산: 상단 `source_type` 만, `language`/`dedup role`/`publication 정렬`/`본문 contains` 는 하단 별도 "Archive Ext" 섹션
- `publication_time` 기간 슬라이더 없음
- 전문 검색이 **BM25 아님** — `/api/search` 는 text contains (코드 주석에 명시). 목업은 `BM25 · 전문 검색`
- dedup lineage 뱃지(● root / ○ derived / ◆ independent)·클러스터 그룹 헤더 없음 (`dedup_clusters=0`)

### P1-2. Watchtower `/watchtower`
- KPI 스트립 **3타일**(Sources/Freshness/Documents) ↔ 목업 **5타일**: `Ingestion Backlog`·`실패율(24h)`·`Dead-letter 유입` 없음
- **Pipeline · Stage Throughput 패널 전무** — S1 Fetch / S3 Parse·Normalize / S4 Dedup 의 docs/min·backlog·실패율
- **Correlation ID 전파 표시 전무** (fetch S1 → doc S2 → parse S3 → dedup S4)
- **Failure · Dead-letter 패널 전무** — 백엔드 모듈 자체 없음(`grep dead_letter` 0건) → 신규 백엔드 또는 명시적 범위 밖 선언 필요
- Sources 표 컬럼 부족: `Freshness`·`성공률`·`Backlog`·`License`·`schedule.cron` (현재 source/type/문서수 3열)
- SLO 5항 전부 `not-measured` — 로컬 in-memory 미누적. 원격 prod 축적분 조회 경로가 없음

### P1-3. Chronicle Vault `/chronicle`
- 목업 1순위 패널인 **Bitemporal Plane(2축 SVG)이 페이지 하단**으로 밀리고, 상단은 스타일 없는 raw `input` 폼 2개
- "두 축이 답하는 질문" 3카드 설명 블록(Valid time / Transaction time / Supersession) 없음
- AS-OF Snapshot 우측 패널(현재 신뢰 카드 ↔ superseded 카드 대비) 구조 부족
- ⚠️ `valid_from`/`valid_to` **29건 전부 `—`**(`bounds.valid_min/max` null) → 평면 X축에 실데이터 없음 (L3-C4)
- `supersedes_chain` 0건, `graph_replay.available=False`(postgres SoT 미가동) — 정직 갭 유지

### P1-4. War Table `/table`
3열 골격은 있으나 렌더 품질 결함:
- **그래프 캔버스가 판독 불가** — 29 claim 을 단일 중심 방사형으로 배치해 라벨이 전부 겹치고, 캔버스가 패널 폭의 1/3만 사용
- **`panel-head` 텍스트 겹침** — `CAMPAIGN MAP` 2줄 줄바꿈 + `SUBJECTS·3 SUBCLAIMS` 충돌
- Evidence Inspector claim 카드가 전부 `ANNOUNCES · —` (L3-C2)
- Chronicle rail 이 스크롤 아래 (목업은 고정 3행 하단)
- contradicts / Seer 후보 정직 빈 (파사드 미확장)

### P2. Citadel Gate `/`
- **New Campaign 카드(질문 입력 + Scope 4필터 + 조사 실행)** — 쓰기라 **범위 밖**(불변식 §3-3). 목업 대비 **영구 갭으로 문서에 명시**할 것 (현재 암묵적 누락)
- 프로세스 3단계 스트립(Scouts → Seers·Council → 보고서) + 오크 초상 없음
- `crest-hero.png` 96px 워드마크·태그라인 블록 없음
- Campaign 카드가 subject 랭킹으로 대체 — 목업의 상태 배지(Running/Paused/Done)·최근 이벤트 라인 없음 (쓰기 개념 부재로 일부는 범위 밖)
- Watchtower 요약이 4타일이 아니라 표

---

## 3. L3 — 데이터/백엔드 선행 (UI 작업으로 못 메움)

| # | 사실 (실측) | UI 영향 |
| --- | --- | --- |
| C1 | curated 29 assertions·7 entities, normalized **6 docs** vs raw **105,252** — 파이프라인 미실행 | **대부분 화면이 비어 보이는 최대 원인**. Witnesses 원문 왕복 실패, Archive Stacks 6행 |
| C2 | 모든 claim `object_literal=null`, `surface_fragment` 단어 1개, predicate 전부 `announces` | claim 카드 29행이 전부 동일 표기 → Witnesses·War Table·Council 목록 무의미 |
| C3 | alert 영속 저장소 없음 (in-memory fire-once) | Signal Spire 영구 빈 |
| C4 | `valid_from/valid_to` 전부 null | Chronicle 평면 X축 무의미 |
| C5 | `dedup_clusters=0`, `url_groups=[]` | Archive lineage 뱃지·Stacks 클러스터 헤더 무의미 |
| C6 | contradicts 0, Seer 미영속 | War Table·Witnesses 반증 섹션 영구 빈 |
| C7 | postgres SoT 미가동 | `graph_replay.available=False` |
| C8 | 로컬 `slo_log` 미누적 · 원격 prod 축적분 조회 경로 없음 | Watchtower SLO 5항 전부 not-measured |

---

## 4. 권장 순서

1. **A1·A2·A7·A8** (정적 자산 라우트 + 히어로/빈상태) — 1커밋, 체감 개선 최대
2. **P0-2** Council 중복 패널 병합 — 명백한 구조 결함
3. **A4** 헤더 검색 `shell()` 승격
4. **L3-C1/C2** 파이프라인 재실행으로 curated·normalized 실적재 (UI 아님, 병행 트랙)
5. **P0-1** Spire 3열 + 알림 카드 골격 (빈 상태 유지)
6. **P1-1/2/3** Archive·Watchtower·Chronicle 다열화 (A6 선행)
7. **P1-4** War Table 그래프 레이아웃·panel-head 수정
8. **A3** 폰트 vendoring, **P2** Gate

## 5. 규약 (기존과 동일)

read-only(§3-3) · stdlib only · 외부 CDN 금지(로컬 자산은 허용) · honest-gap(§6.2) · TDD 라우트 스모크 선작성 · Tidy First 구조/행위 커밋 분리 · 표시 계층만이면 **Spec 1.1.0 유지** · 완료 시 3단계 기록(design 09 §1.3 → design README → ROADMAP §5).
