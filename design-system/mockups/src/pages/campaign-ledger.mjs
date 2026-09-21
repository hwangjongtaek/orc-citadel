/** Campaign Ledger · Investigation Reports — Council utility master/detail mockup. */

import {shell} from '../../../ui/shell.mjs';
import {campaignLedgerSlots} from '../../../ui/reports.mjs';

export const title = 'Campaign Ledger · 조사 보고서 — Orc Citadel';

const CAMPAIGNS = [
  {
    investigation_id: 'inv-demo-001',
    status: 'completed',
    question: '2024년 이후 A사의 AI 가속기 공급망 다변화가 실제로 진행되었는지 조사하라. 공식 발표와 실제 계약·공시를 구분하고 반대 증거도 포함하라.',
    mode: 'llm',
    created_at: '2026-09-18T08:55:00Z',
    completed_at: '2026-09-18T09:42:00Z',
    coverage: {covered: 5, planned: 8, ratio: 0.63},
    artifact: {generation_mode: 'llm_assisted'},
  },
  {
    investigation_id: 'inv-demo-002',
    status: 'running',
    question: '2025년 이후 B사의 핵심 광물 조달 다변화가 계약과 인도 실적으로 이어졌는지 조사하라.',
    mode: 'deterministic',
    created_at: '2026-09-19T14:08:00Z',
    coverage: {covered: 5, planned: 8, ratio: 0.63},
    current_step: {stage: 'counter_evidence', step_id: 'step-003'},
  },
  {
    investigation_id: 'inv-demo-003',
    status: 'queued',
    question: 'C사의 데이터센터 확장 계획이 인허가와 착공 증거로 확인되는지 조사하라.',
    mode: 'deterministic',
    created_at: '2026-09-19T15:22:00Z',
    coverage: {covered: 0, planned: 8, ratio: 0},
  },
  {
    investigation_id: 'inv-demo-004',
    status: 'failed',
    question: 'D사의 장기 공급 계약이 최신 공시에서도 유효한지 조사하라.',
    mode: 'llm',
    created_at: '2026-09-17T11:03:00Z',
    coverage: {},
    termination: 'source_unavailable',
  },
  {
    investigation_id: 'inv-demo-005',
    status: 'cancelled',
    question: 'E사의 해외 생산 거점 이전 발표와 실제 집행을 비교하라.',
    mode: 'deterministic',
    created_at: '2026-09-16T07:31:00Z',
    coverage: {},
    termination: 'user_cancelled',
  },
];

const ARTIFACT = {
  artifact_id: 'rpt-demo-001',
  generation_mode: 'llm_assisted',
  template_version: 'citadel-report-1',
  output_schema_version: '1.0.0',
  provider: 'bunker',
  model_id: 'bunker-flash',
  prompt_template_hash: 'sha256:84d2…',
  content_hash: 'sha256:7b31a4d9c102…',
  source_report_hash: 'sha256:1b7d…',
  draft_hash: 'sha256:20a4…',
  audit_summary: {linked: 5, verifiable: 5, blocked: 0},
  version_tuple: {ontology: '1.0.0', schema: '1.2.0', extraction: 'git:demo'},
};

export const render = () => shell({
  route: 'council-chamber',
  eyebrow: 'Council Chamber · Reports',
  context: 'Campaign Ledger · 조사 기록',
  title: 'Campaign Ledger · 조사 보고서',
  subtitle: '완료·진행·실패한 Campaign을 찾고 감사 가능한 HTML 리포트를 열람합니다.',
  hero: 'campaign-ledger-hero.png',
  heroAlt: '완료된 조사 두루마리가 정돈된 Campaign Ledger 기록실',
  alerts: 0,
  slots: campaignLedgerSlots({
    items: CAMPAIGNS,
    selectedId: CAMPAIGNS[0].investigation_id,
    selectedItem: CAMPAIGNS[0],
    artifact: ARTIFACT,
    filter: 'all',
    listState: 'ready',
    detailState: 'ready',
    fixtureLabel: 'DEMO FIXTURE',
    page: {nextCursor: 'demo-next', hasPrevious: false, label: '1–5'},
    selectionHref: (investigationId) =>
      `./campaign-ledger.html?investigation=${encodeURIComponent(investigationId)}`,
    artifactUrls: {
      html: './investigation-report.html',
      json: './investigation-report.html',
    },
    councilUrl: './council-chamber.html',
    assetBase: './assets/',
    showStateReferences: true,
  }),
});
