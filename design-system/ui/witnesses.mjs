/**
 * Hall of Witnesses 공용 컴포넌트 — claim 목록 · Evidence/Provenance · 원문 왕복.
 * 목업(fixture)과 앱(/api/*)이 공유한다 (TS-2·TS-5). props-only · no-JSX.
 */

import {h, Badge, HStack, Text, id} from './components.mjs';

/** claim 목록 행 — 텍스트 + id·predicate + modality 배지 + confidence. */
export function claimRow({text, meta, modality, conf, active, onClick, key}) {
  return h('div', {key: key || meta, onClick,
    style: {
      border: `1px solid ${active ? 'var(--color-accent)' : 'var(--color-border)'}`,
      background: active ? 'rgba(69,224,111,.05)' : 'transparent',
      borderRadius: 'var(--radius-element)', padding: 12, marginBottom: 10,
      ...(onClick ? {cursor: 'pointer'} : null)}},
    h(Text, {type: 'supporting'}, text),
    h('div', {style: {display: 'flex', alignItems: 'center',
      justifyContent: 'space-between', gap: 8, marginTop: 8}},
      id(meta),
      h(HStack, {gap: 1},
        h(Badge, {variant: modality === 'Fact' || modality === 'fact'
          ? 'success' : 'neutral', label: modality}),
        conf != null ? h('span', {style: {fontFamily: 'var(--font-family-heading)',
          fontSize: 13, fontWeight: 600,
          color: 'var(--color-text-primary)'}}, conf) : null)));
}

export const MODALITY_TONES = [
  ['fact', 'success'], ['asserted', 'neutral'],
  ['opinion', 'yellow'], ['prediction', 'purple'],
];

/** modality 필터 칩 — onToggle 없으면 정적 표기(목업). */
export function modalityChips({active, onToggle} = {}) {
  return h('div', {style: {display: 'flex', flexWrap: 'wrap', gap: 6}},
    MODALITY_TONES.map(([m, v]) => h('span', {
      key: m, onClick: onToggle ? () => onToggle(m) : undefined,
      style: {
        ...(onToggle ? {cursor: 'pointer'} : null),
        ...(active && active !== m ? {opacity: .45} : null)}},
      h(Badge, {variant: v, label: m}))));
}

/** 선택 claim 포커스 박스 — accent 테두리 + modality/valid + 본문 + 메타 id. */
export function claimFocus({badgeLabel, badgeVariant = 'success', validLabel, text, meta}) {
  return h('div', {style: {border: '1px solid var(--color-accent)',
    background: 'rgba(69,224,111,.05)', borderRadius: 'var(--radius-element)',
    padding: 12, marginBottom: 16}},
    h(HStack, {gap: 2},
      h(Badge, {variant: badgeVariant, label: badgeLabel}),
      validLabel ? h(Text, {type: 'supporting'}, validLabel) : null),
    h('div', {style: {marginTop: 8}}, h(Text, {}, text)),
    h('div', {style: {marginTop: 8}}, id(meta)));
}

/** 독립성 보정 설명 블록 (09 §4 — 근거 수로 confidence 부풀리기 금지). */
export function independenceNote(text) {
  return h('div', {style: {marginTop: 16, padding: '10px 12px',
    border: '1px solid var(--color-border)', borderRadius: 'var(--radius-element)'}},
    h(Text, {type: 'label'}, '독립성 보정'),
    h('div', {style: {marginTop: 4}}, h(Text, {type: 'supporting'}, text)));
}

/** provenance trail 스텝 카드 그리드 — steps: [{step, value, fields:[[k,v]…]}]. */
export function provenanceTrail(steps) {
  return h('div', {style: {display: 'grid', gap: 8}},
    steps.map(({step, value, fields}) =>
      h('div', {key: step, style: {border: '1px solid var(--color-border)',
        borderRadius: 'var(--radius-element)', padding: '10px 12px'}},
        h(Text, {type: 'label'}, step),
        h('div', {style: {marginTop: 4}}, id(value)),
        h('div', {style: {display: 'flex', flexWrap: 'wrap', gap: 10, marginTop: 6}},
          (fields || []).map(([k, v]) =>
            h('span', {key: k, style: {fontSize: 10,
              color: 'var(--color-text-secondary)'}},
              `${k} `,
              h('b', {style: {fontFamily: 'var(--font-family-code)',
                color: 'var(--color-text-primary)', fontWeight: 400}}, String(v))))))));
}

/** 원문 세그먼트 렌더 — highlightId 세그먼트를 mark 로 강조 (3-hop 종착). */
export function documentSegments({segments, highlightId, tone = 'support'}) {
  const markStyle = tone === 'contra'
    ? {background: 'rgba(224,82,82,.16)', borderBottom: '2px double var(--color-error)'}
    : {background: 'rgba(69,224,111,.18)', borderBottom: '2px solid var(--color-accent)'};
  return h('div', {style: {fontSize: 12.5, lineHeight: 1.7,
    color: 'var(--color-text-secondary)'}},
    segments.map((s) => h('div', {key: s.segment_id,
      'data-segment': s.segment_id, style: {marginBottom: 10}},
      h('div', {}, id(`[${s.segment_id.split('#')[1] || s.segment_id} · char ${s.char_start}–${s.char_end}]`)),
      s.segment_id === highlightId
        ? h('p', {style: {margin: '4px 0 0'}},
            h('mark', {style: {...markStyle, color: 'var(--color-text-primary)',
              padding: '1px 2px'}}, s.text))
        : h('p', {style: {margin: '4px 0 0'}}, s.text))));
}

/** Round-trip 푸터 스트립 — 3-hop 왕복 안내. */
export function roundTripFooter(statusLabel) {
  return h('div', {style: {display: 'flex', alignItems: 'center', gap: 16,
    flexWrap: 'wrap'}},
    h(Text, {type: 'label'}, 'Round-trip'),
    ...['① Claim 선택', '② Evidence · Trail', '③ 원문 span 하이라이트']
      .flatMap((s, i) => [
        i ? h('span', {key: `a${i}`, style: {color: 'var(--color-text-secondary)'}}, '→') : null,
        h(Text, {key: s, type: 'supporting'}, s)]),
    h('div', {style: {flex: 1}}),
    h(Badge, {variant: 'success',
      label: statusLabel || '결과 → 원문 3-hop 이내 · provenance 완전'}));
}
