/** Generated Investigation Report — script-free HTML artifact concept mockup. */

import {
  h, Badge, Card, Text, confidence, sectionLabel, sourceSpan, trail, id, grid,
  Table, TableHeader, TableHeaderCell, TableBody, TableRow, TableCell,
} from '../../../ui/components.mjs';

export const title = 'Investigation Report · DEMO — Orc Citadel';

const box = {maxWidth: 1040, margin: '0 auto', padding: '32px 24px 64px'};
const section = {marginTop: 28};
const heading = {fontFamily: 'var(--font-family-heading)', fontSize: 20,
  lineHeight: 1.25, color: 'var(--color-text-primary)', margin: '0 0 12px'};
const label = {fontFamily: 'var(--font-family-heading)', fontSize: 10,
  letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--color-text-secondary)'};

function statement({modality, tone, text, claim}) {
  return h('article', {style: {padding: '14px 16px', marginBottom: 10,
    border: '1px solid var(--color-border)', borderLeft: `3px solid ${tone}`,
    borderRadius: 'var(--radius-element)', background: 'var(--color-background-card)'}},
    h('div', {style: {display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap'}},
      h(Badge, {variant: modality === 'asserted' ? 'success' : 'warning',
        label: modality}),
      claim ? id(claim) : h(Text, {type: 'supporting'}, 'claim_ref 없음 · 예측')),
    h('p', {style: {margin: '10px 0 0', fontSize: 15, lineHeight: 1.65,
      color: 'var(--color-text-primary)'}}, text));
}

const report = h('main', {id: 'report', style: box},
  h('style', {}, `
    :root {
      color-scheme: dark;
      --color-accent:#45E06F;
      --color-on-accent:#07111C;
      --color-background-body:#07111C;
      --color-background-surface:#0D1B2A;
      --color-background-card:#111820;
      --color-background-muted:#26313A;
      --color-border:#3A4651;
      --color-border-emphasized:#59636A;
      --color-text-primary:#D6CCB8;
      --color-text-secondary:#A69D8D;
      --color-text-disabled:#7C7468;
      --color-success:#45E06F;
      --color-error:#E05252;
      --color-warning:#FFB13B;
      --astryx-theme-citadel-parchment:#C8B58E;
      --astryx-theme-citadel-signal-amber:#FFB13B;
    }
    html, body { background-color:#07111C; color:#D6CCB8; }
    body { margin:0; }
    main#report { background-color:#07111C; color:#D6CCB8; }
    a { color:#45E06F; text-underline-offset:3px; }
    .report-toc { display:flex; flex-wrap:wrap; gap:8px 16px; margin-top:20px; }
    .report-toc a { font:600 11px var(--font-family-heading); }
    @media (max-width: 720px) {
      main#report { padding:20px 14px 40px !important; }
      .report-meta, .report-kpis { grid-template-columns:1fr !important; }
    }
    @media print {
      html, body { background:#fff !important; color:#111 !important; }
      main#report { max-width:none !important; padding:0 !important; }
      main#report * { background-color:#fff !important; color:#111 !important; border-color:#777 !important; }
      main#report a { color:#0645ad !important; }
      .screen-only { display:none !important; }
      section, article, tr { break-inside:avoid; }
      #audit { break-before:page; }
      * { box-shadow:none !important; }
    }
  `),
  h('a', {href: '#conclusion', className: 'screen-only',
    style: {position: 'absolute', left: -9999}}, '본문으로 건너뛰기'),
  h('header', {},
    h('div', {style: {display: 'flex', justifyContent: 'space-between', gap: 16,
      alignItems: 'start', flexWrap: 'wrap'}},
      h('div', {},
        h('div', {style: label}, 'Campaign Ledger · Investigation Report'),
        h('h1', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 30,
          lineHeight: 1.2, color: 'var(--color-text-primary)', margin: '8px 0 10px'}},
          'A사의 AI 가속기 공급망 다변화는 실제로 진행되었는가?'),
        h(Text, {type: 'supporting'},
          '시스템 지식 스냅샷 · 2026-09-18 09:42 UTC 이후 증거는 포함하지 않음')),
      h('div', {style: {display: 'flex', gap: 8, flexWrap: 'wrap'}},
        h(Badge, {variant: 'neutral', label: 'DEMO FIXTURE'}),
        h(Badge, {variant: 'success', label: 'completed'}),
        h(Badge, {variant: 'neutral', label: 'LLM assisted'}))),
    h('div', {className: 'report-meta', style: {display: 'grid',
      gridTemplateColumns: 'repeat(3,1fr)', gap: 1, marginTop: 20,
      border: '1px solid var(--color-border)', borderRadius: 'var(--radius-element)',
      overflow: 'hidden', background: 'var(--color-border)'}},
      [['Investigation ID', 'inv-demo-001'], ['Scope', '2024-01-01 이후 · US/KR/TW'],
        ['Artifact', 'rpt-demo-001 · citadel-report-1']].map(([k, v]) =>
        h('div', {key: k, style: {padding: 12, background: 'var(--color-background-card)'}},
          h('div', {style: label}, k),
          h('div', {style: {marginTop: 5, fontFamily: 'var(--font-family-code)',
            fontSize: 11, color: 'var(--color-text-primary)'}}, v)))),
    h('p', {style: {margin: '18px 0 0', padding: '12px 14px',
      border: '1px solid var(--color-border)', borderRadius: 'var(--radius-element)',
      color: 'var(--astryx-theme-citadel-parchment)', lineHeight: 1.6}},
      'Evidence-first report · 검증 가능한 문장은 claim과 source span으로 역추적되는 경우에만 포함합니다. '
      + '미측정 값은 추정하지 않습니다. 아래 조직·수치·ID는 레이아웃 검증용 DEMO입니다.'),
    h('nav', {className: 'report-toc', 'aria-label': '보고서 목차'},
      [['#conclusion', '1. 현재 결론'], ['#findings', '2. 핵심 발견'],
        ['#timeline', '3. 변화 타임라인'], ['#questions', '4. 열린 질문'],
        ['#method', '5. 방법과 한계'], ['#audit', '6. Audit 부록']].map(([href, text]) =>
        h('a', {key: href, href}, text)))),

  h('section', {id: 'conclusion', style: section},
    h('h2', {style: heading}, '1. 현재 결론 · Current Conclusion'),
    h(Card, {}, h('div', {style: {padding: 6}},
      h('p', {style: {fontSize: 17, lineHeight: 1.7, margin: '0 0 16px',
        color: 'var(--color-text-primary)'}},
        '공식 발표 수준의 다변화는 확인되지만, 계약·공시로 검증되는 실제 집행 증거는 제한적입니다.'),
      confidence('0.61', 7, 2),
      h('p', {style: {margin: '12px 0 0', fontSize: 13, lineHeight: 1.6,
        color: 'var(--astryx-theme-citadel-parchment)'}},
        'Confidence basis · 지지 문서 5건 중 4건이 동일 보도자료 파생입니다. 독립 출처 2건으로 보정했으며 반박 1차 자료 1건이 존재합니다.')))),

  h('section', {id: 'findings', style: section},
    h('h2', {style: heading}, '2. 핵심 발견과 근거 · Findings & Evidence'),
    statement({modality: 'asserted', tone: 'var(--color-accent)',
      text: 'A사는 2024년 5월 복수 공급처 확보 계획을 공식 발표했습니다.', claim: 'clm-demo-01'}),
    h('details', {open: true, style: {margin: '-4px 0 14px', padding: '10px 14px',
      border: '1px solid var(--color-border)', borderRadius: 'var(--radius-element)'}},
      h('summary', {style: {cursor: 'pointer', fontFamily: 'var(--font-family-heading)',
        fontSize: 12, fontWeight: 600}}, 'Evidence & Provenance · supports 2 · contradicts 1'),
      sectionLabel('Supports · 지지'),
      sourceSpan('“We are qualifying multiple supply partners for the next accelerator generation.”'),
      trail('evd-demo-01', 'doc-demo-press', 'segment p4.s2', 'char 118–196'),
      sectionLabel('Contradicts · 반박'),
      sourceSpan('“Substantially all accelerator components remain sourced from one supplier.”'),
      trail('evd-demo-02', 'doc-demo-filing', 'segment p42.s3', 'char 1180–1244'),
      h('a', {href: './hall-of-witnesses.html?claim=clm-demo-01',
        style: {display: 'inline-block', marginTop: 12,
          fontFamily: 'var(--font-family-heading)', fontSize: 11}},
        'Hall of Witnesses에서 근거 열기')),
    statement({modality: 'prediction', tone: 'var(--astryx-theme-citadel-signal-amber)',
      text: '다변화가 조달 안정성으로 이어지는지는 다음 분기 공시의 실제 인도 실적으로 확인해야 합니다.',
      claim: null})),

  h('section', {id: 'timeline', style: section},
    h('h2', {style: heading}, '3. 변화 타임라인 · Change Timeline'),
    h(Text, {type: 'supporting'},
      'Valid time은 주장이 현실에 적용되는 시점, Observed at은 Citadel이 기록한 시점입니다.'),
    h('div', {style: {marginTop: 12, overflowX: 'auto'}},
      h(Table, {},
        h(TableHeader, {}, h(TableRow, {},
          ['Valid time', 'Observed at', 'Change', 'Claim', 'Supersedes'].map((x) =>
            h(TableHeaderCell, {key: x}, x)))),
        h(TableBody, {},
          h(TableRow, {},
            h(TableCell, {}, '2024-05'), h(TableCell, {}, '2024-05-02 UTC'),
            h(TableCell, {}, 'Asserted'), h(TableCell, {}, id('clm-demo-01')),
            h(TableCell, {}, '—')),
          h(TableRow, {},
            h(TableCell, {}, '2025-Q1'), h(TableCell, {}, '2025-02-15 UTC'),
            h(TableCell, {}, 'Contradicts'), h(TableCell, {}, id('clm-demo-02')),
            h(TableCell, {}, '—')))))),

  h('section', {id: 'questions', style: section},
    h('h2', {style: heading}, '4. 열린 질문 · Open Questions'),
    grid(2, 12,
      h(Card, {}, h('div', {style: {padding: 4}},
        h(Text, {type: 'label'}, '2025-H2 조달 계약의 실제 인도 실적'),
        h('div', {style: {marginTop: 8}},
          h(Text, {type: 'supporting'}, 'Reason · 공시 미확인 · Coverage 0%')))),
      h(Card, {}, h('div', {style: {padding: 4}},
        h(Text, {type: 'label'}, '복수 공급처의 생산 비중'),
        h('div', {style: {marginTop: 8}},
          h(Text, {type: 'supporting'}, 'Reason · 독립 1차 자료 부족 · Coverage 25%')))))),

  h('section', {id: 'method', style: section},
    h('h2', {style: heading}, '5. 조사 방법과 한계 · Method & Limits'),
    h(Card, {}, h('div', {style: {padding: 4}},
      h('div', {className: 'report-kpis', style: {display: 'grid',
        gridTemplateColumns: 'repeat(4,1fr)', gap: 12}},
        [['Steps', '5'], ['Coverage', '5/8 · 63%'], ['Termination', 'no_new_evidence'],
          ['Cost', '가격 미측정']].map(([k, v]) => h('div', {key: k},
          h('div', {style: label}, k), h('div', {style: {marginTop: 5}}, id(v))))),
      h('p', {style: {margin: '14px 0 0', lineHeight: 1.6}},
        '종료 조건은 이 실행이 끝난 이유이며 관련 증거를 모두 찾았다는 뜻이 아닙니다. '
        + '문서 수는 독립 출처 수로 간주하지 않습니다.')))),

  h('section', {id: 'audit', style: section},
    h('h2', {style: heading}, '6. Audit & Reproducibility Appendix'),
    h(Card, {}, h('div', {style: {padding: 4}},
      h('div', {style: {display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap'}},
        h(Badge, {variant: 'success', label: 'VERIFIED 5/5'}),
        h(Badge, {variant: 'neutral', label: 'BLOCKED 0'})),
      h('p', {style: {lineHeight: 1.6}},
        '검증 가능한 문장 5개 모두 claim → extraction record → source span으로 연결되었습니다.'),
      sectionLabel('Generation'),
      id('mode · llm_assisted · model bunker-flash · prompt sha256:84d2…'),
      h('div', {style: {marginTop: 6}}, id('template · citadel-report-1 · draft-schema 1.0.0')),
      sectionLabel('Version Tuple'),
      id('ontology 1.0.0 · schema 1.2.0 · extraction git:demo'),
      sectionLabel('Artifact Integrity'),
      id('source sha256:1b7d… · draft sha256:20a4… · html sha256:7b31a4d9c102…')))),

  h('footer', {style: {marginTop: 32, paddingTop: 16,
    borderTop: '1px solid var(--color-border)'}},
    h(Text, {type: 'supporting'},
      'Generated from audited investigation data · inv-demo-001 · content hash 7b31a4d9c102 · DEMO fixture')));

export const render = () => report;
