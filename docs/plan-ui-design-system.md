# UI 개선 계획 — Astryx 기반 디자인 시스템 도입

> 작성 2026-09-07. 전제: 갭 목록은 [`handoff-viewer-mockup-gap.md`](./handoff-viewer-mockup-gap.md) (L1 셸/자산 · L2 정보구조 · L3 데이터).
> 확정 결정 — **아키텍처: 하이브리드 파일럿** · **디자인 방향: `DESIGN.md` 유지(픽셀은 액센트 한정)**.

## 0. Astryx 실사 결과 (계획의 근거)

`@astryxdesign/core@0.5.3` · MIT · React 19 + StyleX peer dep · beta · unpacked 20.2MB.

| # | 확인 사실 | 계획에 미치는 영향 |
| --- | --- | --- |
| F1 | **`dist/astryx.css`(166KB)는 StyleX 원자 클래스를 해시 이름으로 컴파일**한 것. 1,894개 중 안정적 시맨틱 이름은 `.astryx-layout-header`·`.astryx-layout-footer`·`.astryx-nav-icon` **3개뿐**, 나머지는 `.x100vrsf` 형태 | **"파이썬 템플릿에 Astryx 클래스만 붙인다" 경로는 불가능.** 문서의 "no build step"은 *번들러 없이 React 컴포넌트 스타일이 먹는다*는 뜻 |
| F2 | `theme-*/theme.css` 는 **CSS 커스텀 프로퍼티 232개** + `@layer` / `@scope ([data-astryx-theme="…"])`. 엘리먼트 레벨 스타일은 `h1~h6·p·small·hr·code/pre` 한정 | **테마 레이어는 스택 무관 재사용 가능.** Phase 1(파이썬 뷰어)에서 그대로 소비 |
| F3 | 테마 저작 = `defineTheme({typography, motion, syntax, tokens, components})` → `astryx theme build <src> --out <css>` (`@astryxdesign/cli`) | `theme-citadel` 을 **정식 Astryx 테마 패키지로 저작** → 타 프로젝트 재사용 목표 달성 |
| F4 | 테마가 `--radius-none/inner/element/container/page/full` 스케일과 **컴포넌트/variant 단위 오버라이드**(`components: {badge: {base: {borderRadius, …}}}`)를 노출 | 형태·모서리까지 테마로 제어 가능 |
| F5 | 내장 7종(neutral·butter·chocolate·gothic·matcha·stone·y2k) 중 컨셉 부합 없음. **`gothic` 은 이름과 달리** 청회색 뉴트럴 + 파스텔 카테고리 다크 테마 | 커스텀 테마 저작이 전제. 다만 `gothic` 의 radius 기본값(4/8/12px)이 **DESIGN.md `rounded` 스케일과 정확히 일치** — 매핑 부담 낮음 |
| F6 | CLI + MCP 서버 제공 (`astryx component`·`docs`·`template`·`docs tokens`) | 에이전트 주도 개발과 잘 맞음. Phase 2 에서 활용 |
| F7 | ⚠️ npm `astryx`(424B·ISC·저자 무관)·`astryx-ui` 는 **별개의 무관한 패키지** | **정본은 `@astryxdesign/*` 뿐.** 오설치 방지를 위해 문서·스크립트에 스코프 고정 |

## 1. 컨셉 판정 — 픽셀은 액센트, 코어는 다크 전술-아카이브

`DESIGN.md`(디자인 SSOT)는 이미 픽셀/판타지 스킨을 **명시적으로 배제**한다:

- "UI는 판타지 스킨을 씌운 관리자 페이지가 아니라 … 시각적 무게 중심은 장식이나 캐릭터가 아니라 **데이터와 근거**"
- "**픽셀 폰트는 워드마크·작은 배지·게임적 상태 표현에만 제한**한다"
- "일관된 **rounded** 스케일(4/8/12/full) … rounded와 sharp corner를 혼용하지 않는다"
- "그림자에 의존하지 않는 **평면 + 경계 + 선택적 발광**", "무한 반복 점멸 금지"

→ 오크·레트로·픽셀은 **자산 레이어**(히어로 8·오크 초상 5·빈상태 6·crest 워드마크 = 현재 전부 미서빙)가 담당하고, 코어 UI는 고밀도 다크 데이터 인터페이스를 유지한다. 이 방향은 Astryx 의 성격과 충돌하지 않는다. **`DESIGN.md` 개정 불필요.**

**공용화 산출물의 정체:** "픽셀 테마"가 아니라 **`theme-citadel` = 다크 전술-아카이브 토큰셋**. 증거·불확실성·시간축을 다루는 다른 프로젝트에 그대로 이식 가능하다.

---

## 2. Phase 0 — `theme-citadel` 저작 (SSOT 확립) · ✅ 완료 (2026-09-07)

> 산출: `design-system/theme-citadel/` — `src/citadelTheme.ts`(저작) + `dist/theme.css`(생성물 커밋, 194 토큰 선언) + `README.md`(매핑표·함정).
> 회귀 가드: `prototype/tests/test_theme_citadel.py` 25개 — DESIGN.md 값 ↔ 생성 CSS 대조, node 불필요. 전체 스위트 **1210 passed**(pre-existing `test_claude_*` 2건 무관).
> 브라우저 실렌더 확인: `@scope`·`@layer` 적용, 표면 4단·관계색 9종·accent 버튼·monospace/parchment 전부 해소.

**산출물:** `design-system/theme-citadel/` — `src/citadelTheme.ts`(저작) + `dist/theme.css`(**생성물 커밋**) + `LICENSE` + `README.md`.

`dist/theme.css` 를 리포에 커밋하는 이유: 런타임·배포 어디에도 node 를 요구하지 않기 위해서다. node 는 **테마를 고칠 때만** 필요한 저작 도구다(폰트 vendoring 과 같은 성격).

**토큰 매핑** (`DESIGN.md` → Astryx):

| DESIGN.md | 값 | Astryx 토큰 |
| --- | --- | --- |
| `citadel-void` | `#07111C` | `--color-background-body` |
| `citadel-night` | `#0D1B2A` | `--color-background-surface` |
| `surface` | `#111820` | `--color-background-card` |
| `surface-variant` | `#26313A` | `--color-background-muted` · `--color-border` |
| `on-surface` | `#D6CCB8` | `--color-text-primary` |
| `on-surface-muted` | `#59636A` | `--color-text-secondary` |
| `primary` (war-green) | `#45E06F` | `--color-accent` |
| `error` / `uncertain` / `superseded` | `#E05252` / `#A78BFA` / `#59636A` | `--color-error` · `--color-data-*` |
| `ember` / `signal-amber` | `#E97824` / `#FFB13B` | `--color-warning` · `--color-data-*` |
| `parchment` | `#C8B58E` | 인용 표면 (커스텀 토큰) |
| `rounded sm/md/lg/full` | 4/8/12/9999px | `--radius-inner/element/container/full` — **기본값과 일치** |

**해결해야 할 불일치 2건:**
1. **폰트 역할이 3 vs 4.** Astryx 는 `body`/`heading`/`code`, `DESIGN.md` 는 여기에 **`display`(Cinzel 워드마크)** 가 더 있다. → `--font-family-display` 를 커스텀 토큰으로 추가하고 컴포넌트 오버라이드에서 참조.
2. **그림자·모션 기본값.** Astryx 는 `--shadow-*`·`--duration-*` 을 쓰고 `DESIGN.md` 는 "그림자 없음 / 무한 점멸 금지 / `prefers-reduced-motion` 시 제거". → 테마에서 shadow 를 경계선으로 치환하고 motion 을 축소.

**이름 이중화 방지:** `DESIGN.md` 는 의미론적 이름(`citadel-night`)을 SSOT 로 유지하고, `theme.css` 가 그 값을 Astryx 이름으로 발행하며, 뷰어 CSS 는 Astryx 이름을 쓴다. 기존 `--citadel-*` 은 얇은 alias 블록으로 한 단계만 남긴다.

**검증:** 232 토큰 중 뷰어 실사용분 매핑표 + `DESIGN.md` 색/형태 값과의 대조표를 `README.md` 에 남긴다.

---

## 3. Phase 1 — 목업 재작성 (Astryx SSG) · ✅ 완료 (2026-09-07)

> 산출: 저작 소스 `design-system/mockups/src/` → 출력 `docs/mockups/`(정본 승격). 10페이지(8공간 + index + empty-states) 328KB.
> 회귀 가드: `prototype/tests/test_mockups_build.py` 42개(테마 스코프·클라이언트 JS 0·핵심 블록·Astryx 컴포넌트 흔적·자산 참조 실재·토큰 하드코딩 금지). 전체 스위트 **1252 passed**(pre-existing `test_claude_*` 2건 무관).
> 브라우저 실렌더 8공간 전부 확인. **히어로 크기 정책** — 원본이 전 페이지 132px 고정 밴드였는데 히어로가 전부 1920×720(8:3)이라 세로 23% 만 보였다. 히어로가 있는 페이지는 전부 `aspect-ratio: 8/3` 을 지키고 상한으로 본문 공간을 지킨다 — 문서형 360px, 앱셸 300px. 상한이 없으면 2560px 뷰포트에서 960px 를 먹는다. 히어로가 없는 index·empty-states 는 평평한 밴드.
> **폰트 vendoring 동반 완료** — `design-system/fonts/`(12 faces·217KB·SIL OFL-1.1 동봉)로 A3 해소. 목업이 로컬 woff2 를 물어 Cinzel 워드마크·Space Grotesk·Inter 가 실제 적용된다(한글은 여전히 시스템 폴백 — 라틴 4서체에 한글 글리프 없음, 원본 동일).

**왜 여기가 먼저인가 (2026-09-07 실측으로 순서 변경).** Astryx 컴포넌트를 `renderToStaticMarkup` 으로 **정적 HTML 로 뽑을 수 있음을 실증**했다 — 번들러·SPA·클라이언트 JS 없이 산출물은 HTML 한 장 + CSS 3장(`reset.css`·`astryx.css`·`theme-citadel/theme.css`). React 는 빌드 시점 도구일 뿐이라 `theme-citadel` 빌드와 같은 지위다.

따라서 목업 재작성은 **백엔드·배포·테스트 전략 질문이 전혀 없는 무위험 구간**이면서, Phase 3 게이트 ②(목업 재현도)·③(테마·컴포넌트 충돌)을 **미리 실측**한다. 그리고 재작성된 목업은 그대로 **Phase 3 `frontend/` 스캐폴드**가 된다 — 목업과 앱이 같은 컴포넌트 코드를 쓰고 차이는 데이터 소스뿐(하드코딩 vs `/api/*`).

역으로 이 단계를 건너뛰고 Phase 2 만 하면, 소스가 React 인 목업을 파이썬 템플릿으로 **수작업 번역**하는 비용이 생긴다.

### 실증된 사실

| 확인 | 내용 |
| --- | --- |
| SSG 가능 | `dist` 가 순수 ESM 프리컴파일 → `node build.mjs` 로 직접 렌더. `'use client'`(420/600 파일)는 RSC 경계 표시일 뿐 SSR 을 막지 않는다 |
| 3+1 앱셸 | `Layout` 이 `header`/`start`/`content`/`end`/`footer` 슬롯 + `height:'fill'` 제공. `LayoutPanel` 은 `width`·`isScrollable`·`hasDivider` — 현재 뷰어가 손수 만드는 `grid-template-columns` 를 대체 |
| 빈 상태 | `EmptyState` 가 `icon: ReactNode` 슬롯 → `empty-*.png` 6종 직결. `title`/`description`/`actions`/`isCompact` |
| 테스트 훅 | 렌더 출력에 안정적 시맨틱 클래스(`astryx-card`·`astryx-badge`)와 `data-variant` 가 붙는다 — 스타일시트에는 없고 **컴포넌트가 런타임에 부여** |
| 중복 제거 | 현행 목업 9개 파일의 `<style>` 이 **2,541줄 / 전체 5,331줄의 48%** — 페이지마다 복제된 토큰·컴포넌트 CSS. 재작성하면 공유 테마로 접힌다 |

### 산출물

```
design-system/mockups/     저작 소스
├── build.mjs              SSG 드라이버
├── src/shell.mjs          공유 셸 (헤더·공간 탭·히어로)
├── src/ui.mjs             Astryx 헬퍼 + 도메인 시각 요소
├── src/svg/*.svg          원본에서 옮긴 도메인 SVG
└── src/pages/*.mjs        8공간 + index + empty-states

docs/mockups/              출력 (정본·커밋)
├── *.html *.css fonts/    생성물
├── assets/                히어로·초상·빈상태 PNG (생성물 아님)
└── illustration-prompts.md (생성물 아님)
```

JSX 를 쓰지 않고 `React.createElement` 로 저작한다 — 번들러 없음 성질을 끝까지 유지하기 위해서다. Phase 3 로 확대할 때 Vite/esbuild 도입은 게이트 ④·⑤에서 별도로 판단한다.

**출력은 `docs/mockups/` 정본을 덮어쓴다** (2026-09-07 승격 완료). 재작성 이전의 손으로 쓴 판본(2026-08-03)은 승격 직전 커밋에 남아 있고, 갭 분석의 기준선이 그 판본이다. `docs/mockups/` 에는 생성물이 아닌 것도 살므로(`illustration-prompts.md`·`assets/`) 빌드는 디렉터리를 통째로 지우지 않고 자기가 만드는 파일만 덮어쓴다.

### 범위 밖 (재작성해도 손으로 써야 하는 것)

- **도메인 시각화** — 그래프 캔버스·bitemporal plane 2축 SVG·provenance trail hop·엣지 타입 범례. Astryx 에 대응 컴포넌트가 없다. 특히 범례는 DESIGN.md 가 "색만으로 의미 전달 금지·선 형태 병기"를 요구하는데 Badge 로는 실선·이중선·점선을 표현할 수 없다 → Astryx 컨테이너 안에 SVG 직접 작성.
- **한글 폰트** — 라틴 4서체는 vendoring 으로 해소했으나 이 서체들에 한글 글리프가 없어 **Hangul 은 시스템 폴백**이다(원본 목업 동일). 한글 서체 도입은 DESIGN.md 에 정의가 없어 범위 밖 — 용량(수 MB) 때문에 subset 전략을 함께 정해야 한다.
- **상호작용** — 현행 목업은 JS 0 이고 SSG 산출물도 동일(파리티). 동작하는 목업을 원하면 하이드레이션은 별도 결정.

## 4. Phase 2 — 셸·자산 (파이썬 뷰어, stdlib 유지) · ✅ 완료 (2026-09-07)

> 산출: `viewer_static.py`(`/assets/*` 라우트 3갈래 + 404) · 셸에 테마·폰트 링크 + 스코프 루트 `<html>` · `:root` 토큰 별칭화 · 히어로 마스트헤드 8종 · 빈 상태 일러스트 6종 · 헤더 검색 전 페이지.
> **자산은 복제하지 않는다** — 히어로 PNG 19MB 는 `docs/mockups/assets` 원본을 참조하고, 컨테이너에는 `prototype/` 만 COPY 되므로 compose 바인드 마운트로 주입한다(`VIEWER_ASSETS_*` 로 덮어쓰기 가능).
> 배너 폭은 본문(`main max-width:1200px`)에 맞춘다 — 전폭이면 본문과 어긋나고 8:3 상한에 더 많이 걸려 세로가 잘린다(2560px 전폭 37% vs 1200px 80%).
> 회귀 가드: `test_viewer_static.py` 36개. 전체 스위트 **1299 passed**.


L1 갭 전체를 소진한다. Phase 3 의 성패와 무관하게 **손실 없는 투자**다.

| 순서 | 커밋 성격 | 내용 | 갭 |
| --- | --- | --- | --- |
| S1 | 구조 | `prototype/orc_citadel/static/` 신설 + `/assets/*` 라우트(MIME·경로 이스케이프 방어) + **404 처리**. `docs/mockups/assets/` PNG 22종을 배포 범위 안으로 복사 | A1·A8 |
| S2 | 구조 | `theme-citadel/dist/theme.css` + `@astryxdesign/core/reset.css` 를 static 으로 vendoring, `shell()` 에 `<link>` + `data-astryx-theme="citadel"` | — |
| S3 | 행위 | `viewer_pages.CSS` 의 `:root` 블록을 Astryx 토큰 소비 + alias 로 축소 | — |
| S4 | 행위 | masthead 히어로 8종 적용 | A2 |
| S5 | 행위 | 빈 상태 일러스트 6종 (`empty-states.html` 패턴) | A7 |
| S6 | 행위 | 헤더 검색을 `shell()` 레벨로 승격 (현재 8페이지 중 6곳 무동작) | A4 |
| S7 | 구조 | 폰트 — **Phase 1 에서 이미 vendoring 완료**(`design-system/fonts/dist/`). 뷰어는 이를 `/assets/fonts/` 로 서빙하고 `<link>` 만 걸면 된다 | A3 (해소됨) |

**테스트(TDD 선작성):** `/assets/*` 200 + Content-Type, 경로 탈출 차단, 미지정 경로 404, 8페이지 무회귀, 기존 `node --check` 인라인 JS 문법 가드 유지.

**Spec:** 표시 계층만 → **1.1.0 유지**.

---

## 5. Phase 3 — Signal Spire React 파일럿

**대상 선정 근거:** `/spire` 는 (a) 갭이 가장 크고 (b) `viewer_pages.py:1126–1137` 에서 유일하게 `_inject` 가 빠져 Wave 2 프런트가 통째로 없으며 (c) **실데이터가 0건**이라 빈 상태 구조가 주력 — 파일럿에서 잃을 게 없다.

- `frontend/` 신설: Vite + React 19 + `@astryxdesign/core` + `theme-citadel`
- 기존 `/api/spire` 를 그대로 소비 (백엔드 무변경)
- 뷰어는 빌드 산출물을 `/app/spire` 로 정적 서빙, 기존 `/spire` 는 롤백 경로로 존치
- 구현 범위 = 목업 3열(`288px 1fr 340px`) + Campaigns/Scope 필터 + Alert Feed 탭 + 알림 카드(before→after 델타·cause mutation·correlation·dedup key·`1회 점화` 배지·딥링크) + Subscriptions
- 데이터가 없는 축은 **정직 빈 상태 유지**(§6.2)

**판정 게이트 — 아래를 실측해 기록한 뒤 확대 여부를 결정한다:**

1. 번들 크기 · 초기 렌더 시간 (현행 인라인 HTML 대비)
2. Astryx 컴포넌트만으로 목업 3열·알림 카드 재현도
3. `theme-citadel` 이 컴포넌트 위에서 `DESIGN.md` 대로 보이는가 — 특히 **그림자·모션 기본값 충돌**(§2 불일치 2)
4. **오프라인·원격 빌드 가능성** — prod 는 rsync → 원격 compose build 이므로 원격 호스트의 npm 네트워크 접근 또는 산출물 사전 빌드 커밋 여부를 결정해야 한다
5. 테스트 전략 — 현행 라우트 스모크·`node --check` 가드를 SPA 에서 어떻게 대체할 것인가
6. **2체계 공존 유지비** — 파이썬 7페이지 + React 1페이지 상태의 실제 부담

## 6. Phase 4 — 판정 후 분기

- **확대:** 갭 순서(Council 중복 패널 → Archive → Watchtower → Chronicle → War Table → Witnesses → Gate)대로 이관. 이 시점에 `stdlib only` 불변식 개정과 3단계 기록 절차를 밟는다.
- **축소:** 파일럿 폐기. Phase 2 토큰 위에서 L2 갭을 파이썬으로 구현. `theme-citadel` 은 그대로 남아 타 프로젝트 자산이 된다.

## 7. 병행 트랙 — L3 데이터 · ✅ 적재 완료 (2026-09-07)

> **근본 원인은 데이터 부재가 아니라 드라이버 선택이었다.** `pipeline_full_smoke`(구 스모크)는
> extraction record 를 영속하지 않아 claim 이 `missing_provenance_record`(ADR-305)로 전량
> quarantine 된다 — 실측 722 claims 중 promoted **0**. 정식 진입점 `run_pipeline` 은 그 단계를
>포함해 같은 입력에서 **722/722** 를 승격시킨다.
>
> 신설 `prototype/scripts/rebuild_zones.py` — 대량 적재 드라이버가 없었다. 정식 경로만 쓰고,
> `.new` 로 만들어 성공 시에만 교체(직전은 `.bak`), 승격 0 이면 교체하지 않고 중단한다.
>
> 결과: normalized **6 → 105,252 docs / 823,629 segments** (전량, 실패 0) ·
> curated **29 → 722 assertions**, entities **7 → 25**, dup_clusters **0 → 528**.
> Hall of Witnesses 원문 왕복 **해소율 100%** (깨져 있던 핵심 기능 복구).
>
> **알려진 한계 — 파이프라인이 10만 규모에 안 선다.** `canonicalize_claims` 는 (subject,
> predicate) 그룹 내 쌍별 비교, `find_conflict_candidates` 는 5단 중첩이라 O(n²)다. 전량
> 105k 로 돌리면 2시간 넘게 100% CPU 로 산출물이 정지한다(실측 후 중단). curated 는 도메인
> 소스 781건으로 적재했다 — arXiv cs-CR 104,471건은 공급망 도메인 관련도가 낮다. normalized 는
> 선형이라 전량 유지. 2차 복잡도 해소는 별도 과제.


curated 29 assertions / normalized 6 docs vs raw 105,252. **어느 경로를 택하든 이게 해결되지 않으면 화면은 계속 비어 보인다.** 특히 Hall of Witnesses 의 3-hop 원문 왕복은 curated evidence 의 `doc_id` 가 normalized 존에 없어 현재 기능 자체가 무효다. Phase 2 와 병행 착수를 권장한다.

## 8. 리스크

| 리스크 | 대응 |
| --- | --- |
| Astryx beta(0.5.x) API 변동 | Phase 2 까지는 `theme-citadel` 만 의존. 버전 고정 + 생성 CSS 커밋으로 런타임 격리 |
| npm 이름 혼동 (`astryx` / `astryx-ui` 는 무관한 패키지) | 스코프 `@astryxdesign/*` 고정, 문서·스크립트에 명시 |
| 그림자·모션 기본값이 `DESIGN.md` 와 충돌 | Phase 0 에서 테마 레벨로 치환, Phase 3 게이트 ③에서 실측 |
| 2체계 공존 장기화 | Phase 4 판정을 미루지 않는다. 게이트 항목을 사전에 고정 |
| 원격 배포에 node 유입 | Phase 2 는 node 무관(생성물 커밋). Phase 3 은 게이트 ④의 명시적 결정 사항 |

## 9. 규약

read-only(§3-3) · 외부 CDN 금지(로컬 vendoring 은 허용) · honest-gap(§6.2) · TDD 선작성 · Tidy First 구조/행위 커밋 분리 · 표시 계층만이면 **Spec 1.1.0 유지** · 완료 시 3단계 기록(design 09 §1.3 → design README → ROADMAP §5). **Phase 4 확대 시에만** `stdlib only` 불변식 개정이 필요하다.
