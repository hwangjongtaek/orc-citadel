/**
 * War Table · 그래프 탐색 (Step 8 — specs TS-5).
 *
 * subject 중심 서브그래프 + predicate 그룹 집계 + 클릭 단계 확장 (hairball 가드).
 * 소비 API: /api/table(subjects·이름) · /api/graph(subject 서브그래프·독립성) ·
 * /api/claim(Inspector) · /api/chronicle(하단 레일). ?subject= 부트스트랩
 * (⌘K 팔레트·Chronicle 딥링크 진입점). contradicts·Seer 는 파사드 미확장 —
 * 정직 표기(§6.2).
 */

import React from 'react';
import {createRoot} from 'react-dom/client';
import {LayoutContent, LayoutPanel, LayoutFooter} from '@astryxdesign/core/Layout';

import {shell, APP_URLS} from '@ui/shell.mjs';
import {
  h, Badge, Text, sectionLabel, confidence, coverage, relationLegend, id, panelHead,
} from '@ui/components.mjs';
import {claimFocus} from '@ui/witnesses.mjs';
import {warGraph, CLAIMS_PER_PAGE} from '@ui/graph.mjs';
import {Palette, usePaletteHotkey} from '../../lib/palette.jsx';

const urls = APP_URLS;
const jfetch = (p) => fetch(p)
  .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${p} → ${r.status}`))));

const SIGNAL_TONE = {high_confidence: 'success', contradicted: 'error',
                     low_evidence: 'warning', normal: 'neutral'};

function useWarTable() {
  const [table, setTable] = React.useState(null);
  const [chron, setChron] = React.useState(null);
  const [subjectId, setSubjectId] = React.useState(null);
  const [graph, setGraph] = React.useState(null);
  const [claim, setClaim] = React.useState(null);
  const [error, setError] = React.useState(null);

  React.useEffect(() => {
    const boot = new URLSearchParams(window.location.search).get('subject');
    Promise.all([jfetch('/api/table'), jfetch('/api/chronicle')])
      .then(([t, c]) => {
        setTable(t); setChron(c);
        const ids = t.subjects.map((s) => s.subject_id);
        setSubjectId(boot && ids.includes(boot) ? boot : ids[0]);
      })
      .catch(setError);
  }, []);

  React.useEffect(() => {
    if (!subjectId) return;
    setGraph(null); setClaim(null);
    jfetch(`/api/graph?subject=${encodeURIComponent(subjectId)}`)
      .then(setGraph).catch(setError);
  }, [subjectId]);

  const selectClaim = React.useCallback((claimId) => {
    jfetch(`/api/claim?claim=${encodeURIComponent(claimId)}`)
      .then(setClaim).catch(setError);
  }, []);

  return {table, chron, subjectId, setSubjectId, graph, claim, selectClaim, error};
}

/** 서브그래프 claims → predicate 그룹 (count 내림차순 → 이름순, 결정적). */
function toGroups(subgraph) {
  const by = new Map();
  (subgraph.claims || []).forEach((c) => {
    if (!by.has(c.label)) by.set(c.label, []);
    by.get(c.label).push(c);
  });
  return [...by.entries()]
    .map(([predicate, claims]) => ({predicate, count: claims.length, claims}))
    .sort((a, b) => b.count - a.count || a.predicate.localeCompare(b.predicate));
}

function App() {
  const s = useWarTable();
  const [expanded, setExpanded] = React.useState(null);
  const [page, setPage] = React.useState(0);
  const [paletteOpen, setPaletteOpen] = React.useState(false);
  usePaletteHotkey(setPaletteOpen);

  const names = React.useMemo(() => new Map(
    ((s.table && s.table.entities) || []).map((e) => [e.entity_id, e.name])), [s.table]);
  const nameOf = (sid) => names.get(sid) || sid;

  const groups = React.useMemo(
    () => (s.graph ? toGroups(s.graph.subgraph) : []), [s.graph]);

  // subject 바뀌면 첫 그룹 자동 펼침 (결정적).
  React.useEffect(() => {
    setExpanded(groups[0] ? groups[0].predicate : null);
    setPage(0);
  }, [groups]);

  const subjMeta = ((s.table && s.table.subjects) || [])
    .find((x) => x.subject_id === s.subjectId);

  // 좌 — Campaign Map: subject 목록 (signal·coverage·ev/독립)
  const campaignMap = h(LayoutPanel, {width: 288, hasDivider: true, padding: 0,
    label: 'Campaign Map'},
    panelHead('Campaign Map', `Subjects · ${((s.table && s.table.subjects) || []).length}`),
    h('div', {style: {padding: 16}},
      ((s.table && s.table.subjects) || []).map((sub) =>
        h('div', {key: sub.subject_id,
          onClick: () => s.setSubjectId(sub.subject_id),
          style: {cursor: 'pointer', padding: 12, marginBottom: 10,
            border: `1px solid ${sub.subject_id === s.subjectId
              ? 'var(--color-accent)' : 'var(--color-border)'}`,
            background: sub.subject_id === s.subjectId
              ? 'rgba(69,224,111,.05)' : 'transparent',
            borderRadius: 'var(--radius-element)'}},
          h('div', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 13,
            fontWeight: 600, color: 'var(--color-text-primary)'}},
            nameOf(sub.subject_id)),
          h('div', {style: {margin: '6px 0'}},
            h(Badge, {variant: SIGNAL_TONE[sub.signal] || 'neutral', label: sub.signal})),
          coverage(Math.round((sub.coverage || 0) * 100),
            (sub.coverage || 0) < .5 ? 'warn' : null),
          h('div', {style: {marginTop: 6}},
            id(`ev ${sub.evidence_count} · 독립 ${sub.independent_source_count}`))))));

  // 중앙 — 그래프 캔버스
  const g = s.graph;
  const canvas = h(LayoutContent, {padding: 0},
    panelHead('War Table · Temporal Evidence Graph',
      g ? `${nameOf(s.subjectId)} · claims ${g.subgraph.claims.length}`
          + (g.subgraph.truncated ? ' (truncated)' : '') : '…'),
    h('div', {style: {padding: 16}},
      !g ? h(Text, {type: 'supporting'}, s.error ? String(s.error) : '서브그래프 불러오는 중…')
        : h(React.Fragment, {},
            warGraph({
              subjectLabel: nameOf(s.subjectId),
              groups, expanded, page,
              selectedClaimId: s.claim && s.claim.claim_id,
              truncated: g.subgraph.truncated,
              onSelectGroup: (p) => {
                setExpanded((cur) => (cur === p ? null : p));
                setPage(0);
              },
              onSelectClaim: s.selectClaim,
              onMore: () => setPage((p) => p + 1),
            }),
            h('div', {style: {marginTop: 12, display: 'flex', alignItems: 'center',
              gap: 16, flexWrap: 'wrap'}},
              relationLegend(),
              h(Text, {type: 'supporting'},
                '이 서브그래프의 엣지는 구조(ABOUT) — supports/contradicts 는 '
                + 'evidence 레벨이며 Witnesses 에서 왕복 검사')))));

  // 우 — Evidence Inspector
  const c = s.claim;
  const conf = c && c.confidence;
  const indep = g && g.independence_summary;
  const inspector = h(LayoutPanel, {width: 372, hasDivider: true, padding: 0,
    label: 'Evidence Inspector'},
    panelHead('Evidence Inspector', 'Hall of Witnesses'),
    h('div', {style: {padding: 16}},
      subjMeta ? h(React.Fragment, {},
        claimFocus({
          badgeLabel: `Subject · ${subjMeta.signal}`,
          badgeVariant: SIGNAL_TONE[subjMeta.signal] || 'neutral',
          text: nameOf(s.subjectId),
          meta: `${s.subjectId} · predicates ${Object.keys(subjMeta.predicates || {}).length}`}),
        confidence(Number(subjMeta.value ?? 0).toFixed(2),
          String(subjMeta.evidence_count), String(subjMeta.independent_source_count)),
        indep ? h('div', {style: {marginTop: 10, padding: '8px 10px',
          border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius-element)'}},
          h(Text, {type: 'supporting'}, indep.note
            || `독립 ${indep.independent_source_count} / 근거 ${indep.evidence_count}`)) : null)
        : h(Text, {type: 'supporting'}, '…'),

      sectionLabel('Claim'),
      !c ? h(Text, {type: 'supporting'}, '그래프에서 claim 노드를 선택하세요')
        : h(React.Fragment, {},
            claimFocus({
              badgeLabel: `Claim · ${c.modality || '—'}`,
              text: [c.predicate, c.object_literal || c.surface_fragment]
                .filter(Boolean).join(' · '),
              meta: `${c.claim_id} · subj ${nameOf(c.subject_id)}`}),
            conf ? confidence(Number(conf.value ?? 0).toFixed(2),
              String(conf.evidence_count ?? 0),
              String(conf.independent_source_count ?? 0)) : null,
            h('div', {style: {marginTop: 12, display: 'flex', gap: 14, flexWrap: 'wrap'}},
              h('a', {href: `/witnesses?claim=${encodeURIComponent(c.claim_id)}`,
                style: {fontFamily: 'var(--font-family-heading)', fontSize: 11.5,
                  fontWeight: 600, color: 'var(--color-accent)',
                  textDecoration: 'none'}}, '근거 열람 · Witnesses →'))),

      sectionLabel('Contradicts · Seer'),
      h(Text, {type: 'supporting'},
        (s.table && s.table.notes && s.table.notes.contradicts) || '—')));

  // 하단 — Chronicle 레일 (subject 의 최근 assertion 3)
  const rail = (((s.chron && s.chron.assertions) || [])
    .filter((a) => a.subject_id === s.subjectId)).slice(-3).reverse();
  const footer = h(LayoutFooter, {hasDivider: true},
    h('div', {style: {display: 'flex', alignItems: 'center', gap: 18, flexWrap: 'wrap'}},
      h(Text, {type: 'label'}, 'Chronicle'),
      rail.length
        ? rail.map((a) => h('span', {key: a.assertion_id,
            style: {display: 'flex', alignItems: 'baseline', gap: 6}},
            id(`${String(a.tx_from || '').slice(0, 10) || 'tx —'}`),
            h(Text, {type: 'supporting'}, `${a.predicate} · ${a.assertion_id.slice(0, 14)}…`)))
        : h(Text, {type: 'supporting'}, '이 subject 의 assertion 이벤트 없음'),
      h('div', {style: {flex: 1}}),
      h('a', {href: `/chronicle?subject=${encodeURIComponent(s.subjectId || '')}`,
        style: {fontFamily: 'var(--font-family-heading)', fontSize: 11.5, fontWeight: 600,
          color: 'var(--color-accent)', textDecoration: 'none'}},
        'Chronicle Vault에서 시간축 보기 →')));

  return h(React.Fragment, {},
    shell({
      route: 'war-table',
      eyebrow: 'War Table · Graph',
      context: '그래프 탐색',
      title: 'War Table · 그래프 탐색',
      subtitle: '엔티티 · 주장 · 증거 · 시간 관계의 Temporal Knowledge Graph',
      hero: 'war-table-hero.png',
      alerts: 0,
      urls,
      onSearchOpen: () => setPaletteOpen(true),
      slots: {start: campaignMap, content: canvas, end: inspector, footer},
    }),
    h(Palette, {open: paletteOpen, onClose: () => setPaletteOpen(false)}));
}

createRoot(document.getElementById('root')).render(h(App));
