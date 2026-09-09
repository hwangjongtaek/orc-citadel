/**
 * Chronicle Vault · 시간 탐색 (Step 13 — specs TS-5, 마지막 공간 이관).
 *
 * Bitemporal Plane 최상단(듀얼 슬라이더 — bounds 실측) + "두 축" 3카드 +
 * AS-OF 대비 패널. 소비 API: /api/chronicle (assertions·bounds·events·replay ·
 * ?valid_at/tx_at as-of 재조회). valid 축은 현 실데이터에서 전부 null —
 * 가짜 축 대신 정직 빈 라벨 (§6.2). preset 3종은 실재 assertion 재료에서
 * 파생 — 재료 없으면 비활성. ?claim= 부트스트랩 (aux_ext 파리티).
 */

import React from 'react';
import {createRoot} from 'react-dom/client';
import {LayoutContent, LayoutPanel, LayoutFooter} from '@astryxdesign/core/Layout';

import {shell, APP_URLS} from '@ui/shell.mjs';
import {
  h, Card, Badge, Text, sectionLabel, id, panelHead, grid, svgBlock,
} from '@ui/components.mjs';
import {axisSlider, presetChips, eventsRail, assertionCard, ts, fmt}
  from '@ui/chronicle.mjs';
import planeSvg from '@ui/svg/bitemporal-plane.svg?raw';
import {Palette, usePaletteHotkey} from '../../lib/palette.jsx';

const urls = APP_URLS;
const jfetch = (p) => fetch(p)
  .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${p} → ${r.status}`))));

/** preset 질문 3종 — 실재 assertion 재료(subject·predicate)에서 파생. */
function presetsOf(a, nameOf) {
  const subj = a && a.subject_id ? nameOf(a.subject_id) : '';
  const pred = (a && a.predicate) || '';
  return [
    {label: subj ? `무엇이 ${subj}(으)로 확인됐나?` : '과거 시점에는 무엇을 알고 있었나?',
     enabled: !!subj, valid: true, tx: false},
    {label: pred ? `${subj}는 무엇을 ${pred}했나?` : '무엇을 믿었나?',
     enabled: !!pred, valid: true, tx: true},
    {label: subj ? `${subj}에 대해 무엇이 정정됐나?` : '정정 자료가 과거 결론을 어떻게 바꿨나?',
     enabled: !!subj, valid: false, tx: true},
  ];
}

function useChronicle() {
  const [chron, setChron] = React.useState(null);
  const [names, setNames] = React.useState(() => new Map());
  const [asof, setAsof] = React.useState(null);   // {label, rows}
  const [selected, setSelected] = React.useState(null);
  const [error, setError] = React.useState(null);

  React.useEffect(() => {
    jfetch('/api/chronicle').then((r) => {
      setChron(r);
      const claim = new URLSearchParams(window.location.search).get('claim');
      if (claim) {
        const hit = (r.assertions || []).find(
          (a) => String(a.claim_id || '') === claim);
        setSelected(hit || {missing: claim});
      }
    }).catch(setError);
    // subject 이름 매핑 (표기용) — 실패해도 id 로 정직 표기 (치명 아님).
    jfetch('/api/table').then((t) => setNames(new Map(
      (t.entities || []).map((e) => [e.entity_id, e.name])))).catch(() => {});
  }, []);

  const runAsof = React.useCallback((label, params) => {
    jfetch(`/api/chronicle${params.toString() ? `?${params}` : ''}`)
      .then((r) => setAsof({label, rows: r.assertions || []}))
      .catch(setError);
  }, []);

  return {chron, names, asof, selected, setSelected, runAsof, error};
}

function App() {
  const s = useChronicle();
  const [sl, setSl] = React.useState({va: 0, vb: 100, ta: 0, tb: 100});
  const [paletteOpen, setPaletteOpen] = React.useState(false);
  usePaletteHotkey(setPaletteOpen);

  const r = s.chron;
  const bounds = (r && r.bounds) || {};
  const all = (r && r.assertions) || [];
  const events = (r && r.events) || [];
  const vLo = ts(bounds.valid_min), vHi = ts(bounds.valid_max);
  const tLo = ts(bounds.tx_min), tHi = ts(bounds.tx_max);

  const nameOf = (sid) => s.names.get(sid) || sid;
  const latest = React.useMemo(() => all.slice()
    .sort((x, y) => String(y.tx_from || '').localeCompare(String(x.tx_from || '')))[0],
    [all]);
  const presets = presetsOf(latest, nameOf);

  // 슬라이더 하한 시점 → War Table as-of 딥링크 (실측 축만 파라미터 생성).
  const deepLink = React.useMemo(() => {
    const p = new URLSearchParams();
    if (vLo != null && vHi != null) {
      p.set('as_of_valid', new Date(vLo + (vHi - vLo) * (sl.va / 100)).toISOString());
    }
    if (tLo != null && tHi != null) {
      p.set('as_of_tx', new Date(tLo + (tHi - tLo) * (sl.ta / 100)).toISOString());
    }
    return p.toString();
  }, [sl, vLo, vHi, tLo, tHi]);

  const selectAssertion = (a) => {
    // supersedes 체인 역추적 (순환 가드).
    const chain = [];
    const seen = new Set();
    let cur = a;
    let guard = 0;
    while (cur && cur.supersedes_id && guard++ < 20 && !seen.has(cur.supersedes_id)) {
      seen.add(cur.supersedes_id);
      const prev = all.find((x) => x.assertion_id === cur.supersedes_id);
      if (!prev) break;
      chain.push(prev.assertion_id);
      cur = prev;
    }
    s.setSelected({...a, _chain: chain});
  };

  const onPreset = (i) => {
    const q = presets[i];
    setSl((cur) => ({...cur, va: q.valid ? 0 : 100, ta: q.tx ? 0 : 100}));
    const p = new URLSearchParams();
    if (q.valid && bounds.valid_min) p.set('valid_at', String(bounds.valid_min));
    if (q.tx && bounds.tx_max) p.set('tx_at', String(bounds.tx_max));
    s.runAsof(q.label, p);
  };

  // 중앙 — Bitemporal Plane 최상단 + 두 축 3카드 + preset + as-of 결과
  const axes = [
    ['Valid time', '현실에서 사실이 유효했던 시점 (T_v)',
     vLo != null ? `실측 ${fmt(vLo).slice(0, 10)} ~ ${fmt(vHi).slice(0, 10)}`
       : 'valid_from/valid_to 실측 없음 — 전부 null (§6.2)'],
    ['Transaction time', '시스템이 그 사실을 믿은 시점 (T_t)',
     tLo != null ? `실측 ${fmt(tLo).slice(0, 10)} ~ ${fmt(tHi).slice(0, 10)} · `
       + `assertion ${all.length}` : 'tx 실측 없음'],
    ['Supersession', '정정이 과거 결론을 바꾼 기록',
     `supersedes 체인 ${((r && r.supersedes_chain) || []).length}건 실측`],
  ];
  const plane = h(LayoutContent, {padding: 0},
    panelHead('Bitemporal Plane · 시간 평면',
      r ? `valid × transaction · assertions ${all.length}` : '…'),
    h('div', {style: {padding: '12px 16px', borderBottom: '1px solid var(--color-border)'}},
      axisSlider({label: 'Valid 시간축', color: 'var(--color-accent)',
        lo: vLo, hi: vHi, a: sl.va, b: sl.vb,
        onChange: (a, b) => setSl((c) => ({...c, va: a, vb: b})),
        emptyNote: 'valid 시간축 실측 없음 — assertions 의 valid_from/valid_to 가 '
          + '전부 null (honest-gap §6.2, L3 데이터 트랙 과제)'}),
      axisSlider({label: 'TX 시간축 · AS-OF', color: 'var(--astryx-theme-citadel-signal-amber)',
        lo: tLo, hi: tHi, a: sl.ta, b: sl.tb,
        onChange: (a, b) => setSl((c) => ({...c, ta: a, tb: b}))}),
      h('div', {style: {marginTop: 10, display: 'flex', alignItems: 'center', gap: 12,
        flexWrap: 'wrap'}},
        h('a', {href: `/table${deepLink ? `?${deepLink}` : ''}`,
          style: {fontFamily: 'var(--font-family-heading)', fontSize: 11.5,
            fontWeight: 600, color: 'var(--color-accent)', textDecoration: 'none'}},
          'War Table @ 슬라이더 시점 →'),
        id(deepLink || 'bounds 미측정 축 제외 — 딥링크는 실측 축만'))),
    h('div', {style: {padding: 16}},
      grid(3, 12, ...axes.map(([name, q, a]) =>
        h(Card, {key: name}, h('div', {style: {padding: 4}},
          h(Text, {type: 'label'}, name),
          h('div', {style: {marginTop: 6}}, h(Text, {type: 'supporting'}, q)),
          h('div', {style: {marginTop: 6}}, id(a)))))),
      h('div', {style: {marginTop: 12}},
        svgBlock(planeSvg, {ratio: '880 / 400', maxHeight: 420})),

      sectionLabel('Preset 질문 · 실재 assertion 파생 (재료 없으면 비활성)'),
      presetChips({presets, onSelect: onPreset}),

      sectionLabel('AS-OF 결과 · 시점 유효 assertion'),
      !s.asof
        ? h(Text, {type: 'supporting'},
            'preset 을 누르면 그 시점 as-of 질의를 실행한다 — GET /api/chronicle'
            + '?valid_at·tx_at')
        : h(React.Fragment, {},
            h(Text, {type: 'supporting'},
              `${s.asof.label} — as-of 유효 assertion ${s.asof.rows.length}건 `
              + '(상위 10 표시)'),
            h('div', {style: {marginTop: 8}},
              s.asof.rows.slice(0, 10).map((a) =>
                h('div', {key: a.assertion_id, onClick: () => selectAssertion(a),
                  style: {cursor: 'pointer', display: 'flex', alignItems: 'baseline',
                    gap: 10, padding: '6px 8px', flexWrap: 'wrap',
                    borderBottom: '1px solid var(--color-border)'}},
                  id(a.assertion_id),
                  h(Text, {type: 'supporting'}, a.predicate || '—'),
                  id(`valid ${String(a.valid_from || '—').slice(0, 10)} · `
                     + `tx ${String(a.tx_from || '—').slice(0, 10)}`)))))));

  // 우 — AS-OF Snapshot 대비 패널 + assertion 상세
  const current = all.filter((a) => !a.tx_to);
  const closed = all.filter((a) => a.tx_to);
  const replay = (r && r.graph_replay) || {};
  const sel = s.selected;
  const snapshot = h(LayoutPanel, {width: 388, hasDivider: true, padding: 0,
    label: 'AS-OF Snapshot'},
    panelHead('AS-OF Snapshot · 상태 대비', 'assertions_as_of'),
    h('div', {style: {padding: 16}},
      grid(2, 8,
        h('div', {style: {padding: '10px 12px', border: '1px solid var(--color-accent)',
          background: 'rgba(69,224,111,.05)', borderRadius: 'var(--radius-element)'}},
          h(Text, {type: 'label'}, '현재 믿음 · tx_to=∞'),
          h('div', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 22,
            fontWeight: 600, color: 'var(--color-accent)', marginTop: 4}},
            String(current.length))),
        h('div', {style: {padding: '10px 12px', border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius-element)'}},
          h(Text, {type: 'label'}, '대체됨 · tx_to 닫힘'),
          h('div', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 22,
            fontWeight: 600, color: 'var(--color-text-primary)', marginTop: 4}},
            String(closed.length)))),
      h('div', {style: {marginTop: 8}},
        h(Text, {type: 'supporting'},
          current.slice(0, 6).map((a) => a.predicate).join(' · ') || '—')),

      sectionLabel('Assertion 상세'),
      !sel ? h(Text, {type: 'supporting'},
          'AS-OF 결과 행이나 하단 이벤트 핀을 선택하세요')
        : sel.missing
          ? h(Text, {type: 'supporting'},
              `딥링크 미일치 — ?claim= ${sel.missing} 와 일치하는 assertion 실측 없음 `
              + '(honest-gap §6.2)')
          : assertionCard({a: sel, chain: sel._chain || [],
              events: events.filter((e) => e.assertion_id === sel.assertion_id)}),

      sectionLabel('Graph Replay · postgres SoT (ADR-304)'),
      h('div', {style: {display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap'}},
        h(Badge, {variant: replay.available ? 'success' : 'warning',
          label: replay.available ? `정상 · mutations ${replay.mutation_count}`
            : 'unavailable'})),
      replay.note ? h('div', {style: {marginTop: 6}},
        h(Text, {type: 'supporting'}, replay.note)) : null));

  // 하단 — 이벤트 레일
  const footer = h(LayoutFooter, {hasDivider: true},
    h('div', {style: {display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap',
      width: '100%'}},
      h(Text, {type: 'label'}, 'Chronicle'),
      eventsRail({events, onSelect: (e) => {
        const a = all.find((x) => x.assertion_id === e.assertion_id);
        if (a) selectAssertion(a);
      }})));

  return h(React.Fragment, {},
    shell({
      route: 'chronicle-vault',
      eyebrow: 'Chronicle Vault · History',
      context: '시간 탐색',
      title: 'Chronicle Vault · 시간 탐색',
      subtitle: 'valid time × transaction time · bitemporal history',
      hero: 'chronicle-vault-hero.png',
      alerts: 0,
      urls,
      onSearchOpen: () => setPaletteOpen(true),
      slots: {content: s.error && !r ? h(LayoutContent, {},
        h(Text, {type: 'supporting'}, String(s.error))) : plane,
        end: snapshot, footer},
    }),
    h(Palette, {open: paletteOpen, onClose: () => setPaletteOpen(false)}));
}

createRoot(document.getElementById('root')).render(h(App));
