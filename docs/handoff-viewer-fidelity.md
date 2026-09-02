# 위임 지시문 — viewer 목업 충실 UI 심화

> 새 세션에 이 문서 전체를 전달한다. 목표: 실데이터 화면 + 목업 공유 셸까지 적용된 viewer 8페이지를, **목업(`docs/mockups/*.html`)의 정보 구조·상호작용에 근접**하게 페이지 단위로 심화한다. 선행 위임(`docs/handoff-viewer-pages.md`, 완료)의 후속.

## 0. 컨텍스트 (30초 요약)

- viewer(`prototype/orc_citadel/viewer.py` + `viewer_pages.py`, stdlib `http.server`, 포트 8791, read-only)는 8페이지 전부 실데이터(또는 정직 빈 상태)로 렌더링한다: `/`(Citadel Gate)·`/watchtower`·`/archive`·`/chronicle`·`/spire`·`/table`(War Table·Council 개발 화면).
- 목업 공유 시각 셸(마스트헤드·공간 탭·DESIGN.md 토큰)은 `viewer_pages.shell()` 로 이미 적용됨(커밋 03e725e). **남은 갭은 페이지 본문의 정보 블록·상호작용**이다.
- API 는 `/api/gate|watchtower|archive|chronicle|spire` JSON + `api_facade.ApiFacade`(09 §2·§3 wire 계약: claim·evidence·provenance trail·investigation report·graph node/expand cursor).

## 1. 작업 범위 (페이지 단위 — 한 번에 1~2페이지씩)

**공통 1단계 — 갭 분석 선행**: 대상 페이지의 목업 HTML 과 현재 페이지를 나란히 열어, 목업의 패널/블록별로 `구현됨 / 실데이터 가능 / 데이터 없음(정직 빈)` 3분류 체크리스트를 먼저 작성하고 시작한다.

| 우선 | 페이지 | 목업 | 알려진 주요 갭 |
| --- | --- | --- | --- |
| 1 | War Table | `war-table.html` | 목업 핵심 **3+1 패널**(그래프 캔버스 + 상세/근거 패널 + 하단 보조) — 현재 `/table` 은 개발 화면. `get_graph_node/expand`(cursor) 로 클릭 확장, `get_claim_evidence`·`get_evidence_provenance` trail 연결 |
| 2 | Hall of Witnesses | `hall-of-witnesses.html` | Evidence 검사 전용 화면 분리 — provenance trail(claim→extraction_record char span→document, 원문 왕복 §3-2) 시각화 |
| 3 | Council Chamber | `council-chamber.html` | `get_investigation_report`(결론·by_predicate·open_questions·signal) 표시. **조사 '실행'은 쓰기라 범위 밖** — 기존 결과 조회만 |
| 4 | Citadel Gate / Watchtower / Archive / Chronicle / Spire | 각 대응 목업 | 목업의 미구현 보조 블록(필터·검색·시계열 등)을 실데이터 가능 범위에서 추가 |

- 클라이언트 상호작용(검색·필터·노드 확장·cursor 페이지네이션)은 **인라인 vanilla JS + 기존 `/api/*` fetch 패턴**으로.
- 빈 상태는 `docs/mockups/empty-states.html` 패턴을 따른다.

## 2. 지켜야 할 불변식·규약

1. **read-only** (§3-3) — 쓰기 엔드포인트 금지. Campaign 등록·조사 실행 등 쓰기 개념 미구현.
2. **stdlib only** — 신규 의존 금지. **오프라인 전제**: 외부 폰트/CDN/JS 라이브러리 불가 — 로컬 fallback 스택 유지. 그래프 시각화도 외부 lib 없이 (SVG/canvas 직접 or 목록형 우선).
3. **honest-gap (§6.2)** — 없는 데이터(예: postgres SoT 미가동 graph_replay, in-memory SLO 누적)는 가짜로 채우지 않고 `not-measured`/`available=False`/정직 빈 상태로.
4. **AGENTS.md** — 라우트·API 스모크 테스트 선작성(TDD), 구조/행위 커밋 분리(Tidy First). 픽셀 단위 재현·애니메이션·일러스트는 범위 밖.
5. **UI 세계관 명칭 + 기술 용어 병기** (blueprint L244), wire 계약 변경 시에만 Spec 번프 — 표시 계층만이면 Spec 1.1.0 유지.

## 3. 알려진 함정

- DuckDB 잠금: 연결은 read-only, 수집 파이프라인과 동시 실행 금지 (아침 07:07·07:37 nightly 시간대 주의 — APScheduler 상주 중).
- `_build()` 가 curated 전체 그래프 재구축이라 시작이 느림 — lazy `Handler.facade is None` 패턴 유지.
- `ApiFacade` 생성자가 `zone.claims()` 전체를 메모리에 올린다 — 페이지 렌더마다 재생성하지 말 것.
- cursor 는 opaque hex (`_hex_cursor`) — 클라이언트에서 파싱하지 않는다 (09 §1.4).

## 4. 검증 (완료 조건)

1. 전체 스위트 무회귀 (기준선 **1064 passed**, 2026-09-02) + 신규/변경 라우트 스모크 Green.
2. 라이브 기동 후 해당 페이지가 목업 대비 갭 분석 체크리스트의 `실데이터 가능` 블록을 전부 렌더링.
3. 페이지별 완료 시 체크리스트(구현/정직 빈/범위 밖)를 plan 문서로 남긴다 (선례: p1-viewer-pages 자가 체크리스트).

## 5. 완료 후 기록 (3단계 규칙)

(1) design 09 §1.3 프로토타입 뷰어 주석 갱신 → (2) `docs/design/README.md` Spec version (wire 계약 변경 시만) → (3) `docs/ROADMAP.md` §5 Changelog. 커밋 메시지 한글 관례(`feat(viewer): ...`).
