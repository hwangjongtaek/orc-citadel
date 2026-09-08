/**
 * Citadel Gate · 브리핑 대시보드 목업 — ui/gate 공용 컴포넌트 + fixture 결합.
 * 구조 정의는 [ui/gate.mjs](../../../ui/gate.mjs) 가 정본 (specs TS-3).
 */

import {LayoutContent} from '@astryxdesign/core/Layout';
import {shell, PRIMARY_SPACES, SECONDARY_SPACES} from '../../../ui/shell.mjs';
import {h, Text, sectionLabel, statTile, grid} from '../../../ui/components.mjs';
import {
  brandBlock, conclusionCard, changeCard, newCampaignCard, quickEntry,
} from '../../../ui/gate.mjs';

export const title = 'Citadel Gate · 브리핑 — Orc Citadel';

/** 지식 현황 KPI — 실측 규모(2026-09 L3 재적재)를 반영한 정직한 스케일. */
const KPI = [
  {value: '105,252', label: 'Documents · raw', note: 'normalized 전량 · segments 823,629', tone: 'good'},
  {value: '25', label: 'Entities', note: '결정적 ER — exact match 병합만'},
  {value: '722', label: 'Claims · promoted', note: 'dup 528 클러스터 · 독립성 보정', tone: 'good'},
  {value: '+38', label: '최근 24h 수집', note: 'nightly 07:07 · RSS + arXiv'},
];

const MODALITY = {fact: 'success', asserted: 'warning', opinion: 'neutral', prediction: 'purple'};

/** 주요 subject 결론 — confidence 는 값+근거+독립 출처 병기 (단일 게이지 금지). */
const CONCLUSIONS = [
  {subject: 'B사 — HBM 공급 능력 확대', modality: 'fact',
   statement: 'SEC 10-K 등 독립 출처 5건이 2024–2025 증설 실행을 확인한다. 이전 결론 1건은 superseded.',
   conf: '0.83', ev: 14, indep: 5, cid: 'sub-b-hbm'},
  {subject: 'A사 — AI 가속기 공급망 다변화', modality: 'asserted',
   statement: '신규 공급 계약 공시 3건이 다변화 주장을 지지하나, 물량 기준 B사 의존은 유지 — 반증 1건 수집됨.',
   conf: '0.61', ev: 7, indep: 2, cid: 'sub-a-diversify'},
  {subject: 'C사 — 데이터센터 증설 착공', modality: 'asserted',
   statement: '발표 대비 착공 확인은 1건 — 지자체 인허가 공고가 지지, 부지 계약 공시는 미확인.',
   conf: '0.44', ev: 5, indep: 3, cid: 'sub-c-dc'},
];

/** 최근 변화 — Signal Spire 피드의 상위 3건 요약. */
const CHANGES = [
  {kind: 'Confidence Δ', tone: 'success', subject: 'B사 HBM 확대', delta: '0.79 → 0.83',
   note: 'SEC 10-K 독립 출처 +1 — 결론 상향', ref: 'evd-4021'},
  {kind: 'Contradiction', tone: 'error', subject: 'A사 단일 의존 주장', delta: '반증 후보 수집',
   note: '보도자료 1건이 contradicts 후보로 격리 — 판정 대기', ref: 'evd-789'},
  {kind: 'New Evidence', tone: 'warning', subject: 'C사 착공', delta: '근거 +1 (독립)',
   note: '지자체 인허가 공고 — asserted 유지, coverage 상승', ref: 'evd-3377'},
];

const body = h(LayoutContent, {padding: 4},
  brandBlock(),

  grid(4, 16, ...KPI.map(k => h('div', {key: k.label}, statTile(k)))),

  sectionLabel('Conclusions · 주요 결론 — subject 단위 현재 결론과 근거'),
  grid(3, 16, ...CONCLUSIONS.map(c => conclusionCard({
    ...c, badge: {variant: MODALITY[c.modality] || 'neutral', label: c.modality}}))),

  sectionLabel('Recent Changes · 최근 변화 — confidence 델타 · 반증 · 신규 근거'),
  grid(3, 16, ...CHANGES.map(c => changeCard(c))),

  sectionLabel('New Campaign · 새 조사 (비활성)'),
  newCampaignCard(),

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
