/** Council Chamber · 조사 실행 — Warchief's Council | 조사 루프·발언 | Stopping·Cost·Audit. */

import {LayoutContent, LayoutPanel} from '@astryxdesign/core/Layout';
import {shell} from '../../../ui/shell.mjs';
import {
  h, Badge, HStack, Text, sectionLabel, coverage, id, panelHead, grid,
} from '../../../ui/components.mjs';

export const title = 'Council Chamber · 조사 실행 — Orc Citadel';

/** 8 Agent — [기능명, 세계관명, 상태, 설명, 모델, 초상]. */
const AGENTS = [
  ['Investigation Planner', '조사 설계관', 'done',
    'subclaim 8개 분해 · known/gap 라벨 부착', 'opus-4-8 · 고성능·reasoning', 'char-warchief.png'],
  ['Graph Explorer', '지도 탐색관', 'done',
    'War Table subgraph 조회 · read-only · 관계 경로 3', 'sonnet-5 · 중급', 'char-seer.png'],
  ['Retrieval Agent', '수색대', 'done',
    'hybrid 검색 · 후보 span 12건 반환 (문서 아님)', 'sonnet-5 · 중급', 'char-scout.png'],
  ['Evidence Extractor', '증언 채록관', 'running',
    'span → claim/evidence 후보 추출 · strict JSON · batch', 'sonnet-5 · 중급·batch', 'char-archivist.png'],
  ['Counter-Evidence', '반증 심문관', 'running',
    '반대 가설·부정 검색질의 생성 · 모순 후보 판정', 'opus-4-8 · 고성능·reasoning', 'char-seer.png'],
  ['Source Independence Judge', '출처 독립성 판관', 'idle',
    '복제본 → 독립 근거 수 보정 · root/derived 분해', 'opus-4-8 · 고성능', 'char-sentinel.png'],
  ['Synthesis Agent', '종합 서기관', 'idle',
    '검증 subgraph 확정 후에만 문장 생성 · 사실/주장/추론/예측 구분', 'opus-4-8 · 고성능·reasoning', 'char-warchief.png'],
  ['Audit Agent', '감사관', 'idle',
    '문장 → claim+source span 역추적 · 무출처 문장 차단', 'sonnet-5 + deterministic 검증', 'char-sentinel.png'],
];

/** 조사 루프 12 스텝 (07 §4). */
const LOOP = [
  ['계획 수립', 'plan'], ['subgraph 조회', 'retrieve subgraph'],
  ['공백 식별', 'identify gaps'], ['검색', 'search'], ['추출', 'extract'],
  ['해소 · Lorekeepers', 'resolve'], ['provisional 갱신', 'update provisional'],
  ['반증 조사', 'counter-evidence'], ['종료 조건 평가', 'stopping?'],
  ['종합', 'synthesize'], ['감사', 'audit'],
];

/** 발언 타임라인. */
const TURNS = [
  ['Graph Explorer', 'sonnet-5', '04:11:38Z',
    'provisional War Table 에서 C사 계약 subgraph 를 조회 — 계약 발표(claim-201)는 존재하나, '
    + '이를 지지하는 1차 공시·계약 문서 노드는 없음. quarantine 에 미해소 후보 "C사?" 1건.',
    'relation_path: A사 —[made_claim]→ claim-201 —[about]→ C사 · 지지 evidence 0 · 반박 evidence 1(보도자료)',
    '◐ coverage 0.20 · 독립 출처 0'],
  ['Retrieval Agent', 'sonnet-5', '04:11:52Z',
    '공백(계약 실집행 증거)에 대해 부정 질의 포함 hybrid 검색 실행 — 후보 span 5건 회수. '
    + '전체 문서가 아닌 span·주변 그래프만 반환.',
    'query: (C사 AND (공급계약 OR 조달) AND (공시 OR 인도실적)) · source_type ∈ {exchange, gov} · top-5 span',
    '◐ 후보 5건 중 1차 자료 2건'],
];

/** 종료 조건 — STOP = (A ∧ B ∧ C) ∨ D. */
const STOPPING = [
  ['A', '핵심 subclaim evidence coverage', '0.63', 63,
    '5 / 8 covered · 임계 ≥ 0.90 · 미충족'],
  ['B', '신규 독립증거 발견률 감소', 'Δ 0.07', 30,
    '최근 5 step 증가율 · 임계 < ε 0.05 · 미충족(아직 발견 중)'],
  ['C', 'contradiction 조사 완료', '2 / 3', 66,
    '미해결 모순 후보 1건 (H2 시간차, 판정 중) · 임계 = 0 · 미완'],
  ['δ', 'confidence 변화폭 (보조 신호)', 'Δ 0.04', 20,
    '최근 step 간 결론 confidence 변화 · 수렴 신호로 A·B 보강'],
  ['D', 'budget (hard stop)', '$3.02 / $8.00', 38,
    'time 640s / 1800s · 여유 · task budget 으로 우아하게 마무리'],
];

const COST = [['$3.02', 'llm usd'], ['51', 'tool calls'],
  ['940K', 'tokens in'], ['72K', 'tokens out']];
const MODELS = [['opus-4-8', '14 · $2.31'], ['sonnet-5', '29 · $0.63'], ['haiku-4-5', '8 · $0.08']];

const STATUS = {done: 'success', running: 'warning', idle: 'neutral'};

function agentCard([fn, wn, state, desc, model, art]) {
  // alignItems 필수 — 기본 stretch 면 초상(img, reset 이 height:auto 로 만듦)이
  // 행 높이만큼 세로로 늘어나 찌그러진다. 크기도 속성이 아니라 인라인 style 로.
  return h('div', {key: fn, style: {display: 'flex', gap: 10, padding: '10px 12px',
    alignItems: 'flex-start',
    border: '1px solid var(--color-border)', borderRadius: 'var(--radius-element)',
    marginBottom: 8, background: state === 'running' ? 'rgba(255,177,59,.05)' : 'transparent'}},
    h('img', {src: `./assets/${art}`, alt: '',
      style: {width: 34, height: 34, imageRendering: 'pixelated',
        borderRadius: 'var(--radius-inner)', flex: 'none'}}),
    h('div', {style: {minWidth: 0}},
      h('div', {style: {display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap'}},
        h('span', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 12,
          fontWeight: 600, color: 'var(--color-text-primary)'}}, fn),
        h('span', {style: {fontSize: 10, color: 'var(--color-text-secondary)'}}, wn),
        h(Badge, {variant: STATUS[state], label: state})),
      h('div', {style: {marginTop: 4}}, h(Text, {type: 'supporting'}, desc)),
      h('div', {style: {marginTop: 4}}, id(model))));
}

const council = h(LayoutPanel, {width: 320, hasDivider: true, padding: 0,
  label: "Warchief's Council"},
  panelHead("Warchief's Council", '8 Agents · Loop 2'),
  h('div', {style: {padding: 16}}, AGENTS.map(agentCard)));

const loopStrip = h('div', {style: {display: 'flex', flexWrap: 'wrap', gap: 4}},
  LOOP.map(([ko, en], i) =>
    h('span', {key: en, style: {display: 'inline-flex', alignItems: 'center', gap: 6,
      padding: '5px 9px', borderRadius: 'var(--radius-full)', fontSize: 10.5,
      border: '1px solid var(--color-border)',
      background: i < 8 ? 'rgba(69,224,111,.06)' : 'transparent',
      color: i < 8 ? 'var(--color-text-primary)' : 'var(--color-text-secondary)'}},
      ko, h('span', {style: {fontFamily: 'var(--font-family-code)', fontSize: 9,
        color: 'var(--color-text-secondary)'}}, en))));

function turnCard([agent, model, at, body, evidence, uncertainty]) {
  return h('div', {key: at, style: {border: '1px solid var(--color-border)',
    borderRadius: 'var(--radius-element)', padding: 12, marginBottom: 10}},
    h('div', {style: {display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap'}},
      h('span', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 12,
        fontWeight: 600, color: 'var(--color-text-primary)'}}, agent),
      h(Badge, {variant: 'neutral', label: model}), id(at)),
    h('div', {style: {marginTop: 8}}, h(Text, {type: 'supporting'}, body)),
    h('div', {style: {marginTop: 10, padding: '8px 10px',
      background: 'var(--color-background-muted)', borderRadius: 'var(--radius-inner)'}},
      h(Text, {type: 'label'}, '근거 · Evidence'),
      h('div', {style: {marginTop: 4}}, id(evidence))),
    h('div', {style: {marginTop: 6}},
      h(Text, {type: 'label'}, '불확실성 · Uncertainty'),
      h('div', {style: {marginTop: 4}}, id(uncertainty))));
}

const loopBody = h(LayoutContent, {padding: 0},
  panelHead('조사 루프 · Investigation Loop', 'subclaim-3 · step-014'),
  h('div', {style: {padding: 16}},
    loopStrip,
    sectionLabel('현재 하위 질문'),
    h('div', {style: {border: '1px solid var(--color-accent)',
      background: 'rgba(69,224,111,.05)', borderRadius: 'var(--radius-element)',
      padding: 12}},
      h(Text, {}, 'C사와의 신규 공급 계약은 발표가 아닌 실제 집행이 확인되는가?'),
      h('div', {style: {marginTop: 6}}, id('subclaim-3 · step-014'))),
    sectionLabel('발언 · Turns'),
    TURNS.map(turnCard)));

const stopping = h(LayoutPanel, {width: 372, hasDivider: true, padding: 0,
  label: 'Stopping · Cost · Audit'},
  panelHead('Stopping · Cost · Audit', 'running'),
  h('div', {style: {padding: 16}},
    h(Text, {type: 'label'}, '종료 조건 · Stopping (조합)'),
    h('div', {style: {margin: '8px 0 12px', padding: '8px 10px',
      background: 'var(--color-background-muted)', borderRadius: 'var(--radius-inner)',
      fontFamily: 'var(--font-family-code)', fontSize: 11.5,
      color: 'var(--astryx-theme-citadel-parchment)'}},
      'STOP = ( A ∧ B ∧ C ) ∨ D   · D=budget hard stop'),
    STOPPING.map(([k, name, value, pct, note]) =>
      h('div', {key: k, style: {marginBottom: 12}},
        h('div', {style: {display: 'flex', alignItems: 'baseline',
          justifyContent: 'space-between', gap: 8}},
          h('span', {style: {fontSize: 11.5, color: 'var(--color-text-primary)'}},
            h('b', {style: {fontFamily: 'var(--font-family-code)',
              color: 'var(--color-accent)'}}, k), ' ', name),
          h('span', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 13,
            fontWeight: 600, color: 'var(--color-text-primary)'}}, value)),
        h('div', {style: {margin: '6px 0 4px'}}, coverage(pct, pct < 70 ? 'warn' : null)),
        h(Text, {type: 'supporting'}, note))),

    sectionLabel('비용 · Cost (investigation 누적)'),
    grid(2, 8, ...COST.map(([v, c]) =>
      h('div', {key: c, style: {padding: '8px 10px',
        border: '1px solid var(--color-border)', borderRadius: 'var(--radius-inner)'}},
        h('div', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 16,
          fontWeight: 600, color: 'var(--color-text-primary)'}}, v),
        h('div', {style: {fontSize: 9.5, letterSpacing: '.06em', textTransform: 'uppercase',
          color: 'var(--color-text-secondary)', marginTop: 2}}, c)))),
    h('div', {style: {marginTop: 8}},
      h(Text, {type: 'supporting'}, '모델별 호출 · 문서당 $0.19 · p50 latency 3.4s')),
    h('div', {style: {display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 6}},
      MODELS.map(([m, v]) => h(Badge, {key: m, variant: 'neutral', label: `${m} ${v}`}))),

    sectionLabel('Audit Agent · 역추적 감사'),
    [['9 / 9', '검증가능 문장이 claim + source span 으로 역추적됨',
      'claim → source span → doc version → raw → source URL (직전 draft 기준)', 'success'],
     ['3', '무출처·과도한 일반화 문장 차단',
      '보고서에서 제거 또는 "unsupported" 로 명시 표기', 'warning'],
     ['대기', '최종 감사는 Synthesis 완료 후 실행',
      '모든 검증가능 문장 역추적 통과 시에만 보고서 완료', 'neutral']]
      .map(([v, title2, note, variant]) =>
        h('div', {key: title2, style: {display: 'flex', gap: 10, marginBottom: 10}},
          h('span', {style: {flex: 'none', minWidth: 46, textAlign: 'center',
            padding: '3px 8px', borderRadius: 'var(--radius-inner)',
            fontFamily: 'var(--font-family-heading)', fontSize: 11, fontWeight: 600,
            color: variant === 'success' ? 'var(--color-accent)'
              : variant === 'warning' ? 'var(--astryx-theme-citadel-signal-amber)'
              : 'var(--color-text-secondary)',
            background: variant === 'success' ? 'rgba(69,224,111,.14)'
              : variant === 'warning' ? 'rgba(255,177,59,.14)'
              : 'var(--color-background-muted)'}}, v),
          h('div', {style: {minWidth: 0}},
            h(Text, {type: 'supporting'}, title2),
            h('div', {style: {marginTop: 2}}, id(note)))))));

export const render = () => shell({
  route: 'council-chamber',
  eyebrow: 'Council Chamber · Investigation',
  context: '조사 실행',
  title: 'Council Chamber · 조사 실행',
  subtitle: 'Agent 계획 · 토론 · 반증 · 종합 · 조사 루프 · 비용',
  hero: 'council-chamber-hero.png',
  slots: {start: council, content: loopBody, end: stopping},
});
