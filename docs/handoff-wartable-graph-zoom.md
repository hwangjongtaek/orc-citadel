# War Table · Temporal Evidence Graph 확대 장치 — handoff

> 작성 2026-09-10. 근거: `design-system/ui/graph.mjs`·`frontend/src/pages/table/main.jsx` 코드 실측.
> 범위: **표시 계층만** (read-only §3-3 불변, API·데이터 변경 없음). 완료 시 ROADMAP §5 기록.
>
> **상태: 완료 (2026-09-10).** Z1~Z3 구현 + 리뷰에서 인터랙션 결함 3건 실측 수정
> (scrim dim 부재·트랙패드 휠 과확대 → pinch 전용, 드리프트 클릭 삼킴, +/− 연타
> dblclick 리셋). ROADMAP §5 2026-09-10 항목이 정본.

## 0. 문제 — 왜 작게 보이는가 (실측)

| # | 사실 | 위치 |
| --- | --- | --- |
| F1 | SVG 는 고정 viewBox `0 0 900 560` + `width:100%` 뿐 — 컨테이너 폭에 **축소만** 되고 확대 수단이 없다 | `graph.mjs:16, 121-124` |
| F2 | 중앙 캔버스가 좌 288px(Campaign Map) + 우 372px(Evidence Inspector)에 끼임 → 1440px 뷰포트에서 실렌더 ≈ 760px (스케일 0.84), 1280px 에서 ≈ 600px (0.67) | `table/main.jsx:100, 155` |
| F3 | claim 라벨 9.5px·그룹 카운트 9px 이 위 스케일로 **6~8px** 실표시 — 판독 불가 | `graph.mjs:80, 100` |
| F4 | 확대·팬·전체화면 어포던스 0건 — 목업(`docs/mockups/war-table.html`)에도 없던 갭 (신규 개선) | — |

hairball 가드(중심+1링 그룹+2링 claim ≤100 노드, 결정적 각도 슬롯)는 **건드리지 않는다**
— 문제는 정보 밀도가 아니라 **렌더 크기**다.

## 1. 개선안 — UI 장치 2 + 1

### Z1 · Focus Mode 오버레이 (P0 — 체감 최대, 1커밋 가능)

panelHead(`War Table · Temporal Evidence Graph`) 우측에 `확대 ⤢` 버튼 →
`position:fixed; inset:0` 오버레이(배경 `var(--color-background)` + 헤더/닫기)에서
**동일한 `warGraph`를 뷰포트 전폭·전고로 렌더**.

- 상태(그룹 펼침 `expanded`·`page`·`selectedClaimId`)는 이미 `App` 상위 state —
  오버레이 안에서도 그룹 펼침/claim 선택/"+N 더 보기"가 그대로 동작하고,
  닫으면 선택이 Inspector 에 반영돼 있다 (상태 재사용, 이중화 금지).
- 닫기: 우상단 `✕` + `Esc`. ⚠ `Esc` 리스너는 ⌘K Palette(`palette.jsx`)와 공존해야
  한다 — 오버레이 열림 시에만 등록하고 capture 순서를 확인할 것.
- 오버레이 하단에 기존 `relationLegend()` + honest 문구 재사용.
- 브라우저 Fullscreen API(`requestFullscreen`)는 **채택 안 함** — 권한 UI·ESC 시맨틱
  충돌 대비 이득 없음. fixed 오버레이로 충분.

### Z2 · 캔버스 pan/zoom (P1 — 오버레이·인라인 공통)

viewBox 조작 방식 (레이아웃 좌표는 불변 → **결정성 유지**, 노드 재배치 없음):

- 휠 = 줌 (커서 앵커), 드래그 = 팬, 더블클릭 = 리셋.
- 우하단 컨트롤 `+ / − / ⟲(fit)` 버튼 — 터치패드/접근성 폴백.
- 줌 범위 clamp: 0.5× ~ 4× (4× 에서 9.5px 라벨 ≈ 38px 실표시).
- 구현: `warGraph` 는 pure 유지, 선택적 `view` prop(`{x,y,w,h}` → viewBox 문자열)만
  추가. 휠/드래그/버튼 상태는 React 래퍼 훅으로 — **`design-system/ui`(.mjs, 목업
  공유 1벌)에는 훅을 넣지 않는다**. 현재 `warGraph` 소비자는 frontend `table` 뿐
  (목업은 자체 정적 SVG)이라 prop 추가는 안전.
- viewBox 산술(줌 clamp·커서 앵커 좌표 변환·fit)은 **순수 함수로 분리**해
  `graph.mjs` 에 export — 저장소에 JS 테스트 러너가 없으므로 (아래 §3) 최소한
  로직을 검증 가능한 형태로 남긴다.

### Z3 · 인라인 캔버스 실높이 확보 (P2 — 소폭)

현재 인라인 SVG 는 폭 기준 종횡비(900:560)로만 크기가 잡힌다. `LayoutContent`
가용 높이를 채우도록 `height` 계산(또는 `max-height` + `preserveAspectRatio="xMidYMid meet"`)
— 세로 여백이 남는 와이드 화면에서 수 % 추가 확보. Z1/Z2 뒤에 해도 된다.

**검토 후 보류**: 좌우 패널 접기 토글 — 3열 정보구조(목업 정본)를 흔들고
Inspector 왕복 동선을 해침. Z1 이 같은 효과를 더 싸게 준다.

## 2. 구현 계획 (파일 단위)

| 파일 | 작업 | 내용 |
| --- | --- | --- |
| `design-system/ui/graph.mjs` | 수정 | `warGraph` 에 선택적 `view` prop · viewBox 산술 순수 함수(`clampView`·`zoomAt`·`fitView`) export. 기본값 = 현행과 동일 렌더 (기존 소비처 무변) |
| `frontend/src/lib/graph-viewport.jsx` | 신설 | `useGraphViewport()` 훅(휠·드래그·버튼·리셋) + `ZoomControls`·`GraphOverlay` 컴포넌트 |
| `frontend/src/pages/table/main.jsx` | 수정 | panelHead 에 `확대 ⤢` 버튼, 인라인 캔버스에 viewport 적용, 오버레이 마운트 |
| `frontend/dist/*` | 재빌드 | `cd frontend && npm run build` — **dist 는 커밋 대상** |
| `prototype/tests/test_frontend_dist.py` | 수정 | 기존 계약(외부 오리진 0·번들 실재) 자동 커버 + `table.js` 에 확대 어포던스 마커(aria-label) 존재 검사 1건 추가 |

권장 커밋 분리 (Tidy First): ① `graph.mjs` view prop + 순수 함수 (행위 무변, 구조) →
② Z1 오버레이 → ③ Z2 pan/zoom → ④ Z3. ①은 렌더 결과가 바이트 동일해야 한다.

## 3. 검증

- **로컬 실기동**: `.venv/bin/python -m orc_citadel.viewer` → `/table` 에서
  확대 버튼·오버레이·휠 줌·Esc·⌘K 공존·claim 선택 → Inspector 반영 왕복 확인.
- **스위트**: `cd prototype && .venv/bin/python -m pytest -q` — dist 계약·라우트
  스모크 Green (현재 1367).
- JS 단위 러너는 저장소에 없음(빌드 도구는 저작 도구, dist 커밋 정책) — viewBox
  산술은 순수 함수 분리로 갈음하고, 러너 도입은 이 handoff 범위 밖.
- a11y 최소선: 버튼 `aria-label`, 오버레이 `role="dialog"` + `Esc`, 포커스 복귀.

## 4. 배포

구현 완료 후: commit(dist 포함) → push → `scripts/deploy.sh orchwang-macbookpro`
(viewer 는 dist 를 ro 마운트로 서빙하므로 rsync 만으로 반영, 이미지 재빌드 불필요하나
deploy.sh 표준 경로 사용) → 터널로 `/table` 실측.

## 5. 규약 (기존과 동일)

read-only(§3-3) · 외부 CDN/오리진 금지 · honest-gap(§6.2) · dist 커밋 ·
Tidy First 구조/행위 분리 · **표시 계층만이므로 Spec 1.2.0 유지** ·
완료 시 ROADMAP §5 changelog 기록 · 커밋 트레일러 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
