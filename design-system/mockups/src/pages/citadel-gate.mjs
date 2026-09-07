/** Citadel Gate · 본부 — New Campaign | Campaigns | Watchtower 요약 | 공간 빠른 진입. */

import {LayoutContent} from '@astryxdesign/core/Layout';
import {shell, SPACES} from '../shell.mjs';
import {
  h, Card, Badge, Text, Button, sectionLabel, coverage, statTile, id, grid,
} from '../ui.mjs';

export const title = 'Citadel Gate · 본부 — Orc Citadel';

const PROCESS = [
  ['char-scout.png', 'Scouts', '근거 수집'],
  ['char-seer.png', 'Seers · Council', '그래프 조사 · 반증'],
  ['char-warchief.png', '보고서', '근거로 답'],
];

const SCOPE = [
  ['기간', '2024-01 → now'], ['지역', '글로벌 · US·KR·TW'],
  ['source_type', '공시·보도자료·뉴스'], ['조사 깊이', '표준 (3-hop)'],
];

const CAMPAIGNS = [
  ['Running', 'camp-0142', 'running',
    '2024년 이후 A사의 AI 가속기 공급망 다변화가 실제로 진행되었는가 — 발표 대 실제 계약·공시 구분',
    72, '0.61', 7, 2, '반증 발견', 'B사 단일 의존 주장에 모순되는 보도자료(ev-789) 수집됨', 'error'],
  ['Running', 'camp-0137', 'running',
    'C사의 신규 데이터센터 증설 발표가 실제 착공·부지 계약으로 이어졌는지 검증',
    48, '0.44', 5, 3, '신규 근거', '지자체 인허가 공고 1건이 착공 주장을 지지 (독립 출처 +1)', 'success'],
  ['Paused', 'camp-0119', 'paused',
    '규제 변경(수출 통제)이 A사·C사 공급 계약에 직·간접으로 영향을 미쳤는가',
    35, '0.29', 4, 1, '일시중지', '독립 출처 1건 · 근거 부족으로 사용자 검토 대기', 'warning'],
  ['Done', 'camp-0103', 'done',
    'B사의 HBM 공급 능력 확대 주장이 2024–2025 공시 실적으로 확인되는지 종합',
    91, '0.83', 14, 5, '결론 확정', 'SEC 10-K 등 독립 출처 5건이 확대 주장을 지지', 'success'],
  ['Running', 'camp-0148', 'running',
    'A사–C사 간 장기 공급 계약(LTA) 존재 여부와 발효 시점의 bitemporal 정합성 검증',
    57, '0.52', 6, 2, '엔티티 미확정', '"C사?" 후보 1건 격리(quarantine) 중 · 해소 대기', 'purple'],
  ['Paused', 'camp-0091', 'paused',
    '데이터센터 전력 조달(PPA) 발표가 실제 계약 체결로 이어졌는지 국가별 비교',
    22, '0.18', 3, 1, 'source 대기', '신규 공시 freshness 낮음 · Scout 재수집 예약됨', 'warning'],
];

const WATCH = [
  {value: '38', label: 'Sources active', note: '/ 41 등록 · 3 유휴', tone: 'good'},
  {value: '96', unit: '%', label: 'Freshness', note: '중앙값 지연 4.2h', tone: 'good'},
  {value: '1,284', label: 'Ingestion backlog', note: 'docs 대기 · +6%/1h'},
  {value: '7', label: 'Quarantine', note: '엔티티 해소·검토 대기', tone: 'warn'},
];

const STATE = {running: 'success', paused: 'warning', done: 'neutral'};

const newCampaign = h(Card, {}, h('div', {style: {padding: 4}},
  h('div', {style: {display: 'flex', alignItems: 'center',
    justifyContent: 'space-between', gap: 12, flexWrap: 'wrap'}},
    h('div', {},
      h(Text, {}, 'New Campaign · 새 조사 요청'),
      h('div', {style: {marginTop: 4}},
        h(Text, {type: 'supporting'},
          '자연어 질문 → Council 이 계획을 세우고 Scouts 가 근거를 수집'))),
    h(Badge, {variant: 'neutral', label: 'Council 대기'})),

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

  h('div', {style: {marginTop: 10}}, h(Text, {type: 'label'}, 'Scope · 조사 범위 (선택)')),
  h('div', {style: {display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 6}},
    SCOPE.map(([k, v]) => h(Badge, {key: k, variant: 'neutral', label: `${k} · ${v} ▾`}))),

  h('div', {style: {display: 'flex', alignItems: 'center',
    justifyContent: 'space-between', gap: 12, marginTop: 14, flexWrap: 'wrap'}},
    h(Text, {type: 'supporting'},
      '발표와 실제 집행을 구분하고 반증도 함께 수집합니다. 실행 전 계획을 Council Chamber 에서 검토할 수 있습니다.'),
    h(Button, {variant: 'primary'}, '조사 실행'))));

function campaignCard([state, cid, tone, question, cov, conf, ev, indep, evtLabel, evtNote, evtTone]) {
  return h(Card, {key: cid}, h('div', {style: {padding: 4}},
    h('div', {style: {display: 'flex', alignItems: 'center', gap: 8}},
      h(Badge, {variant: STATE[tone], label: state}), id(cid)),
    h('div', {style: {marginTop: 8, minHeight: 54}},
      h(Text, {type: 'supporting'}, question)),
    h('div', {style: {marginTop: 8}},
      h(Text, {type: 'label'}, 'Evidence coverage'),
      h('div', {style: {marginTop: 4}}, coverage(cov, cov < 50 ? 'warn' : null))),
    h('div', {style: {display: 'flex', gap: 14, marginTop: 10}},
      ...[[conf, 'Confidence'], [String(ev), '근거'], [String(indep), '독립 출처']]
        .map(([v, c]) => h('div', {key: c},
          h('div', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 15,
            fontWeight: 600, color: 'var(--color-text-primary)'}}, v),
          h('div', {style: {fontSize: 9.5, letterSpacing: '.06em',
            textTransform: 'uppercase', color: 'var(--color-text-secondary)'}}, c)))),
    h('div', {style: {marginTop: 10, display: 'flex', gap: 8, alignItems: 'flex-start'}},
      h(Badge, {variant: evtTone, label: evtLabel}),
      h(Text, {type: 'supporting'}, evtNote))));
}

const body = h(LayoutContent, {padding: 4},
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

  newCampaign,

  sectionLabel('Campaigns · 진행 중 조사'),
  grid(3, 16, ...CAMPAIGNS.map(campaignCard)),

  sectionLabel('Watchtower · 수집 관제 요약 — Scouts ingestion · freshness · quarantine 현황'),
  grid(4, 16, ...WATCH.map(w => h('div', {key: w.label}, statTile(w)))),

  sectionLabel('Citadel · 공간 빠른 진입'),
  grid(4, 16, ...SPACES.map(([slug, name, role]) =>
    h('a', {key: slug, href: `./${slug}.html`, style: {textDecoration: 'none'}},
      h(Card, {}, h('div', {style: {padding: 4}},
        h('div', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 13,
          fontWeight: 600, color: 'var(--color-text-primary)'}}, name),
        h('div', {style: {marginTop: 4}}, h(Text, {type: 'supporting'}, role))))))));

export const render = () => shell({
  route: 'citadel-gate',
  eyebrow: 'Citadel Gate · Home',
  context: '본부 · Home',
  title: 'Citadel Gate · 본부',
  subtitle: 'Temporal Evidence Intelligence · 시간을 기억하는 증거 정보 본부',
  hero: 'gate-hero.png',
  slots: {content: body},
});
