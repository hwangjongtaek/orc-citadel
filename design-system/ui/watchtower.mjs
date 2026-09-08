/**
 * Watchtower 조각 — stage 카드 · 실패/DLQ 카드 · SLO 카드 · Grafana 딥링크 카드.
 *
 * 목업은 fixture 로 구조를 증명하고, 앱은 실측(/api/watchtower)만 그린다 —
 * stage 수치·실패 사례가 wire 에 없으면 가공하지 않고 not-measured 정직 렌더.
 */

import {h, Card, Badge, Text, id} from './components.mjs';

/** stage 처리량 카드 — rate 미측정('—')이어도 같은 골격. */
export function stageCard({sid, name, rate, rateUnit = 'docs/min', backlog, fail}) {
  return h(Card, {}, h('div', {style: {padding: 4}},
    h('div', {style: {display: 'flex', alignItems: 'center', gap: 8}},
      h(Badge, {variant: 'neutral', label: sid}),
      h(Text, {type: 'label'}, name)),
    h('div', {style: {display: 'flex', alignItems: 'baseline', gap: 4, marginTop: 8}},
      h('span', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 24,
        fontWeight: 600, color: rate === '—' ? 'var(--color-text-secondary)'
          : 'var(--color-text-primary)'}}, rate),
      h(Text, {type: 'supporting'}, rateUnit)),
    h('div', {style: {display: 'flex', gap: 16, marginTop: 8}},
      h('div', {}, h(Text, {type: 'label'}, 'backlog'), h('div', {}, id(backlog))),
      h('div', {}, h(Text, {type: 'label'}, '실패'), h('div', {}, id(fail))))));
}

/** 실패·DLQ 카드 — 좌측 톤 띠 + 사유/상태/식별자/조치. */
export function failureCard({reason, state, tone, ids, note}) {
  return h('div', {style: {border: '1px solid var(--color-border)',
    borderLeft: `3px solid ${tone === 'error' ? 'var(--color-error)'
      : 'var(--astryx-theme-citadel-signal-amber)'}`,
    borderRadius: 'var(--radius-element)', padding: '10px 12px', marginBottom: 10}},
    h('div', {style: {display: 'flex', alignItems: 'center',
      justifyContent: 'space-between', gap: 8}},
      h(Text, {}, reason), h(Badge, {variant: tone, label: state})),
    h('div', {style: {marginTop: 4}}, id(ids)),
    h('div', {style: {marginTop: 4}}, h(Text, {type: 'supporting'}, note)));
}

/** SLO 판정 카드 — 현재값·목표·측정 창 + 판정 뱃지 (not-measured 정직). */
export function sloCard({name, sid, current, target, window: win, verdict}) {
  const tones = {ok: 'success', warn: 'warning', 'slo-gate': 'warning',
                 'not-measured': 'purple', TBD: 'purple'};
  return h('div', {style: {border: '1px solid var(--color-border)',
    borderRadius: 'var(--radius-element)', padding: '11px 12px', marginBottom: 10}},
    h('div', {style: {display: 'flex', alignItems: 'center',
      justifyContent: 'space-between', gap: 8}},
      h(Text, {type: 'supporting'}, name), id(sid)),
    h('div', {style: {display: 'flex', alignItems: 'baseline',
      justifyContent: 'space-between', marginTop: 6}},
      h('span', {style: {fontFamily: 'var(--font-family-code)', fontSize: 15,
        color: verdict === 'warn' ? 'var(--astryx-theme-citadel-signal-amber)'
          : 'var(--color-text-primary)'}}, current),
      h('span', {style: {fontFamily: 'var(--font-family-code)', fontSize: 11,
        color: 'var(--color-text-secondary)'}}, target ? `목표 ${target}` : '')),
    h('div', {style: {display: 'flex', alignItems: 'center', gap: 8, marginTop: 6}},
      h(Badge, {variant: tones[verdict] || 'neutral', label: verdict}),
      h(Text, {type: 'supporting'}, win)));
}

/** Grafana 딥링크 카드 (FR-6) — 운영 drill-down 은 Grafana, 여기는 요약+링크. */
export function grafanaCard({url, note}) {
  return h('div', {style: {marginTop: 10, padding: '10px 12px', display: 'flex',
    alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap',
    background: 'rgba(255,177,59,.05)', border: '1px solid rgba(255,177,59,.25)',
    borderRadius: 'var(--radius-element)'}},
    h('div', {style: {minWidth: 0}},
      h(Text, {type: 'label'}, 'Grafana · Pipeline Observability'),
      h('div', {style: {marginTop: 4}}, h(Text, {type: 'supporting'}, note))),
    url ? h('a', {href: url, target: '_blank', rel: 'noopener',
      style: {fontFamily: 'var(--font-family-heading)', fontSize: 11.5,
        fontWeight: 600, color: 'var(--astryx-theme-citadel-signal-amber)',
        textDecoration: 'none', whiteSpace: 'nowrap'}}, 'Grafana에서 열기 →')
      : h('span', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 11.5,
        fontWeight: 600, color: 'var(--color-text-secondary)',
        whiteSpace: 'nowrap'}}, 'Grafana 미배선 (14b)'));
}
