# 위임 지시문 — 미구현 페이지 viewer 구현 (목업 수준)

> 새 세션에 이 문서 전체를 전달한다. 목표: **목업 8페이지 중 미구현 5개 페이지를, 목업 충실도까지는 아니어도 실데이터가 흐르는 화면으로 viewer 에 구현**한다.

## 0. 컨텍스트 (30초 요약)

- 이 프로젝트는 temporal evidence intelligence 플랫폼 **Orc Citadel**. 백엔드 로직은 Phase 1~6 에서 **전부 구현·테스트 봉인**(스위트 1040 Green)됐다.
- UI 는 `prototype/orc_citadel/viewer.py` 단일 페이지(stdlib `http.server`, 포트 8791, read-only)뿐이다.
- 완성 화면의 청사진은 `docs/mockups/*.html` (8페이지 정적 목업, 2026-08-03 작성) — 디자인 토큰은 `DESIGN.md`.
- 화면 ↔ 기능 매핑 정본: `docs/blueprint.md` L118–125.

## 1. 작업 범위 (우선순위 순)

viewer 에 이미 부분 구현된 공간(Hall of Witnesses·War Table·Council Chamber·랭킹)은 **건드리지 않는다**. 아래 5개 미구현 페이지만 신설한다.

| 순위 | 페이지 | 라우트(제안) | 데이터 소스 (모두 기구현 모듈) |
| --- | --- | --- | --- |
| 1 | **Watchtower** (수집 관제) | `/watchtower` | `slo_nightly_gate.run_nightly_gate` · `watchtower_slo_alert.WatchtowerSloAlert.route` · `slo_observation_log` — SLO 판정표·경보·error budget |
| 2 | **Signal Spire** (알림 센터) | `/spire` | `signal_spire.SignalSpire`(5 트리거·fire-once·`make_alert` 스키마). 이벤트 원천은 `mutation_log` |
| 3 | **Grand Archive** (문서 탐색) | `/archive` | `duckdb_zone.NormalizedZone.documents()/segments()` · `prototype/data/raw/` 디렉터리 · dedup lineage (`dedup.py`) |
| 4 | **Chronicle Vault** (시간 탐색) | `/chronicle` | `graph_replay.replay_graph_at_tx` · `curated_zone` bitemporal 조회(`assertions_as_of`) |
| 5 | **Citadel Gate** (홈) | `/` (기존 페이지는 `/table` 등으로 이동 가능) | 각 존 카운트(raw/normalized/curated)·랭킹 상위 N·최근 알림 — 진입점 대시보드 |

각 페이지는 대응 목업(`docs/mockups/watchtower.html` 등)을 **참조**하되, 완전 복제가 아니라 **핵심 정보 구조**(목업의 패널·테이블 구성)를 실데이터로 채우는 수준이면 충분하다. Campaign 등록 같은 쓰기 개념은 **구현하지 않는다** (아래 불변식).

## 2. 지켜야 할 불변식·규약

1. **read-only** (설계 불변식 §3-3) — 쓰기 엔드포인트 금지. 조회·렌더링만.
2. **stdlib only** — FastAPI·신규 의존 추가 금지. 기존 `http.server` 패턴(`viewer.py` 의 `Handler`·`_j` 데코레이터·`_PAGE` 문자열)을 따른다.
3. **결정적·정직(honest-gap §6.2)** — 실측값이 없는 축(예: in-memory `slo_log` 는 런 간 누적 없음)은 가짜 데이터로 채우지 말고 `not-measured` 로 표시한다. Signal Spire 도 실제 mutation 이벤트에서 파생되는 알림만 렌더링하고, 없으면 빈 상태(`docs/mockups/empty-states.html` 참조)를 보여준다.
4. **AGENTS.md 준수** — TDD(라우트별 스모크 테스트 선작성), Tidy First(구조/행위 커밋 분리), 최소 구현. 목업의 픽셀 단위 재현·애니메이션·장식 일러스트는 범위 밖.
5. **UI 명칭은 세계관, 경로는 기술 용어 병기 허용** — 화면 표기는 `Watchtower · Ingestion Monitor` 식 병기 (blueprint L244).
6. 파일이 커지면 `viewer.py` 를 페이지 모듈로 분리해도 된다(구조 변경 커밋으로 분리). 단일 파일 유지도 허용.

## 3. 알려진 함정

- **DuckDB 잠금**: viewer 가 `curated.duckdb` 를 열면 다른 프로세스가 잠금 충돌한다. 연결은 read-only 로 열고, 수집 파이프라인과 동시 실행하지 않는다.
- **raw 형식 혼재**: `prototype/data/raw/` 에는 arXiv Atom 메타와 전체 page 두 형식이 의도적으로 공존한다(설계 04 §2.2, ADR-301). Grand Archive 목록에서 형식을 구분 표기하되 "중복"으로 취급하지 않는다.
- `_build()` 가 curated 전체를 그래프로 재구축하므로 시작이 느릴 수 있다 — 페이지 추가 시 lazy 초기화(현행 `Handler.facade is None` 패턴) 유지.

## 4. 검증 (완료 조건)

1. `prototype/.venv/bin/python -m pytest` — **기존 스위트 1040 무회귀** + 신규 라우트 스모크 테스트 Green.
2. `prototype/.venv/bin/python -m orc_citadel.viewer` 실행 후 5개 라우트가 실데이터(HTTP 200·비어있지 않은 본문 또는 정직한 빈 상태)를 렌더링.
3. 각 페이지가 대응 목업의 핵심 정보 블록을 1개 이상 실데이터로 구현했는지 자가 체크리스트 작성.

## 5. 완료 후 기록 (3단계 규칙)

ROADMAP 규칙에 따라: (1) 관련 design 문서(09-api 또는 해당 절)에 viewer 라우트 반영 여부 판단·수정 → (2) `docs/design/README.md` Spec version 갱신(해당 시) → (3) `docs/ROADMAP.md` §5 Changelog 에 기록. 커밋 메시지는 한글 관례(`feat(viewer): ...`)를 따른다.
