# P1 · Viewer 미구현 페이지 5종 신설 (Citadel Gate / Watchtower / Signal Spire / Grand Archive / Chronicle Vault)

## 배경

handoff `docs/handoff-viewer-pages.md`: 목업 8페이지 중 미구현 5개 페이지를, 목업 픽셀 재현은 범위 밖으로 하고 **실데이터가 흐르는(또는 정직한 빈 상태) 화면**으로 `viewer.py`(stdlib `http.server`, read-only)에 구현한다. 백엔드 로직(Phase 1~6, 스위트 1040 Green)은 전부 기봉인 — viewer는 기존 모듈을 조합·렌더링만 한다.

사용자 확정(2026-08-23): ① 기존 개발용 화면은 기능 그대로 보존하고 Citadel Gate 를 `/` 에 신설, ② 새 5개 페이지에 **경량 기능 내비**(공간 링크 나열) 구현. 목업 장식·애니메이션·일러스트는 항상 범위 밖.

## 실데이터 가용성 (honest-gap §6.2 근거)

| 페이지 | 지속 실데이터 | 결론 |
| --- | --- | --- |
| Citadel Gate `/` | curated(29 assertions·7 entities·586 mentions)·normalized(`oc.duckdb` documents 6·segments 90)·raw(8 source, 104,965 doc) | ✅ 실데이터 |
| Grand Archive `/archive` | `oc.duckdb` documents/segments + `data/raw/<source>/doc/` | ✅ 실데이터 |
| Chronicle Vault `/chronicle` | curated `assertions_as_of`(bitemporal) — `replay_graph_at_tx` 는 postgres SoT 필요(기동 안 됨) | ✅ curated + honest gap(postgres) |
| Watchtower `/watchtower` | SLO 관측·경보는 in-memory(런 간 미누적) — §6.2 정직 표시 | ⚠️ source 수집 사실은 실측, SLO 는 `not-measured` |
| Signal Spire `/spire` | alert 는 mutation 이벤트에서 파생·영속 저장소 없음 | ⚠️ 트리거 카탈로그 실상수, 피드는 정직 빈 상태 |

## 아키텍처

기존 `viewer.py` 는 단일 `_PAGE` 문자열 + `@_j` JSON 핸들러. 이를 확장하되 파일 비대 방지를 위해:
- **`viewer_pages.py` 신설**(구조 변경 커밋): 기존 `_PAGE` 와 모든 새 페이지 HTML 문자열을 이 모듈로 이동. 공유 nav·공유 CSS 조각도 여기. `viewer.py` 는 dispatch + JSON API 핸들러만 담당.
- **라우팅**: `Handler.do_GET` 의 `parsed.path` 로 dispatch.
  - `/` → **Citadel Gate**(신설)
  - `/table` → **기존 개발 화면**(랭킹/보고서/조사/근거, 기능 그대로 — Gate·nav 에서 진입)
  - `/watchtower` `/spire` `/archive` `/chronicle` → 신설
- **JSON API**(`@_j`, 기존 패턴): `/api/gate` `/api/watchtower` `/api/spire` `/api/archive` `/api/chronicle`.
- 모든 신규 HTML 페이지는 API 를 fetch 해 클라이언트 렌더(기존 `_PAGE` JS 패턴 재사용). 결정적·read-only(쓰기 엔드포인트 금지, 불변식 §3-3).
- DuckDB 는 **read-only 연결**(`duckdb.connect(path, read_only=True)`)로 열어 잠금 충돌 방지(handoff 함정 1). `_build()` 는 기존 패턴 유지. normalized/raw 카운트는 facade 구축과 무관하게 가벼운 read-only 연결 or 디렉터리 walk.

## 구현 (TDD, 페이지별 독립 커밋)

### Step 0 — 구조 변경 (Tidy First, 별도 커밋)
- `viewer_pages.py` 신설 + `_PAGE`(→`/table`), 신규 5페이지 템플릿, 공유 nav 헬퍼 배치.
- `viewer.py` 는 dispatch·핸들러만. **행위 변경 없음** 확인(기존 스위트 Green).

### Step 1 — Citadel Gate `/`
- `/api/gate`: raw 존(source×doc 수, `data/raw` walk) · normalized `documents` 수 · curated assertions/entities/mentions 수 · 랭킹 top 5(`facade._ranking.ranked(limit=5)`) · 신호 분포(`by_signal()`).
- 테스트: `test_viewer_gate.py` — 인메모리 facade 로 `/api/gate` 응답이 존 카운트·랭킹 포함.

### Step 2 — Watchtower `/watchtower`
- `/api/watchtower`: source 목록(이름·source_type·raw doc 수 — `data/raw` walk) · SLO 판정표(`run_nightly_gate({})` → 전항 `not-measured`, error_budget ratio=None 정직 표시).
- 테스트: SLO 5종 전부 `not_measured` 버킷·위반 0·`violation_ratio=None`(honest-gap), sources 목록 비칼럼 포함.

### Step 3 — Signal Spire `/spire`
- `/api/spire`: 5 트리거 카탈로그(`signal_spire.TRIGGER_TYPES`) + fire-once 규칙 + **빈 alert feed**(실 점화 없음 정직).
- 테스트: 트리거 5종 열거·`alerts=[]`(정직 빈 상태).

### Step 4 — Grand Archive `/archive`
- `/api/archive`: normalized `documents()`(+segments 수, `oc.duckdb` read-only) · raw source 목록(+doc 수) · dedup cluster 수(`curated.clusters()`, 현재 0 정직). raw/normalized 형식 구분 표기(설계 04 §2.2 — "중복" 아님).
- 테스트: documents 목록·raw source 카운트 반환, cluster 수 정직 반영.

### Step 5 — Chronicle Vault `/chronicle`
- `/api/chronicle`: `CuratedZone.assertions_as_of(valid_at, tx_at)` 기본 now → 현재 assertions + `supersedes_id` 체인 · 이벤트 타임라인(valid/tx range). 예시 프리셋 1~2종(목업 단순화). postgres SoT 미가동 → graph-replay 는 정직 `not-measured` 표기.
- 테스트: `assertions` 반환·supersedes 체인·AS-OF 필터 동작.

### Step 6 — 문서 3단계 규칙 + 회귀
1. `docs/design/09-api.md`: 프로토타입 viewer 라우트(`/watchtower` 등 SPA 개발 라우트, 프로덕션 REST 와 구분) 반영 여부 판단·메모.
2. `docs/design/README.md`: Spec version — 계약/스키마 추가 없음(뷰어 라우트만) → **1.1.0 유지** 예상, 필요시 판단.
3. `docs/ROADMAP.md` §5 Changelog 기록(한글 관례).
- 회귀: `prototype/.venv/bin/python -m pytest` 전체 Green(1040 이상·회귀 0).

## 앤티-골 (하지 않음)
- 목업의 픽셀·애니메이션·장식 일러스트 재현, Campaign 등록 등 쓰기 개념.
- 기존 Hall/War Table/Council/랭킹 화면 로직 수정(배치·내비 노출만).
- 실제 SLO 운용 축적·postgres 가동·수집 파이프라인 배선.

## 성공 기준
1. 신규 라우트 스모크 테스트 Green + 전체 스위트 회귀 0.
2. 실행 후 5개 라우트 실데이터 또는 정직한 빈/`not-measured` 상태 HTTP 200 렌더.
3. 페이지별 목업 핵심 정보 블록 ≥1 실데이터 구현 체크리스트 작성(handoff §4-3).
4. 3단계 문서 반영.

## 테스트 격리 주의
- 신규 테스트는 인메모리 zone(`CuratedZone(":memory:")`)/facade 로 실 `data/*.duckdb` 를 열지 않음(기존 `test_viewer_graph.py` 패턴). 실제 웹 렌더 검증은 실행 스모크로.
- api 핸들러 테스트는 `types.SimpleNamespace(facade=...)` + unbound 호출(기존 패턴).
- read-only 연결로만 DuckDB 접근 — 잠금 충돌 회피.

## 완료 검증 (2026-08-23, handoff §4-3 자가 체크리스트)

| 페이지 | 목업 핵심 정보 블록 | 실데이터/정직 상태 | 상태 |
| --- | --- | --- | --- |
| `/` Citadel Gate | 존 요약(raw/normalized/curated)·랭킹 top5·신호 분포 | raw 8 source/104,970 · normalized 6/90 · curated 29·7·586 · 랭킹 3 | ✅ |
| `/table` (기존 화면) | 랭킹·보고서·조사·근거 (기존 기능 무손실) | 29 어세션, 랭킹, E2E 조사 | ✅ 회귀 0 |
| `/watchtower` | source 상태표 + SLO 판정표 + error budget | source 8(source_type·doc 수 실측); SLO nightly 5 전항 `not-measured`(관측 미누적), budget ratio None | ✅ |
| `/archive` | normalized documents(+segments)·raw 목록·dedup lineage | normalized 6 docs(segment 수 포함)·raw 8 source·cluster 0, 형식 구분 표기 | ✅ |
| `/chronicle` | bitemporal assertions 범위·supersedes 체인·as-of | curated 29 assertions(valid/tx 범위)·supersedes 체인; graph_replay `available=False`(postgres 미가동, honest-gap) | ✅ |
| `/spire` | 5 트리거 카탈로그·fire-once·alert 피드 | TRIGGER_TYPES 5종(docstring 설명)·fire-once 규칙; alert feed 정직 빈(영속 저장소 없음) | ✅ |

**검증:** viewer 스모크 신규 10개 + 기존 graph = 15 Green · 전체 스위트 **1054 passed, 회귀 0** (2개 실패 `test_claude_cost`/`test_claude_judge` 는 base 커밋에서도 동일 — pre-existing, 본 작업 무관) · 6 라우트 라이브 HTTP 200 실데이터 렌더 실측.

