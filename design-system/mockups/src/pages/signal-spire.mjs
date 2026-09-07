/** Signal Spire · 알림 센터 — Triggers·Campaigns·Scope | Alert Feed | Subscriptions. */

import {LayoutContent, LayoutPanel} from '@astryxdesign/core/Layout';
import {shell} from '../shell.mjs';
import {h, Card, Badge, Text, sectionLabel, id, panelHead, grid} from '../ui.mjs';

export const title = 'Signal Spire · 알림 센터 — Orc Citadel';

const TRIGGERS = [
  ['contradicting_evidence', '기존 결론 반박', 2],
  ['claim_changed', '주장 변경', 1],
  ['plan_to_execution', '계획→실행 증거', 1],
  ['new_independent_source', '독립 출처 추가', 1],
  ['confidence_threshold', 'confidence 임계 변동', 0],
];

const CAMPAIGNS = [['A사 공급망 다변화', 3], ['C사 계약 집행 추적', 1], ['규제 변경 영향 관찰', 1]];
const SCOPE = [['안읽음', 3], ['전체', 5], ['material', 4]];

const ALERTS = [
  {
    trigger: 'contradicting_evidence', severity: 'material', at: '2026-08-03 09:00 KST',
    unread: true, tone: 'error',
    headline: '기존 결론 반박 — "A사는 B사에 주로 의존한다" 주장에 반대 증거 발견',
    campaign: 'inv-01J9C4 · A사 공급망 다변화', target: 'claim clm-01J9K2',
    before: '0.61', delta: '−0.13', after: '0.48', afterLabel: 'After · contested',
    basis: '지지 7건 → 7건(불변) · 반대 1→2건 · 독립 출처 2건 · 신규 CONTRADICTS 엣지 1',
    meta: [['Cause · mutation', 'mut-01J9M7'], ['신규 문서', 'doc-5540 · 보도자료'],
      ['correlation', 'cor-7f2a…c19'], ['독립 증거 수', '2 (dup 보정)']],
    dedup: 'inv-01J9C4:contradicting_evidence:clm-01J9K2',
    fireNote: '1회 점화 — 동일 변화 재알림 안 함 (fire_count 1)',
  },
  {
    trigger: 'new_independent_source', severity: 'material', at: '2026-08-02 15:20 KST',
    unread: true, tone: 'success',
    headline: '독립 출처 추가 — C사 계약 관련 독립 취득 1차 자료 확보',
    campaign: 'inv-01J9C4 · A사 공급망 다변화', target: 'claim clm-01J9P8',
    before: '0.44', delta: '+0.16', after: '0.60', afterLabel: 'After · supports',
    basis: '지지 4→5건 · 독립 출처 1→2건(핵심 상승) · 신규 문서는 기존 클러스터와 별개 root',
    meta: [['Cause · mutation', 'mut-01J9N3'], ['신규 문서', 'doc-6120 · SEC 8-K'],
      ['correlation', 'cor-2b81…4de'], ['독립 증거 수', '2 (신규 root +1)']],
    dedup: 'inv-01J9C4:new_independent_source:clm-01J9P8',
    fireNote: '1회 점화 — 독립 출처 증가 시점 1회만 (fire_count 1)',
  },
  {
    trigger: 'plan_to_execution', severity: 'minor', at: '2026-08-01 11:05 KST',
    tone: 'warning',
    headline: '계획→실행 증거 — "C사 공급 계약"이 발표(planned)에서 집행(confirmed)으로 전환',
    campaign: 'inv-01J9C4 · A사 공급망 다변화', target: 'mutation mut-01J9L1',
    before: 'planned', delta: 'Event.status', after: 'confirmed', afterLabel: '실행 증거 확인',
    basis: '집행 증빙 1건(공시) 확보 · confidence 0.60 유지(값+근거 병기, 게이지 아님) · claim clm-01J9P8 로 연결',
    meta: [['Cause · mutation', 'mut-01J9L1'], ['신규 문서', 'doc-6120 · SEC 8-K'],
      ['correlation', 'cor-2b81…4de'], ['독립 증거 수', '2']],
    dedup: 'inv-01J9C4:plan_to_execution:evt-01J9R5',
    fireNote: '1회 점화 — planned→confirmed 전환 시 1회 (fire_count 1)',
  },
];

const SUBSCRIPTIONS = [
  ['A사 공급망 다변화', 'inv-01J9C4 · sub-01J9S1', true,
    [['webhook', '/hooks/spire'], ['in_app', '']],
    ['contradicting', 'claim_changed', 'new_source', 'confidence_thr'], '0.15'],
  ['C사 계약 집행 추적', 'inv-01J9D7 · sub-01J9S2', true,
    [['email', 'watch@a-desk']], ['plan_to_exec', 'new_source'], '0.10'],
  ['규제 변경 영향 관찰', 'inv-01J9E2 · sub-01J9S3', false,
    [['in_app', '']], ['confidence_thr', 'contradicting'], '0.20'],
];

function filterRow(label, count, on) {
  return h('div', {key: label, style: {display: 'flex', alignItems: 'center',
    justifyContent: 'space-between', gap: 8, padding: '7px 10px',
    borderRadius: 'var(--radius-inner)',
    background: on ? 'rgba(69,224,111,.07)' : 'transparent'}},
    h(Text, {type: 'supporting'}, label),
    h('span', {style: {fontFamily: 'var(--font-family-code)', fontSize: 11,
      color: count ? 'var(--color-text-primary)' : 'var(--color-text-secondary)'}}, count));
}

const filters = h(LayoutPanel, {width: 288, hasDivider: true, padding: 0, label: 'Triggers'},
  panelHead('Triggers', '점화 유형 · 5'),
  h('div', {style: {padding: '8px 12px'}},
    TRIGGERS.map(([t, ko, n]) =>
      h('div', {key: t, style: {display: 'flex', alignItems: 'center',
        justifyContent: 'space-between', gap: 8, padding: '7px 4px'}},
        h('div', {style: {minWidth: 0}}, id(t),
          h('div', {}, h(Text, {type: 'supporting'}, ko))),
        h(Badge, {variant: n ? 'warning' : 'neutral', label: String(n)})))),
  panelHead('Campaigns'),
  h('div', {style: {padding: '8px 12px'}},
    CAMPAIGNS.map(([c, n], i) => filterRow(c, n, i === 0))),
  panelHead('Scope'),
  h('div', {style: {padding: '8px 12px'}},
    SCOPE.map(([s, n], i) => filterRow(s, n, i === 0))));

function alertCard(a) {
  return h('div', {key: a.dedup, style: {border: '1px solid var(--color-border)',
    borderLeft: `3px solid ${a.tone === 'error' ? 'var(--color-error)'
      : a.tone === 'success' ? 'var(--color-accent)'
      : 'var(--astryx-theme-citadel-signal-amber)'}`,
    borderRadius: 'var(--radius-element)', padding: 14, marginBottom: 12,
    background: a.unread ? 'rgba(255,177,59,.03)' : 'transparent'}},
    h('div', {style: {display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap'}},
      h(Badge, {variant: a.tone, label: a.trigger}),
      h(Badge, {variant: a.severity === 'material' ? 'warning' : 'neutral', label: a.severity}),
      a.unread ? h(Badge, {variant: 'info', label: '안읽음'}) : null,
      h('div', {style: {flex: 1}}), id(a.at)),
    h('div', {style: {marginTop: 10}}, h(Text, {}, a.headline)),
    h('div', {style: {marginTop: 6}}, id(`${a.campaign} · ${a.target}`)),

    h('div', {style: {display: 'flex', alignItems: 'center', gap: 12, margin: '12px 0',
      padding: '10px 12px', background: 'var(--color-background-muted)',
      borderRadius: 'var(--radius-inner)'}},
      h('div', {}, h('div', {style: {fontFamily: 'var(--font-family-heading)',
        fontSize: 18, fontWeight: 600, color: 'var(--color-text-secondary)'}}, a.before),
        h(Text, {type: 'label'}, 'Before')),
      h('span', {style: {fontFamily: 'var(--font-family-code)', fontSize: 12,
        color: a.tone === 'error' ? 'var(--color-error)' : 'var(--color-accent)'}}, a.delta),
      h('div', {}, h('div', {style: {fontFamily: 'var(--font-family-heading)',
        fontSize: 18, fontWeight: 600, color: 'var(--color-text-primary)'}}, a.after),
        h(Text, {type: 'label'}, a.afterLabel))),

    h(Text, {type: 'supporting'}, `근거: ${a.basis}`),
    h('div', {style: {display: 'grid', gridTemplateColumns: 'repeat(2,minmax(0,1fr))',
      gap: 8, marginTop: 10}},
      a.meta.map(([k, v]) => h('div', {key: k},
        h(Text, {type: 'label'}, k), h('div', {}, id(v))))),
    h('div', {style: {marginTop: 10, display: 'flex', alignItems: 'center', gap: 8,
      flexWrap: 'wrap'}},
      h(Badge, {variant: 'neutral', label: a.fireNote})),
    h('div', {style: {marginTop: 4}}, id(`dedup: ${a.dedup}`)),
    h('div', {style: {marginTop: 10, display: 'flex', gap: 8, flexWrap: 'wrap'}},
      ...['War Table에서 보기', 'Hall of Witnesses', '확인 처리'].map(t =>
        h('span', {key: t, style: {padding: '6px 12px', fontSize: 11,
          fontFamily: 'var(--font-family-heading)', fontWeight: 600,
          border: '1px solid var(--color-border)', borderRadius: 'var(--radius-element)',
          color: 'var(--color-text-secondary)'}}, t))));
}

const feed = h(LayoutContent, {padding: 0},
  panelHead('Alert Feed', 'A사 공급망 다변화 · 안읽음 3 / 5'),
  h('div', {style: {display: 'flex', gap: 6, padding: '10px 16px',
    borderBottom: '1px solid var(--color-border)'}},
    ...['안읽음', '전체', '확인됨'].map((t, i) =>
      h('span', {key: t, style: {padding: '5px 12px', fontSize: 11.5,
        fontFamily: 'var(--font-family-heading)', fontWeight: 600,
        borderRadius: 'var(--radius-element)',
        background: i === 0 ? 'rgba(69,224,111,.08)' : 'transparent',
        color: i === 0 ? 'var(--color-accent)' : 'var(--color-text-secondary)'}}, t)),
    h('div', {style: {flex: 1}}),
    h(Text, {type: 'supporting'}, '최신순 · 1회 점화 · dedup 적용')),
  h('div', {style: {padding: 16}}, ALERTS.map(alertCard)));

const subscriptions = h(LayoutPanel, {width: 340, hasDivider: true, padding: 0,
  label: 'Subscriptions'},
  panelHead('Subscriptions', 'Campaign 구독 · 3'),
  h('div', {style: {padding: 16}},
    SUBSCRIPTIONS.map(([name, ids, on, channels, triggers, threshold]) =>
      h('div', {key: ids, style: {border: '1px solid var(--color-border)',
        borderRadius: 'var(--radius-element)', padding: 12, marginBottom: 10}},
        h('div', {style: {display: 'flex', alignItems: 'center',
          justifyContent: 'space-between', gap: 8}},
          h(Text, {type: 'supporting'}, name),
          h(Badge, {variant: on ? 'success' : 'neutral', label: on ? 'ON' : 'OFF'})),
        h('div', {style: {marginTop: 4}}, id(ids)),
        h('div', {style: {marginTop: 8}}, h(Text, {type: 'label'}, 'Channels')),
        h('div', {style: {display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 4}},
          channels.map(([c, v]) =>
            h(Badge, {key: c, variant: 'neutral', label: v ? `${c} ${v}` : c}))),
        h('div', {style: {marginTop: 8}}, h(Text, {type: 'label'}, 'Active Triggers')),
        h('div', {style: {display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 4}},
          triggers.map(t => h(Badge, {key: t, variant: 'blue', label: t}))),
        h('div', {style: {display: 'flex', alignItems: 'baseline',
          justifyContent: 'space-between', marginTop: 8}},
          h(Text, {type: 'supporting'}, 'confidence Δ 임계'),
          id(threshold)))),
    h('div', {style: {padding: '10px 12px', border: '1px dashed var(--color-border)',
      borderRadius: 'var(--radius-element)', textAlign: 'center'}},
      h(Text, {type: 'supporting'}, '새 구독 · New Subscription'))));

export const render = () => shell({
  route: 'signal-spire',
  eyebrow: 'Signal Spire · Alerts',
  context: '알림 센터',
  title: 'Signal Spire · 알림 센터',
  subtitle: '결론·confidence 변화 · 신규 모순 · 독립 출처 알림',
  hero: 'signal-spire-hero.png',
  slots: {start: filters, content: feed, end: subscriptions},
});
