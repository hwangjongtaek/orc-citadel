/**
 * 통합 검색 팔레트(⌘K) — 프레젠테이션 (specs TS-3).
 *
 * 데이터 무지: `groups = [{label, items: [{key, primary, secondary, href}]}]` 를
 * 받아 그리기만 한다. fetch·디바운스·키보드는 frontend 컨테이너 몫
 * (`frontend/src/lib/palette.jsx`). 목업은 오버레이 컴포넌트라 싣지 않는다.
 * 검색은 ILIKE contains — BM25 아님을 정직하게 표기한다.
 */

import {h, Text} from './components.mjs';

const S = {
  backdrop: {position: 'fixed', inset: 0, zIndex: 60,
    background: 'rgba(7,17,28,.72)', backdropFilter: 'blur(2px)',
    display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
    paddingTop: '12vh'},
  panel: {width: 'min(640px, calc(100vw - 48px))', maxHeight: '64vh',
    display: 'flex', flexDirection: 'column', overflow: 'hidden',
    background: 'var(--color-background-card)',
    border: '1px solid var(--color-border)', borderRadius: 'var(--radius-container)'},
  inputRow: {display: 'flex', alignItems: 'center', gap: 10, padding: '12px 16px',
    borderBottom: '1px solid var(--color-border)'},
  input: {flex: 1, background: 'none', border: 0, outline: 'none',
    color: 'var(--color-text-primary)', fontFamily: 'var(--font-family-body)',
    fontSize: 15},
  kbd: {fontFamily: 'var(--font-family-code)', fontSize: 10, flex: 'none',
    padding: '2px 6px', border: '1px solid var(--color-border)',
    borderRadius: 'var(--radius-inner)', color: 'var(--color-text-secondary)'},
  list: {overflowY: 'auto', padding: '6px 0'},
  groupLabel: {padding: '10px 16px 4px', fontFamily: 'var(--font-family-heading)',
    fontSize: 10, fontWeight: 600, letterSpacing: '.1em', textTransform: 'uppercase',
    color: 'var(--color-text-secondary)'},
  row: {display: 'flex', alignItems: 'baseline', gap: 10, padding: '8px 16px',
    textDecoration: 'none'},
  rowOn: {background: 'rgba(69,224,111,.08)'},
  primary: {fontFamily: 'var(--font-family-body)', fontSize: 13.5,
    color: 'var(--color-text-primary)', whiteSpace: 'nowrap', overflow: 'hidden',
    textOverflow: 'ellipsis'},
  secondary: {fontFamily: 'var(--font-family-code)', fontSize: 11,
    color: 'var(--color-text-secondary)', whiteSpace: 'nowrap', marginLeft: 'auto',
    flex: 'none'},
  footer: {display: 'flex', alignItems: 'center', gap: 14, padding: '9px 16px',
    borderTop: '1px solid var(--color-border)'},
};

const searchIcon = () =>
  h('svg', {width: 15, height: 15, viewBox: '0 0 24 24', fill: 'none',
    'aria-hidden': 'true', style: {color: 'var(--color-text-secondary)', flex: 'none'}},
    h('circle', {cx: 11, cy: 11, r: 7, stroke: 'currentColor', strokeWidth: 2}),
    h('path', {d: 'M20 20 L16.5 16.5', stroke: 'currentColor', strokeWidth: 2,
      strokeLinecap: 'round'}));

/**
 * @param query        현재 질의 문자열
 * @param groups       [{label, items:[{key, primary, secondary, href}]}]
 * @param activeKey    키보드 선택된 item.key
 * @param status       보조 상태줄 (검색 중 · 결과 없음 · 정직 라벨)
 * @param inputRef     input DOM ref (컨테이너가 autofocus 제어)
 * @param onQueryChange(value) / onBackdrop() 콜백
 */
export function searchPalette({query, groups, activeKey, status, inputRef,
                               onQueryChange, onBackdrop}) {
  return h('div', {style: S.backdrop, role: 'dialog', 'aria-modal': 'true',
    'aria-label': '통합 검색',
    onMouseDown: (e) => { if (e.target === e.currentTarget && onBackdrop) onBackdrop(); }},
    h('div', {style: S.panel},
      h('div', {style: S.inputRow},
        searchIcon(),
        h('input', {style: S.input, value: query, ref: inputRef,
          placeholder: 'subject · claim · document 통합 검색',
          onChange: (e) => onQueryChange && onQueryChange(e.target.value)}),
        h('span', {style: S.kbd}, 'esc')),
      h('div', {style: S.list},
        groups.length
          ? groups.map((g) => h('div', {key: g.label},
              h('div', {style: S.groupLabel}, g.label),
              g.items.map((it) => h('a', {
                key: it.key, href: it.href, 'data-palette-key': it.key,
                style: it.key === activeKey ? {...S.row, ...S.rowOn} : S.row},
                h('span', {style: S.primary}, it.primary),
                h('span', {style: S.secondary}, it.secondary)))))
          : h('div', {style: {padding: '18px 16px'}},
              h(Text, {type: 'supporting'}, status || '검색어를 입력하세요'))),
      h('div', {style: S.footer},
        h('span', {style: S.kbd}, '↑↓'), h(Text, {type: 'supporting'}, '이동'),
        h('span', {style: S.kbd}, '⏎'), h(Text, {type: 'supporting'}, '열기'),
        h('div', {style: {flex: 1}}),
        h(Text, {type: 'supporting'}, 'text contains (ILIKE) — BM25 아님'))));
}
