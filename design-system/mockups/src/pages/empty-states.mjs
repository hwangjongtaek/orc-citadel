/** 빈 상태 아트 — 각 공간의 no-data 상태를 한데 모아 확인하는 참조 페이지. */

import {LayoutContent} from '@astryxdesign/core/Layout';
import {shell} from '../shell.mjs';
import {h, Card, Text, emptyState, grid} from '../ui.mjs';

export const title = '빈 상태 아트 · Empty States — Orc Citadel';

const STATES = [
  ['조사 미선택', 'War Table', 'Graph · 그래프 탐색', 'empty-wartable.png', 'war-table',
    'Campaign Map 에서 subclaim 을 선택하면 Temporal Evidence Graph 가 그려집니다.'],
  ['모든 소스 정상', 'Watchtower', 'Ingestion · 수집 관제', 'empty-watchtower.png', 'watchtower',
    '실패·지연·dead-letter 가 없습니다. 초병이 쉬는 중.'],
  ['검색 결과 없음', 'Grand Archive', 'Documents · 문서 탐색', 'empty-archive.png', 'grand-archive',
    '필터를 넓히거나 다른 질의어를 시도해 보세요.'],
  ['claim 미선택', 'Hall of Witnesses', 'Evidence · 증거 검사', 'empty-witnesses.png', 'hall-of-witnesses',
    'claim 을 선택하면 지지·반박 근거와 원문 왕복 추적이 표시됩니다.'],
  ['이력 없음', 'Chronicle Vault', 'History · 시간 탐색', 'empty-chronicle.png', 'chronicle-vault',
    '이 subject 에 아직 bitemporal 버전 이력이 없습니다.'],
  ['새 알림 없음', 'Signal Spire', 'Alerts · 알림 센터', 'empty-spire.png', 'signal-spire',
    '점화된 트리거가 없습니다. 봉화는 상태가 바뀔 때만 오릅니다.'],
];

const body = h(LayoutContent, {padding: 4},
  h(Text, {type: 'supporting'},
    '각 Citadel 공간의 데이터 없음(no-data) 상태에 표시되는 픽셀아트 스팟 일러스트. '
    + '실제 화면에서는 해당 조건에서만 조건부로 렌더된다. 프롬프트는 illustration-prompts.md §4.'),
  h('div', {style: {marginTop: 20}},
    grid(3, 16, ...STATES.map(([title2, space, fn, art, slug, desc]) =>
      h(Card, {key: art}, h('div', {style: {padding: 4}},
        h(Text, {type: 'label'}, `${space} · ${fn}`),
        h('div', {style: {marginTop: 8}},
          emptyState({art, title: title2, description: desc, isCompact: true})),
        h('div', {style: {marginTop: 8, textAlign: 'center'}},
          h('a', {href: `./${slug}.html`, style: {fontSize: 11,
            color: 'var(--astryx-theme-citadel-seer-green)'}}, '화면 열기 ›'))))))));

export const render = () => shell({
  route: null,
  eyebrow: 'Empty States · No-data',
  context: '빈 상태 아트',
  title: '빈 상태 아트 · Empty States',
  subtitle: '각 Citadel 공간의 no-data 상태 · 조건부 렌더',
  alerts: 0,
  slots: {content: body},
});
