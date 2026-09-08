/**
 * Signal Spire 조각 — 필터 행 · 알림 카드 · 구독 카드 · 피드 탭.
 *
 * alert 는 in-memory fire-once 라 영속이 없다 (honest-gap §6.2) — 카드 구조는
 * 목업이 fixture 로 증명하고, 앱은 실 점화가 생길 때 같은 조각으로 렌더한다.
 * 여기는 props 렌더만 — 상태·fetch 없음.
 */

import {h, Badge, Text, id} from './components.mjs';

/** 좌측 필터 행 — 라벨 + 카운트 (on 이면 강조 배경). */
export function filterRow({label, count, on, onClick}) {
  return h('div', {onClick, style: {display: 'flex', alignItems: 'center',
    justifyContent: 'space-between', gap: 8, padding: '7px 10px',
    cursor: onClick ? 'pointer' : 'default', borderRadius: 'var(--radius-inner)',
    background: on ? 'rgba(69,224,111,.07)' : 'transparent'}},
    h(Text, {type: 'supporting'}, label),
    h('span', {style: {fontFamily: 'var(--font-family-code)', fontSize: 11,
      color: count ? 'var(--color-text-primary)' : 'var(--color-text-secondary)'}},
      String(count)));
}

/** 트리거 카탈로그 행 — 트리거 id + 설명 + 점화 수 뱃지. */
export function triggerRow({trigger, description, fired}) {
  return h('div', {style: {display: 'flex', alignItems: 'center',
    justifyContent: 'space-between', gap: 8, padding: '7px 4px'}},
    h('div', {style: {minWidth: 0}}, id(trigger),
      h('div', {}, h(Text, {type: 'supporting'}, description))),
    // 뱃지는 수축 금지 — 설명이 길면 텍스트 쪽이 줄바꿈한다 (truncate 방지).
    h('span', {style: {flexShrink: 0}},
      h(Badge, {variant: fired ? 'warning' : 'neutral',
        label: fired ? String(fired) : '0 · not-fired'})));
}

/** 피드 탭 스트립 — 탭 이름 배열 + 활성 인덱스 + 우측 보조 라벨. */
export function feedTabs({tabs, active = 0, note, onSelect}) {
  return h('div', {style: {display: 'flex', gap: 6, padding: '10px 16px',
    alignItems: 'center', borderBottom: '1px solid var(--color-border)'}},
    ...tabs.map((t, i) =>
      h('span', {key: t, onClick: onSelect ? () => onSelect(i) : undefined,
        style: {padding: '5px 12px', fontSize: 11.5,
          fontFamily: 'var(--font-family-heading)', fontWeight: 600,
          cursor: onSelect ? 'pointer' : 'default',
          borderRadius: 'var(--radius-element)',
          background: i === active ? 'rgba(69,224,111,.08)' : 'transparent',
          color: i === active ? 'var(--color-accent)' : 'var(--color-text-secondary)'}},
        t)),
    h('div', {style: {flex: 1}}),
    note ? h(Text, {type: 'supporting'}, note) : null);
}

/**
 * 알림 카드 — Before → Δ → After 를 값+근거 병기로 (단일 게이지 금지, DESIGN.md).
 * fire-once dedup 키를 카드에 노출한다 (ADR-1104 — 재알림 없음의 증거).
 */
export function alertCard(a) {
  return h('div', {style: {border: '1px solid var(--color-border)',
    borderLeft: `3px solid ${a.tone === 'error' ? 'var(--color-error)'
      : a.tone === 'success' ? 'var(--color-accent)'
      : 'var(--astryx-theme-citadel-signal-amber)'}`,
    borderRadius: 'var(--radius-element)', padding: 14, marginBottom: 12,
    background: a.unread ? 'rgba(255,177,59,.03)' : 'transparent'}},
    h('div', {style: {display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap'}},
      h(Badge, {variant: a.tone, label: a.trigger}),
      h(Badge, {variant: a.severity === 'material' ? 'warning' : 'neutral',
        label: a.severity}),
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
        color: a.tone === 'error' ? 'var(--color-error)' : 'var(--color-accent)'}},
        a.delta),
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

/** 구독 카드 — 채널·활성 트리거·임계. 쓰기 UI 없음(read-only §3-3). */
export function subscriptionCard({name, ids, on, channels, triggers, threshold}) {
  return h('div', {style: {border: '1px solid var(--color-border)',
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
      id(threshold)));
}

/** 새 구독 자리 — 비활성 (read-only 프로토타입 §3-3, 쓰기 UI 는 자리만). */
export function newSubscriptionSlot() {
  return h('div', {style: {padding: '10px 12px',
    border: '1px dashed var(--color-border)',
    borderRadius: 'var(--radius-element)', textAlign: 'center', opacity: .75}},
    h(Text, {type: 'supporting'},
      '새 구독 · New Subscription — read-only 프로토타입 · 비활성'));
}
