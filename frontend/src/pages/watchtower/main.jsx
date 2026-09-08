/**
 * Watchtower · 수집 관제 (Step 12 — specs TS-5·TS-6).
 *
 * 소비 API: /api/watchtower (sources 실측 · freshness · intake · SLO 판정표 ·
 * run_metrics 표시 필드). 실측이 없는 축은 가공하지 않고 not-measured 정직
 * 렌더 (§6.2) — stage runner metric·DLQ 는 wire 에 없어 목업 fixture 로만
 * 구조를 증명한다. 운영 drill-down 은 Grafana(14b) 몫 — 여기는 요약 + 딥링크.
 */

import React from 'react';
import {createRoot} from 'react-dom/client';
import {LayoutContent} from '@astryxdesign/core/Layout';

import {shell, APP_URLS} from '@ui/shell.mjs';
import {
  h, Card, Badge, Text, sectionLabel, statTile, id, grid,
  Table, TableHeader, TableHeaderCell, TableBody, TableRow, TableCell,
} from '@ui/components.mjs';
import {stageCard, failureCard, sloCard, grafanaCard} from '@ui/watchtower.mjs';
import {Palette, usePaletteHotkey} from '../../lib/palette.jsx';

const urls = APP_URLS;
const jfetch = (p) => fetch(p)
  .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${p} → ${r.status}`))));

const num = (n) => Number(n || 0).toLocaleString();
// 신선도 분 값 → 읽을 수 있는 단위 (48h 넘으면 일 단위) — 값 가공 아님, 표기만.
const age = (min) => {
  const m = Number(min || 0);
  if (m >= 2880) return `${num(Math.round(m / 1440))}d`;
  if (m >= 120) return `${num(Math.round(m / 60))}h`;
  return `${num(Math.round(m))}m`;
};

function kpis(r) {
  const srcs = r.sources || [];
  const active = srcs.filter((s) => s.doc_count > 0).length;
  const f = r.freshness || {};
  const rm = r.run_metrics || {};
  const lastRun = (rm.runs || [])[0];
  const slo = (r.slo && r.slo.nightly_slos) || [];
  const measured = slo.filter((s) => s.measured).length;
  return [
    {label: 'Sources', value: String(srcs.length), unit: `· active ${active}`,
     note: 'raw 존 실측', tone: 'good'},
    f.measured
      ? {label: 'Freshness', value: age(f.median_age_min), unit: 'median',
         note: `max ${age(f.max_age_min)} · n=${num(f.n)} · publication_time 기준`,
         tone: 'warn'}
      : {label: 'Freshness', value: '—', unit: '',
         note: f.note || 'not-measured (§6.2)'},
    {label: 'Raw Documents', value: num(srcs.reduce((a, s) => a + s.doc_count, 0)),
     unit: 'docs', note: 'raw 존 총계'},
    lastRun
      ? {label: '최근 런 신규', value: num(lastRun.metrics.total_new ?? '—'),
         unit: 'docs', note: `${lastRun.job_id} · ${String(lastRun.recorded_at).slice(0, 16)}`,
         tone: 'good'}
      : {label: '최근 런 신규', value: '—', unit: '',
         note: 'run 메트릭 미영속 — postgres 미가동 (§6.2)'},
    {label: 'SLO 판정', value: `${measured}/${slo.length || 5}`, unit: 'measured',
     note: 'nightly SLO — 미측정은 not-measured', tone: measured ? 'good' : undefined},
  ];
}

function App() {
  const [r, setR] = React.useState(null);
  const [error, setError] = React.useState(null);
  const [paletteOpen, setPaletteOpen] = React.useState(false);
  usePaletteHotkey(setPaletteOpen);

  React.useEffect(() => { jfetch('/api/watchtower').then(setR).catch(setError); }, []);

  const rm = (r && r.run_metrics) || {available: false, runs: [], source_tables: []};
  const body = h(LayoutContent, {padding: 4},
    !r ? h(Text, {type: 'supporting'}, error ? String(error) : '수집 관제 불러오는 중…')
      : h(React.Fragment, {},
          h('div', {style: {display: 'grid',
            gridTemplateColumns: 'repeat(5, minmax(0,1fr))', gap: 16}},
            kpis(r).map((k) => h('div', {key: k.label}, statTile(k)))),

          sectionLabel('Pipeline · Stage Throughput — stage runner metric 미영속'),
          grid(3, 16,
            ...[['S1', 'Fetch'], ['S3', 'Parse / Normalize'], ['S4', 'Dedup']]
              .map(([sid, name]) => h('div', {key: sid},
                stageCard({sid, name, rate: '—', backlog: '—', fail: '—'})))),
          h('div', {style: {marginTop: 6}},
            h(Text, {type: 'supporting'},
              'stage 단위 처리량은 wire 미영속 — not-measured 정직 렌더 (§6.2). '
              + '런 단위 실측은 아래 Run Metrics · Grafana.')),

          sectionLabel('Run Metrics — postgres pipeline_run_metrics (nightly flush)'),
          rm.available && rm.runs.length
            ? h(Card, {}, h(Table, {},
                h(TableHeader, {}, h(TableRow, {},
                  ...['Run', 'Job', '기록 시각', 'Metrics']
                    .map((c) => h(TableHeaderCell, {key: c}, c)))),
                h(TableBody, {}, rm.runs.map((run) =>
                  h(TableRow, {key: run.run_id},
                    h(TableCell, {}, id(run.run_id)),
                    h(TableCell, {}, h(Badge, {variant: 'neutral', label: run.job_id})),
                    h(TableCell, {}, id(String(run.recorded_at).slice(0, 19))),
                    h(TableCell, {}, h('div', {style: {display: 'flex', gap: 6,
                      flexWrap: 'wrap'}},
                      Object.entries(run.metrics).map(([m, v]) =>
                        h(Badge, {key: m, variant: 'neutral',
                          label: `${m} ${num(v)}`})))))))))
            : h(Text, {type: 'supporting'},
                rm.note || 'run 메트릭 없음 — nightly 런이 돌면 여기 쌓인다 (14a flush)'),
          grafanaCard({url: null,
            note: '런 단위 drill-down(정확도·지연·correlation 분해)은 Grafana 대시보드가 '
              + '담당 — 소스: postgres pipeline_run_metrics · pipeline_slo_observations '
              + '(nightly flush)'}),

          sectionLabel('Sources · 수집 상태 — raw 존 실측 + fetch.json governance'),
          h(Card, {}, h(Table, {},
            h(TableHeader, {}, h(TableRow, {},
              ...['Source', 'Type', '문서 수', '마지막 수집', 'HTTP', 'robots']
                .map((c) => h(TableHeaderCell, {key: c}, c)))),
            h(TableBody, {}, (r.sources || []).map((s) =>
              h(TableRow, {key: s.source_id},
                h(TableCell, {}, h(Text, {}, s.source_id)),
                h(TableCell, {}, h(Badge, {variant: 'neutral', label: s.source_type})),
                h(TableCell, {}, id(num(s.doc_count))),
                h(TableCell, {}, id(s.last_fetch
                  ? String(s.last_fetch).slice(0, 19) : '—')),
                h(TableCell, {}, id(s.governance && s.governance.http_status != null
                  ? String(s.governance.http_status) : '—')),
                h(TableCell, {}, s.governance && s.governance.robots_allowed != null
                  ? h(Badge, {variant: s.governance.robots_allowed
                      ? 'success' : 'error',
                      label: String(s.governance.robots_allowed)})
                  : id('—'))))))),

          h('div', {style: {display: 'grid', gridTemplateColumns: '1.9fr 1fr',
            gap: 24, alignItems: 'start', marginTop: 8}},
            h('div', {},
              sectionLabel('Failure · Dead-letter'),
              failureCard({reason: 'Dead-letter 큐', state: '범위 밖',
                tone: 'warning', ids: 'DLQ 미구현 — 재시도·보관 구조는 목업 fixture 로 증명',
                note: 'raw 는 immutable 보존 — 실패 시에도 원본 유실 없음. DLQ 는 '
                  + '프로토타입 범위 밖 명시 (§6.2 — 가짜 실패 사례 렌더 금지).'})),
            h('div', {},
              sectionLabel('SLO · nightly 판정표'),
              ((r.slo && r.slo.nightly_slos) || []).map((s) =>
                h('div', {key: s.slo_id},
                  sloCard({name: s.slo_id, sid: s.measured ? 'measured' : '',
                    current: s.classified, target: '',
                    window: s.reason, verdict: s.classified}))),
              r.slo ? h(Text, {type: 'supporting'},
                `error budget — violations ${r.slo.error_budget.violations} · `
                + `measured ${r.slo.error_budget.measured_count} · ratio `
                + `${r.slo.error_budget.violation_ratio == null
                    ? 'not-measured (분모 제외)' : r.slo.error_budget.violation_ratio}`)
                : null))));

  return h(React.Fragment, {},
    shell({
      route: 'watchtower',
      eyebrow: 'Watchtower · Ingestion',
      context: '수집 관제',
      title: 'Watchtower · 수집 관제',
      subtitle: 'source 상태 · freshness · ingestion backlog · failure',
      hero: 'watchtower-hero.png',
      alerts: 0,
      urls,
      onSearchOpen: () => setPaletteOpen(true),
      slots: {content: body},
    }),
    h(Palette, {open: paletteOpen, onClose: () => setPaletteOpen(false)}));
}

createRoot(document.getElementById('root')).render(h(App));
