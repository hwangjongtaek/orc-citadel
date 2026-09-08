/**
 * Citadel Gate · 브리핑 대시보드 (Step 5 본구현 — specs TS-3).
 *
 * 목업(design-system/mockups/src/pages/citadel-gate.mjs)과 **같은 ui/ 컴포넌트**를
 * 쓰고, 차이는 데이터 소스뿐이다 — 목업 fixture ↔ /api/gate·/api/table·/api/spire.
 * 데이터가 없는 축(alert 0건)은 정직 빈 상태(§6.2).
 */

import React from 'react';
import {createRoot} from 'react-dom/client';
import {LayoutContent} from '@astryxdesign/core/Layout';

import {shell, APP_URLS, PRIMARY_SPACES, SECONDARY_SPACES} from '@ui/shell.mjs';
import {
  h, Card, Text, sectionLabel, statTile, grid, emptyState,
} from '@ui/components.mjs';
import {
  brandBlock, conclusionCard, changeCard, newCampaignCard, quickEntry,
} from '@ui/gate.mjs';

const urls = APP_URLS;

/** ranking signal(ranking.py 정본 enum) → 배지 톤. 미지의 값은 neutral. */
const SIGNAL_TONE = {
  high_confidence: 'success',
  contradicted: 'error',
  low_evidence: 'warning',
  normal: 'neutral',
};

function useDashboard() {
  const [state, set] = React.useState({loading: true, error: null, data: null});
  React.useEffect(() => {
    let live = true;
    Promise.all(['/api/gate', '/api/table', '/api/spire'].map((p) =>
      fetch(p).then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${p} → ${r.status}`))))))
      .then(([gate, table, spire]) => live && set({loading: false, error: null,
        data: {gate, table, spire}}))
      .catch((error) => live && set({loading: false, error, data: null}));
    return () => { live = false; };
  }, []);
  return state;
}

const n = (v) => Number(v ?? 0).toLocaleString('en-US');

function kpis(gate) {
  const c = gate.curated || {};
  const norm = gate.normalized_counts || {};
  return [
    {value: n(gate.raw_doc_count), label: 'Documents · raw',
     note: `normalized ${n(norm.documents ?? norm.doc_count)} · segments ${n(norm.segments ?? norm.segment_count)}`,
     tone: 'good'},
    {value: n(c.entities), label: 'Entities', note: '결정적 ER — exact match 병합만'},
    {value: n(c.claims), label: 'Claims · promoted',
     note: `assertions ${n(c.assertions)}`, tone: 'good'},
    {value: n(c.dup_clusters), label: 'Dup clusters',
     note: '독립성 보정의 재료 — 근거 N건 → 독립 M건'},
  ];
}

/** subject 결론 카드 데이터 — /api/table.subjects (rank 순 상위 3) + entity 이름. */
function conclusions(table) {
  const names = new Map((table.entities || []).map((e) => [e.entity_id, e.name]));
  return (table.subjects || []).slice(0, 3).map((s) => {
    const preds = Object.entries(s.predicates || {})
      .map(([k, v]) => `${k} ×${v}`).join(' · ');
    return {
      cid: s.subject_id,
      subject: names.get(s.subject_id) || s.subject_id,
      badge: {variant: SIGNAL_TONE[s.signal] || 'neutral', label: s.signal || 'ranked'},
      statement: `${preds || '집계된 predicate 없음'} — evidence coverage ${Math.round((s.coverage || 0) * 100)}%`,
      conf: Number(s.value ?? 0).toFixed(2),
      ev: s.evidence_count ?? 0,
      indep: s.independent_source_count ?? 0,
      urls,
    };
  });
}

function App() {
  const {loading, error, data} = useDashboard();

  let body;
  if (loading) {
    body = h('div', {style: {padding: 24}}, h(Text, {type: 'supporting'}, '불러오는 중 — /api/gate · table · spire'));
  } else if (error) {
    body = h('div', {style: {padding: 24}},
      h(Card, {}, h('div', {style: {padding: 4}},
        h(Text, {}, 'API 오류 — 뷰어가 실행 중인지 확인하세요'),
        h('div', {style: {marginTop: 6}}, h(Text, {type: 'supporting'}, String(error))))));
  } else {
    const {gate, table, spire} = data;
    const alerts = spire.alerts || [];
    body = h(React.Fragment, {},
      brandBlock({urls}),
      grid(4, 16, ...kpis(gate).map((k) => h('div', {key: k.label}, statTile(k)))),

      sectionLabel('Conclusions · 주요 결론 — subject 단위 현재 결론과 근거'),
      grid(3, 16, ...conclusions(table).map((c) => conclusionCard(c))),

      sectionLabel('Recent Changes · 최근 변화 — confidence 델타 · 반증 · 신규 근거'),
      alerts.length
        ? grid(3, 16, ...alerts.slice(0, 3).map((a, i) => changeCard({
            kind: a.trigger_type || 'alert', tone: 'warning',
            subject: a.target || a.investigation_id || '—',
            delta: a.delta || '', note: a.note || '', ref: a.alert_id || `alert-${i}`,
            urls})))
        : h(Card, {}, emptyState({
            art: 'empty-spire.png', isCompact: true, assetBase: '/assets/img/',
            title: '점화된 알림 없음',
            description: spire.note
              || 'alert 영속 저장소가 없어 런 간 유지되지 않는다 (honest-gap §6.2).'})),

      sectionLabel('New Campaign · 새 조사 (비활성)'),
      newCampaignCard({urls}),

      sectionLabel('Citadel · 공간 빠른 진입'),
      quickEntry(PRIMARY_SPACES, urls),
      h('div', {style: {marginTop: 12, marginBottom: 6}},
        h(Text, {type: 'supporting'}, '운영 · 감사')),
      quickEntry(SECONDARY_SPACES, urls));
  }

  const alerts = data?.spire?.alerts?.length ?? 0;
  return shell({
    route: 'citadel-gate',
    eyebrow: 'Citadel Gate · Briefing',
    context: '브리핑 · Home',
    title: 'Citadel Gate · 브리핑',
    subtitle: '지금 무슨 결론이 있고, 그 근거는 무엇인가 — 3클릭 이내',
    hero: 'gate-hero.png',
    alerts,
    urls,
    slots: {content: h(LayoutContent, {padding: 4}, body)},
  });
}

createRoot(document.getElementById('root')).render(h(App));
