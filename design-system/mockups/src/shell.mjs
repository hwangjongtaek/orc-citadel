/**
 * 목업 공유 셸 — 마스트헤드(히어로 밴드)·공간 탭·헤더.
 *
 * 원본 `docs/mockups/*.html` 의 header + masthead 구조를 Astryx `Layout` 위에 옮긴 것.
 * 의도적 차이 하나: 원본은 페이지끼리 링크가 없어 `index.html` 로만 오갔지만,
 * 여기서는 공간 탭을 셸에 넣어 목업 자체를 순회할 수 있게 했다(뷰어 현행과 동일).
 */

import React from 'react';
import {Layout, LayoutHeader} from '@astryxdesign/core/Layout';
import {HStack, VStack} from '@astryxdesign/core/Stack';
import {Text} from '@astryxdesign/core/Text';

const h = React.createElement;

/** 문서형 페이지의 본문·배너 최대 폭. 뷰어(`main{max-width:1200px}`)와 같은 값. */
export const CONTENT_WIDTH = 1200;

/**
 * 공간 목록 — (경로, 세계관 명칭, 기술 용어). blueprint L244 병기 규약.
 *
 * 브리핑-우선 IA (specs/ui-overhaul-astryx TS-3): 주요 작업 4종(결론 조회 ·
 * 근거 추적 · 변화 확인 · 검색)에 대응하는 4공간이 1차, 운영·감사 성격의
 * 4공간은 2차 그룹으로 강등한다. URL·기능은 그대로다 — 배치만 바뀐다.
 */
export const PRIMARY_SPACES = [
  ['citadel-gate', 'Citadel Gate', '브리핑 · Home'],
  ['war-table', 'War Table', '그래프 탐색'],
  ['hall-of-witnesses', 'Hall of Witnesses', '증거 검사'],
  ['signal-spire', 'Signal Spire', '알림 센터'],
];
export const SECONDARY_SPACES = [
  ['grand-archive', 'Grand Archive', '문서 탐색'],
  ['council-chamber', 'Council Chamber', '조사 실행'],
  ['watchtower', 'Watchtower', '수집 관제'],
  ['chronicle-vault', 'Chronicle Vault', '시간 탐색'],
];
export const SPACES = [...PRIMARY_SPACES, ...SECONDARY_SPACES];

/**
 * 브랜드 로고 — 신규 픽셀아트 lockup 을 mark/title 로 분리한 자산 (FR-4).
 * 원본(621·1129px)보다 항상 작게 그리므로 `image-rendering: pixelated` 를 쓰지
 * 않는다 — pixelated 는 업스케일용이고 다운스케일에선 앨리어싱만 남긴다.
 */
// height 는 반드시 인라인 style 로 준다 — reset.css 의 `:where(img){height:auto}` 가
// height *속성*을 덮어써 자연 크기(621·1129px)로 커지는 함정.
const logoMark = (height) =>
  h('img', {src: './assets/logo-mark.png', alt: '',
    style: {height, width: 'auto', flex: 'none', display: 'block'}});
const logoTitle = (height) =>
  h('img', {src: './assets/logo-title.png', alt: 'ORC CITADEL',
    style: {height, width: 'auto', flex: 'none', display: 'block'}});
export {logoMark, logoTitle};

const searchIcon = () =>
  h('svg', {width: 15, height: 15, viewBox: '0 0 24 24', fill: 'none', 'aria-hidden': 'true'},
    h('circle', {cx: 11, cy: 11, r: 7, stroke: 'currentColor', strokeWidth: 2}),
    h('path', {d: 'M20 20 L16.5 16.5', stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round'}));

const S = {
  bar: {display: 'flex', alignItems: 'center', gap: 24, padding: '10px 24px',
    background: 'var(--color-background-card)',
    borderBottom: '1px solid var(--color-border)'},
  wordmark: {fontFamily: 'var(--astryx-theme-citadel-font-display)', fontWeight: 700,
    fontSize: 18, letterSpacing: '.14em', color: 'var(--color-text-primary)',
    display: 'flex', alignItems: 'center', gap: 10, whiteSpace: 'nowrap',
    textDecoration: 'none'},
  ctx: {display: 'flex', flexDirection: 'column', minWidth: 0, paddingLeft: 24,
    borderLeft: '1px solid var(--color-border)'},
  search: {display: 'flex', alignItems: 'center', gap: 8, width: 300,
    background: 'var(--color-background-muted)', borderRadius: 'var(--radius-element)',
    padding: '8px 12px', color: 'var(--color-text-secondary)'},
  searchInput: {background: 'none', border: 0, outline: 'none', width: '100%',
    color: 'var(--color-text-primary)', fontFamily: 'var(--font-family-body)', fontSize: 13},
  spire: {display: 'flex', alignItems: 'center', gap: 8, whiteSpace: 'nowrap',
    fontFamily: 'var(--font-family-heading)', fontSize: 12, fontWeight: 600,
    color: 'var(--astryx-theme-citadel-signal-amber)',
    background: 'rgba(255,177,59,.08)', border: '1px solid rgba(255,177,59,.3)',
    padding: '8px 12px', borderRadius: 'var(--radius-element)', textDecoration: 'none'},
  dot: {width: 7, height: 7, borderRadius: 'var(--radius-full)',
    background: 'var(--astryx-theme-citadel-signal-amber)',
    boxShadow: '0 0 8px 1px var(--astryx-theme-citadel-signal-amber)'},
  tabs: {display: 'flex', flexWrap: 'wrap', gap: 2, padding: '8px 24px',
    background: 'var(--color-background-card)',
    borderBottom: '1px solid var(--color-border)'},
  tab: {padding: '6px 12px', borderRadius: 'var(--radius-element)', textDecoration: 'none',
    fontFamily: 'var(--font-family-heading)', fontSize: 12, fontWeight: 600,
    color: 'var(--color-text-secondary)'},
  tabOn: {color: 'var(--color-accent)', background: 'rgba(69,224,111,.08)'},
  // 2차 그룹 — 강등이지 은닉이 아니다. 크기만 한 단계 줄이고 링크는 전부 유지.
  tab2: {fontSize: 11, fontWeight: 500},
  navSep: {width: 1, alignSelf: 'stretch', margin: '2px 10px',
    background: 'var(--color-border)'},
  navGroupLabel: {alignSelf: 'center', fontFamily: 'var(--font-family-heading)',
    fontSize: 9.5, fontWeight: 600, letterSpacing: '.12em', textTransform: 'uppercase',
    color: 'var(--color-text-secondary)', whiteSpace: 'nowrap', marginRight: 4},
  kbd: {fontFamily: 'var(--font-family-code)', fontSize: 10, flex: 'none',
    padding: '2px 6px', border: '1px solid var(--color-border)',
    borderRadius: 'var(--radius-inner)', color: 'var(--color-text-secondary)'},
  // 히어로는 전부 1920×720 (8:3). 밴드 높이를 고정하면 세로 23% 만 보인다.
  // `width: 100%` 필수 — LayoutHeader 의 flex 자식이라 폭이 콘텐츠로 접히고,
  // 그러면 aspect-ratio 가 접힌 폭 기준으로 계산돼 히어로가 조각으로 나온다.
  mast: {position: 'relative', display: 'flex', alignItems: 'flex-end', width: '100%',
    padding: '0 24px 20px', overflow: 'hidden',
    borderBottom: '1px solid var(--color-border)'},
  // 8공간 동일 셸 — 전폭 밴드 하나만 쓴다. 문서형(Gate·Watchtower) 액자 히어로
  // (1200px 정렬·상한 360px) 특례는 두 페이지만 다르게 보이는 문제로 폐지했다
  // (2026-09-08). 8:3 을 지키되 상한 300px — 상한이 없으면 2560px 뷰포트에서
  // 960px 를 먹는다. 잘리는 곳은 천장 창살·바닥 카펫으로 정보량이 가장 적다.
  // `flexShrink: 0` 없으면 `height:'fill'` 에서 헤더가 눌려 더 잘린다.
  mastBand: {aspectRatio: '8 / 3', maxHeight: 300, minHeight: 150, flexShrink: 0},
  // 히어로 이미지가 없으면 8:3 이 빈 그라데이션 덩어리가 된다 (index·empty-states).
  mastFlat: {height: 132, alignItems: 'center', padding: '0 24px', flexShrink: 0},
  mastH1: {fontFamily: 'var(--font-family-heading)', fontSize: 22, fontWeight: 600,
    color: 'var(--color-text-primary)', textShadow: '0 2px 14px rgba(7,17,28,.9)', margin: 0},
  mastP: {fontFamily: 'var(--font-family-heading)', fontSize: 11, fontWeight: 500,
    letterSpacing: '.08em', textTransform: 'uppercase',
    color: 'var(--astryx-theme-citadel-parchment)', marginTop: 5,
    textShadow: '0 2px 14px rgba(7,17,28,.9)'},
  eyebrow: {fontFamily: 'var(--font-family-heading)', fontSize: 10, fontWeight: 600,
    letterSpacing: '.14em', textTransform: 'uppercase', color: 'var(--color-text-secondary)'},
  ctxTitle: {fontFamily: 'var(--font-family-heading)', fontSize: 15, fontWeight: 600,
    color: 'var(--color-text-primary)', whiteSpace: 'nowrap', overflow: 'hidden',
    textOverflow: 'ellipsis'},
};

/**
 * 히어로 밴드 — 원본 목업의 3중 배경(그라데이션 + 히어로 PNG + night).
 * `hero` 가 없으면 그라데이션만 (empty-states·index 처럼 공간이 아닌 페이지).
 */
function masthead({title, subtitle, hero}) {
  const shape = hero ? S.mastBand : S.mastFlat;
  // 히어로가 있으면 아래에서 위로 걷히는 스크림 — 글자만 덮고 그림 본체는 살린다.
  // 히어로가 없으면 좌→우 (원본 밴드 조판).
  const scrim = hero
    ? 'linear-gradient(0deg, rgba(7,17,28,.94) 0%, rgba(7,17,28,.55) 26%, rgba(7,17,28,.12) 55%, rgba(7,17,28,0) 80%)'
    : 'linear-gradient(90deg, rgba(7,17,28,.92) 0%, rgba(7,17,28,.6) 42%, rgba(7,17,28,.32) 100%)';
  const layers = [
    scrim,
    hero ? `url('./assets/${hero}') center center / cover no-repeat` : null,
    'var(--color-background-surface)',
  ].filter(Boolean).join(', ');
  return h('div', {
    style: {...S.mast, ...shape, background: layers},
  },
    h('div', {},
      h('h1', {style: S.mastH1}, title),
      h('p', {style: S.mastP}, subtitle)));
}

/**
 * 페이지 셸.
 *
 * @param route    현재 공간 slug (공간 탭 active 표시)
 * @param eyebrow  헤더 컨텍스트 상단 라벨 (영문·기능)
 * @param context  헤더 컨텍스트 제목 (Campaign 명 등)
 * @param title    마스트헤드 h1
 * @param subtitle 마스트헤드 부제
 * @param hero     `assets/` 내 히어로 PNG 파일명
 * @param alerts   Signal Spire 칩 카운트
 * @param slots    Layout 슬롯 { start, content, end, footer }
 */
export function shell({route, eyebrow, context, title, subtitle, hero, alerts = 3,
                       slots}) {
  const header = h(LayoutHeader, {padding: 0, hasDivider: false},
    h('div', {style: S.bar},
      h('a', {style: S.wordmark, href: './index.html', 'aria-label': 'ORC CITADEL'},
        logoMark(30), logoTitle(22)),
      h('div', {style: S.ctx},
        h('span', {style: S.eyebrow}, eyebrow),
        h('span', {style: S.ctxTitle}, context)),
      h('div', {style: {flex: '1 1 auto'}}),
      h('label', {style: S.search}, searchIcon(),
        h('input', {style: S.searchInput,
          placeholder: 'subject · claim · document 통합 검색', readOnly: true}),
        h('span', {style: S.kbd, 'aria-hidden': 'true'}, '⌘K')),
      h('a', {style: S.spire, href: './signal-spire.html',
        title: 'Signal Spire · 결론·confidence 변화 알림'},
        h('span', {style: S.dot}), `Signal Spire · ${alerts}`)),
    h('nav', {style: S.tabs, 'aria-label': 'Citadel 공간'},
      PRIMARY_SPACES.map(([slug, name]) =>
        h('a', {key: slug, href: `./${slug}.html`,
          style: slug === route ? {...S.tab, ...S.tabOn} : S.tab}, name)),
      h('span', {style: S.navSep, 'aria-hidden': 'true'}),
      h('span', {style: S.navGroupLabel}, '운영 · 감사'),
      SECONDARY_SPACES.map(([slug, name]) =>
        h('a', {key: slug, href: `./${slug}.html`,
          style: slug === route
            ? {...S.tab, ...S.tab2, ...S.tabOn} : {...S.tab, ...S.tab2}}, name))),
    masthead({title, subtitle, hero}));

  // 8공간 동일 셸: 항상 `fill`(패널·본문 독립 스크롤). 좌·우 패널이 없는
  // 페이지(Gate·Watchtower)는 본문 폭만 1200px 로 제한해 가독을 지킨다 —
  // 셸(헤더·히어로)은 전폭으로 나머지 공간과 동일하다.
  const contentOnly = !slots.start && !slots.end;
  return h(Layout, {
    height: 'fill',
    ...(contentOnly ? {contentWidth: CONTENT_WIDTH} : null),
    header, ...slots,
  });
}

/** 섹션 소제목 — 원본 목업 `.panel-head` 의 라벨 조판. */
export function panelHead(title, sub) {
  return h(HStack, {gap: 2, justifyContent: 'space-between',
    style: {alignItems: 'baseline'}},
    h(Text, {type: 'label'}, title),
    sub ? h(Text, {type: 'supporting'}, sub) : null);
}

export {h, HStack, VStack, Text};
