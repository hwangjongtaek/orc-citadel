/**
 * Chronicle Vault 조각 — 듀얼 타임 슬라이더 · preset 질문 칩 · 이벤트 레일 ·
 * assertion 상세 카드.
 *
 * 시간축은 /api/chronicle bounds 실측만 그린다 — valid 축 실측 부재(전부 null)
 * 면 가짜 축 대신 정직 빈 라벨 (§6.2). props 렌더만 — fetch·상태는 소비자 몫.
 */

import {h, Badge, Text, id} from './components.mjs';

export const ts = (v) => {
  const x = v ? Date.parse(String(v)) : NaN;
  return Number.isNaN(x) ? null : x;
};
export const fmt = (ms) => ms == null ? '—'
  : new Date(ms).toISOString().slice(0, 16).replace('T', ' ');

/**
 * 듀얼 레인지 슬라이더 축 — [a, b] 는 0~100 퍼센트, onChange(a, b).
 * bounds 실측 없으면(lo/hi null) 정직 빈 라벨을 그린다 (슬라이더 없음).
 */
export function axisSlider({label, color, lo, hi, a, b, onChange, emptyNote}) {
  const head = h('div', {style: {display: 'flex', alignItems: 'baseline', gap: 8,
    margin: '8px 0 4px'}},
    h('span', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 10,
      fontWeight: 600, letterSpacing: '.1em', textTransform: 'uppercase', color}},
      label),
    lo != null && hi != null
      ? id(`${fmt(lo + (hi - lo) * (a / 100))} — ${fmt(lo + (hi - lo) * (b / 100))}`)
      : null);
  if (lo == null || hi == null) {
    return h('div', {}, head,
      h(Text, {type: 'supporting'},
        emptyNote || `${label} 실측 없음 — 타임스탬프 미누적 (honest-gap §6.2)`));
  }
  const range = (key, value) => h('input', {
    type: 'range', min: 0, max: 100, value,
    onChange: (e) => {
      const v = Number(e.target.value);
      onChange(key === 'a' ? Math.min(v, b) : a,
               key === 'b' ? Math.max(v, a) : b);
    },
    style: {position: 'absolute', left: 0, right: 0, top: 0, width: '100%',
      appearance: 'none', WebkitAppearance: 'none', background: 'none',
      pointerEvents: 'none', height: 22}});
  return h('div', {}, head,
    h('div', {style: {display: 'flex', alignItems: 'center', gap: 8}},
      id(fmt(lo).slice(0, 10)),
      h('div', {style: {position: 'relative', flex: 1, height: 22}},
        h('span', {style: {position: 'absolute', top: 10, left: 0, right: 0,
          height: 2, background: 'var(--color-border)'}}),
        h('span', {style: {position: 'absolute', top: 10, height: 2,
          left: `${a}%`, width: `${Math.max(0, b - a)}%`, background: color}}),
        range('a', a), range('b', b)),
      id(fmt(hi).slice(0, 10))),
    // thumb 만 포인터 활성 — 두 레인지가 겹쳐도 둘 다 잡힌다.
    h('style', {}, `input[type=range]::-webkit-slider-thumb{pointer-events:auto;
      -webkit-appearance:none;appearance:none;width:12px;height:12px;
      border-radius:9999px;background:var(--color-text-primary);
      border:2px solid var(--color-background-body);cursor:pointer;margin-top:-5px}
      input[type=range]::-webkit-slider-runnable-track{height:2px;background:transparent}`));
}

/** preset 질문 칩 — 재료 없으면 비활성 (클릭 불가 + 사유 병기). */
export function presetChips({presets, onSelect}) {
  return h('div', {style: {display: 'flex', flexWrap: 'wrap', gap: 8}},
    presets.map((q, i) =>
      h('span', {key: i,
        onClick: q.enabled && onSelect ? () => onSelect(i) : undefined,
        style: {display: 'inline-flex', alignItems: 'center', gap: 6,
          padding: '5px 12px', borderRadius: 'var(--radius-full)', fontSize: 11,
          fontFamily: 'var(--font-family-heading)', fontWeight: 600,
          border: `1px solid ${q.enabled ? 'var(--color-accent)'
            : 'var(--color-border)'}`,
          background: q.enabled ? 'rgba(69,224,111,.06)' : 'transparent',
          color: q.enabled ? 'var(--color-text-primary)'
            : 'var(--color-text-secondary)',
          opacity: q.enabled ? 1 : .5,
          cursor: q.enabled ? 'pointer' : 'not-allowed'}},
        q.label + (q.enabled ? '' : ' · 재료 없음 (비활성)'))));
}

const EVENT_COLORS = {
  asserted: 'var(--color-accent)',
  closed: 'var(--color-error)',
  superseded: 'var(--astryx-theme-citadel-uncertain)',
};

/** 이벤트 레일 — tx 타임스탬프 실측 핀 (asserted·closed·superseded). */
export function eventsRail({events, onSelect}) {
  const stamps = events.map((e) => ts(e.at)).filter((x) => x != null);
  if (!stamps.length) {
    return h(Text, {type: 'supporting'},
      '이벤트 실측 없음 — assertion tx 타임스탬프 미누적 (honest-gap §6.2)');
  }
  const lo = Math.min(...stamps), hi = Math.max(...stamps);
  const span = Math.max(1, hi - lo);
  return h('div', {style: {flex: 1, minWidth: 280}},
    h('div', {style: {position: 'relative', height: 18, margin: '0 6px'}},
      h('span', {style: {position: 'absolute', top: 8, left: 0, right: 0, height: 1,
        background: 'var(--color-border)'}}),
      events.map((e, i) => {
        const t = ts(e.at);
        if (t == null) return null;
        return h('span', {key: i,
          title: `${e.at} · ${e.kind} · ${e.predicate || ''}`,
          onClick: onSelect ? () => onSelect(e) : undefined,
          style: {position: 'absolute', top: '50%', left: `${(100 * (t - lo)) / span}%`,
            transform: 'translate(-50%,-50%)', width: 9, height: 9,
            borderRadius: 'var(--radius-full)',
            background: EVENT_COLORS[e.kind] || 'var(--color-border)',
            border: '2px solid var(--color-background-body)',
            cursor: onSelect ? 'pointer' : 'default'}});
      })),
    h('div', {style: {display: 'flex', justifyContent: 'space-between', gap: 8}},
      id(fmt(lo).slice(0, 10)),
      h(Text, {type: 'supporting'},
        `${events.length} events · ● asserted · ● closed · ● superseded`),
      id(fmt(hi).slice(0, 10))));
}

/** assertion 상세 카드 — bitemporal 4셀 + supersedes 체인 + 이벤트 타임라인. */
export function assertionCard({a, chain = [], events = []}) {
  const cell = (v, cap) => h('div', {style: {background: 'var(--color-background-card)',
    padding: '8px 10px'}},
    h('div', {style: {fontFamily: 'var(--font-family-code)', fontSize: 12,
      color: 'var(--color-text-primary)'}}, v),
    h('div', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 9,
      letterSpacing: '.06em', textTransform: 'uppercase',
      color: 'var(--color-text-secondary)', marginTop: 3}}, cap));
  const d = (v, inf) => v ? String(v).slice(0, 10) : (inf ? '∞' : '—');
  return h('div', {},
    h('div', {style: {border: '1px solid var(--color-accent)',
      background: 'rgba(69,224,111,.05)', borderRadius: 'var(--radius-element)',
      padding: 12}},
      h(Text, {}, [a.predicate || 'assertion',
        a.object_literal != null ? String(a.object_literal) : null]
        .filter(Boolean).join(' → ')),
      h('div', {style: {marginTop: 6}},
        id(`${a.assertion_id} · subj ${a.subject_id || '—'}`)),
      a.claim_id ? h('div', {style: {marginTop: 2}}, id(`claim ${a.claim_id}`)) : null),
    h('div', {style: {display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: 1,
      background: 'var(--color-border)', border: '1px solid var(--color-border)',
      borderRadius: 'var(--radius-element)', overflow: 'hidden', marginTop: 10}},
      cell(d(a.valid_from), 'valid_from'), cell(d(a.valid_to, true), 'valid_to'),
      cell(d(a.tx_from), 'tx_from'), cell(d(a.tx_to, true), 'tx_to')),
    h('div', {style: {marginTop: 8, display: 'flex', alignItems: 'center', gap: 8,
      flexWrap: 'wrap'}},
      h(Badge, {variant: a.supersedes_id ? 'warning' : 'neutral',
        label: a.supersedes_id ? `supersedes ${a.supersedes_id.slice(0, 12)}…`
          : 'supersedes —'}),
      h(Badge, {variant: 'neutral', label: `events ${events.length}`})),
    events.length ? h('div', {style: {marginTop: 8}},
      h(Text, {type: 'label'}, 'Timeline'),
      h('div', {style: {marginTop: 4, display: 'flex', flexWrap: 'wrap', gap: 6}},
        events.map((e, i) => h('span', {key: i},
          id(`${String(e.at || '—').slice(0, 16).replace('T', ' ')} · ${e.kind}`
             + (i < events.length - 1 ? '  →' : '')))))) : null,
    chain.length ? h('div', {style: {marginTop: 8}},
      h(Text, {type: 'label'}, 'Supersedes 체인'),
      h('div', {style: {marginTop: 4}},
        chain.map((c) => h('div', {key: c}, id(`◀ ${c}`))))) : null);
}
