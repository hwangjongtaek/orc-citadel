/**
 * Grand Archive · 문서 탐색 (Step 9 — specs TS-5).
 *
 * 3열: Sifter(검색·facet) | Stacks(문서 목록·페이저) | Codex(상세).
 * 문서 축은 전부 서버(/api/archive 파라미터)다 — facet·contains(q)·정렬·페이지를
 * 클라이언트 전량 필터링으로 되돌리지 않는다 (실측 10만+ 문서가 페이지를 멈췄다).
 * URL 부트스트랩 ?doc=(단일 문서 선택)·?src=(source 드릴다운) — aea7965 파리티.
 */

import React from 'react';
import {createRoot} from 'react-dom/client';
import {LayoutContent, LayoutPanel, LayoutFooter} from '@astryxdesign/core/Layout';

import {shell, APP_URLS} from '@ui/shell.mjs';
import {h, Badge, Text, sectionLabel, id, panelHead, grid} from '@ui/components.mjs';
import {facetChips, lineageBadge, docCard, pager, sifterSearch} from '@ui/archive.mjs';
import {Palette, usePaletteHotkey} from '../../lib/palette.jsx';

const urls = APP_URLS;
const jfetch = (p) => fetch(p)
  .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${p} → ${r.status}`))));

const INITIAL = {limit: 50, offset: 0, source_type: '', source: '', language: '',
                 role: '', q: '', sort: 'doc_id', doc_ids: ''};

function useArchive() {
  const [state, setState] = React.useState(() => {
    const up = new URLSearchParams(window.location.search);
    return {...INITIAL,
      doc_ids: up.get('doc') || '', source: up.get('src') || ''};
  });
  const [data, setData] = React.useState(null);
  const [selected, setSelected] = React.useState(
    () => new URLSearchParams(window.location.search).get('doc') || null);
  const [error, setError] = React.useState(null);

  React.useEffect(() => {
    const p = new URLSearchParams();
    Object.entries(state).forEach(([k, v]) => { if (v !== '' && v != null) p.set(k, v); });
    jfetch(`/api/archive?${p}`).then(setData).catch(setError);
  }, [state]);

  // facet·검색은 offset 리셋, 페이지 이동은 유지 — 인라인 판과 동일 계약.
  const set = React.useCallback((patch, keepOffset) =>
    setState((s) => ({...s, ...(keepOffset ? {} : {offset: 0}), ...patch})), []);

  return {state, set, data, selected, setSelected, error};
}

function codexPanel(doc, urlGroups) {
  const stype = (sid) => {
    const t = String(sid || '').split('-', 1)[0];
    return ['official', 'press', 'gov', 'research', 'exchange'].includes(t) ? t : 'source';
  };
  const stat = (v, cap) => h('div', {style: {padding: '8px 10px',
    border: '1px solid var(--color-border)', borderRadius: 'var(--radius-inner)'}},
    h('div', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 16,
      fontWeight: 600, color: 'var(--color-text-primary)'}}, String(v)),
    h('div', {style: {fontSize: 9.5, letterSpacing: '.06em', textTransform: 'uppercase',
      color: 'var(--color-text-secondary)', marginTop: 2}}, cap));
  const group = doc && (urlGroups || []).find((g) => g.url === doc.url);
  return h(React.Fragment, {},
    !doc ? h(Text, {type: 'supporting'},
        '문서 카드를 선택하세요 — 현재 페이지 밖 문서는 검색으로 좁혀 선택.')
      : h(React.Fragment, {},
          h(Text, {}, doc.title || doc.doc_id),
          h('div', {style: {marginTop: 6}}, id(`${doc.doc_id} · content-hash 기반 ID`)),
          h('div', {style: {display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8}},
            h(Badge, {variant: 'neutral', label: `${doc.source_id} · ${stype(doc.source_id)}`}),
            h(Badge, {variant: 'neutral', label: doc.language || 'unknown'}),
            lineageBadge(doc.cluster_role),
            h(Badge, {variant: 'neutral', label: doc.parser_version || 'parser —'})),

          sectionLabel('Parsing · Normalized'),
          grid(2, 8,
            stat(doc.segments, 'segments'),
            stat(doc.char_len, 'char_len'),
            stat(String(doc.publication_time || '—').slice(0, 10), 'publication'),
            stat(String(doc.revision_time || '—').slice(0, 10), 'revision')),

          group ? h(React.Fragment, {},
            sectionLabel('버전 히스토리 · 같은 URL, 여러 doc_id'),
            group.doc_ids.map((d) =>
              h('div', {key: d, style: {padding: '6px 0'}},
                h('a', {href: `/archive?doc=${encodeURIComponent(d)}`,
                  style: {textDecoration: 'none'}},
                  id(d === doc.doc_id ? `${d} ← 현재` : d)))),
            h(Text, {type: 'supporting'},
              `같은 URL 문서 ${group.count}건 — 변경분은 덮어쓰지 않고 새 doc_id 로 `
              + '전부 보존 (raw immutable · ADR-301).')) : null,

          h('div', {style: {marginTop: 14, display: 'flex', gap: 14, flexWrap: 'wrap'}},
            doc.url ? h('a', {href: doc.url, target: '_blank', rel: 'noopener',
              style: {fontFamily: 'var(--font-family-heading)', fontSize: 11.5,
                fontWeight: 600, color: 'var(--color-accent)', textDecoration: 'none'}},
              '원문 열기 ↗') : null)));
}

function App() {
  const s = useArchive();
  const [paletteOpen, setPaletteOpen] = React.useState(false);
  usePaletteHotkey(setPaletteOpen);

  const r = s.data;
  const docs = (r && r.normalized_documents) || [];
  const page = (r && r.normalized_page) || {};
  const facets = (r && r.facets) || {};
  const doc = docs.find((d) => d.doc_id === s.selected) || null;

  // 좌 — Sifter: contains 검색 + 서버 실측 facet 3축 + 정렬
  const sifter = h(LayoutPanel, {width: 300, hasDivider: true, padding: 0,
    label: 'Sifter'},
    panelHead('Sifter · 검색·필터',
      r ? `Docs · ${Number(r.normalized_counts.documents).toLocaleString()}` : '…'),
    h('div', {style: {padding: 16}},
      sifterSearch({defaultValue: s.state.q || s.state.doc_ids,
        placeholder: '본문 contains 검색 (title · url · doc_id)',
        onSubmit: (v) => s.set({q: v, doc_ids: ''})}),
      sectionLabel('source_type · 발행 주체'),
      facetChips({counts: facets.source_type, active: s.state.source_type,
        onToggle: (v) => s.set({source_type: v})}),
      sectionLabel('language · 언어'),
      facetChips({counts: facets.language, active: s.state.language,
        onToggle: (v) => s.set({language: v})}),
      sectionLabel('dedup role · 계보'),
      facetChips({counts: facets.cluster_role, active: s.state.role,
        onToggle: (v) => s.set({role: v})}),
      h('div', {style: {marginTop: 4}},
        h(Text, {type: 'supporting'},
          'role facet 은 curated dup_clusters 전역 실측 — 검색 범위로 좁히지 않음')),
      sectionLabel('정렬'),
      facetChips({
        counts: {doc_id: '결정적', publication: '최신순'},
        active: page.sort || s.state.sort,
        onToggle: (v) => s.set({sort: v || 'doc_id'})}),
      s.state.source ? h(React.Fragment, {},
        sectionLabel('source 드릴다운'),
        facetChips({counts: {[s.state.source]: page.total ?? 0},
          active: s.state.source, onToggle: () => s.set({source: ''})})) : null));

  // 중앙 — Stacks: 서버 페이지 + 문서 카드 (lineage 뱃지)
  const stacks = h(LayoutContent, {padding: 0},
    panelHead('Stacks · 문서 목록',
      page.sort === 'publication' ? '정렬 · publication_time ↓' : '정렬 · doc_id'),
    h('div', {style: {padding: 16}},
      !r ? h(Text, {type: 'supporting'},
          s.error ? String(s.error) : '문서 페이지 불러오는 중…')
        : h(React.Fragment, {},
            h('div', {style: {marginBottom: 12}},
              pager({offset: page.offset || 0, limit: page.limit || 50,
                shown: docs.length, total: page.total || 0,
                zoneTotal: r.normalized_counts.documents,
                onPrev: () => s.set({offset: Math.max(0,
                  (page.offset || 0) - (page.limit || 50))}, true),
                onNext: () => s.set({offset: (page.offset || 0)
                  + (page.limit || 50)}, true)})),
            docs.length ? docs.map((d) =>
              h('div', {key: d.doc_id},
                docCard({docId: d.doc_id, title: d.title || '(제목 없음)',
                  source: d.source_id,
                  meta: `${String(d.publication_time || '—').slice(0, 10)} · `
                    + `${d.language || 'unknown'} · seg ${d.segments}`,
                  role: d.cluster_role, active: d.doc_id === s.selected,
                  onClick: () => s.setSelected(d.doc_id)})))
              : h(Text, {type: 'supporting'}, '조건 일치 문서 없음 — 정직 빈'),
            h('div', {style: {marginTop: 8}},
              h(Text, {type: 'supporting'}, r.page_note)))));

  // 우 — Codex: 문서 상세 + 같은 URL 버전 히스토리 + dedup 총계
  const codex = h(LayoutPanel, {width: 380, hasDivider: true, padding: 0,
    label: 'Codex'},
    panelHead('Codex · 문서 상세',
      doc ? `${doc.doc_id.slice(0, 14)}…` : '문서 선택'),
    h('div', {style: {padding: 16}},
      codexPanel(doc, r && r.url_groups),
      sectionLabel('Dedup Cluster · 존 총계'),
      r ? h('div', {style: {display: 'flex', flexWrap: 'wrap', gap: 6}},
        h(Badge, {variant: 'neutral', label: `dup_clusters ${r.dedup_clusters}`}),
        h(Badge, {variant: 'neutral', label: `raw ${Number(r.raw_doc_count).toLocaleString()}`}),
        h(Badge, {variant: 'neutral',
          label: `segments ${Number(r.normalized_counts.segments).toLocaleString()}`}))
        : h(Text, {type: 'supporting'}, '…'),
      r ? h('div', {style: {marginTop: 8}},
        h(Text, {type: 'supporting'}, r.format_note)) : null));

  // 하단 — segment kinds 실측 스트립
  const kinds = (r && r.segment_kinds) || {};
  const footer = h(LayoutFooter, {hasDivider: true},
    h('div', {style: {display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap'}},
      h(Text, {type: 'label'}, 'Segment kinds'),
      Object.keys(kinds).length
        ? Object.keys(kinds).sort().map((k) =>
            h('span', {key: k, style: {display: 'flex', alignItems: 'baseline', gap: 4}},
              h(Text, {type: 'supporting'}, k),
              id(Number(kinds[k]).toLocaleString())))
        : h(Text, {type: 'supporting'},
            'segment kinds 미측정 — normalized 존 segments 없음 (honest-gap §6.2)')));

  return h(React.Fragment, {},
    shell({
      route: 'grand-archive',
      eyebrow: 'Grand Archive · Documents',
      context: '문서 탐색',
      title: 'Grand Archive · 문서 탐색',
      subtitle: '원문 · 버전 · parsing · 출처 계보(dedup cluster) lineage',
      hero: 'grand-archive-hero.png',
      alerts: 0,
      urls,
      onSearchOpen: () => setPaletteOpen(true),
      slots: {start: sifter, content: stacks, end: codex, footer},
    }),
    h(Palette, {open: paletteOpen, onClose: () => setPaletteOpen(false)}));
}

createRoot(document.getElementById('root')).render(h(App));
