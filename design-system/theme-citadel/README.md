# theme-citadel — Citadel Nightwatch

[`DESIGN.md`](../../DESIGN.md)(디자인 SSOT) 토큰의 **실행 가능한 발행본**. [Astryx](https://astryx.atmeta.com/) 테마 계약(`defineTheme`)으로 저작하고 `astryx theme build` 로 CSS 를 생성한다.

값의 정본은 `DESIGN.md` 다. 색·형태를 바꿀 때는 **`DESIGN.md` 를 먼저 고치고** `src/citadelTheme.ts` 에 반영한 뒤 재빌드한다.

## 왜 생성물(`dist/theme.css`)을 커밋하는가

뷰어는 stdlib `http.server` 이고 오프라인·무의존이 불변식이다. 생성된 CSS 를 커밋해 두면 **런타임과 배포 어디에도 node 가 필요 없다**. node 는 테마를 고칠 때만 쓰는 저작 도구이며, 폰트 vendoring 과 같은 성격이다.

## 빌드

```bash
npm install          # 저작 도구만 (@astryxdesign/cli · core)
npm run build        # → dist/theme.css (+ citadel.js · 타입 선언)
```

`⚠ Theme "citadel" names fonts it does not load` 경고는 정상이다 — 폰트 로딩은 소비자 책임이고, 뷰어가 `/assets/fonts/` 에서 `@font-face` 로 공급한다(CDN 금지 규약).

## 소비

```html
<link rel="stylesheet" href="/assets/theme-citadel.css" />
<body data-astryx-theme="citadel">
```

토큰은 `@scope ([data-astryx-theme="citadel"])` 로 스코프되어 전역을 오염시키지 않는다. React 프로젝트는 `citadelTheme` 을 `<Theme theme={citadelTheme}>` 에 그대로 넘기면 컴포넌트까지 같은 토큰을 쓴다.

## 토큰 매핑

### 코어 (Astryx 표준 이름 — 타 프로젝트 이식 가능)

| DESIGN.md | 값 | Astryx 토큰 |
| --- | --- | --- |
| `citadel-void` | `#07111C` | `--color-background-body` · `--color-on-accent` |
| `citadel-night` | `#0D1B2A` | `--color-background-surface` |
| `surface` | `#111820` | `--color-background-card` · `--color-background-popover` |
| `surface-variant` | `#26313A` | `--color-background-muted` · `--color-border` · `--color-track` · `--color-skeleton` |
| `on-surface` | `#D6CCB8` | `--color-text-primary` · `--color-icon-primary` · `--color-on-dark` |
| `on-surface-muted` | `#59636A` | `--color-text-secondary` · `--color-border-emphasized` · `--color-icon-secondary` |
| `primary` (war-green) | `#45E06F` | `--color-accent` · `--color-success` |
| `error` | `#E05252` | `--color-error` · `--color-text-red` |
| `signal-amber` | `#FFB13B` | `--color-warning` · `--color-text-yellow` |
| `uncertain` | `#A78BFA` | `--color-text-purple` |
| `superseded` | `#59636A` | `--color-text-gray` |
| `ember` | `#E97824` | `--color-text-orange` |
| `rounded` sm/md/lg | 4 / 8 / 12px | `--radius-inner` / `--radius-element` / `--radius-container` |
| `headline-*` | Space Grotesk | `--font-family-heading` |
| `body-*` | Inter | `--font-family-body` |
| `data-md` | JetBrains Mono | `--font-family-code` |

`--color-shadow` 는 `transparent` 로 둔다 — DESIGN.md 의 "그림자에 의존하지 않는 평면 + 경계 + 선택적 발광" 모델.

### 도메인 (`localTokens` — Astryx 코어에 대응물 없음)

Astryx 는 `--astryx-theme-<name>-*` 철자를 강제한다. 소비자는 얇은 alias 로 짧은 이름을 만든다.

| DESIGN.md | 값 | 토큰 |
| --- | --- | --- |
| `parchment` | `#C8B58E` | `--astryx-theme-citadel-parchment` |
| `secondary` (seer-green) | `#20B85A` | `--astryx-theme-citadel-seer-green` |
| `ember` | `#E97824` | `--astryx-theme-citadel-ember` |
| `signal-amber` | `#FFB13B` | `--astryx-theme-citadel-signal-amber` |
| `crimson` | `#7B2833` | `--astryx-theme-citadel-crimson` |
| `uncertain` | `#A78BFA` | `--astryx-theme-citadel-uncertain` |
| `superseded` | `#59636A` | `--astryx-theme-citadel-superseded` |
| `headline-display` | Cinzel | `--astryx-theme-citadel-font-display` |

## 저작 시 함정

1. **`--color-accent` 는 `tokens` 로 고정한다.** `color: {accent}` 시드는 HCT 로 정규화되어 `#45E06F` → `#47E270` 로 표류한다. `tokens` 로 되돌릴 때 `--color-on-accent` 도 **함께** 지정해야 한다 — 이 토큰만 시드에서 대비 계산으로 구워져 자동으로 따라오지 않는다(`--color-accent-muted`·`--color-text-accent`·`--color-icon-accent` 는 `var(--color-accent)` 참조라 따라온다).
2. **컴포넌트 키는 kebab-case 이고 검증된다.** `input` 은 없다 — `text-input` 이다. 오타는 `⚠ Unknown component` 경고로만 나오고 빌드는 성공하므로 경고를 흘리지 말 것. 목록은 `npx astryx component`.
3. **다크 전용.** DESIGN.md 에 light 모드 정의가 없다. 토큰 값은 `[light, dark]` 튜플이 아니라 단일 문자열로 쓴다.
4. **npm 이름 주의.** 정본은 `@astryxdesign/*` 스코프뿐이다. `astryx`·`astryx-ui` 는 Meta 와 무관한 별개 패키지다.

## 회귀 가드

`prototype/tests/test_theme_citadel.py` 가 생성물을 SSOT 값과 대조한다(node 불필요). 재빌드 없이 `DESIGN.md` 만 고치면 실패한다.

```bash
prototype/.venv/bin/python -m pytest tests/test_theme_citadel.py
```

## 다른 프로젝트에서 쓰려면

이 디렉터리는 자체 완결적이다. `src/citadelTheme.ts` + `package.json` 만 옮기면 별도 패키지로 추출할 수 있다. 추출 시 `LICENSE` 를 추가하고 `private: true` 를 해제한다.
