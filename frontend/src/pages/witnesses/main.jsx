/**
 * Hall of Witnesses · 증거 검사 (Step 7 — specs TS-5).
 *
 * 페이지의 존재 이유 = 결과 → 원문 3-hop 왕복:
 *   ① claim 선택 → ② evidence · provenance trail → ③ 원문 세그먼트 하이라이트.
 * 소비 API: /api/table(subjects·이름) · /api/subject_claims · /api/claim ·
 * /api/evidence · /api/provenance · /api/document. URL 부트스트랩 ?claim= 유지.
 * contradicts 0건은 정직 빈 자리(§6.2 — 파사드 미확장).
 */

import React from 'react';
import {createRoot} from 'react-dom/client';
import {LayoutContent, LayoutPanel, LayoutFooter} from '@astryxdesign/core/Layout';

import {shell, APP_URLS} from '@ui/shell.mjs';
import {
  h, Badge, HStack, Text, sectionLabel, confidence, evidenceCard, id, panelHead,
} from '@ui/components.mjs';
import {
  claimRow, modalityChips, claimFocus, independenceNote, provenanceTrail,
  roundTripFooter, documentSegments,
} from '@ui/witnesses.mjs';
import {Palette, usePaletteHotkey} from '../../lib/palette.jsx';

const urls = APP_URLS;

const jfetch = (p) => fetch(p)
  .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${p} → ${r.status}`))));

const claimLabel = (c) => [c.predicate, c.object_literal || c.surface_fragment]
  .filter(Boolean).join(' · ') || c.claim_id;

function useWitnesses() {
  const [table, setTable] = React.useState(null);
  const [subjectId, setSubjectId] = React.useState(null);
  const [claims, setClaims] = React.useState([]);
  const [claimId, setClaimId] = React.useState(null);
  const [detail, setDetail] = React.useState(null);
  const [evidence, setEvidence] = React.useState(null);
  const [prov, setProv] = React.useState(null);
  const [doc, setDoc] = React.useState(null);
  const [error, setError] = React.useState(null);

  // 부트스트랩 — ?claim= 이 있으면 그 claim 의 subject 로 진입.
  React.useEffect(() => {
    const boot = new URLSearchParams(window.location.search).get('claim');
    Promise.all([jfetch('/api/table'),
                 boot ? jfetch(`/api/claim?claim=${encodeURIComponent(boot)}`) : null])
      .then(([t, c]) => {
        setTable(t);
        const subj = (c && c.subject_id) || (t.subjects[0] && t.subjects[0].subject_id);
        setSubjectId(subj);
        if (c && c.claim_id) setClaimId(c.claim_id);
      })
      .catch(setError);
  }, []);

  // subject → claims 목록 (첫 claim 자동 선택).
  React.useEffect(() => {
    if (!subjectId) return;
    jfetch(`/api/subject_claims?subject=${encodeURIComponent(subjectId)}`)
      .then((r) => {
        setClaims(r.items || []);
        setClaimId((cur) => cur && (r.items || []).some((i) => i.claim_id === cur)
          ? cur : (r.items[0] && r.items[0].claim_id));
      })
      .catch(setError);
  }, [subjectId]);

  // claim → 상세 + evidence, 첫 evidence 의 provenance 자동 전개.
  React.useEffect(() => {
    if (!claimId) return;
    setDetail(null); setEvidence(null); setProv(null); setDoc(null);
    Promise.all([
      jfetch(`/api/claim?claim=${encodeURIComponent(claimId)}`),
      jfetch(`/api/evidence?claim=${encodeURIComponent(claimId)}`),
    ]).then(([d, ev]) => {
      setDetail(d);
      setEvidence(ev.items || []);
      const first = (ev.items || [])[0];
      if (first) selectEvidence(first.evidence_id);
    }).catch(setError);
  }, [claimId]);

  // evidence → provenance trail → 원문 (3-hop 종착).
  const selectEvidence = React.useCallback((evidenceId) => {
    jfetch(`/api/provenance?evidence=${encodeURIComponent(evidenceId)}`)
      .then((p) => {
        setProv(p);
        const ext = (p.trail || []).find((t) => t.step === 'extraction_record');
        const segDoc = ext && ext.segment_id ? ext.segment_id.split('#')[0] : null;
        if (segDoc) {
          jfetch(`/api/document?doc=${encodeURIComponent(segDoc)}`)
            .then((docr) => {
              // extraction 의 세그먼트 ID 체계(#p1)와 normalized 세그먼트(#p0.s0)가
              // 어긋나는 문서가 실측 존재 — 정확 일치 → 접두(p1 → p1.s*) 순으로
              // 폴백하고, 못 찾으면 정직하게 미매칭을 표기한다 (§6.2).
              const segs = docr.segments || [];
              const want = ext.segment_id;
              const hl = segs.some((x) => x.segment_id === want) ? want
                : (segs.find((x) => x.segment_id.startsWith(`${want}.`)) || {}).segment_id
                  || null;
              setDoc({...docr, highlight: hl, wanted: want});
            })
            .catch(setError);
        }
      })
      .catch(setError);
  }, []);

  return {table, subjectId, setSubjectId, claims, claimId, setClaimId,
          detail, evidence, prov, doc, selectEvidence, error};
}

function trailSteps(prov) {
  const byStep = Object.fromEntries((prov.trail || []).map((t) => [t.step, t]));
  const claim = byStep.claim || {};
  const ext = byStep.extraction_record || {};
  const docStep = byStep.document || {};
  return [
    {step: '① Graph Element',
     value: `${prov.evidence_id.slice(0, 18)}… · ${(prov.relation || '').toUpperCase()}`,
     fields: [['type', 'Evidence'], ['rel', prov.relation],
              ['strength', Number(prov.strength ?? 0).toFixed(2)]]},
    {step: '② Extraction Record', value: ext.extraction_id || '—',
     fields: [['segment', ext.segment_id || '—'],
              ['char', `${ext.char_start ?? '—'}–${ext.char_end ?? '—'}`],
              ['ontology', claim.ontology_version || '—']]},
    {step: '③ Normalized Document', value: ext.segment_id
       ? ext.segment_id.split('#')[0] : (docStep.doc_id || '—'),
     fields: [['zone', 'normalized (DuckDB)']]},
    {step: '④ Source Document', value: docStep.doc_id || '—',
     fields: [['role', 'evidence source']]},
  ];
}

function App() {
  const s = useWitnesses();
  const [modality, setModality] = React.useState(null);
  const [paletteOpen, setPaletteOpen] = React.useState(false);
  usePaletteHotkey(setPaletteOpen);

  const names = React.useMemo(() => new Map(
    ((s.table && s.table.entities) || []).map((e) => [e.entity_id, e.name])), [s.table]);
  const subjectName = (sid) => names.get(sid) || sid;

  const shown = modality
    ? s.claims.filter((c) => (c.modality || '').toLowerCase() === modality)
    : s.claims;

  const claimListPanel = h(LayoutPanel, {width: 292, hasDivider: true, padding: 0,
    label: 'Claims'},
    panelHead('Claims', s.subjectId
      ? `${subjectName(s.subjectId)} · ${shown.length}` : '…'),
    h('div', {style: {padding: 16}},
      h('select', {
        value: s.subjectId || '',
        onChange: (e) => s.setSubjectId(e.target.value),
        style: {width: '100%', marginBottom: 12, padding: '8px 10px',
          background: 'var(--color-background-muted)',
          color: 'var(--color-text-primary)',
          border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius-element)',
          fontFamily: 'var(--font-family-body)', fontSize: 12.5}},
        ((s.table && s.table.subjects) || []).map((sub) =>
          h('option', {key: sub.subject_id, value: sub.subject_id},
            `${subjectName(sub.subject_id)} · ev ${sub.evidence_count}`))),
      shown.map((c) => claimRow({
        key: c.claim_id,
        text: claimLabel(c),
        meta: `${c.claim_id.slice(0, 16)}… · ${c.predicate}`,
        modality: c.modality || '—',
        conf: null,
        active: c.claim_id === s.claimId,
        onClick: () => s.setClaimId(c.claim_id)})),
      shown.length === 0 && s.claims.length
        ? h(Text, {type: 'supporting'}, `modality=${modality} 인 claim 없음`) : null,
      sectionLabel('Modality'),
      modalityChips({active: modality,
        onToggle: (m) => setModality((cur) => (cur === m ? null : m))})));

  const d = s.detail;
  const conf = d && d.confidence;
  const supports = (s.evidence || []).filter((e) => e.relation === 'supports');
  const contras = (s.evidence || []).filter((e) => e.relation !== 'supports');
  const EV_SHOWN = 6;

  const evidenceItem = (e) => h('div', {key: e.evidence_id,
    onClick: () => s.selectEvidence(e.evidence_id),
    style: {cursor: 'pointer'}},
    evidenceCard({
      tone: e.relation === 'supports' ? undefined : 'contra',
      relation: e.relation,
      source: e.source_doc,
      quote: `strength ${Number(e.strength ?? 0).toFixed(2)} — 클릭해 trail·원문 전개`,
      trailHops: [`${e.evidence_id.slice(0, 18)}…`, e.source_doc]}));

  const evidencePanel = h(LayoutContent, {padding: 0},
    panelHead('Evidence & Provenance', s.claimId
      ? `${s.claimId.slice(0, 20)}… · 왕복 추적` : '…'),
    h('div', {style: {padding: 16}},
      !d ? h(Text, {type: 'supporting'}, s.error ? String(s.error) : '불러오는 중…')
        : h(React.Fragment, {},
            claimFocus({
              badgeLabel: `Claim · ${d.modality || '—'}`,
              validLabel: d.doc_id ? `원문 ${d.doc_id.slice(0, 16)}…` : null,
              text: claimLabel(d),
              meta: `id ${d.claim_id} · predicate ${d.predicate}`
                + ` · subj ${subjectName(d.subject_id)}`}),
            conf ? confidence(Number(conf.value ?? 0).toFixed(2),
              String(conf.evidence_count ?? 0),
              String(conf.independent_source_count ?? 0)) : null,
            conf && conf.basis ? independenceNote(
              `${conf.basis} — dup 클러스터 보정으로 독립 출처만 집계.`) : null,

            sectionLabel(`Supporting Evidence · 지지 ${supports.length}건`
              + (supports.length > EV_SHOWN ? ` (상위 ${EV_SHOWN} 표시)` : '')),
            supports.slice(0, EV_SHOWN).map(evidenceItem),
            supports.length === 0
              ? h(Text, {type: 'supporting'}, '지지 근거 없음') : null,

            sectionLabel(`Contradicting Evidence · 반증 ${contras.length}건`),
            contras.slice(0, EV_SHOWN).map(evidenceItem),
            contras.length === 0
              ? h(Text, {type: 'supporting'},
                  '반증 0건 — contradicts 근거는 파사드 미확장 (honest-gap §6.2). '
                  + '반증이 곧 "거짓"은 아니며 supersedes 판정은 Council 심의.')
              : null,

            s.prov ? h(React.Fragment, {},
              sectionLabel('Provenance Trail · 선택 evidence → 원문'),
              provenanceTrail(trailSteps(s.prov))) : null)));

  const docMeta = s.doc && (s.doc.documents || [])[0];
  const docPanel = h(LayoutPanel, {width: 384, hasDivider: true, padding: 0,
    label: '원문'},
    panelHead(s.doc ? s.doc.doc_id.slice(0, 22) + '…' : '원문',
      s.doc ? (s.doc.highlight || '') : '3-hop 종착'),
    h('div', {style: {padding: 16}},
      !s.doc
        ? h(Text, {type: 'supporting'}, 'evidence 를 선택하면 원문 세그먼트가 열립니다')
        : !s.doc.available
          ? h(Text, {type: 'supporting'},
              s.doc.note || '원문 미가용 (honest-gap §6.2)')
          : h(React.Fragment, {},
              docMeta ? h('div', {style: {marginBottom: 12}},
                h(Text, {type: 'label'},
                  docMeta.title || s.doc.doc_id),
                h('div', {style: {marginTop: 4}},
                  id(`${docMeta.source_id || ''} · ${docMeta.language || ''}`
                    + ` · ${String(docMeta.publication_time || '').slice(0, 10)}`))) : null,
              !s.doc.highlight && s.doc.wanted
                ? h('div', {style: {marginBottom: 10}},
                    h(Badge, {variant: 'warning', label: 'span 미매칭'}),
                    h('div', {style: {marginTop: 4}},
                      h(Text, {type: 'supporting'},
                        `추출 세그먼트 ${s.doc.wanted.split('#')[1] || s.doc.wanted} 가 `
                        + 'normalized 세그먼트 목록에 없음 — 문서 전체 표시 (honest-gap §6.2)')))
                : null,
              documentSegments({segments: s.doc.segments || [],
                highlightId: s.doc.highlight}))));

  const footer = h(LayoutFooter, {hasDivider: true},
    roundTripFooter(s.doc && s.doc.available
      ? '결과 → 원문 3-hop 왕복 성립 · provenance 완전'
      : '왕복 대기 — claim·evidence 를 선택하세요'));

  return h(React.Fragment, {},
    shell({
      route: 'hall-of-witnesses',
      eyebrow: 'Hall of Witnesses · Evidence',
      context: '증거 검사',
      title: 'Hall of Witnesses · 증거 검사',
      subtitle: 'claim ↔ 원문 span · 지지·반박 근거 · 독립성 · provenance 왕복 추적',
      hero: 'hall-of-witnesses-hero.png',
      alerts: 0,
      urls,
      onSearchOpen: () => setPaletteOpen(true),
      slots: {start: claimListPanel, content: evidencePanel, end: docPanel, footer},
    }),
    h(Palette, {open: paletteOpen, onClose: () => setPaletteOpen(false)}));
}

createRoot(document.getElementById('root')).render(h(App));
