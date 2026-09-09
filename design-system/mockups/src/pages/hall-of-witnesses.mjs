/**
 * Hall of Witnesses · 증거 검사 목업 — ui/witnesses 공용 컴포넌트 + fixture.
 * 구조 정의는 [ui/witnesses.mjs](../../../ui/witnesses.mjs) 가 정본 (specs TS-5).
 * 원문 패널만 목업 전용 서사(두 문서 대조)라 bespoke 로 남긴다 — 앱은
 * documentSegments(실데이터)로 같은 자리를 채운다.
 */

import {LayoutContent, LayoutPanel, LayoutFooter} from '@astryxdesign/core/Layout';
import {shell} from '../../../ui/shell.mjs';
import {
  h, Badge, HStack, Text, sectionLabel, confidence,
  evidenceCard, id, panelHead,
} from '../../../ui/components.mjs';
import {
  claimRow, modalityChips, claimFocus, independenceNote, provenanceTrail,
  roundTripFooter,
} from '../../../ui/witnesses.mjs';

export const title = 'Hall of Witnesses · 증거 검사 — Orc Citadel';

const CLAIMS = [
  ['A사는 AI 가속기 부품을 B사에 주로 의존한다.', 'claim-123 · depends_on', 'Asserted', '0.61', true],
  ['A사는 2025-03 C사와 신규 공급 계약을 체결했다.', 'claim-201 · contracts_with', 'Fact', '0.78'],
  ['공급망 다변화가 A사 리스크를 실질적으로 낮출 것이다.', 'claim-244 · reduces_risk', 'Prediction', '0.33'],
  ['B사 단일 의존은 지정학적으로 위험하다.', 'claim-260 · opinion_on', 'Opinion', '0.40'],
  ['C사 계약은 발표에 그치지 않고 실제 집행되었다.', 'claim-262 · executed', 'Asserted', '0.52'],
];

/** provenance trail 5 hop — 결과에서 원문까지 (03 §8 · ADR-305). */
const TRAIL = [
  {step: '① Graph Element', value: 'evd-456 · SUPPORTS claim-123',
   fields: [['type', 'Evidence'], ['rel', 'supports']]},
  {step: '② Extraction Record', value: 'ext-01J9Q7F2K3XZ',
   fields: [['model_id', 'seer-extract-v3'], ['prompt_hash', 'a91f…d20'],
            ['schema', 'v0.4.2'], ['preproc', 'pp-1.7']]},
  {step: '③ Normalized Document', value: 'doc-2291 · v2',
   fields: [['parser', 'html2md-4.1'], ['lang', 'en'], ['offset map', 'bidirectional']]},
  {step: '④ Source Span', value: 'seg-2291-p42-s3',
   fields: [['char_start', '1180'], ['char_end', '1244'], ['loc', 'p.42 · para 3']]},
  {step: '⑤ Immutable Raw', value: 'raw/2024/a-corp/10-K/content.bin',
   fields: [['content_hash', 'sha256:7c4a…e1b9']]},
];

const claimList = h(LayoutPanel, {width: 292, hasDivider: true, padding: 0, label: 'Claims'},
  panelHead('Claims', '조사 내 · 6'),
  h('div', {style: {padding: 16}},
    CLAIMS.map(([text, meta, modality, conf, active]) =>
      claimRow({text, meta, modality, conf, active})),
    sectionLabel('Modality'),
    modalityChips()));

const evidencePanel = h(LayoutContent, {padding: 0},
  panelHead('Evidence & Provenance', 'claim-123 · 왕복 추적'),
  h('div', {style: {padding: 16}},
    claimFocus({badgeLabel: 'Claim · asserted', validLabel: 'valid 2025-01-01 →',
      text: 'A사는 AI 가속기 부품을 B사에 주로 의존한다.',
      meta: 'id claim-123 · predicate depends_on · subj A사 · obj B사'}),

    confidence('0.61', '7', '2'),

    independenceNote(
      '지지 근거 5건 중 4건이 동일 보도자료(doc-5540)에서 파생(dup_cluster: dc-77). '
      + '유효 독립 출처 2건으로 집계. 근거 수만으로 confidence 를 부풀리지 않음.'),

    sectionLabel('Supporting Evidence · 지지'),
    evidenceCard({
      relation: 'supports · 실선', source: 'SEC 10-K · 1차 자료',
      quote: '"...substantially all of our AI accelerator components are sourced from a single supplier..."',
      trailHops: ['evd-456', 'doc-2291', 'seg-2291-p42-s3 · char 1180–1244'],
    }),

    sectionLabel('Contradicting Evidence · 반증'),
    evidenceCard({
      tone: 'contra', relation: 'contradicts · 이중선', source: '보도자료 · 당사자',
      quote: '"A사는 복수의 공급처를 통해 안정적 조달 체계를 갖췄다"',
      trailHops: ['evd-789', 'doc-5540', 'seg-5540-p3-s1 · char 88–140'],
    }),
    h(Text, {type: 'supporting'},
      '반증이 곧 "거짓"은 아님 — 시점·화자·범위가 다른 진술로 병렬 보존되며, '
      + 'supersedes 판정은 Council 이 별도 심의.'),

    sectionLabel('Provenance Trail · evd-456 → 원문'),
    provenanceTrail(TRAIL)));

const docPanel = h(LayoutPanel, {width: 384, hasDivider: true, padding: 0, label: '원문'},
  panelHead('doc-2291 · v2', 'seg-2291-p42-s3'),
  h('div', {style: {padding: 16}},
    h(HStack, {gap: 2},
      h(Badge, {variant: 'neutral', label: 'http 200'}),
      h(Badge, {variant: 'neutral', label: 'robots allow'})),
    h('div', {style: {marginTop: 12}},
      h(Text, {type: 'label'}, 'A-Corp · Form 10-K (FY2024) · Item 1A. Risk Factors')),
    h('div', {style: {marginTop: 10, fontSize: 12.5, lineHeight: 1.7,
      color: 'var(--color-text-secondary)'}},
      h('div', {}, id('[p.42 · char 1100]')),
      h('p', {}, 'Our business depends on a limited number of suppliers for key components. '
        + 'We do not have long-term volume commitments from all of them, and qualifying '
        + 'alternative sources can take significant time.'),
      h('div', {style: {marginTop: 10}}, id('[char 1180]')),
      h('p', {}, 'As of the fiscal year end, ',
        h('mark', {style: {background: 'rgba(69,224,111,.18)',
          color: 'var(--color-text-primary)', padding: '1px 2px',
          borderBottom: '2px solid var(--color-accent)'}},
          'substantially all of our AI accelerator components are sourced from a single supplier'),
        '.'),
      h('div', {style: {marginTop: 4}},
        h(Badge, {variant: 'success', label: 'supports · evd-456'})),
      h('div', {style: {marginTop: 10}}, id('[char 1320]')),
      h('p', {}, 'We are actively pursuing supply diversification, but there can be no '
        + 'assurance that such efforts will succeed within the periods we anticipate.'),
      h('div', {style: {marginTop: 14}}, id('[doc-5540 · para 3 · char 88]')),
      h('p', {}, '별도 문서(보도자료) 대조: ',
        h('mark', {style: {background: 'rgba(224,82,82,.16)',
          color: 'var(--color-text-primary)', padding: '1px 2px',
          borderBottom: '2px double var(--color-error)'}},
          'A사는 복수의 공급처를 통해 안정적 조달 체계를 갖췄다'),
        ' — 발표 시점·화자가 다른 병렬 진술.'),
      h('div', {style: {marginTop: 4}},
        h(Badge, {variant: 'error', label: 'contradicts · evd-789'})))));

const roundTrip = h(LayoutFooter, {hasDivider: true}, roundTripFooter());

export const render = () => shell({
  route: 'hall-of-witnesses',
  eyebrow: 'Hall of Witnesses · Evidence',
  context: '증거 검사',
  title: 'Hall of Witnesses · 증거 검사',
  subtitle: 'claim ↔ 원문 span · 지지·반박 근거 · 독립성 · provenance 왕복 추적',
  hero: 'hall-of-witnesses-hero.png',
  slots: {start: claimList, content: evidencePanel, end: docPanel, footer: roundTrip},
});
