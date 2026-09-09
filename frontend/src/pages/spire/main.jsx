/**
 * Signal Spire · 알림 센터 (Step 10 — specs TS-5).
 *
 * 소비 API: /api/spire (trigger_catalog · fire_once_rule · alerts · note).
 * alert 는 in-memory fire-once 로 영속이 없다 — 전 열을 가공 없이 정직 빈으로
 * 렌더한다 (honest-gap §6.2). 카드 골격(ui/spire.mjs)은 목업 fixture 가 증명하고,
 * 실 점화가 생기면 같은 조각으로 그린다. 구독은 쓰기 UI 없이 비활성 자리만(§3-3).
 */

import React from 'react';
import {createRoot} from 'react-dom/client';
import {LayoutContent, LayoutPanel} from '@astryxdesign/core/Layout';

import {shell, APP_URLS} from '@ui/shell.mjs';
import {h, Text, panelHead, emptyState, sectionLabel} from '@ui/components.mjs';
import {filterRow, triggerRow, feedTabs, alertCard, newSubscriptionSlot}
  from '@ui/spire.mjs';
import {Palette, usePaletteHotkey} from '../../lib/palette.jsx';

const urls = APP_URLS;
const jfetch = (p) => fetch(p)
  .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${p} → ${r.status}`))));

function App() {
  const [spire, setSpire] = React.useState(null);
  const [error, setError] = React.useState(null);
  const [paletteOpen, setPaletteOpen] = React.useState(false);
  usePaletteHotkey(setPaletteOpen);

  React.useEffect(() => { jfetch('/api/spire').then(setSpire).catch(setError); }, []);

  const alerts = (spire && spire.alerts) || [];
  const catalog = (spire && spire.trigger_catalog) || [];

  // 좌 — Triggers(정본 카탈로그 실측) · Campaigns · Scope
  const filters = h(LayoutPanel, {width: 288, hasDivider: true, padding: 0,
    label: 'Triggers'},
    panelHead('Triggers', `점화 유형 · ${catalog.length || '…'}`),
    h('div', {style: {padding: '8px 12px'}},
      catalog.length
        ? catalog.map((t) => h('div', {key: t.trigger},
            triggerRow({trigger: t.trigger, description: t.description,
              fired: alerts.filter((a) => a.trigger === t.trigger).length})))
        : h(Text, {type: 'supporting'}, error ? String(error) : '카탈로그 불러오는 중…')),
    panelHead('Campaigns'),
    h('div', {style: {padding: '8px 12px'}},
      h(Text, {type: 'supporting'},
        'campaign 구독 영속 없음 — 점화된 alert 가 생기면 campaign 축으로 묶인다')),
    panelHead('Scope'),
    h('div', {style: {padding: '8px 12px'}},
      ['안읽음', '전체', 'material'].map((s, i) =>
        h('div', {key: s}, filterRow({label: s, count: alerts.length, on: i === 0})))));

  // 중앙 — Alert Feed: 실 점화 없음 → 정직 빈 (fire-once 규칙 인용)
  const feed = h(LayoutContent, {padding: 0},
    panelHead('Alert Feed', `안읽음 ${alerts.length} / ${alerts.length}`),
    feedTabs({tabs: ['안읽음', '전체', '확인됨'], active: 0,
      note: '최신순 · 1회 점화 · dedup 적용'}),
    h('div', {style: {padding: 16}},
      alerts.length
        ? alerts.map((a, i) => h('div', {key: a.dedup || i}, alertCard(a)))
        : emptyState({art: 'empty-spire.png', assetBase: '/assets/img/',
            title: '새 알림 없음',
            description: spire
              ? `${spire.note} ${spire.fire_once_rule}`
              : '알림 상태 불러오는 중…'})));

  // 우 — Subscriptions: 영속 없음 → 정직 빈 + 비활성 자리(read-only §3-3)
  const subscriptions = h(LayoutPanel, {width: 340, hasDivider: true, padding: 0,
    label: 'Subscriptions'},
    panelHead('Subscriptions', 'Campaign 구독 · 0'),
    h('div', {style: {padding: 16}},
      h(Text, {type: 'supporting'},
        '구독 영속 저장소 없음 (honest-gap §6.2) — 채널·트리거·임계 카드 구조는 '
        + '목업 fixture 로 증명, 실데이터가 생기면 같은 조각으로 렌더.'),
      sectionLabel('New Subscription'),
      newSubscriptionSlot()));

  return h(React.Fragment, {},
    shell({
      route: 'signal-spire',
      eyebrow: 'Signal Spire · Alerts',
      context: '알림 센터',
      title: 'Signal Spire · 알림 센터',
      subtitle: '결론·confidence 변화 · 신규 모순 · 독립 출처 알림',
      hero: 'signal-spire-hero.png',
      alerts: alerts.length,
      urls,
      onSearchOpen: () => setPaletteOpen(true),
      slots: {start: filters, content: feed, end: subscriptions},
    }),
    h(Palette, {open: paletteOpen, onClose: () => setPaletteOpen(false)}));
}

createRoot(document.getElementById('root')).render(h(App));
