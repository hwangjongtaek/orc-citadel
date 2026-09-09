/**
 * Council Chamber 조각 — Agent 카드 · 조사 루프 스트립 · 발언 카드.
 *
 * 목업은 fixture(가상 실행 상태·모델 칩)로 구조를 증명하고, 앱은 wire 필드
 * 존재로 executed/not-run 을 판정한다 — live 실행·비용·모델 ID 는 wire 미영속
 * 이라 앱에서 하드코딩하지 않는다 (honest-gap §6.2).
 */

import {h, Badge, Text, id} from './components.mjs';

/** 조사 루프 12 스텝 카탈로그 (07 §4) — 목업·앱 공용 정본. */
export const LOOP_STEPS = [
  ['계획 수립', 'plan'], ['subgraph 조회', 'retrieve subgraph'],
  ['공백 식별', 'identify gaps'], ['검색', 'search'], ['추출', 'extract'],
  ['해소 · Lorekeepers', 'resolve'], ['provisional 갱신', 'update provisional'],
  ['반증 조사', 'counter-evidence'], ['종료 조건 평가', 'stopping?'],
  ['종합', 'synthesize'], ['감사', 'audit'],
];

const STATUS_TONES = {
  done: 'success', executed: 'success', running: 'warning',
  idle: 'neutral', 'not-run': 'neutral',
};

/**
 * Agent 카드 — 초상은 카드 세로에 꽉 차게, 비율 유지 (2026-09-08 확정).
 * img 에 직접 stretch 를 걸면 주축 폭이 고유 크기(512px)로 남아 거인이 된다 —
 * 래퍼 div 의 aspect-ratio 가 stretch 높이를 폭으로 전이하게 하고,
 * img 는 래퍼를 absolute + cover 로 채운다 (reset img 함정 회피).
 */
export function agentCard({name, worldName, state, desc, model, art,
                           assetBase = './assets/'}) {
  return h('div', {style: {display: 'flex', gap: 12, padding: '10px 12px',
    alignItems: 'stretch',
    border: '1px solid var(--color-border)', borderRadius: 'var(--radius-element)',
    marginBottom: 8,
    background: state === 'running' ? 'rgba(255,177,59,.05)' : 'transparent'}},
    h('div', {style: {alignSelf: 'stretch', aspectRatio: '1 / 1', minHeight: 56,
      position: 'relative', flex: 'none', overflow: 'hidden',
      borderRadius: 'var(--radius-inner)'}},
      h('img', {src: `${assetBase}${art}`, alt: '',
        style: {position: 'absolute', inset: 0, width: '100%', height: '100%',
          objectFit: 'cover', imageRendering: 'pixelated'}})),
    h('div', {style: {minWidth: 0}},
      h('div', {style: {display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap'}},
        h('span', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 12,
          fontWeight: 600, color: 'var(--color-text-primary)'}}, name),
        h('span', {style: {fontSize: 10, color: 'var(--color-text-secondary)'}},
          worldName),
        h(Badge, {variant: STATUS_TONES[state] || 'neutral', label: state})),
      h('div', {style: {marginTop: 4}}, h(Text, {type: 'supporting'}, desc)),
      model ? h('div', {style: {marginTop: 4}}, id(model)) : null));
}

/** 조사 루프 12스텝 스트립 — `doneCount` 앞까지 진행 색. */
export function loopStrip({steps = LOOP_STEPS, doneCount = 0}) {
  return h('div', {style: {display: 'flex', flexWrap: 'wrap', gap: 4}},
    steps.map(([ko, en], i) =>
      h('span', {key: en, style: {display: 'inline-flex', alignItems: 'center', gap: 6,
        padding: '5px 9px', borderRadius: 'var(--radius-full)', fontSize: 10.5,
        border: '1px solid var(--color-border)',
        background: i < doneCount ? 'rgba(69,224,111,.06)' : 'transparent',
        color: i < doneCount ? 'var(--color-text-primary)'
          : 'var(--color-text-secondary)'}},
        ko, h('span', {style: {fontFamily: 'var(--font-family-code)', fontSize: 9,
          color: 'var(--color-text-secondary)'}}, en))));
}

/** 발언(턴) 카드 — 본문 + 근거 + 불확실성 3층 (DESIGN.md 발언 구조). */
export function turnCard({agent, model, at, body, evidence, uncertainty}) {
  return h('div', {style: {border: '1px solid var(--color-border)',
    borderRadius: 'var(--radius-element)', padding: 12, marginBottom: 10}},
    h('div', {style: {display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap'}},
      h('span', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 12,
        fontWeight: 600, color: 'var(--color-text-primary)'}}, agent),
      model ? h(Badge, {variant: 'neutral', label: model}) : null,
      at ? id(at) : null),
    h('div', {style: {marginTop: 8}}, h(Text, {type: 'supporting'}, body)),
    evidence ? h('div', {style: {marginTop: 10, padding: '8px 10px',
      background: 'var(--color-background-muted)',
      borderRadius: 'var(--radius-inner)'}},
      h(Text, {type: 'label'}, '근거 · Evidence'),
      h('div', {style: {marginTop: 4}}, id(evidence))) : null,
    uncertainty ? h('div', {style: {marginTop: 6}},
      h(Text, {type: 'label'}, '불확실성 · Uncertainty'),
      h('div', {style: {marginTop: 4}}, id(uncertainty))) : null);
}

/**
 * 8역할 카탈로그 (앱용) — wire 필드 존재로 executed/not-run 판정 (council_ext
 * CX_ROLES 와 동일 계약). `wire: null` 은 wire 신호 자체가 없는 역할(항상 not-run
 * 표기 + 사유). 초상은 세계관 캐릭터 아트.
 */
export const COUNCIL_ROLES = [
  {name: 'Investigation Planner', worldName: '조사 설계관', art: 'char-warchief.png',
   desc: '질문 → subclaim 분해 · known/gap 라벨',
   wire: (r) => (r.planned_subclaims || []).length > 0},
  {name: 'Graph Explorer', worldName: '지도 탐색관', art: 'char-seer.png',
   desc: 'ABOUT subgraph 조회 · read-only',
   wire: (r) => !!r.subgraph
     && !((r.subgraph.relationships || []).length === 0 && !r.subgraph.entity)},
  {name: 'Retrieval Agent', worldName: '수색대', art: 'char-scout.png',
   desc: 'gap → 후보 span 검색 · ≤10 반환',
   wire: (r) => (r.retrieved || []).length > 0},
  {name: 'Counter-Evidence', worldName: '반증 심문관', art: 'char-seer.png',
   desc: '반증 가설·부정 질의 · 결정적 규칙 산출',
   wire: (r) => (r.counter_evidence || []).length > 0},
  {name: 'Synthesis Agent', worldName: '종합 서기관', art: 'char-warchief.png',
   desc: '결론 반영 asserted 문장 생성',
   wire: (r) => (r.statements || []).length > 0},
  {name: 'Audit Agent', worldName: '감사관', art: 'char-sentinel.png',
   desc: '문장 → claim → source span 역추적',
   wire: (r) => !!r.audit_trace && typeof r.audit_trace === 'object'},
  {name: 'route_llm', worldName: '전령 배정관', art: 'char-archivist.png',
   desc: 'tier 라우팅 — 판정 미영속 · wire 신호 없음 (honest-gap)', wire: null},
  {name: 'Evidence Extractor', worldName: '증언 채록관', art: 'char-archivist.png',
   desc: 'span → claim 추출 — 쓰기 경로 범위 밖 · wire 신호 없음 (honest-gap)',
   wire: null},
];
