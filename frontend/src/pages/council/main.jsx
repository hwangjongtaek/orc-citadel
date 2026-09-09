/**
 * Council Chamber · 조사 실행 (Step 11 — specs TS-5).
 *
 * 단일 3열: Council(Subjects+8 Agent) | 보고서·루프·발언 | Stopping·Cost·Audit —
 * 구 인라인 판의 중복 패널(요약 그리드 + ext 그리드 2단 적층) 결함을 소멸시킨다.
 * 소비 API: /api/table(subjects·이름) · /api/council(보고서) ·
 * /api/investigate(on-request trace — 버튼 클릭 시 1회, 로드 시 자동 fetch 없음).
 * live 실행·비용·모델 ID 는 wire 미영속 — Cost 는 '—' 정직 표기 (§6.2).
 */

import React from 'react';
import {createRoot} from 'react-dom/client';
import {LayoutContent, LayoutPanel} from '@astryxdesign/core/Layout';

import {shell, APP_URLS} from '@ui/shell.mjs';
import {
  h, Badge, Text, sectionLabel, confidence, coverage, id, panelHead, grid,
} from '@ui/components.mjs';
import {claimFocus} from '@ui/witnesses.mjs';
import {agentCard, loopStrip, turnCard, COUNCIL_ROLES} from '@ui/council.mjs';
import {Palette, usePaletteHotkey} from '../../lib/palette.jsx';

const urls = APP_URLS;
const jfetch = (p) => fetch(p)
  .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${p} → ${r.status}`))));

const SIGNAL_TONE = {high_confidence: 'success', contradicted: 'error',
                     low_evidence: 'warning', normal: 'neutral'};

function useCouncil() {
  const [table, setTable] = React.useState(null);
  const [subjectId, setSubjectId] = React.useState(null);
  const [report, setReport] = React.useState(null);
  const [trace, setTrace] = React.useState(null);
  const [tracing, setTracing] = React.useState(false);
  const [error, setError] = React.useState(null);

  React.useEffect(() => {
    const boot = new URLSearchParams(window.location.search).get('subject');
    jfetch('/api/table').then((t) => {
      setTable(t);
      const ids = t.subjects.map((s) => s.subject_id);
      setSubjectId(boot && ids.includes(boot) ? boot : ids[0]);
    }).catch(setError);
  }, []);

  React.useEffect(() => {
    if (!subjectId) return;
    setReport(null); setTrace(null);
    jfetch(`/api/council?subject=${encodeURIComponent(subjectId)}`)
      .then(setReport).catch(setError);
  }, [subjectId]);

  // trace 는 on-request 계산이다 — 로드 시 자동 fetch 없음, 버튼 클릭 시 1회.
  const runTrace = React.useCallback(() => {
    if (!subjectId) return;
    setTracing(true);
    jfetch(`/api/investigate?subject=${encodeURIComponent(subjectId)}`)
      .then(setTrace).catch(setError).finally(() => setTracing(false));
  }, [subjectId]);

  return {table, subjectId, setSubjectId, report, trace, tracing, runTrace, error};
}

function App() {
  const s = useCouncil();
  const [paletteOpen, setPaletteOpen] = React.useState(false);
  usePaletteHotkey(setPaletteOpen);

  const names = React.useMemo(() => new Map(
    ((s.table && s.table.entities) || []).map((e) => [e.entity_id, e.name])), [s.table]);
  const nameOf = (sid) => names.get(sid) || sid;

  const r = s.report;
  const t = s.trace;
  const roleState = (role) => !t ? 'idle'
    : (role.wire && role.wire(t) ? 'executed' : 'not-run');

  // 좌 — Subjects 선택 + Warchief's Council 8 Agent
  const council = h(LayoutPanel, {width: 320, hasDivider: true, padding: 0,
    label: "Warchief's Council"},
    panelHead('Subjects', `랭킹 · ${((s.table && s.table.subjects) || []).length}`),
    h('div', {style: {padding: '10px 12px'}},
      ((s.table && s.table.subjects) || []).map((sub) =>
        h('div', {key: sub.subject_id, onClick: () => s.setSubjectId(sub.subject_id),
          style: {cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8,
            justifyContent: 'space-between', padding: '7px 10px', marginBottom: 4,
            border: `1px solid ${sub.subject_id === s.subjectId
              ? 'var(--color-accent)' : 'transparent'}`,
            background: sub.subject_id === s.subjectId
              ? 'rgba(69,224,111,.05)' : 'transparent',
            borderRadius: 'var(--radius-inner)'}},
          h('span', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 12,
            fontWeight: 600, color: 'var(--color-text-primary)', minWidth: 0}},
            nameOf(sub.subject_id)),
          h(Badge, {variant: SIGNAL_TONE[sub.signal] || 'neutral', label: sub.signal})))),
    panelHead("Warchief's Council",
      t ? 'trace 판정 — wire 필드 존재' : '8 Agents · trace 대기'),
    h('div', {style: {padding: 16}},
      COUNCIL_ROLES.map((role) =>
        h('div', {key: role.name},
          agentCard({name: role.name, worldName: role.worldName,
            state: role.wire === null ? 'not-run' : roleState(role),
            desc: role.desc, art: role.art, assetBase: '/assets/img/'}))),
      h(Text, {type: 'supporting'},
        '모델 ID·라우팅 판정은 wire 미영속 — 표기하지 않음 (honest-gap §6.2)')));

  // 중앙 — Investigation Report + 조사 루프 + 발언(evidence-first statements)
  const conf = r && r.confidence;
  const dims = (conf && conf.dimensions) || {};
  const traceSteps = t ? [
    ['coverage', typeof t.coverage === 'number' ? `${Math.round(t.coverage * 100)}%` : '—'],
    ['gaps', (t.gaps || []).length],
    ['retrieved', (t.retrieved || []).length],
    ['counter_evidence', (t.counter_evidence || []).length],
    ['statements', (t.statements || []).length],
    ['audit', t.audit_trace
      ? `${t.audit_trace.linked || 0}/${t.audit_trace.verifiable || 0}` : '—'],
  ] : [];
  const report = h(LayoutContent, {padding: 0},
    panelHead('Investigation Report',
      r ? `${nameOf(s.subjectId)} · get_investigation_report` : '…'),
    h('div', {style: {padding: 16}},
      !r ? h(Text, {type: 'supporting'}, s.error ? String(s.error) : '보고서 불러오는 중…')
        : r.error ? h(Text, {type: 'supporting'}, `보고서 없음 — ${s.subjectId}`)
        : h(React.Fragment, {},
            claimFocus({
              badgeLabel: `Subject · ${r.signal}`,
              badgeVariant: SIGNAL_TONE[r.signal] || 'neutral',
              text: nameOf(r.subject_id),
              meta: `${r.id || r.subject_id} · 결론 봉투`}),
            confidence(Number((conf && conf.value) || 0).toFixed(2),
              String((conf && conf.evidence_count) || 0),
              String((conf && conf.independent_source_count) || 0)),
            conf && conf.basis ? h('div', {style: {marginTop: 8}},
              h(Text, {type: 'supporting'}, conf.basis)) : null,

            sectionLabel('by_predicate'),
            Object.entries(r.by_predicate || {}).map(([p, v]) =>
              h('div', {key: p, style: {display: 'flex', alignItems: 'baseline',
                justifyContent: 'space-between', gap: 8, padding: '6px 0',
                borderBottom: '1px solid var(--color-border)'}},
                h('span', {style: {fontFamily: 'var(--font-family-heading)',
                  fontSize: 12, fontWeight: 600,
                  color: 'var(--color-text-primary)'}}, p),
                id(`count ${v.count} · 독립 ${v.independent_source_count} · `
                   + `max ${Number(v.max_value).toFixed(2)}`))),

            (r.open_questions || []).length ? h(React.Fragment, {},
              sectionLabel('open_questions · 미결'),
              r.open_questions.map((q, i) =>
                h('div', {key: i, style: {padding: '6px 0'}},
                  h(Text, {type: 'supporting'},
                    `미결 · ${q.predicate || ''} — ${q.reason || ''}`)))) : null),

      sectionLabel('조사 루프 · Investigation Loop (07 §4)'),
      loopStrip({doneCount: t ? 11 : 0}),
      h('div', {style: {marginTop: 10}},
        !t ? h(Text, {type: 'supporting'},
            '[조사 trace] 실행 시 결과 trace 를 표시 — on-request, non-persistent '
            + '(실행 로그 아님)')
          : h(React.Fragment, {},
              h('div', {style: {display: 'flex', flexWrap: 'wrap', gap: 6}},
                traceSteps.map(([k, v], i) =>
                  h(Badge, {key: k, variant: 'neutral', label: `${i + 1} ${k} · ${v}`}))),
              h('div', {style: {marginTop: 6}},
                id(`computed: ${t.computed || 'on-request, non-persistent'}`)))),

      sectionLabel('발언 · Statements (evidence-first)'),
      !t ? h(Text, {type: 'supporting'},
          'Synthesizer 산출 문장은 trace 실행 시에만 — 무출처 문장은 Audit 이 차단')
        : (t.statements || []).length
          ? t.statements.map((st, i) =>
              h('div', {key: i},
                turnCard({agent: 'Synthesis Agent', model: st.modality || null,
                  body: st.text || '',
                  evidence: st.claim_ref
                    ? `claim_ref ${st.claim_ref}` : 'claim_ref 없음 (prediction/opinion)'}),
                st.claim_ref ? h('div', {style: {margin: '-4px 0 10px'}},
                  h('a', {href: `/witnesses?claim=${encodeURIComponent(st.claim_ref)}`,
                    style: {fontFamily: 'var(--font-family-heading)', fontSize: 11.5,
                      fontWeight: 600, color: 'var(--color-accent)',
                      textDecoration: 'none'}}, '증거 검사 · Witnesses →')) : null))
          : h(Text, {type: 'supporting'}, '문장 없음 — 결론 미산출 (정직 빈)')));

  // 우 — Stopping · Cost · Audit
  const at = (t && t.audit_trace) || null;
  const verifiable = at ? (at.verifiable || 0) : null;
  const linked = at ? (at.linked || 0) : null;
  const stopping = h(LayoutPanel, {width: 372, hasDivider: true, padding: 0,
    label: 'Stopping · Cost · Audit'},
    panelHead('Stopping · Cost · Audit', 'read-only'),
    h('div', {style: {padding: 16}},
      h('button', {onClick: s.runTrace, disabled: s.tracing || !s.subjectId,
        style: {width: '100%', padding: '9px 12px', cursor: 'pointer',
          border: '1px solid var(--color-accent)', background: 'rgba(69,224,111,.08)',
          borderRadius: 'var(--radius-element)',
          fontFamily: 'var(--font-family-heading)', fontSize: 12, fontWeight: 600,
          color: 'var(--color-accent)', opacity: s.tracing ? .5 : 1}},
        s.tracing ? '계산 중…' : '조사 trace (on-request · read-only)'),

      sectionLabel('종료 조건 · Stopping'),
      h('div', {style: {margin: '0 0 12px', padding: '8px 10px',
        background: 'var(--color-background-muted)',
        borderRadius: 'var(--radius-inner)',
        fontFamily: 'var(--font-family-code)', fontSize: 11.5,
        color: 'var(--astryx-theme-citadel-parchment)'}},
        'STOP = ( A ∧ B ∧ C ) ∨ D · D=budget hard stop'),
      [['A', 'evidence coverage', dims.coverage],
       ['B', 'support', dims.support],
       ['C', 'contradiction', dims.contradiction]].map(([k, name, v]) =>
        h('div', {key: k, style: {marginBottom: 10}},
          h('div', {style: {display: 'flex', alignItems: 'baseline',
            justifyContent: 'space-between', gap: 8}},
            h('span', {style: {fontSize: 11.5, color: 'var(--color-text-primary)'}},
              h('b', {style: {fontFamily: 'var(--font-family-code)',
                color: 'var(--color-accent)'}}, k), ` ${name}`),
            id(v == null ? '—' : Number(v).toFixed(2))),
          h('div', {style: {marginTop: 4}},
            coverage(Math.round((v || 0) * 100), (v || 0) < .7 ? 'warn' : null)))),
      t ? h(Text, {type: 'supporting'},
          `iterations ${t.iterations ?? '—'} · terminated_by = ${t.terminated_by || '—'} `
          + '— evaluate_stop 임계 상수는 wire 미노출')
        : h(Text, {type: 'supporting'},
            'A·B·C 는 보고서 dimensions — trace 실행 시 terminated_by 를 병기'),

      sectionLabel('비용 · Cost'),
      grid(2, 8,
        ...[['—', 'llm usd'], ['—', 'tool calls'], ['—', 'tokens in'],
            ['—', 'tokens out']].map(([v, c]) =>
          h('div', {key: c, style: {padding: '8px 10px',
            border: '1px solid var(--color-border)',
            borderRadius: 'var(--radius-inner)'}},
            h('div', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 16,
              fontWeight: 600, color: 'var(--color-text-secondary)'}}, v),
            h('div', {style: {fontSize: 9.5, letterSpacing: '.06em',
              textTransform: 'uppercase', color: 'var(--color-text-secondary)',
              marginTop: 2}}, c)))),
      h('div', {style: {marginTop: 8}},
        h(Text, {type: 'supporting'},
          (r && r.execution && r.execution.note)
          || '조사 실행(쓰기)은 범위 밖 — 비용·턴 로그 미영속 (honest-gap §6.2)')),

      sectionLabel('Audit Agent · 역추적 감사'),
      !at ? h(Text, {type: 'supporting'},
          'audit_trace 는 trace 실행 시에만 — 검증가능 문장의 claim+span 역추적률')
        : h(React.Fragment, {},
            verifiable === 0
              ? h(Badge, {variant: 'warning',
                  label: '검증가능 문장 없음 — PASS 표시 불가 (분모 0)'})
              : h(Badge, {variant: linked === verifiable ? 'success' : 'error',
                  label: linked === verifiable
                    ? '전 문장 claim+span 역추적'
                    : `역추적 미완 ${verifiable - linked}건`}),
            h('div', {style: {marginTop: 8}},
              confidence(
                typeof at.linkage_ratio === 'number'
                  ? at.linkage_ratio.toFixed(2) : '—',
                String(verifiable), String(linked))),
            h('div', {style: {marginTop: 4}},
              id('linkage · verifiable · linked')))));

  return h(React.Fragment, {},
    shell({
      route: 'council-chamber',
      eyebrow: 'Council Chamber · Investigation',
      context: '조사 실행',
      title: 'Council Chamber · 조사 실행',
      subtitle: 'Agent 계획 · 토론 · 반증 · 종합 · 조사 루프 · 비용',
      hero: 'council-chamber-hero.png',
      alerts: 0,
      urls,
      onSearchOpen: () => setPaletteOpen(true),
      slots: {start: council, content: report, end: stopping},
    }),
    h(Palette, {open: paletteOpen, onClose: () => setPaletteOpen(false)}));
}

createRoot(document.getElementById('root')).render(h(App));
