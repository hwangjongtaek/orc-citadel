/**
 * 목업 공용 조각 — Astryx 위에 얹는 얇은 헬퍼.
 *
 * 여기 있는 것은 두 부류뿐이다:
 *  (1) Astryx 컴포넌트 조합을 반복 쓰기 위한 단축 (sectionLabel, confidence…)
 *  (2) Astryx 에 대응 컴포넌트가 없는 도메인 시각 요소 (관계 엣지 범례, coverage 레일…)
 * 새 스타일을 여기서 발명하지 말 것 — 값은 전부 theme-citadel 토큰을 참조한다.
 */

import React from 'react';

import {Card} from '@astryxdesign/core/Card';
import {Badge} from '@astryxdesign/core/Badge';
import {HStack, VStack} from '@astryxdesign/core/Stack';
import {Text, Heading} from '@astryxdesign/core/Text';
import {Button} from '@astryxdesign/core/Button';
import {EmptyState} from '@astryxdesign/core/EmptyState';
import {Table, TableHeader, TableHeaderCell, TableBody, TableRow, TableCell}
  from '@astryxdesign/core/Table';
import {Divider} from '@astryxdesign/core/Divider';

export const h = React.createElement;
export {Card, Badge, HStack, VStack, Text, Heading, Button, EmptyState,
  Table, TableHeader, TableHeaderCell, TableBody, TableRow, TableCell, Divider};

/**
 * 도메인 SVG 마크업을 그대로 삽입한다. SVG **문자열**을 받는다 — 파일 로딩은
 * 소비자 몫이다 (목업은 `svg-node.mjs` 의 readFileSync, 앱은 Vite `?raw` import).
 * 이 모듈은 브라우저 번들에 들어가므로 node API 를 import 하지 않는다.
 *
 * `ratio` (viewBox 종횡비)를 주면 래퍼가 aspect-ratio 로 크기를 잡는다 —
 * flex 조상 체인의 확정 높이에 의존하지 않아 어느 슬롯에 넣어도 안정적이다.
 */
export function svgBlock(svg, {ratio, ...style} = {}) {
  return h('div', {
    style: {minWidth: 0, width: '100%', ...(ratio ? {aspectRatio: ratio} : null), ...style},
    dangerouslySetInnerHTML: {__html: svg},
  });
}

/** 구분선이 딸린 섹션 라벨 — 원본 `.sec-label`. */
export function sectionLabel(text) {
  return h('div', {style: {display: 'flex', alignItems: 'center', gap: 8,
    margin: '16px 0 10px'}},
    h(Text, {type: 'label'}, text),
    h('span', {style: {flex: 1, height: 1, background: 'var(--color-border)'}}));
}

/** 패널 머리 — 제목 + 우측 보조 라벨. */
export function panelHead(title, sub) {
  return h('div', {style: {display: 'flex', alignItems: 'baseline',
    justifyContent: 'space-between', gap: 16, padding: '12px 16px',
    borderBottom: '1px solid var(--color-border)'}},
    h(Text, {type: 'label'}, title),
    sub ? h(Text, {type: 'supporting'}, sub) : null);
}

/**
 * Confidence 표시 — DESIGN.md: "단일 색상 게이지 금지.
 * 값 + 근거 수 + 독립 출처 수 + 계산 근거를 함께 표시한다."
 */
export function confidence(value, evidence, independent) {
  const cell = (num, cap, good) =>
    h('div', {style: {background: 'var(--color-background-card)', padding: '10px 12px'}},
      h('div', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 20,
        fontWeight: 600, lineHeight: 1.1,
        color: good ? 'var(--color-accent)' : 'var(--color-text-primary)'}}, num),
      h('div', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 9.5,
        letterSpacing: '.06em', textTransform: 'uppercase',
        color: 'var(--color-text-secondary)', marginTop: 4}}, cap));
  return h('div', {style: {display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 1,
    background: 'var(--color-border)', border: '1px solid var(--color-border)',
    borderRadius: 'var(--radius-element)', overflow: 'hidden'}},
    cell(value, 'Confidence', Number(value) >= 0.7),
    cell(evidence, 'Evidence'),
    cell(independent, '독립 출처'));
}

/** coverage 레일 — 값 + 퍼센트. `tone` 으로 amber 경고 표현. */
export function coverage(pct, tone) {
  const fill = tone === 'warn'
    ? 'var(--astryx-theme-citadel-signal-amber)' : 'var(--color-accent)';
  return h('div', {style: {display: 'flex', alignItems: 'center', gap: 8}},
    h('span', {style: {position: 'relative', flex: 1, height: 4,
      background: 'var(--color-border)', borderRadius: 'var(--radius-full)'}},
      h('i', {style: {position: 'absolute', inset: '0 auto 0 0', width: `${pct}%`,
        background: fill, borderRadius: 'var(--radius-full)'}})),
    h('span', {style: {fontFamily: 'var(--font-family-code)', fontSize: 11,
      color: 'var(--color-text-secondary)'}}, `${pct}%`));
}

/**
 * 관계 유형 범례 — DESIGN.md: "색상만으로 의미를 전달하지 않으며
 * 선 형태·표식·라벨을 병기한다." Badge 로는 실선/이중선/점선을 못 그려 SVG 로 둔다.
 */
export const RELATIONS = [
  ['supports', '#45E06F', {}],
  ['contradicts', '#E05252', {double: true}],
  ['qualifies', '#FFB13B', {dash: '5 3'}],
  ['uncertain', '#A78BFA', {dash: '2 3'}],
  ['superseded', '#59636A', {dash: '1 3'}],
];

export function relationLegend() {
  const line = (color, {double, dash}) => double
    ? h('svg', {width: 26, height: 8, 'aria-hidden': 'true'},
        h('line', {x1: 0, y1: 2.5, x2: 26, y2: 2.5, stroke: color, strokeWidth: 1.5}),
        h('line', {x1: 0, y1: 5.5, x2: 26, y2: 5.5, stroke: color, strokeWidth: 1.5}))
    : h('svg', {width: 26, height: 8, 'aria-hidden': 'true'},
        h('line', {x1: 0, y1: 4, x2: 26, y2: 4, stroke: color, strokeWidth: 2,
          strokeDasharray: dash}));
  return h('div', {style: {display: 'flex', gap: 16, flexWrap: 'wrap'},
    'aria-label': '관계 유형 범례'},
    RELATIONS.map(([name, color, style]) =>
      h('span', {key: name, style: {display: 'flex', alignItems: 'center', gap: 6,
        fontFamily: 'var(--font-family-heading)', fontSize: 11,
        color: 'var(--color-text-secondary)'}}, line(color, style), name)));
}

/** 원문 인용 span — monospace + parchment (DESIGN.md `source-span`). */
export function sourceSpan(children) {
  return h('div', {style: {fontFamily: 'var(--font-family-code)', fontSize: 11.5,
    lineHeight: 1.55, color: 'var(--astryx-theme-citadel-parchment)',
    background: 'var(--color-background-muted)', borderRadius: 'var(--radius-inner)',
    padding: '8px 10px', margin: '6px 0'}}, children);
}

/** provenance trail — `evd › doc › segment · char` 한 줄. */
export function trail(...hops) {
  return h('div', {style: {display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap',
    fontFamily: 'var(--font-family-code)', fontSize: 10,
    color: 'var(--color-text-secondary)'}},
    hops.flatMap((hop, i) => i === 0 ? [hop] : ['›', hop])
      .map((x, i) => h('span', {key: i}, x)));
}

/** 좌측 색 띠가 있는 근거 카드 — supports/contradicts 를 형태로도 구분. */
export function evidenceCard({relation, source, quote, trailHops, tone}) {
  const color = tone === 'contra' ? 'var(--color-error)' : 'var(--color-accent)';
  return h('div', {style: {border: '1px solid var(--color-border)',
    borderLeft: `3px solid ${color}`, borderRadius: 'var(--radius-element)',
    padding: '10px 12px', marginBottom: 10}},
    h('div', {style: {display: 'flex', justifyContent: 'space-between', gap: 8,
      marginBottom: 6}},
      h('span', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 10,
        fontWeight: 600, letterSpacing: '.06em', textTransform: 'uppercase', color}},
        `${tone === 'contra' ? '╪' : '■'} ${relation}`),
      h('span', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 10,
        color: 'var(--color-text-secondary)'}}, source)),
    sourceSpan(quote),
    trail(...trailHops));
}

/** 정직 빈 상태 — `empty-*.png` 일러스트를 icon 슬롯에 넣는다.
 * `assetBase` 로 URL 공간을 주입한다 (목업 `./assets/` · 앱 `/assets/img/`). */
export function emptyState({art, title, description, actions, isCompact,
                            assetBase = './assets/'}) {
  return h(EmptyState, {
    title, description, actions, isCompact,
    icon: art ? h('img', {src: `${assetBase}${art}`, alt: '', width: 132, height: 132,
      style: {imageRendering: 'pixelated', opacity: .9}}) : undefined,
  });
}

/** 큰 수치 타일 — Watchtower KPI 스트립 / Gate 요약. */
export function statTile({value, unit, label, note, tone}) {
  const color = tone === 'good' ? 'var(--color-accent)'
    : tone === 'warn' ? 'var(--astryx-theme-citadel-signal-amber)'
    : tone === 'bad' ? 'var(--color-error)' : 'var(--color-text-primary)';
  return h(Card, {}, h('div', {style: {padding: 4}},
    h('div', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 10,
      fontWeight: 600, letterSpacing: '.1em', textTransform: 'uppercase',
      color: 'var(--color-text-secondary)'}}, label),
    h('div', {style: {display: 'flex', alignItems: 'baseline', gap: 4, marginTop: 6}},
      h('span', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 28,
        fontWeight: 600, lineHeight: 1, color}}, value),
      unit ? h('span', {style: {fontSize: 12, color: 'var(--color-text-secondary)'}}, unit) : null),
    note ? h('div', {style: {marginTop: 6}}, h(Text, {type: 'supporting'}, note)) : null));
}

/** 등폭 ID — claim/doc/segment 식별자는 반드시 monospace (DESIGN.md `data-md`). */
export function id(v) {
  return h('span', {style: {fontFamily: 'var(--font-family-code)', fontSize: 11.5,
    color: 'var(--color-text-secondary)'}}, v);
}

/** 3열 그리드 — Gate 캠페인 카드 등. */
export function grid(cols, gap, ...kids) {
  return h('div', {style: {display: 'grid',
    gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`, gap}}, ...kids);
}
