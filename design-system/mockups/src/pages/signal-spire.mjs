/** Signal Spire · 알림 센터 — Triggers·Campaigns·Scope | Alert Feed | Subscriptions. */

import {LayoutContent, LayoutPanel} from '@astryxdesign/core/Layout';
import {shell} from '../../../ui/shell.mjs';
import {h, panelHead} from '../../../ui/components.mjs';
import {filterRow, triggerRow, feedTabs, alertCard, subscriptionCard,
  newSubscriptionSlot} from '../../../ui/spire.mjs';

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

const filters = h(LayoutPanel, {width: 288, hasDivider: true, padding: 0, label: 'Triggers'},
  panelHead('Triggers', '점화 유형 · 5'),
  h('div', {style: {padding: '8px 12px'}},
    TRIGGERS.map(([t, ko, n]) =>
      h('div', {key: t}, triggerRow({trigger: t, description: ko, fired: n})))),
  panelHead('Campaigns'),
  h('div', {style: {padding: '8px 12px'}},
    CAMPAIGNS.map(([c, n], i) =>
      h('div', {key: c}, filterRow({label: c, count: n, on: i === 0})))),
  panelHead('Scope'),
  h('div', {style: {padding: '8px 12px'}},
    SCOPE.map(([s, n], i) =>
      h('div', {key: s}, filterRow({label: s, count: n, on: i === 0})))));

const feed = h(LayoutContent, {padding: 0},
  panelHead('Alert Feed', 'A사 공급망 다변화 · 안읽음 3 / 5'),
  feedTabs({tabs: ['안읽음', '전체', '확인됨'], active: 0,
    note: '최신순 · 1회 점화 · dedup 적용'}),
  h('div', {style: {padding: 16}},
    ALERTS.map(a => h('div', {key: a.dedup}, alertCard(a)))));

const subscriptions = h(LayoutPanel, {width: 340, hasDivider: true, padding: 0,
  label: 'Subscriptions'},
  panelHead('Subscriptions', 'Campaign 구독 · 3'),
  h('div', {style: {padding: 16}},
    SUBSCRIPTIONS.map(([name, ids, on, channels, triggers, threshold]) =>
      h('div', {key: ids},
        subscriptionCard({name, ids, on, channels, triggers, threshold}))),
    newSubscriptionSlot()));

export const render = () => shell({
  route: 'signal-spire',
  eyebrow: 'Signal Spire · Alerts',
  context: '알림 센터',
  title: 'Signal Spire · 알림 센터',
  subtitle: '결론·confidence 변화 · 신규 모순 · 독립 출처 알림',
  hero: 'signal-spire-hero.png',
  slots: {start: filters, content: feed, end: subscriptions},
});
