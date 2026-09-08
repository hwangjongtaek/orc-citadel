/** War Table · 그래프 탐색 — 목업 3+1 (Campaign Map | 그래프 | Evidence Inspector | Chronicle). */

import {LayoutContent, LayoutPanel, LayoutFooter} from '@astryxdesign/core/Layout';
import {shell} from '../../../ui/shell.mjs';
import {
  h, Card, Badge, VStack, HStack, Text, sectionLabel, confidence, coverage,
  relationLegend, evidenceCard, rawSvg, id, panelHead,
} from '../../../ui/components.mjs';

export const title = 'War Table · 그래프 탐색 — Orc Citadel';

const SUBCLAIMS = [
  ['A사의 B사 단일 공급자 의존도는 실제로 감소했는가?', 72, true],
  ['C사와의 신규 공급 계약은 발표가 아닌 실제 집행이 확인되는가?', 48, false],
  ['공급망 다변화 경고는 독립된 복수 근거에 기반하는가?', 35, false],
  ['규제 변경이 A사 공급 계약에 직·간접 영향을 미쳤는가?', 20, false, 'warn'],
];

const ENTITY_FILTERS = [
  ['Organization · 12', 'var(--color-text-primary)'],
  ['Product · 6', 'var(--astryx-theme-citadel-parchment)'],
  ['Event · 9', 'var(--astryx-theme-citadel-seer-green)'],
  ['Quarantine · 2', 'var(--astryx-theme-citadel-uncertain)'],
];

const CHRONICLE = [
  ['ingest', '2024-06', 'muted'],
  ['claim-123', '2024-09', 'on'],
  ['ingest', '2025-01', 'muted'],
  ['contradicts', '2025-02', 'bad'],
  ['supersedes?', '2025-03', 'warn'],
];

function subclaimCard([q, cov, active, tone]) {
  return h('div', {key: q, style: {
    border: `1px solid ${active ? 'var(--color-accent)' : 'var(--color-border)'}`,
    background: active ? 'rgba(69,224,111,.05)' : 'transparent',
    borderRadius: 'var(--radius-element)', padding: 12, marginBottom: 10}},
    h(Text, {type: 'supporting'}, q),
    h('div', {style: {marginTop: 8}}, coverage(cov, tone)));
}

function chip([label, color]) {
  return h('span', {key: label, style: {display: 'inline-flex', alignItems: 'center',
    gap: 6, padding: '4px 10px', border: '1px solid var(--color-border)',
    borderRadius: 'var(--radius-full)', fontSize: 11,
    color: 'var(--color-text-secondary)'}},
    h('span', {style: {width: 8, height: 8, borderRadius: 'var(--radius-full)',
      background: color}}),
    label);
}

const campaignMap = h(LayoutPanel, {width: 288, hasDivider: true, padding: 0,
  label: 'Campaign Map'},
  panelHead('Campaign Map', 'Subclaims · 5'),
  h('div', {style: {padding: 16}},
    SUBCLAIMS.map(subclaimCard),
    sectionLabel('Entities · Filters'),
    h('div', {style: {display: 'flex', flexWrap: 'wrap', gap: 6}},
      ENTITY_FILTERS.map(chip))));

const graphCanvas = h(LayoutContent, {padding: 0},
  h('div', {style: {display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    gap: 16, padding: '12px 16px', borderBottom: '1px solid var(--color-border)'}},
    h('div', {style: {display: 'flex', alignItems: 'baseline', gap: 10}},
      h(Text, {}, 'War Table'),
      h(Text, {type: 'label'}, '· Temporal Evidence Graph')),
    relationLegend()),
  h('div', {style: {position: 'relative', flex: 1, minHeight: 0, overflow: 'hidden',
    background: 'radial-gradient(1200px 700px at 50% 42%, rgba(38,49,58,.5), transparent 70%), var(--color-background-surface)'}},
    rawSvg('war-table-graph', {ratio: '900 / 560', height: '100%'})));

const inspector = h(LayoutPanel, {width: 340, hasDivider: true, padding: 0,
  label: 'Evidence Inspector'},
  panelHead('Evidence Inspector', 'Hall of Witnesses'),
  h('div', {style: {padding: 16}},
    h('div', {style: {border: '1px solid var(--color-accent)',
      background: 'rgba(69,224,111,.05)', borderRadius: 'var(--radius-element)',
      padding: 12, marginBottom: 16}},
      h(HStack, {gap: 2}, h(Badge, {variant: 'success', label: 'Claim · asserted'})),
      h('div', {style: {marginTop: 8}},
        h(Text, {}, 'A사는 AI 가속기 부품을 B사에 주로 의존한다.')),
      h('div', {style: {marginTop: 8}},
        id('claim-123 · valid 2025-01-01 → · predicate: depends_on'))),

    confidence('0.61', '7', '2'),

    h('div', {style: {display: 'flex', gap: 10, marginTop: 16, padding: '10px 12px',
      border: '1px solid var(--color-border)', borderRadius: 'var(--radius-element)'}},
      h('div', {},
        h(Text, {type: 'label'}, '독립성 보정'),
        h('div', {style: {marginTop: 4}},
          h(Text, {type: 'supporting'},
            '지지 근거 5건 중 4건이 동일 보도자료 파생 → 독립 출처 2건으로 집계.')))),

    sectionLabel('Supporting Evidence'),
    evidenceCard({
      relation: 'supports', source: 'SEC 10-K · 1차 자료',
      quote: '"...substantially all of our AI accelerator components are sourced from a single supplier..."',
      trailHops: ['ev-456', 'doc-2291', 'p.42 · char 1180–1244'],
    }),

    sectionLabel('Contradicting Evidence'),
    evidenceCard({
      tone: 'contra', relation: 'contradicts', source: '보도자료 · 당사자',
      quote: '"A사는 복수의 공급처를 통해 안정적 조달 체계를 갖췄다"',
      trailHops: ['ev-789', 'doc-5540', 'para 3 · char 88–140'],
    }),

    sectionLabel('Seer · LLM Inference'),
    h('div', {style: {border: '1px solid var(--astryx-theme-citadel-uncertain)',
      borderRadius: 'var(--radius-element)', padding: '10px 12px',
      background: 'rgba(167,139,250,.06)'}},
      h(Badge, {variant: 'purple', label: '반증 후보 · 미확정'}),
      h('div', {style: {marginTop: 8}},
        h(Text, {type: 'supporting'},
          '보도자료(ev-789)의 "복수 공급처" 표현은 계획 발표일 가능성. '
          + '실제 계약·공시 증거를 탐색해 supersedes 여부를 판정하도록 Council 에 제안함.')),
      h('div', {style: {marginTop: 6}},
        id('근거: 시점 차이 + 당사자 이해관계 · 확실성 0.44')))));

const chronicleRail = h(LayoutFooter, {hasDivider: true},
  h('div', {style: {display: 'flex', alignItems: 'center', gap: 24, flexWrap: 'wrap'}},
    h('div', {style: {display: 'flex', alignItems: 'baseline', gap: 8}},
      h(Text, {type: 'label'}, 'Chronicle'),
      h(Text, {type: 'supporting'}, 'Bitemporal History')),
    h('div', {style: {display: 'flex', alignItems: 'center', gap: 4, flex: 1,
      minWidth: 0, flexWrap: 'wrap'}},
      CHRONICLE.map(([label, at, tone], i) => {
        const color = tone === 'bad' ? 'var(--color-error)'
          : tone === 'warn' ? 'var(--astryx-theme-citadel-signal-amber)'
          : tone === 'on' ? 'var(--color-accent)' : 'var(--color-text-secondary)';
        return h('span', {key: label + at, style: {display: 'flex', alignItems: 'center', gap: 4}},
          i ? h('span', {style: {width: 28, height: 1,
            background: 'var(--color-border)'}}) : null,
          h('span', {style: {width: 7, height: 7, borderRadius: 'var(--radius-full)',
            background: color}}),
          h('span', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 10,
            letterSpacing: '.06em', textTransform: 'uppercase', color}}, label),
          h('span', {style: {fontFamily: 'var(--font-family-code)', fontSize: 10,
            color: 'var(--color-text-secondary)'}}, at));
      }))));

export const render = () => shell({
  route: 'war-table',
  eyebrow: 'Campaign · Investigation',
  context: 'A사 AI 가속기 공급망 다변화 (2024–)',
  title: 'War Table · 그래프 탐색',
  subtitle: '엔터티 · 주장 · 증거 · 시간 관계의 Temporal Knowledge Graph',
  hero: 'war-table-hero.png',
  slots: {start: campaignMap, content: graphCanvas, end: inspector, footer: chronicleRail},
});
