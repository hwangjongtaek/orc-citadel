/**
 * Grand Archive 조각 — Sifter(facet chip) · Stacks(문서 카드·페이저) · lineage 뱃지.
 *
 * 목업(fixture)과 앱(/api/archive)이 같은 조각을 소비한다. 필터·검색·페이지의
 * 상태는 소비자 몫 — 여기는 props 렌더만 한다 (재조회·fetch 없음).
 */

import {h, Badge, Text, id} from './components.mjs';

/** dedup 계보 역할 → 표식·톤. 기호 병기 — 색만으로 의미 전달 금지 (DESIGN.md). */
export const ROLE_MARKS = {
  root: ['●', 'success', '근원'],
  derived: ['○', 'neutral', '파생'],
  independent: ['◆', 'info', '독립추가'],
};

/** dedup lineage 뱃지 — cluster_role null 은 클러스터 밖(뱃지 없음 아님, — 표기). */
export function lineageBadge(role) {
  const m = ROLE_MARKS[role];
  if (!m) return id('—');
  return h(Badge, {variant: m[1], label: `${m[0]} ${role} · ${m[2]}`});
}

/**
 * Facet chip 묶음 — {키: 건수} 를 클릭 가능한 chip 행으로.
 * `active` 와 같은 키를 다시 누르면 해제(onToggle(''))가 소비자 계약.
 */
export function facetChips({counts, active, onToggle, fmt = (k) => k}) {
  const keys = Object.keys(counts || {}).sort();
  if (!keys.length) return h(Text, {type: 'supporting'}, '실측 0 — 문서 없음');
  return h('div', {style: {display: 'flex', flexWrap: 'wrap', gap: 6}},
    keys.map((k) => {
      const on = active === k;
      return h('span', {key: k,
        onClick: onToggle ? () => onToggle(on ? '' : k) : undefined,
        style: {display: 'inline-flex', alignItems: 'center', gap: 6,
          padding: '4px 10px', cursor: onToggle ? 'pointer' : 'default',
          border: `1px solid ${on ? 'var(--color-accent)' : 'var(--color-border)'}`,
          background: on ? 'rgba(69,224,111,.08)' : 'transparent',
          borderRadius: 'var(--radius-full)',
          fontFamily: 'var(--font-family-heading)', fontSize: 11,
          color: on ? 'var(--color-accent)' : 'var(--color-text-secondary)'}},
        fmt(k), id(String(counts[k])));
    }));
}

/** Stacks 문서 카드 — id + lineage 뱃지 + 제목 + 출처·시각 메타. */
export function docCard({docId, title, source, meta, role, active, onClick}) {
  return h('div', {onClick,
    style: {cursor: onClick ? 'pointer' : 'default',
      border: `1px solid ${active ? 'var(--color-accent)' : 'var(--color-border)'}`,
      background: active ? 'rgba(69,224,111,.05)' : 'transparent',
      borderRadius: 'var(--radius-element)', padding: 12, marginBottom: 8}},
    h('div', {style: {display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap'}},
      id(docId), lineageBadge(role)),
    h('div', {style: {marginTop: 6}}, h(Text, {}, title)),
    h('div', {style: {marginTop: 6, display: 'flex', gap: 10, flexWrap: 'wrap',
      alignItems: 'baseline'}},
      h(Text, {type: 'supporting'}, source), meta ? id(meta) : null));
}

/** 서버 페이지네이션 컨트롤 — `from–to / total (존 전체 all)` + 이전/다음. */
export function pager({offset, limit, shown, total, zoneTotal, onPrev, onNext}) {
  const from = total ? offset + 1 : 0;
  const to = offset + shown;
  const num = (n) => Number(n || 0).toLocaleString();
  const btn = (label, disabled, onClick) =>
    h('button', {onClick, disabled, style: {
      padding: '4px 12px', cursor: disabled ? 'default' : 'pointer',
      border: '1px solid var(--color-border)', background: 'transparent',
      borderRadius: 'var(--radius-element)',
      fontFamily: 'var(--font-family-heading)', fontSize: 11,
      color: disabled ? 'var(--color-text-secondary)' : 'var(--color-accent)',
      opacity: disabled ? .5 : 1}}, label);
  return h('div', {style: {display: 'flex', alignItems: 'center', gap: 10,
    flexWrap: 'wrap'}},
    id(`${num(from)}–${num(to)} / ${num(total)}`
       + (zoneTotal != null && zoneTotal !== total ? ` (존 전체 ${num(zoneTotal)})` : '')),
    btn('‹ 이전', offset <= 0, onPrev),
    btn('다음 ›', to >= (total || 0), onNext));
}

/** Sifter 검색창 — Enter 로 onSubmit(value). 서버 contains(ILIKE) — BM25 아님. */
export function sifterSearch({defaultValue, placeholder, onSubmit}) {
  return h('div', {},
    h('input', {defaultValue, placeholder,
      onKeyDown: onSubmit ? (e) => {
        if (e.key === 'Enter') onSubmit(e.target.value.trim());
      } : undefined,
      style: {width: '100%', boxSizing: 'border-box', padding: '8px 12px',
        border: '1px solid var(--color-border)',
        borderRadius: 'var(--radius-element)',
        background: 'var(--color-background-muted)',
        fontFamily: 'var(--font-family-code)', fontSize: 11.5,
        color: 'var(--color-text-primary)', outline: 'none'}}),
    h('div', {style: {marginTop: 6}},
      h(Text, {type: 'supporting'},
        'text contains (ILIKE) — title · url · doc_id · BM25 아님')));
}
