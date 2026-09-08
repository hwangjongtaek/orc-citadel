/** Chronicle Vault · 시간 탐색 — 두 축 설명 | Bitemporal Plane | AS-OF Snapshot | Chronicle rail. */

import {LayoutContent, LayoutPanel, LayoutFooter} from '@astryxdesign/core/Layout';
import {shell} from '../../../ui/shell.mjs';
import {
  h, Card, Badge, Text, sectionLabel, confidence, rawSvg, id, panelHead, grid,
} from '../../../ui/components.mjs';

export const title = 'Chronicle Vault · 시간 탐색 — Orc Citadel';

/** 두 축이 답하는 질문 — bitemporal 을 처음 보는 사람을 위한 설명 블록. */
const AXES = [
  ['Valid time', '2025-03에 A사는 실제로 누구에게 의존했나?',
    '→ 복수 공급처(B사+C사) · claim-201'],
  ['Transaction time', '2025-03 당시 시스템은 무엇을 믿었나?',
    '→ 당시엔 B사 단일 의존 · claim-123 (T_t=2025-03)'],
  ['Supersession', '정정 자료가 과거 결론을 어떻게 바꿨나?',
    '→ claim-123 → claim-201 · tx_to 2025-03 close'],
];

const EVENTS = [
  ['ingest', '2024-06', 'muted'],
  ['claim-123 asserted', '2024-09', 'on'],
  ['ingest 10-K', '2025-01', 'muted'],
  ['contradicts', '2025-02', 'bad'],
  ['supersede · tx_to close', '2025-03', 'warn'],
  ['seer 후보', '2025-07', 'seer'],
];

const controls = h('div', {style: {display: 'flex', alignItems: 'center', gap: 24,
  flexWrap: 'wrap', padding: '12px 16px', borderBottom: '1px solid var(--color-border)'}},
  ...[['Valid time', '현실에서 유효한 시점', 'T_v', '2025-03'],
      ['TX time · AS-OF', '시스템이 관찰한 시점', 'T_t', 'now · 2026-08']]
    .map(([name, desc, sym, value]) =>
      h('div', {key: name, style: {display: 'flex', alignItems: 'center', gap: 10}},
        h('div', {},
          h(Text, {type: 'label'}, name),
          h('div', {}, h(Text, {type: 'supporting'}, desc))),
        h('span', {style: {fontFamily: 'var(--font-family-code)', fontSize: 11,
          color: 'var(--color-text-secondary)'}}, sym),
        h('span', {style: {position: 'relative', width: 160, height: 4,
          background: 'var(--color-border)', borderRadius: 'var(--radius-full)'}},
          h('i', {style: {position: 'absolute', inset: '0 auto 0 0', width: '62%',
            background: 'linear-gradient(90deg, var(--color-border), var(--astryx-theme-citadel-seer-green))',
            borderRadius: 'var(--radius-full)'}}),
          h('i', {style: {position: 'absolute', left: '62%', top: '50%', width: 12, height: 12,
            marginLeft: -6, marginTop: -6, borderRadius: 'var(--radius-full)',
            background: 'var(--color-text-primary)',
            boxShadow: '0 0 0 3px var(--color-background-surface)'}})),
        h('span', {style: {fontFamily: 'var(--font-family-code)', fontSize: 12,
          color: 'var(--color-text-primary)'}}, value))));

const plane = h(LayoutContent, {padding: 0},
  panelHead('Bitemporal Plane · 시간 평면', 'valid × transaction · assertion 버전'),
  controls,
  h('div', {style: {padding: 16}},
    grid(3, 12, ...AXES.map(([name, q, a]) =>
      h(Card, {key: name}, h('div', {style: {padding: 4}},
        h(Text, {type: 'label'}, name),
        h('div', {style: {marginTop: 6}}, h(Text, {type: 'supporting'}, q)),
        h('div', {style: {marginTop: 6}}, id(a))))))),
  h('div', {style: {padding: '0 16px 16px'}},
    rawSvg('bitemporal-plane', {ratio: '880 / 400', maxHeight: 420})));

const snapshot = h(LayoutPanel, {width: 388, hasDivider: true, padding: 0,
  label: 'AS-OF Snapshot'},
  panelHead('AS-OF Snapshot · 시점 스냅샷', 'GET /v1/graph/time-travel'),
  h('div', {style: {padding: 16}},
    h('div', {style: {display: 'flex', gap: 10, flexWrap: 'wrap'}},
      h(Badge, {variant: 'neutral', label: 'Valid time 2025-03'}),
      h(Badge, {variant: 'neutral', label: 'TX time now · 2026-08'})),
    h('div', {style: {marginTop: 8}},
      h(Text, {type: 'supporting'}, '이 시점 유효 claim · valid + believed')),

    sectionLabel('◆ 현재 신뢰 · Fact'),
    h('div', {style: {border: '1px solid var(--color-accent)',
      background: 'rgba(69,224,111,.05)', borderRadius: 'var(--radius-element)',
      padding: 12}},
      id('claim-201'),
      h('div', {style: {marginTop: 6}},
        h(Text, {}, 'A사는 복수 공급처(B사 + C사)를 통해 조달한다.')),
      grid(2, 6, ...[['Valid time', '2025-01 → (open)'], ['TX time', '2025-03 → now · ∞']]
        .map(([k, v]) => h('div', {key: k, style: {marginTop: 8}},
          h(Text, {type: 'label'}, k), h('div', {}, id(v))))),
      h('div', {style: {marginTop: 8}},
        h(Text, {type: 'supporting'}, 'supersedes claim-123 · 원인: C사 신규 계약 공시 확인'))),

    sectionLabel('↺ 이전 버전 · superseded'),
    h('div', {style: {border: '1px solid var(--color-border)',
      borderRadius: 'var(--radius-element)', padding: 12, opacity: .82}},
      id('claim-123'),
      h('div', {style: {marginTop: 6}},
        h(Text, {}, 'A사는 B사 단일 공급자에 사실상 전량 의존한다.')),
      grid(2, 6, ...[['Valid time', '2024-06 → (open)'], ['TX time', '2024-09 → 2025-03 close']]
        .map(([k, v]) => h('div', {key: k, style: {marginTop: 8}},
          h(Text, {type: 'label'}, k), h('div', {}, id(v))))),
      h('div', {style: {marginTop: 8}},
        h(Text, {type: 'supporting'}, 'T_t=2025-03 로 이동 시 이 값이 현재'))),

    sectionLabel('◇ Seer · LLM 후보'),
    h('div', {style: {border: '1px solid var(--astryx-theme-citadel-uncertain)',
      background: 'rgba(167,139,250,.06)', borderRadius: 'var(--radius-element)',
      padding: 12}},
      h(Badge, {variant: 'purple', label: '미확정 0.44'}),
      h('div', {style: {marginTop: 8}},
        h(Text, {type: 'supporting'},
          'C사 계약은 발표일 뿐 실제 집행은 미확인 — supersedes 여부 Council 판정 대기.')),
      grid(2, 6, ...[['Valid time', '2025-02 → (tentative)'], ['TX time', '2025-07 → now']]
        .map(([k, v]) => h('div', {key: k, style: {marginTop: 8}},
          h(Text, {type: 'label'}, k), h('div', {}, id(v)))))),

    sectionLabel('Confidence · 이 시점 기준'),
    confidence('0.61', '7', '2'),
    h('div', {style: {marginTop: 12, padding: '10px 12px',
      border: '1px solid var(--color-border)', borderRadius: 'var(--radius-element)'}},
      h(Text, {type: 'supporting'}, 'War Table · 그래프에서 이 시점 보기'),
      h('div', {style: {marginTop: 4}}, id('?as_of_valid&as_of_tx')))));

const rail = h(LayoutFooter, {hasDivider: true},
  h('div', {style: {display: 'flex', alignItems: 'center', gap: 20, flexWrap: 'wrap'}},
    h('div', {style: {display: 'flex', alignItems: 'baseline', gap: 8}},
      h(Text, {type: 'label'}, 'Chronicle'),
      h(Text, {type: 'supporting'}, 'Event · Assertion 이력')),
    ...EVENTS.map(([label, at, tone], i) => {
      const color = tone === 'bad' ? 'var(--color-error)'
        : tone === 'warn' ? 'var(--astryx-theme-citadel-signal-amber)'
        : tone === 'seer' ? 'var(--astryx-theme-citadel-uncertain)'
        : tone === 'on' ? 'var(--color-accent)' : 'var(--color-text-secondary)';
      return h('span', {key: label, style: {display: 'flex', alignItems: 'center', gap: 5}},
        i ? h('span', {style: {width: 22, height: 1,
          background: 'var(--color-border)'}}) : null,
        h('span', {style: {width: 7, height: 7, borderRadius: 'var(--radius-full)',
          background: color}}),
        h('span', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 10,
          letterSpacing: '.06em', textTransform: 'uppercase', color}}, label),
        id(at));
    }),
    h('div', {style: {flex: 1}}),
    h(Badge, {variant: 'neutral', label: 'supersession chain · claim-123 tx_to 2025-03 close → claim-201 tx_to ∞'})));

export const render = () => shell({
  route: 'chronicle-vault',
  eyebrow: 'Chronicle Vault · History',
  context: '시간 탐색',
  title: 'Chronicle Vault · 시간 탐색',
  subtitle: 'valid time × transaction time · bitemporal history',
  hero: 'chronicle-vault-hero.png',
  slots: {content: plane, end: snapshot, footer: rail},
});
