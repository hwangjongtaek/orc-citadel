/**
 * Council Chamber · 조사 실행 (Step 11 — specs TS-5).
 *
 * 단일 3열: Council(Subjects+8 Agent) | 보고서·루프·발언 | Stopping·Cost·Audit —
 * 구 인라인 판의 중복 패널(요약 그리드 + ext 그리드 2단 적층) 결함을 소멸시킨다.
 * 소비 API: /api/table(subjects·이름) · /api/council(기존 결론) ·
 * /api/investigations(durable job 생성·상태·완료 report).
 * graph·curated evidence는 read-only, investigation metadata만 PostgreSQL에 영속한다.
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
const jfetch = (p, options) => fetch(p, options)
  .then((r) => (r.ok ? r.json() : r.json().then((body) =>
    Promise.reject(new Error(body.error?.message || `${p} → ${r.status}`)))));
const num = (n) => Number(n || 0).toLocaleString();

const SIGNAL_TONE = {high_confidence: 'success', contradicted: 'error',
                     low_evidence: 'warning', normal: 'neutral'};

function useCouncil() {
  const [table, setTable] = React.useState(null);
  const [subjectId, setSubjectId] = React.useState(null);
  const [report, setReport] = React.useState(null);
  const [trace, setTrace] = React.useState(null);
  const [investigation, setInvestigation] = React.useState(null);
  const [job, setJob] = React.useState(null);
  const [error, setError] = React.useState(null);
  const tracing = job && ['queued', 'running'].includes(job.status);

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
    setReport(null);
    jfetch(`/api/council?subject=${encodeURIComponent(subjectId)}`)
      .then(setReport).catch(setError);
  }, [subjectId]);

  const poll = React.useCallback((investigationId, jobId) => {
    Promise.all([
      jfetch(`/api/jobs/${encodeURIComponent(jobId)}`),
      jfetch(`/api/investigations/${encodeURIComponent(investigationId)}/status`),
    ]).then(([nextJob, nextInvestigation]) => {
      setJob(nextJob);
      setInvestigation(nextInvestigation);
      if (nextJob.status === 'succeeded') {
        return jfetch(`/api/investigations/${encodeURIComponent(investigationId)}/report`)
          .then((result) => {
            const completed = {...result.report, audit_trace: result.audit_trace};
            setTrace(completed);
            const hit = (completed.resolved || []).find((x) => x.known);
            if (hit) setSubjectId(hit.subject_id);
          });
      }
      if (!['failed', 'cancelled'].includes(nextJob.status)) {
        window.setTimeout(() => poll(investigationId, jobId), 1000);
      }
      return null;
    }).catch(setError);
  }, []);

  const startInvestigation = React.useCallback((body) => {
    setTrace(null);
    setError(null);
    jfetch('/api/investigations', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID()},
      body: JSON.stringify(body),
    }).then((created) => {
      setJob(created.job);
      setInvestigation({investigation_id: created.investigation_id, status: 'queued'});
      poll(created.investigation_id, created.job.job_id);
    }).catch(setError);
  }, [poll]);

  const selectSubject = React.useCallback((sid) => {
    setTrace(null); setInvestigation(null); setJob(null); setSubjectId(sid);
  }, []);

  const runTrace = React.useCallback((useLlm) => {
    if (subjectId) startInvestigation({
      subject_id: subjectId, mode: useLlm ? 'llm' : 'deterministic',
    });
  }, [subjectId, startInvestigation]);

  const runQuestion = React.useCallback((question, useLlm) => {
    question = (question || '').trim();
    if (question) startInvestigation({
      question, mode: useLlm ? 'llm' : 'deterministic',
    });
  }, [startInvestigation]);

  const cancel = React.useCallback(() => {
    if (!investigation) return;
    jfetch(`/api/investigations/${encodeURIComponent(investigation.investigation_id)}:cancel`, {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}',
    }).then((cancelled) => {
      setInvestigation(cancelled);
      setJob(cancelled.job);
    }).catch(setError);
  }, [investigation]);

  return {table, subjectId, selectSubject, report, trace, investigation, job, tracing,
          runTrace, runQuestion, cancel, error};
}

function App() {
  const s = useCouncil();
  const [paletteOpen, setPaletteOpen] = React.useState(false);
  const [question, setQuestion] = React.useState('');
  const [useLlm, setUseLlm] = React.useState(false);
  usePaletteHotkey(setPaletteOpen);

  const names = React.useMemo(() => new Map(
    ((s.table && s.table.entities) || []).map((e) => [e.entity_id, e.name])), [s.table]);
  const nameOf = (sid) => names.get(sid) || sid;

  const r = s.report;
  const t = s.trace;
  const roleState = (role) => !t ? 'idle'
    : (role.wire && role.wire(t) ? 'executed' : 'not-run');

  // 조사 지시 — POST 생성 후 worker 상태를 polling하고 완료 report만 렌더한다.
  const directive = h(React.Fragment, {},
    panelHead('조사 지시 · Directive', '질문 → entity 해소 → trace'),
    h('div', {style: {padding: '10px 12px'}},
      h('input', {value: question, disabled: s.tracing,
        onChange: (e) => setQuestion(e.target.value),
        onKeyDown: (e) => { if (e.key === 'Enter') s.runQuestion(question, useLlm); },
        placeholder: '예: NVIDIA 신제품 발표를 조사',
        style: {width: '100%', boxSizing: 'border-box', padding: '8px 10px',
          marginBottom: 8, background: 'var(--color-background-muted)',
          border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius-inner)', fontSize: 12,
          color: 'var(--color-text-primary)', outline: 'none'}}),
      h('button', {onClick: () => s.runQuestion(question, useLlm),
        disabled: s.tracing || !question.trim(),
        style: {width: '100%', padding: '8px 10px', cursor: 'pointer',
          border: '1px solid var(--color-accent)',
          background: 'rgba(69,224,111,.08)',
          borderRadius: 'var(--radius-element)',
          fontFamily: 'var(--font-family-heading)', fontSize: 12,
          fontWeight: 600, color: 'var(--color-accent)',
          opacity: s.tracing || !question.trim() ? .5 : 1}},
        s.tracing ? `조사 ${s.job.status}…` : '조사 지시 · existing evidence'),
      // W2 옵트인 — 문장 종합만 LLM. 결론 봉투·근거·audit 는 결정적 그대로.
      h('label', {style: {display: 'flex', alignItems: 'center', gap: 6,
        marginTop: 8, cursor: 'pointer', fontSize: 11.5,
        color: 'var(--color-text-secondary)'}},
        h('input', {type: 'checkbox', checked: useLlm, disabled: s.tracing,
          onChange: (e) => setUseLlm(e.target.checked),
          style: {accentColor: 'var(--color-accent)'}}),
        'LLM 종합 — 문장만 LLM 생성 (비결정적 · 토큰 실측 표기)'),
      s.job ? h('div', {style: {marginTop: 10}},
        h('div', {style: {display: 'flex', alignItems: 'center', gap: 6,
          flexWrap: 'wrap'}},
          h(Badge, {variant: s.job.status === 'succeeded' ? 'success'
            : s.job.status === 'failed' ? 'error'
            : s.job.status === 'cancelled' ? 'warning' : 'neutral',
          label: `job · ${s.job.status}`}),
          s.investigation ? id(s.investigation.investigation_id) : null),
        s.investigation && s.investigation.current_step
          ? h('div', {style: {marginTop: 6}},
              h(Text, {type: 'supporting'},
                `현재 단계 · ${s.investigation.current_step.stage}`
                + ` · ${s.investigation.current_step.step_id}`))
          : null,
        s.job.error_json
          ? h('div', {style: {marginTop: 6}},
              h(Text, {type: 'supporting'},
                `실행 실패 · ${s.job.error_json.message || s.job.error_json.code}`))
          : null,
        s.tracing && s.job.cancel_requested
          ? h('div', {style: {marginTop: 8}},
              h(Text, {type: 'supporting'},
                '취소 요청됨 · 현재 stage 경계에서 cancelled로 전이'))
          : s.tracing ? h('button', {onClick: s.cancel,
              style: {marginTop: 8, padding: '6px 8px', cursor: 'pointer',
                border: '1px solid var(--color-border)', background: 'transparent',
                borderRadius: 'var(--radius-element)',
                color: 'var(--color-text-secondary)'}},
              '조사 취소') : null) : null,
      t && t.question ? h('div', {style: {marginTop: 8}},
        h('div', {style: {display: 'flex', flexWrap: 'wrap', gap: 6}},
          (t.resolved || []).map((rv, i) =>
            h(Badge, {key: i, variant: rv.known ? 'success' : 'warning',
              label: `${rv.surface || rv.subject_id} · ${rv.known ? 'known' : 'gap'}`}))),
        !(t.resolved || []).some((rv) => rv.known)
          ? h('div', {style: {marginTop: 6}},
              h(Text, {type: 'supporting'},
                '지식에 없는 대상 — gap 정직 표기, 조사 산출 없음 (§6.2)'))
          : null) : null));

  // 좌 — 조사 지시 + Subjects 선택 + Warchief's Council 8 Agent
  const council = h(LayoutPanel, {width: 320, hasDivider: true, padding: 0,
    label: "Warchief's Council"},
    directive,
    panelHead('Subjects', `랭킹 · ${((s.table && s.table.subjects) || []).length}`),
    h('div', {style: {padding: '10px 12px'}},
      ((s.table && s.table.subjects) || []).map((sub) =>
        h('div', {key: sub.subject_id, onClick: () => s.selectSubject(sub.subject_id),
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
        '모델·토큰은 완료 report에 실측값만 표기 (honest-gap §6.2)')));

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
            s.job
              ? `영속 job ${s.job.status} — worker 완료 후 report를 표시`
              : '질문을 제출하면 PostgreSQL job과 진행 상태를 표시')
          : h(React.Fragment, {},
              h('div', {style: {display: 'flex', flexWrap: 'wrap', gap: 6}},
                traceSteps.map(([k, v], i) =>
                  h(Badge, {key: k, variant: 'neutral', label: `${i + 1} ${k} · ${v}`}))),
              h('div', {style: {marginTop: 6}},
                id(`durable investigation · ${s.investigation?.investigation_id || 'completed'}`)))),

      sectionLabel('발언 · Statements (evidence-first)'),
      !t ? h(Text, {type: 'supporting'},
          '완료된 조사 report의 Synthesizer 문장만 표시 — 무출처 문장은 Audit 이 차단')
        : (t.statements || []).length
          ? t.statements.map((st, i) =>
              h('div', {key: i},
                turnCard({agent: t.mode === 'llm'
                    ? `LLM Synthesis · ${(t.llm && t.llm.model) || ''}`
                    : 'Synthesis Agent', model: st.modality || null,
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
    panelHead('Stopping · Cost · Audit', 'existing evidence · durable job'),
    h('div', {style: {padding: 16}},
      h('button', {onClick: () => s.runTrace(useLlm),
        disabled: s.tracing || !s.subjectId,
        style: {width: '100%', padding: '9px 12px', cursor: 'pointer',
          border: '1px solid var(--color-accent)', background: 'rgba(69,224,111,.08)',
          borderRadius: 'var(--radius-element)',
          fontFamily: 'var(--font-family-heading)', fontSize: 12, fontWeight: 600,
          color: 'var(--color-accent)', opacity: s.tracing ? .5 : 1}},
        s.tracing ? `조사 ${s.job.status}…` : '조사 생성 · existing evidence'),

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
      // LLM 종합(mode=llm) 실행 시에만 토큰 실측 — usd 는 단가 미확정이라 '—'
      // 유지 (§6.2). 결정적 경로는 LLM 미사용이라 전부 '—'.
      grid(2, 8,
        ...(() => {
          const lu = (t && t.llm && t.llm.used && t.llm.usage) || null;
          return [['—', 'llm usd'], [lu ? '1' : '—', 'llm calls'],
                  [lu ? num(lu.input_tokens) : '—', 'tokens in'],
                  [lu ? num(lu.output_tokens) : '—', 'tokens out']];
        })().map(([v, c]) =>
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
          t && t.llm && t.llm.used
            ? `LLM 종합 실측 — ${t.llm.model || t.llm.provider} · `
              + `폐기 ${t.llm.discarded} · 차단 ${t.llm.blocked} · `
              + '단가 미확정이라 usd 미표기 (§6.2)'
            : t && t.llm && !t.llm.used
              ? `LLM 종합 미수행 — ${t.llm.error}`
              : (r && r.execution && r.execution.note)
                || '결정적 조사는 LLM 비용 없이 worker trace·report를 PostgreSQL에 영속')),

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
