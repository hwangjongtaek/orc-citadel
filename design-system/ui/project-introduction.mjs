import React from 'react';
import {Badge, Button, Card, Text} from './components.mjs';

const h = React.createElement;

const C = {
  page: {padding: '32px 24px 56px', display: 'grid', gap: 40},
  section: {display: 'grid', gap: 16},
  sectionHead: {display: 'grid', gap: 7, maxWidth: 760},
  kicker: {margin: 0, fontFamily: 'var(--font-family-heading)', fontSize: 10,
    fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase',
    color: 'var(--color-accent)'},
  h2: {margin: 0, fontFamily: 'var(--font-family-heading)', fontSize: 24,
    lineHeight: 1.24, color: 'var(--color-text-primary)'},
  copy: {margin: 0, maxWidth: 760, fontFamily: 'var(--font-family-body)', fontSize: 15,
    lineHeight: 1.72, color: 'var(--astryx-theme-citadel-parchment)'},
  grid3: {display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 12},
  grid2: {display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 14},
  card: {height: '100%'},
  cardBody: {display: 'grid', gap: 10},
  cardTitle: {margin: 0, fontFamily: 'var(--font-family-heading)', fontSize: 16,
    lineHeight: 1.35, color: 'var(--color-text-primary)'},
  cardCopy: {margin: 0, fontFamily: 'var(--font-family-body)', fontSize: 13,
    lineHeight: 1.62, color: 'var(--astryx-theme-citadel-parchment)'},
  eyebrow: {fontFamily: 'var(--font-family-code)', fontSize: 10, lineHeight: 1.4,
    letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--color-accent)'},
  step: {display: 'grid', gridTemplateColumns: '32px minmax(0, 1fr)', gap: 10,
    alignItems: 'start', padding: 12, borderRadius: 'var(--radius-element)',
    border: '1px solid var(--color-border)', background: 'var(--color-background-surface)'},
  stepNo: {display: 'grid', placeItems: 'center', width: 28, height: 28,
    borderRadius: 'var(--radius-full)', fontFamily: 'var(--font-family-code)',
    fontSize: 11, fontWeight: 700, color: 'var(--color-background-base)',
    background: 'var(--color-accent)'},
  demo: {padding: 14, borderLeft: '3px solid var(--astryx-theme-citadel-signal-amber)',
    borderRadius: 'var(--radius-element)', background: 'rgba(255,177,59,.07)'},
  label: {fontFamily: 'var(--font-family-code)', fontSize: 10,
    letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--color-text-primary)'},
  result: {display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto', gap: 12,
    alignItems: 'center'},
  metric: {fontFamily: 'var(--font-family-code)', fontSize: 25, fontWeight: 700,
    color: 'var(--color-accent)'},
  honesty: {display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto', gap: 18,
    alignItems: 'center', padding: 20, borderRadius: 'var(--radius-card)',
    border: '1px solid var(--astryx-theme-citadel-signal-amber)',
    background: 'rgba(255,177,59,.07)'},
};

const STYLES = `
.citadel-skip-link{position:fixed;z-index:1000;top:8px;left:8px;transform:translateY(-160%);padding:8px 12px;border-radius:var(--radius-element);background:var(--color-accent);color:var(--color-background-base);font-family:var(--font-family-heading);font-weight:700;text-decoration:none}
.citadel-skip-link:focus{transform:translateY(0)}
.project-intro-hero{position:relative;width:100%;aspect-ratio:8/3;max-height:300px;min-height:220px;overflow:hidden;border-bottom:1px solid var(--color-border);background:var(--color-background-surface)}
.project-intro-hero picture,.project-intro-hero img{position:absolute;inset:0;width:100%;height:100%}
.project-intro-hero img{object-fit:cover;object-position:center}
.project-intro-scrim{position:absolute;inset:0;background:linear-gradient(90deg,rgba(7,17,28,.97) 0%,rgba(7,17,28,.78) 34%,rgba(7,17,28,.18) 66%,rgba(7,17,28,.48) 100%)}
.project-intro-copy{position:relative;z-index:1;display:grid;align-content:center;gap:8px;width:min(760px,66%);height:100%;padding:22px 32px}
.project-intro-copy h1{margin:0;font-family:var(--font-family-heading);font-size:clamp(25px,3vw,40px);line-height:1.15;color:var(--color-text-primary);text-shadow:0 2px 16px rgba(7,17,28,.95)}
.project-intro-copy p{margin:0;max-width:610px;font-family:var(--font-family-body);font-size:14px;line-height:1.65;color:var(--astryx-theme-citadel-parchment);text-shadow:0 2px 12px rgba(7,17,28,.95)}
.project-intro-badges,.project-intro-actions{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.project-intro-first-screen{display:grid;gap:3px;margin:0;padding:0;list-style:none;font-family:var(--font-family-body);font-size:12px;line-height:1.42;color:var(--astryx-theme-citadel-parchment);text-shadow:0 2px 12px rgba(7,17,28,.95)}
.project-intro-first-screen strong{color:var(--color-text-primary)}
.project-intro-lanes{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
.project-intro-lifecycle{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:0;padding:0;list-style:none}
.project-intro-tech-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:0;padding:0;list-style:none}
.project-intro-tech-card{height:100%}
.project-intro-tech-head{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}
.project-intro-tech-name{font-family:var(--font-family-code);font-size:12px;line-height:1.55;color:var(--color-accent)}
.project-intro-trail{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;align-items:stretch}
.project-intro-trail-item{position:relative;display:grid;align-content:center;min-height:96px;padding:12px;border:1px solid var(--color-border);border-radius:var(--radius-element);background:var(--color-background-surface);font-family:var(--font-family-heading);font-size:12px;line-height:1.45;color:var(--color-text-primary)}
.project-intro-trail-item:not(:last-child)::after{content:'→';position:absolute;z-index:2;right:-13px;top:calc(50% - 9px);color:var(--color-accent);font-family:var(--font-family-code);font-weight:700}
.project-intro-status{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}
.project-intro-status>div{padding:14px;border:1px solid var(--color-border);border-radius:var(--radius-element);background:var(--color-background-surface)}
.project-intro-status strong{display:block;margin:8px 0 5px;font-family:var(--font-family-heading);font-size:14px;color:var(--color-text-primary)}
.project-intro-status p{margin:0;font-size:12px;line-height:1.55;color:var(--astryx-theme-citadel-parchment)}
.project-intro-tool-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.project-intro-tool-state{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.project-intro-tool-link{font-family:var(--font-family-heading);font-size:12px;font-weight:700;color:var(--astryx-theme-citadel-signal-amber);text-decoration:none}
.project-intro-tool-link:focus-visible,.project-intro-tools summary:focus-visible{outline:2px solid var(--color-accent);outline-offset:3px}
.project-intro-tools{padding:14px;border:1px solid var(--color-border);border-radius:var(--radius-element);background:var(--color-background-surface)}
.project-intro-tools summary{cursor:pointer;font-family:var(--font-family-heading);font-size:13px;font-weight:700;color:var(--color-text-primary)}
.project-intro-tools[open] summary{margin-bottom:12px}
@media(max-width:860px){
  .project-intro-copy{width:74%;padding:22px 24px}
  .project-intro-grid3,.project-intro-status,.project-intro-tool-grid{grid-template-columns:repeat(2,minmax(0,1fr))!important}
  .project-intro-trail{grid-template-columns:1fr}
  .project-intro-trail-item{min-height:auto}
  .project-intro-trail-item:not(:last-child)::after{content:'↓';right:auto;left:calc(50% - 5px);top:auto;bottom:-15px}
}
@media(max-width:720px){
  .project-intro-hero{display:flex;flex-direction:column;aspect-ratio:auto;max-height:none;min-height:0;overflow:visible}
  .project-intro-hero picture{position:relative;inset:auto;order:2;display:block;width:100%;height:auto;aspect-ratio:4/3;flex:none}
  .project-intro-hero picture img{position:absolute;inset:0;width:100%;height:100%;object-position:center}
  .project-intro-scrim{display:none}
  .project-intro-copy{position:relative;order:1;align-content:start;width:100%;height:auto;padding:24px 18px;background:var(--color-background-base)}
  .project-intro-copy h1{font-size:28px;text-shadow:none}
  .project-intro-copy p,.project-intro-first-screen{font-size:13px;text-shadow:none}
  .project-intro-lanes,.project-intro-grid2,.project-intro-grid3,.project-intro-status,.project-intro-tech-grid,.project-intro-tool-grid,.project-intro-lifecycle{grid-template-columns:1fr!important}
  .project-intro-page{padding:24px 16px 44px!important;gap:32px!important}
  .project-intro-honesty{grid-template-columns:1fr!important}
}
`;

function sectionHead(kicker, title, description, headingId, availability = '현재 제공') {
  return h('header', {style: C.sectionHead},
    h('p', {style: C.kicker}, kicker),
    availabilityBadge(availability),
    h('h2', {id: headingId, style: C.h2}, title),
    description ? h('p', {style: C.copy}, description) : null);
}

function availabilityBadge(label, variant = 'success') {
  return h('div', {style: {justifySelf: 'start'}},
    h(Badge, {variant, label}));
}

function infoCard(title, copy, badge, key) {
  return h(Card, {key, padding: 'lg', elevation: 'raised', style: C.card},
    h('div', {style: C.cardBody},
      badge ? availabilityBadge(badge, 'neutral') : null,
      h('h3', {style: C.cardTitle}, title),
      h(Text, {type: 'supporting', style: C.cardCopy}, copy)));
}

function step(number, title, copy, key) {
  return h('li', {key, style: C.step},
    h('span', {style: C.stepNo, 'aria-hidden': 'true'}, number),
    h('div', {style: C.cardBody},
      h('strong', {style: C.cardTitle}, title),
      h('span', {style: C.cardCopy}, copy)));
}

export function projectIntroductionStyles() {
  return h('style', {dangerouslySetInnerHTML: {__html: STYLES}});
}

export function projectIntroductionNav({urls}) {
  const link = (href, label, active = false) => h('a', {
    key: label,
    href,
    style: {padding: '6px 12px', borderRadius: 'var(--radius-element)',
      textDecoration: 'none', fontFamily: 'var(--font-family-heading)', fontSize: 12,
      fontWeight: 600, color: active ? 'var(--color-accent)' : 'var(--color-text-primary)',
      background: active ? 'rgba(69,224,111,.08)' : 'transparent'},
  }, label);
  return [
    link(urls.about, '프로젝트 소개', true),
    link(urls.page('citadel-gate'), '공간 둘러보기'),
    link(urls.page('council-chamber'), '조사 시작'),
    link('#capabilities', '현재 상태'),
  ];
}

export function projectIntroductionHero({urls}) {
  const smallHero = urls.asset('project-introduction-hero-960.png');
  const fullHero = urls.asset('project-introduction-hero.png');
  return h('div', {className: 'project-intro-hero'},
    h('picture', null,
      h('source', {
        media: '(max-width: 960px)',
        srcSet: `${smallHero} 960w`,
        sizes: '100vw',
      }),
      h('img', {
        src: fullHero,
        srcSet: `${fullHero} 1920w`,
        sizes: '100vw',
        alt: '조사 지시 두루마리에서 검증된 근거 지도를 지나 감사된 리포트로 이어지는 Citadel 안내 홀',
        width: 1920,
        height: 720,
        loading: 'eager',
        fetchPriority: 'high',
        decoding: 'async',
      })),
    h('div', {className: 'project-intro-scrim', 'aria-hidden': 'true'}),
    h('div', {className: 'project-intro-copy'},
      h('div', {className: 'project-intro-badges'},
        h(Badge, {variant: 'success', label: '현재 제공 · 결정론적 조사'}),
        h(Badge, {variant: 'warning', label: '실험용 서비스'})),
      h('h1', null, '질문이 결론이 되기까지,', h('br'), '모든 근거를 남긴다.'),
      h('ul', {className: 'project-intro-first-screen'},
        h('li', null, h('strong', null, '해결 · '), '흩어진 문서의 주장과 반증을 원문을 잃지 않고 비교합니다.'),
        h('li', null, h('strong', null, '차이 · '), '일반 검색과 챗봇이 답을 먼저 보여준다면, Citadel은 반대 근거와 변화 시점도 연결합니다.'),
        h('li', null, h('strong', null, '결과 · '), '조사 결과 · Evidence Graph · Provenance를 함께 남깁니다.')),
      h('div', {className: 'project-intro-actions'},
        h(Button, {variant: 'primary', size: 'sm', href: '#investigation-flow'},
          '조사 흐름 보기'),
        h(Button, {variant: 'secondary', size: 'sm', href: urls.page('council-chamber'),
          style: {color: 'var(--color-text-primary)', border: '1px solid var(--color-border)'}},
          '조사 시작'))));
}

export function valueTriad() {
  return h('section', {style: C.section, 'aria-labelledby': 'value-title'},
    h('header', {style: C.sectionHead},
      h('p', {style: C.kicker}, 'Why ORC CITADEL'),
      availabilityBadge('현재 제공'),
      h('h2', {id: 'value-title', style: C.h2}, '결론만 빠르게 주지 않습니다'),
      h('p', {style: C.copy}, '결론의 근거, 반증 가능성, 시간에 따른 변화를 함께 보존합니다.')),
    h('div', {className: 'project-intro-grid3', style: C.grid3},
      infoCard('증거를 잃지 않는다', '결과 문장에서 supports 관계와 source span을 거쳐 원문까지 되짚습니다.', 'Trail', 'trail'),
      infoCard('시간을 잃지 않는다', '상충하거나 뒤집힌 주장을 시간축 관계로 배열해 변화의 맥락을 보존합니다.', 'Timeline', 'time'),
      infoCard('불확실성을 숨기지 않는다', '확신도와 증거 수, 서로 다른 출처 수를 함께 보여 과신을 막습니다.', 'Confidence', 'confidence')));
}

export function exampleDirective() {
  return h('section', {style: C.section, 'aria-labelledby': 'example-title'},
    sectionHead('Example directive', '이런 질문을 하나의 조사로 묶습니다',
      '문서 수집부터 결론, 감사 흔적까지 한 작업 단위에서 이어집니다.',
      'example-title'),
    h(Card, {padding: 'lg', elevation: 'raised'},
      h('div', {style: C.cardBody},
        h('span', {style: C.eyebrow}, 'Directive · DEMO'),
        h('blockquote', {style: {margin: 0, fontFamily: 'var(--font-family-heading)',
          fontSize: 20, lineHeight: 1.55, color: 'var(--color-text-primary)'}},
        '“AI 반도체 공급망에서 향후 12개월 내 병목이 될 가능성이 가장 높은 구간은 어디이며, 그 판단을 뒤집을 반증은 무엇인가?”'),
        h('div', {style: C.demo},
          h('strong', {style: C.label}, '설명용 예시 · 실제 조사 결과 아님'),
          h('p', {style: {...C.cardCopy, marginTop: 6}},
            '아래 수치와 결론은 화면 구조를 설명하기 위한 예시이며 서비스가 계산한 실결과가 아닙니다.')))));
}

export function investigationFlow() {
  return h('section', {id: 'investigation-flow', style: C.section, 'aria-labelledby': 'flow-title'},
    h('header', {style: C.sectionHead},
      h('p', {style: C.kicker}, 'Investigation Flow · 조사 흐름'),
      availabilityBadge('현재 제공'),
      h('h2', {id: 'flow-title', style: C.h2}, '자료 처리와 조사를 나란히 추적합니다'),
      h('p', {style: C.copy},
        '현재 조사는 Citadel에 이미 축적된 근거를 한 번 read-only로 확인합니다. PLAN·SYNTHESIZE·AUDIT는 독립 실행 단계가 아니라 RUN 전후에 남는 진행·감사 marker입니다.')),
    h('div', {className: 'project-intro-lanes'},
      h(Card, {padding: 'lg', elevation: 'raised'},
        h('div', {style: C.cardBody},
          availabilityBadge('Evidence lane · 현재 제공'),
          h('ol', {style: {margin: 0, padding: 0, listStyle: 'none'}},
            step('01', '자료 수집', '원문과 출처 메타데이터를 함께 받습니다.', 'e1'),
            step('02', '원문 보존', '수집 시점의 원본을 이후 감사에 남깁니다.', 'e2'),
            step('03', '정규화·중복 보정', '동일 문서와 표현 차이를 정돈합니다.', 'e3'),
            step('04', 'supports 원문 연결', 'Claim이 근거로 삼은 source span을 연결합니다.', 'e4'),
            step('05', '시간축 관계 지도', '주장 간 선후와 변화를 시간 순서로 배열합니다.', 'e5')))),
      h(Card, {padding: 'lg', elevation: 'raised'},
        h('div', {style: C.cardBody},
          availabilityBadge('Investigation lane · 현재 제공'),
          h('ol', {style: {margin: 0, padding: 0, listStyle: 'none'}},
            step('01', '접수 · queued', '질문과 범위를 접수하고 다시 시작해도 이어지는 조사 기록을 만듭니다.', 'i1'),
            step('02', 'PLAN marker', '하위 질문과 아는 것·모르는 것을 RUN 전에 기록합니다.', 'i2'),
            step('03', 'RUN', '저장된 관계 지도와 문서에서 근거·반증·공백을 한 번 확인합니다.', 'i3'),
            step('04', 'SYNTHESIZE marker', '찾은 근거 범위에서 결론을 정리했다는 기록을 남깁니다.', 'i4'),
            step('05', 'AUDIT marker', '문장이 원문까지 연결되는지 검사하고 실패를 표시하되 완료를 막지는 않습니다.', 'i5'),
            step('06', '현재 JSON 결과', '결론·공백·반증·감사 결과를 조사 기록에 저장합니다.', 'i6'),
            step('NEXT', 'REPORT → HTML → Ledger', '계획 · 미구현: 사람이 읽는 보고서와 이력 장부입니다.', 'i7'))))),
    h(Card, {padding: 'lg', elevation: 'raised'},
      h('div', {style: C.cardBody},
        availabilityBadge('현재 조사 상태'),
        h('h3', {style: C.cardTitle}, '접수부터 완료·실패·취소까지 기록합니다'),
        h('ol', {className: 'project-intro-lifecycle', 'aria-label': '조사 상태 흐름'},
          step('01', '접수됨 · queued', 'worker가 가져갈 때까지 기다립니다.', 'queued'),
          step('02', '조사 중 · running', '기존 근거를 읽어 조사와 감사를 수행합니다.', 'running'),
          step('03', '완료 · completed', 'JSON 결과와 audit trace를 다시 조회할 수 있습니다.', 'completed')),
        h('p', {style: C.cardCopy}, '조사 중에는 실패 · failed 또는 취소 · cancelled로 끝날 수 있으며 그 상태도 기록에 남습니다.'))));
}

export function technologyMap() {
  const stages = [
    {
      phase: '수집·원본 보존',
      technology: '설계 스택 · MinIO + Parquet',
      availability: '현재 사용',
      tone: 'success',
      description: 'Python 커넥터가 허용된 자료를 수집합니다. 현재 기본 raw 저장은 source별 불변 Parquet shard이며, MinIO 객체 backend도 같은 원문 보존 규칙으로 사용할 수 있습니다.',
    },
    {
      phase: '정규화·중복 보정',
      technology: 'Python · Parquet · DuckDB',
      availability: '현재 사용',
      tone: 'success',
      description: '문서를 문장·구간 단위로 정리하고 중복 계보를 계산합니다. DuckDB는 Parquet를 직접 읽어 로컬 분석과 read-only 점검에 사용합니다.',
    },
    {
      phase: '작업 큐·감사 원장',
      technology: 'PostgreSQL',
      availability: '현재 사용',
      tone: 'success',
      description: '조사, 실행 단계, 그래프 변경 원장을 영속화합니다. 여러 worker가 같은 작업을 중복 실행하지 않도록 작업 차례도 조정합니다.',
    },
    {
      phase: '검색 후보 찾기',
      technology: 'OpenSearch',
      availability: '실험 · 파생 인덱스',
      tone: 'warning',
      description: '문장과 Claim의 BM25·벡터 검색을 위한 파생 인덱스입니다. 정본이 아니며 curated 데이터에서 전량 다시 만들 수 있습니다.',
    },
    {
      phase: '시간축 관계 지도',
      technology: 'Neo4j Community',
      availability: '현재 사용 · 파생 그래프',
      tone: 'success',
      description: '엔터티와 관계를 War Table이 탐색할 수 있는 그래프로 투영합니다. PostgreSQL mutation log를 replay해 재구축하므로 Neo4j 자체가 정본은 아닙니다.',
    },
    {
      phase: '조사 실행·응답',
      technology: 'Python worker · FastAPI · 선택적 LLM',
      availability: '현재 사용',
      tone: 'success',
      description: 'worker가 기존 근거를 read-only로 PLAN·RUN·SYNTHESIZE·AUDIT합니다. LLM을 켜도 문장 표현만 보조하며 결론과 근거 계산은 바꾸지 않습니다.',
    },
    {
      phase: '운영 관측',
      technology: 'Grafana · DuckDB UI',
      availability: '실험 도구',
      tone: 'warning',
      description: 'Grafana는 PostgreSQL의 run metric과 운영 신호를 보고, DuckDB UI는 export된 Parquet snapshot을 read-only로 살펴봅니다.',
    },
  ];

  return h('section', {style: C.section, 'aria-labelledby': 'technology-title'},
    h('header', {style: C.sectionHead},
      h('p', {style: C.kicker}, 'Technology Map · 기술 활용'),
      h('h2', {id: 'technology-title', style: C.h2}, '각 기술은 조사 흐름의 한 역할만 맡습니다'),
      h('p', {style: C.copy},
        '저장 원본과 운영 로그가 정본이며 검색 인덱스와 그래프는 다시 만들 수 있는 파생물입니다. 현재 쓰는 기술과 규모가 커진 뒤의 후보를 분리합니다.')),
    h('ol', {className: 'project-intro-tech-grid'},
      stages.map((stage, index) => h('li', {key: stage.phase},
        h(Card, {padding: 'lg', elevation: 'raised', className: 'project-intro-tech-card'},
          h('div', {style: C.cardBody},
            h('div', {className: 'project-intro-tech-head'},
              h('span', {style: C.stepNo, 'aria-hidden': 'true'}, String(index + 1).padStart(2, '0')),
              h(Badge, {variant: stage.tone, label: stage.availability})),
            h('h3', {style: C.cardTitle}, stage.phase),
            h('code', {className: 'project-intro-tech-name'}, stage.technology),
            h('p', {style: C.cardCopy}, stage.description)))))),
    h(Card, {padding: 'lg', elevation: 'raised'},
      h('div', {style: C.cardBody},
        h('div', {className: 'project-intro-tech-head'},
          h(Badge, {variant: 'neutral', label: '현재 미사용 · 확장 후보'}),
          h('code', {className: 'project-intro-tech-name'}, 'Apache Iceberg · S3 · Kafka/Redpanda · Ray/Spark')),
        h('h3', {style: C.cardTitle}, '측정된 병목이 생길 때만 확장합니다'),
        h('p', {style: C.cardCopy},
          '현재는 Parquet와 DuckDB, PostgreSQL queue로 충분합니다. 100만 문서 규모의 증분 처리, 수천만 row 또는 스키마 진화가 실제 병목이 될 때 S3 + Apache Iceberg를 검토하고, queue throughput과 batch 재처리 SLO가 한계를 넘을 때 Kafka/Redpanda와 Ray/Spark로 승격합니다.'))));
}

export function evidenceTrail() {
  const items = [
    ['결과 문장', '사람이 읽는 현재 결론'],
    ['Claim', '결론을 이루는 주장'],
    ['Supports evidence', '주장을 지지하는 증거'],
    ['Source span', '근거가 된 원문 구간'],
    ['원문', '보존된 문서'],
  ];
  return h('section', {style: C.section, 'aria-labelledby': 'trail-title'},
    h('header', {style: C.sectionHead},
      h('p', {style: C.kicker}, 'Provenance · 근거 추적'),
      availabilityBadge('현재 제공 · supports only'),
      h('h2', {id: 'trail-title', style: C.h2}, '결과 문장에서 원문까지 되짚습니다'),
      h('p', {style: C.copy},
        '현재 제공 · supports only. contradicts 표현은 화면 설명에만 남아 있으며 uncertain·superseded 상태는 아직 제공하지 않습니다.')),
    h('div', {className: 'project-intro-trail'},
      items.map(([title, copy]) => h('div', {key: title, className: 'project-intro-trail-item'},
        h('strong', null, title), h('span', {style: {...C.cardCopy, marginTop: 5}}, copy)))));
}

export function resultTriad() {
  return h('section', {style: C.section, 'aria-labelledby': 'result-title'},
    sectionHead('Output · 결과', '결론, 관계, 흔적을 한 화면에서 읽습니다',
      'confidence는 진실 확률이 아니라 현재 근거 구조의 평가입니다.',
      'result-title'),
    h('div', {className: 'project-intro-grid3', style: C.grid3},
      h(Card, {padding: 'lg', elevation: 'raised', style: C.card},
        h('div', {style: C.cardBody},
          availabilityBadge('현재 제공 · Investigation Result'),
          h('h3', {style: C.cardTitle}, '현재 결론'),
          h('div', {style: C.result},
            h('p', {style: C.cardCopy}, '검토 우선순위가 가장 높은 병목 후보'),
            h('strong', {style: C.metric}, '0.61')),
          h('p', {style: C.cardCopy}, '0.61 · 근거 구조 평가 · 진실 확률 아님'),
          h('p', {style: C.cardCopy}, '근거 7건 · 서로 다른 출처 2개 · 현재 자료 범위 63%'),
          h('p', {style: C.cardCopy}, '계산 근거 · supports 수, 출처 독립성, 질문 coverage를 함께 봅니다.'),
          h('p', {style: C.cardCopy}, '미해결 질문 · 반대 증거 1건의 원문 연결을 더 확인해야 합니다.'))),
      infoCard('War Table', '주장과 증거의 관계를 시간축 지도에서 비교합니다.', '현재 제공 · 관계 지도', 'war'),
      infoCard('Trail', '결론에서 source span과 보존 원문으로 이동합니다.', '현재 제공 · 감사 흔적', 'result-trail')),
    h('div', {style: C.demo},
      h('strong', {style: C.label}, '설명용 예시 · 실제 조사 결과 아님'),
      h('p', {style: {...C.cardCopy, marginTop: 6}},
        '검증되지 않음 · audit에서 원문 연결 실패가 표시된 문장도 현재 결과에는 남을 수 있습니다.')));
}

export function capabilityMatrix() {
  const states = [
    ['현재 제공', '재시작 후에도 이어지는 조사', 'queued·running·completed 상태와 JSON 결과·audit trace를 다시 조회합니다.'],
    ['실험', '선택적 LLM 문장 표현 보조', '확인된 근거 안에서만 표현을 돕고 결론과 근거 계산은 바꾸지 않습니다.'],
    ['계획 · 미구현', 'HTML 보고서와 Ledger', 'REPORT → 결정적 HTML → 과거 조사 목록은 아직 열거나 내려받을 수 없습니다.'],
    ['제품 방향', '새 근거에 따른 결론 변화 알림', 'Continuous Campaign과 Signal Spire가 중요한 변화를 기록하고 알리는 방향입니다.'],
  ];
  return h('section', {id: 'capabilities', style: C.section, 'aria-labelledby': 'capability-title'},
    h('header', {style: C.sectionHead},
      h('p', {style: C.kicker}, 'Now / Next'),
      h('h2', {id: 'capability-title', style: C.h2}, '현재와 다음을 섞지 않습니다'),
      h('p', {style: C.copy}, '구현 상태는 배지와 평문을 함께 써서 색만으로 구분하지 않습니다.')),
    h('div', {className: 'project-intro-status'},
      states.map(([state, title, copy], index) => h('div', {key: state},
        h(Badge, {variant: index === 0 ? 'success' : index === 1 ? 'warning' : 'neutral', label: state}),
        h('strong', null, title),
        h('p', null, copy)))));
}

const TOOL_GROUPS = {
  promoted: [
    {
      id: 'grafana',
      title: 'Grafana',
      description: '파이프라인 run metric과 SLO를 보는 read-only dashboard입니다. 데이터가 아직 없으면 No data로 보일 수 있습니다.',
      warning: '로컬 접속 또는 SSH tunnel이 필요합니다.',
    },
    {
      id: 'duckdb-ui',
      title: 'DuckDB UI',
      description: '내보낸 Parquet snapshot을 read-only로 살펴봅니다. snapshot 반영이 늦거나 remote UI asset network가 필요할 수 있습니다.',
      warning: '반드시 localhost로 접속해야 하며, remote 환경에서는 SSH tunnel이 필요합니다.',
    },
  ],
  advanced: [
    {
      id: 'neo4j',
      title: 'Neo4j Browser',
      description: '관계 그래프를 직접 탐색하는 고급 도구입니다.',
      warning: '로그인과 7474·7687 tunnel이 필요합니다. 제공 계정에 따라 write가 가능할 수 있습니다.',
    },
    {
      id: 'minio',
      title: 'MinIO Console',
      description: '객체 저장소를 점검하는 고급 도구입니다.',
      warning: 'credentials와 write에 주의하십시오. 현재 prod nightly raw는 filesystem mirror에 있어 Console bucket이 비어 있을 수 있습니다.',
    },
    {
      id: 'opensearch',
      title: 'OpenSearch diagnostic',
      description: 'dashboard가 아니라 cluster health를 읽는 GET 진단입니다.',
      warning: 'base compose는 security plugin이 꺼져 있어 tunnel과 API가 read-only가 아닙니다.',
    },
  ],
};

function toolState(tool, mode, runtime) {
  if (mode === 'demo') {
    return h(React.Fragment, null,
      h(Badge, {variant: 'neutral', label: 'DEMO · 설명용 상태'}),
      h('p', {style: C.cardCopy}, '실제 연결 상태 아님'));
  }
  if (mode === 'loading') {
    return h('p', {style: C.cardCopy}, '상태 확인 중');
  }
  if (mode === 'error') {
    return h('p', {style: C.cardCopy}, '상태 확인 불가');
  }
  if (!runtime?.reachable || !runtime.href) {
    return h('p', {style: C.cardCopy}, '미가동 · local compose 또는 SSH tunnel 필요');
  }
  return h(React.Fragment, null,
    h('div', {className: 'project-intro-tool-state'},
      h(Badge, {variant: 'success', label: 'viewer에서 TCP 연결됨'}),
      h('a', {
        className: 'project-intro-tool-link',
        href: runtime.href,
        target: '_blank',
        rel: 'noopener noreferrer',
      }, `${tool.title} 새 창에서 열기 →`)),
    h('p', {style: C.cardCopy},
      '이 표시는 UI 자산·데이터 준비·인증·브라우저 tunnel 개통을 보장하지 않습니다.'));
}

function toolCard(tool, mode, runtime) {
  return h(Card, {
    key: tool.id,
    padding: 'lg',
    elevation: 'raised',
    style: C.card,
  }, h('article', {style: C.cardBody},
    h('h3', {style: C.cardTitle}, tool.title),
    toolState(tool, mode, runtime),
    h('p', {style: C.cardCopy}, tool.description),
    h('p', {style: C.cardCopy}, h('strong', null, '주의 · '), tool.warning)));
}

export function experimentalTools({urls, toolState: state} = {}) {
  const mode = ['loading', 'ready', 'error'].includes(state?.status)
    ? state.status : 'demo';
  const components = Array.isArray(state?.components) ? state.components : [];
  const byId = new Map(components.map((component) => [component.id, component]));
  const cards = (tools) => tools.map((tool) => toolCard(tool, mode, byId.get(tool.id)));

  return h('section', {style: C.section, 'aria-labelledby': 'tools-title'},
    h('header', {style: C.sectionHead},
      h('p', {style: C.kicker}, 'Experimental services'),
      availabilityBadge('실험', 'warning'),
      h('h2', {id: 'tools-title', style: C.h2}, '운영 도구는 선택적으로 확인합니다'),
      h('p', {style: C.copy},
        '프로젝트 이해에는 운영 도구가 필요하지 않습니다. Watchtower에서 전체 구성요소를 먼저 확인하십시오.')),
    h(Card, {padding: 'lg', elevation: 'raised'},
      h('div', {style: C.cardBody},
        availabilityBadge('기본 진입점', 'warning'),
        h('h3', {style: C.cardTitle}, 'Watchtower · 실험 시스템 상태'),
        h('p', {style: C.cardCopy}, '수집 상태와 모든 구성요소의 도달성 실측을 한곳에서 봅니다.'),
        h('div', null,
          h(Button, {variant: 'primary', size: 'sm', href: urls.page('watchtower')},
            '실험 시스템 상태 보기')))),
    mode === 'error'
      ? h('p', {role: 'status', style: C.cardCopy}, '운영 도구 상태를 확인할 수 없음')
      : null,
    h('div', {className: 'project-intro-tool-grid'}, cards(TOOL_GROUPS.promoted)),
    h('details', {className: 'project-intro-tools'},
      h('summary', null, '고급 실험 도구 · 인증과 쓰기 가능성 주의'),
      h('div', {className: 'project-intro-grid3', style: C.grid3},
        cards(TOOL_GROUPS.advanced))));
}

export function honestyStrip({urls}) {
  return h('section', {className: 'project-intro-honesty', style: C.honesty, 'aria-labelledby': 'honesty-title'},
    h('div', {style: C.cardBody},
      availabilityBadge('현재 제공 · Scope & Safety', 'warning'),
      h('h2', {id: 'honesty-title', style: C.h2}, '읽을 수 있는 근거만으로 판단하십시오'),
      h('p', {style: C.copy},
        '현재 서비스는 저장된 입력과 supports 근거를 다룹니다. 실시간 웹 전체를 포괄하지 않으며, ',
        '법률·의료·투자 결정을 자동으로 대신하지 않습니다. 중요한 결정은 원문과 적절한 전문가 검토를 거치십시오.')),
    h(Button, {variant: 'primary', href: urls.page('council-chamber')},
      'Council에서 조사 시작'));
}

export function projectIntroduction({urls, toolState}) {
  return h('main', {id: 'main-content', tabIndex: -1, className: 'project-intro-page', style: C.page},
    valueTriad(),
    exampleDirective(),
    investigationFlow(),
    technologyMap(),
    evidenceTrail(),
    resultTriad(),
    capabilityMatrix(),
    experimentalTools({urls, toolState}),
    honestyStrip({urls}));
}
