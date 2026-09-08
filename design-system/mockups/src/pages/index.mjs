/** 목업 인덱스 — 8공간 + 빈 상태 참조. */

import {LayoutContent} from '@astryxdesign/core/Layout';
import {shell, SPACES} from '../shell.mjs';
import {h, Card, Text, Badge, sectionLabel, id, grid} from '../ui.mjs';

export const title = 'Orc Citadel — 목업 인덱스';

/** 공간 → (설명, 담당 설계 문서). */
const DETAIL = {
  'citadel-gate': ['조사 요청 진입점 · Campaign 목록 · 시스템 상태 요약', 'POST /v1/investigations'],
  'war-table': ['엔티티·주장·증거의 Temporal Evidence Graph', '02 · 06'],
  'hall-of-witnesses': ['claim ↔ 원문 span 왕복 · 지지/반박 · 독립성', '03 §8 · 05'],
  'council-chamber': ['Agent 계획·토론·반증·종합 · 조사 루프·비용', '07 · 09'],
  'watchtower': ['source 상태·backlog·freshness·failure 감시', '04 · 11'],
  'grand-archive': ['원문·버전·parsing·출처 계보(dedup lineage)', '03 · 04 · 08'],
  'chronicle-vault': ['valid time × transaction time · bitemporal', '03 §6 · 09'],
  'signal-spire': ['결론·confidence 변화 · 신규 모순 알림', '11 §4 · 09'],
};

const body = h(LayoutContent, {padding: 4},
  h('div', {style: {display: 'flex', alignItems: 'center', gap: 14, marginBottom: 16}},
    h('img', {src: './assets/logo-mark.png', alt: 'Orc Citadel 문장',
      height: 56, style: {width: 'auto', flex: 'none'}}),
    h(Text, {type: 'supporting'},
    'Astryx + theme-citadel 로 재작성한 8공간 정적 목업. '
      + '컴포넌트는 빌드 시점에 정적 HTML 로 렌더되며 클라이언트 JS 는 없다.')),
  h('div', {style: {marginTop: 20}},
    grid(4, 16, ...SPACES.map(([slug, name, role]) => {
      const [desc, spec] = DETAIL[slug];
      return h('a', {key: slug, href: `./${slug}.html`, style: {textDecoration: 'none'}},
        h(Card, {}, h('div', {style: {padding: 4}},
          h('div', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 14,
            fontWeight: 600, color: 'var(--color-text-primary)'}}, name),
          h('div', {style: {marginTop: 2}}, h(Text, {type: 'supporting'}, role)),
          h('div', {style: {marginTop: 8, minHeight: 34}},
            h(Text, {type: 'supporting'}, desc)),
          h('div', {style: {marginTop: 8, display: 'flex', alignItems: 'center',
            justifyContent: 'space-between'}},
            id(spec),
            h('span', {style: {fontSize: 11,
              color: 'var(--astryx-theme-citadel-seer-green)'}}, '열기 ›')))));
    }))),
  sectionLabel('참조'),
  h('a', {href: './empty-states.html', style: {textDecoration: 'none'}},
    h(Card, {}, h('div', {style: {padding: 4, display: 'flex', alignItems: 'center',
      justifyContent: 'space-between', gap: 12}},
      h('div', {},
        h('div', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 14,
          fontWeight: 600, color: 'var(--color-text-primary)'}}, '빈 상태 아트 · Empty States'),
        h('div', {style: {marginTop: 4}},
          h(Text, {type: 'supporting'}, '각 공간의 no-data 상태 일러스트 6종'))),
      h(Badge, {variant: 'neutral', label: '참조'})))));

export const render = () => shell({
  route: null,
  eyebrow: 'Mockups · Index',
  context: '목업 인덱스',
  title: 'Orc Citadel · 목업 인덱스',
  subtitle: 'Citadel 8공간 · Astryx + theme-citadel',
  alerts: 3,
  slots: {content: body},
});
