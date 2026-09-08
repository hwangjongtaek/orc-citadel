/**
 * Citadel Gate · 브리핑 대시보드 (specs/ui-overhaul-astryx TS-3).
 *
 * 처음 보는 사람이 3클릭 이내에 "지금 무슨 결론이 있고 근거가 무엇인지"에
 * 도달하는 브리핑 시작점: KPI → 결론 카드(딥링크) → 최근 변화 피드.
 * New Campaign 은 쓰기 개념이라 비활성 자리만 둔다 (read-only §3-3).
 */

import {LayoutContent} from '@astryxdesign/core/Layout';
import {shell, PRIMARY_SPACES, SECONDARY_SPACES} from '../shell.mjs';
import {
  h, Card, Badge, Text, Button, sectionLabel, confidence, statTile, id, grid,
} from '../ui.mjs';

export const title = 'Citadel Gate · 브리핑 — Orc Citadel';

/** 지식 현황 KPI — 실측 규모(2026-09 L3 재적재)를 반영한 정직한 스케일. */
const KPI = [
  {value: '105,252', label: 'Documents · raw', note: 'normalized 전량 · segments 823,629', tone: 'good'},
  {value: '25', label: 'Entities', note: '결정적 ER — exact match 병합만'},
  {value: '722', label: 'Claims · promoted', note: 'dup 528 클러스터 · 독립성 보정', tone: 'good'},
  {value: '+38', label: '최근 24h 수집', note: 'nightly 07:07 · RSS + arXiv'},
];

/** 주요 subject 결론 — confidence 는 값+근거+독립 출처 병기 (단일 게이지 금지). */
const CONCLUSIONS = [
  {subject: 'B사 — HBM 공급 능력 확대', modality: 'fact', tone: 'success',
   statement: 'SEC 10-K 등 독립 출처 5건이 2024–2025 증설 실행을 확인한다. 이전 결론 1건은 superseded.',
   conf: '0.83', ev: 14, indep: 5, cid: 'sub-b-hbm'},
  {subject: 'A사 — AI 가속기 공급망 다변화', modality: 'asserted', tone: 'warning',
   statement: '신규 공급 계약 공시 3건이 다변화 주장을 지지하나, 물량 기준 B사 의존은 유지 — 반증 1건 수집됨.',
   conf: '0.61', ev: 7, indep: 2, cid: 'sub-a-diversify'},
  {subject: 'C사 — 데이터센터 증설 착공', modality: 'asserted', tone: 'warning',
   statement: '발표 대비 착공 확인은 1건 — 지자체 인허가 공고가 지지, 부지 계약 공시는 미확인.',
   conf: '0.44', ev: 5, indep: 3, cid: 'sub-c-dc'},
];

const MODALITY = {fact: 'success', asserted: 'warning', opinion: 'neutral', prediction: 'purple'};

/** 최근 변화 — Signal Spire 피드의 상위 3건 요약. */
const CHANGES = [
  ['Confidence Δ', 'success', 'B사 HBM 확대', '0.79 → 0.83',
   'SEC 10-K 독립 출처 +1 — 결론 상향', 'evd-4021'],
  ['Contradiction', 'error', 'A사 단일 의존 주장', '반증 후보 수집',
   '보도자료 1건이 contradicts 후보로 격리 — 판정 대기', 'evd-789'],
  ['New Evidence', 'warning', 'C사 착공', '근거 +1 (독립)',
   '지자체 인허가 공고 — asserted 유지, coverage 상승', 'evd-3377'],
];

const PROCESS = [
  ['char-scout.png', 'Scouts', '근거 수집'],
  ['char-seer.png', 'Seers · Council', '그래프 조사 · 반증'],
  ['char-warchief.png', '보고서', '근거로 답'],
];

function conclusionCard({subject, modality, tone, statement, conf, ev, indep, cid}) {
  const link = (href, label) =>
    h('a', {href, style: {fontFamily: 'var(--font-family-heading)', fontSize: 11.5,
      fontWeight: 600, color: 'var(--color-accent)', textDecoration: 'none'}}, label);
  return h(Card, {key: cid}, h('div', {style: {padding: 4}},
    h('div', {style: {display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap'}},
      h(Badge, {variant: MODALITY[modality] || 'neutral', label: modality}), id(cid)),
    h('div', {style: {marginTop: 8, fontFamily: 'var(--font-family-heading)',
      fontSize: 14, fontWeight: 600, color: 'var(--color-text-primary)'}}, subject),
    h('div', {style: {marginTop: 6, minHeight: 60}},
      h(Text, {type: 'supporting'}, statement)),
    h('div', {style: {marginTop: 10}}, confidence(conf, ev, indep)),
    h('div', {style: {display: 'flex', gap: 16, marginTop: 12}},
      link('./war-table.html', 'War Table에서 보기 →'),
      link('./hall-of-witnesses.html', '근거 열람 · Witnesses →'))));
}

function changeCard([kind, tone, subject, delta, note, ref]) {
  return h(Card, {key: ref}, h('div', {style: {padding: 4}},
    h('div', {style: {display: 'flex', alignItems: 'center',
      justifyContent: 'space-between', gap: 8}},
      h(Badge, {variant: tone, label: kind}), id(ref)),
    h('div', {style: {marginTop: 8, display: 'flex', alignItems: 'baseline', gap: 8,
      flexWrap: 'wrap'}},
      h('span', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 13,
        fontWeight: 600, color: 'var(--color-text-primary)'}}, subject),
      h('span', {style: {fontFamily: 'var(--font-family-code)', fontSize: 12,
        color: 'var(--color-accent)'}}, delta)),
    h('div', {style: {marginTop: 4}}, h(Text, {type: 'supporting'}, note)),
    h('div', {style: {marginTop: 8}},
      h('a', {href: './signal-spire.html', style: {fontFamily: 'var(--font-family-heading)',
        fontSize: 11.5, fontWeight: 600, color: 'var(--color-accent)',
        textDecoration: 'none'}}, 'Signal Spire에서 보기 →'))));
}

/** New Campaign — 쓰기라 범위 밖. 자리는 두되 비활성 + read-only 표시 (TS-3). */
const newCampaign = h(Card, {}, h('div', {style: {padding: 4, opacity: .75}},
  h('div', {style: {display: 'flex', alignItems: 'center',
    justifyContent: 'space-between', gap: 12, flexWrap: 'wrap'}},
    h('div', {},
      h(Text, {}, 'New Campaign · 새 조사 요청'),
      h('div', {style: {marginTop: 4}},
        h(Text, {type: 'supporting'},
          '자연어 질문 → Council 이 계획을 세우고 Scouts 가 근거를 수집'))),
    h(Badge, {variant: 'neutral', label: 'read-only 프로토타입 · 비활성'})),

  h('div', {style: {display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap',
    margin: '16px 0'}},
    ...PROCESS.flatMap(([art, name, role], i) => [
      i ? h('span', {key: `a${i}`, style: {color: 'var(--color-text-secondary)'}}, '→') : null,
      h('div', {key: name, style: {display: 'flex', alignItems: 'center', gap: 8}},
        h('img', {src: `./assets/${art}`, alt: '', width: 40, height: 40,
          style: {imageRendering: 'pixelated', borderRadius: 'var(--radius-inner)'}}),
        h('div', {},
          h('div', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 12,
            fontWeight: 600, color: 'var(--color-text-primary)'}}, name),
          h(Text, {type: 'supporting'}, role)))])),

  h('div', {style: {padding: '10px 12px', background: 'var(--color-background-muted)',
    borderRadius: 'var(--radius-element)', color: 'var(--color-text-secondary)',
    fontSize: 13}},
    '예) 2024년 이후 A사의 AI 가속기 공급망 다변화가 실제로 진행되었는가?'),

  h('div', {style: {display: 'flex', alignItems: 'center',
    justifyContent: 'space-between', gap: 12, marginTop: 14, flexWrap: 'wrap'}},
    h(Text, {type: 'supporting'},
      '조사 실행은 read-only 불변식(§3-3) 개정 전까지 비활성 — 지금은 이미 축적된 지식을 조회합니다.'),
    h(Button, {variant: 'secondary'}, '조사 실행 (비활성)'))));

function quickEntry(spaces) {
  return grid(4, 16, ...spaces.map(([slug, name, role]) =>
    h('a', {key: slug, href: `./${slug}.html`, style: {textDecoration: 'none'}},
      h(Card, {}, h('div', {style: {padding: 4}},
        h('div', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 13,
          fontWeight: 600, color: 'var(--color-text-primary)'}}, name),
        h('div', {style: {marginTop: 4}}, h(Text, {type: 'supporting'}, role)))))));
}

const body = h(LayoutContent, {padding: 4},
  // 브랜드 블록 — 신규 lockup 로고 도착 시 crest-hero + 텍스트 워드마크를
  // logo-mark / logo-title 분리 자산으로 교체한다 (FR-4, 반입 대기).
  h('div', {style: {display: 'flex', alignItems: 'center', gap: 16, marginBottom: 20}},
    h('img', {src: './assets/crest-hero.png', alt: 'Orc Citadel 문장', width: 96, height: 96,
      style: {imageRendering: 'pixelated'}}),
    h('div', {},
      h('div', {style: {fontFamily: 'var(--astryx-theme-citadel-font-display)',
        fontSize: 34, letterSpacing: '.12em', color: 'var(--color-text-primary)'}},
        'ORC CITADEL'),
      h('div', {style: {marginTop: 4}},
        h(Text, {type: 'supporting'}, 'The Camp works. The Citadel remembers.')),
      h('div', {style: {marginTop: 2}},
        h(Text, {type: 'supporting'},
          'Temporal Evidence Intelligence · 시간을 기억하는 증거 정보 본부')))),

  grid(4, 16, ...KPI.map(k => h('div', {key: k.label}, statTile(k)))),

  sectionLabel('Conclusions · 주요 결론 — subject 단위 현재 결론과 근거'),
  grid(3, 16, ...CONCLUSIONS.map(conclusionCard)),

  sectionLabel('Recent Changes · 최근 변화 — confidence 델타 · 반증 · 신규 근거'),
  grid(3, 16, ...CHANGES.map(changeCard)),

  sectionLabel('New Campaign · 새 조사 (비활성)'),
  newCampaign,

  sectionLabel('Citadel · 공간 빠른 진입'),
  quickEntry(PRIMARY_SPACES),
  h('div', {style: {marginTop: 12, marginBottom: 6}},
    h(Text, {type: 'supporting'}, '운영 · 감사')),
  quickEntry(SECONDARY_SPACES));

export const render = () => shell({
  route: 'citadel-gate',
  eyebrow: 'Citadel Gate · Briefing',
  context: '브리핑 · Home',
  title: 'Citadel Gate · 브리핑',
  subtitle: '지금 무슨 결론이 있고, 그 근거는 무엇인가 — 3클릭 이내',
  hero: 'gate-hero.png',
  slots: {content: body},
});
