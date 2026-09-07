/**
 * Citadel Nightwatch — Orc Citadel Astryx 테마
 *
 * `DESIGN.md`(디자인 SSOT) 토큰의 실행 가능한 발행본. 값의 정본은 DESIGN.md 이며
 * 이 파일은 그것을 Astryx 토큰 이름으로 옮긴 것이다. 값을 바꿀 때는 DESIGN.md 를
 * 먼저 고치고 여기에 반영한다.
 *
 * 컨셉: 어두운 석재(Basalt) 표면 위에서 검증된 evidence trail 과 지식 그래프만
 * 빛나는 다크 전술-아카이브. 판타지 스킨이 아니며 시각적 무게 중심은 데이터와
 * 근거다. 픽셀·오크 감성은 자산 레이어(히어로·초상·빈상태·워드마크)가 담당한다.
 *
 * 빌드: `npm run build` → `astryx theme build src/citadelTheme.ts --out dist/theme.css`
 * 생성된 `dist/theme.css` 는 커밋한다 — 런타임·배포에 node 를 요구하지 않기 위해서다.
 */

import {defineTheme, defineSyntaxTheme} from '@astryxdesign/core/theme';

/**
 * Syntax 팔레트 — Codex(문서 상세)·source span 원문 표시용.
 * DESIGN.md 의 parchment/ember/uncertain 계열에서 파생한 낮은 채도 조합.
 */
const citadelSyntax = defineSyntaxTheme({
  name: 'citadel-nightwatch',
  tokens: {
    keyword: '#A78BFA', // uncertain — 구조 키워드
    string: '#C8B58E', // parchment — 원문 인용
    comment: '#59636A', // on-surface-muted
    number: '#FFB13B', // signal-amber
    function: '#45E06F', // primary — war-green
    type: '#20B85A', // secondary — seer-green
    variable: '#D6CCB8', // on-surface
    operator: '#59636A',
    constant: '#E97824', // ember
    tag: '#E05252', // error
    attribute: '#FFB13B',
    property: '#20B85A',
    punctuation: '#59636A',
    background: '#111820', // surface
  },
});

export const citadelTheme = defineTheme({
  name: 'citadel',

  /**
   * 타이포그래피 — DESIGN.md 4역할 중 Astryx 가 받는 3역할.
   * display(Cinzel 워드마크)는 Astryx 토큰 표면에 없어 localTokens 로 발행한다.
   *
   * scale base 16 = DESIGN.md `body-md`. ratio 1.2 는 고밀도 데이터 UI 기준
   * (1.25 는 헤드라인이 테이블 화면에서 과하게 커진다).
   * 폰트 파일 로딩은 소비자 책임 — 뷰어가 `/assets/fonts/` 에서 @font-face 로 공급한다.
   */
  typography: {
    scale: {base: 16, ratio: 1.2},
    body: {
      family: 'Inter',
      fallbacks: 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
    },
    heading: {
      family: 'Space Grotesk',
      fallbacks: 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
      weights: {3: 'semibold', 4: 'semibold'},
    },
    code: {
      family: 'JetBrains Mono',
      fallbacks: 'ui-monospace, "SF Mono", Monaco, Consolas, monospace',
    },
  },

  /**
   * 모션 — DESIGN.md "무한 반복 점멸 금지 / 발광은 장식이 아니라 상태".
   * 짧고 절제된 값. 감사 가능한 데이터 화면에서 움직임은 상태 변화의 신호일 때만.
   */
  motion: {fast: 120, medium: 220, slow: 380, ratio: 0.8},

  /**
   * 형태 — DESIGN.md `rounded` sm 4 / md 8 / lg 12.
   * Astryx 기본(base 4, multiplier 1)이 inner 4 / element 8 / container 12 로
   * 정확히 일치하므로 그대로 둔다. sharp corner 혼용은 DESIGN.md 가 금지한다.
   */
  radius: {base: 4, multiplier: 1},

  /**
   * `color:` 스케일 설정은 **쓰지 않는다.**
   *
   * HCT 팔레트 생성은 light/dark 두 벌을 만들고 `:root { color-scheme: light dark }`
   * 를 발행한다. 그러면 DESIGN.md 에 없는 라이트 모드가 생겨 — 아래 `tokens` 로
   * 덮지 않은 토큰이 OS 라이트 모드에서 전부 밝은 값으로 뒤집힌다.
   * 다크 전용 선례(theme-gothic)도 `color:` 없이 단일 값 토큰만 쓴다.
   *
   * accent 는 `tokens` 에서 DESIGN.md 값으로 직접 고정한다. HCT 시드를 쓰면
   * `#45E06F` → `#47E270` 로 표류하기도 한다.
   */

  syntax: citadelSyntax,

  /**
   * 다크 전용 테마 — DESIGN.md 에 light 모드 정의가 없다.
   * 따라서 [light, dark] 튜플이 아니라 단일 값을 쓴다.
   */
  tokens: {
    // ── Graph & Evidence — Emerald (브랜드 장식색이 아닌 "검증" 신호) ────
    // primary 는 검증된 관계·선택된 그래프 경로 전용. 일반 버튼 남용 금지.
    '--color-accent': '#45E06F', // war-green
    '--color-on-accent': '#07111C', // DESIGN.md button-primary textColor

    // ── Surfaces — Basalt & Night (어두운 석재 셸) ───────────────────────
    '--color-background-body': '#07111C', // citadel-void — 앱 최외곽
    '--color-background-surface': '#0D1B2A', // citadel-night — 페이지 배경
    '--color-background-card': '#111820', // surface — 패널·사이드바
    '--color-background-popover': '#111820',
    '--color-background-muted': '#26313A', // surface-variant — 비활성 표면
    '--color-background-inverted': '#D6CCB8',

    // ── 경계 — Black iron (그림자 대신 경계선으로 위계) ──────────────────
    '--color-border': '#26313A',
    '--color-border-emphasized': '#59636A',
    '--color-track': '#26313A',
    '--color-skeleton': '#26313A',
    '--color-shadow': 'transparent', // DESIGN.md: 패널에 그림자 없음

    // ── Foreground — Stone & Parchment ────────────────────────────────
    '--color-text-primary': '#D6CCB8', // on-surface — carved stone
    '--color-text-secondary': '#59636A', // on-surface-muted — iron-500
    '--color-text-disabled': '#59636A',
    '--color-icon-primary': '#D6CCB8',
    '--color-icon-secondary': '#59636A',
    '--color-icon-disabled': '#59636A',
    '--color-on-dark': '#D6CCB8',
    '--color-on-light': '#07111C',

    // ── Status — 색만으로 의미를 전달하지 않는다(아이콘·형태·라벨 병기) ──
    '--color-success': '#45E06F', // 검증된 연결
    '--color-error': '#E05252', // contradiction — 반박·모순
    '--color-warning': '#FFB13B', // signal-amber — 신규 정보

    // ── 관계 유형의 카테고리 슬롯 (War Table 엣지·배지 재사용) ──────────
    '--color-text-green': '#45E06F', // supports
    '--color-text-red': '#E05252', // contradicts
    '--color-text-yellow': '#FFB13B', // qualifies
    '--color-text-purple': '#A78BFA', // uncertain
    '--color-text-gray': '#59636A', // superseded
    '--color-text-orange': '#E97824', // ember — 실시간 수집
  },

  /**
   * 도메인 토큰 — Astryx 코어 토큰 표면에 대응물이 없는 Citadel 고유 값.
   * `--astryx-theme-citadel-*` 철자가 강제된다. 뷰어는 얇은 alias 로 짧은 이름을 만든다.
   */
  localTokens: {
    // Foreground
    '--astryx-theme-citadel-parchment': '#C8B58E', // 원문 인용·기록 표면
    // Graph & Evidence
    '--astryx-theme-citadel-seer-green': '#20B85A', // LLM 추론·발견 후보(확정 전)
    // Signals
    '--astryx-theme-citadel-ember': '#E97824', // 활성·실시간 수집
    '--astryx-theme-citadel-signal-amber': '#FFB13B', // Signal Spire·qualifies
    // Brand
    '--astryx-theme-citadel-crimson': '#7B2833', // 브랜드 배너·중요 섹션 표식
    // Status
    '--astryx-theme-citadel-uncertain': '#A78BFA', // 미확정 관계·quarantine
    '--astryx-theme-citadel-superseded': '#59636A', // 대체된 이전 버전
    // Typography — DESIGN.md 4번째 역할(Astryx 는 body/heading/code 3역할만)
    '--astryx-theme-citadel-font-display': 'Cinzel, Georgia, serif',
  },

  /**
   * 컴포넌트 오버라이드 — DESIGN.md `components` 절의 규칙을 Astryx 위에 얹는다.
   * "평면 + 경계 + 선택적 발광" 모델: 그림자를 쓰지 않고 경계선으로 위계를 만든다.
   */
  components: {
    // panel: surface 위 surface-variant 경계, 그림자 없음, rounded lg(12px)
    card: {
      base: {
        backgroundColor: 'var(--color-background-card)',
        borderColor: 'var(--color-border)',
        borderRadius: 'var(--radius-container)',
        boxShadow: 'none',
      },
    },
    // button-primary: emerald 는 화면당 가장 중요한 단일 액션에만
    button: {
      base: {borderRadius: 'var(--radius-element)'},
      'variant:secondary': {
        backgroundColor: 'var(--color-background-card)',
        borderColor: 'var(--color-border)',
        color: 'var(--color-text-primary)',
      },
    },
    // input: surface-variant 배경·경계 (Astryx 컴포넌트명은 kebab-case)
    'text-input': {
      base: {
        backgroundColor: 'var(--color-background-muted)',
        borderColor: 'var(--color-border)',
        borderRadius: 'var(--radius-element)',
      },
    },
    // badge: 상태 라벨 — label-sm 의 넓은 letter-spacing
    badge: {
      base: {
        borderRadius: 'var(--radius-inner)',
        fontFamily: 'var(--font-family-heading)',
        fontWeight: 'var(--font-weight-semibold)',
        letterSpacing: '0.08em',
        textTransform: 'uppercase',
      },
    },
    // source span·ID·hash·timestamp 는 반드시 monospace
    code: {
      base: {
        fontFamily: 'var(--font-family-code)',
        color: 'var(--astryx-theme-citadel-parchment)',
        backgroundColor: 'var(--color-background-muted)',
        borderRadius: 'var(--radius-inner)',
      },
    },
  },
});

export default citadelTheme;
