/** Grand Archive · 문서 탐색 — Sifter(검색·필터) | Stacks(목록) | Codex(상세). */

import {LayoutContent, LayoutPanel} from '@astryxdesign/core/Layout';
import {shell} from '../../../ui/shell.mjs';
import {h, Card, Badge, Text, sectionLabel, id, panelHead, grid} from '../../../ui/components.mjs';
import {facetChips, lineageBadge, docCard, pager, sifterSearch}
  from '../../../ui/archive.mjs';

export const title = 'Grand Archive · 문서 탐색 — Orc Citadel';

const FACETS = [
  ['source_type · 발행 주체',
   {gov: 88, official: 214, press: 903, research: 31, exchange: 11}, 'press'],
  ['language · 언어', {ko: 612, en: 635}, ''],
  ['dedup role · 계보', {root: 340, derived: 861, independent: 46}, ''],
];

const DOCS = [
  {id: 'doc-9f2a1c7e4b03…c1', active: true,
    title: 'A사 FY2024 연차보고서 (Form 10-K) — 공급망 위험 요인',
    source: 'SEC EDGAR · gov', date: '2025-02-15', lang: 'en', role: 'root',
    group: '같은 URL · 2 버전 — data.sec.gov/…/a-corp/10-K'},
  {id: 'doc-3b7e4a91d5f2…a4',
    title: 'A사 FY2024 연차보고서 개정본 (Form 10-K/A) — 위험 요인 정정',
    source: 'SEC EDGAR · gov', date: '2025-03-02', lang: 'en', role: 'derived'},
  {id: 'doc-5540f2a8c19b…7d',
    title: 'A사 "복수 공급처로 안정적 조달 체계 확보" 보도자료',
    source: 'A사 IR · official', date: '2025-03-14', lang: 'ko', role: 'root',
    group: '복제 클러스터 · clus-8Q2 · 500건 — 근원 = doc-5540…7d'},
  {id: 'doc-a1e83f0c62d7…9b',
    title: '"A사, 복수 공급처 확보"… 보도자료 전재 (연합 배포 +498건)',
    source: '종합일보 외 · press', date: '2025-03-15', lang: 'ko', role: 'derived'},
  {id: 'doc-7c02d9b3e5a1…f8',
    title: 'A사 공급망 다변화 분석 — C사 계약 규모·집행 시점 추가 취재',
    source: '반도체저널 · press', date: '2025-03-16', lang: 'ko', role: 'independent'},
];

const VERSIONS = [
  ['10-K 원본', 'revision 2025-02-15', 'doc-9f2a1c7e4b03…c1', 'sha256:9f2a…4c1b'],
  ['10-K/A 개정본', 'revision 2025-03-02', 'doc-3b7e4a91d5f2…a4', 'sha256:3b7e…8a42'],
];

const PARSE = [['1,284', 'segments'], ['57', 'paragraph'],
  ['342', 'table_cell 보존'], ['18', 'footnote 보존']];

const LINEAGE = [
  ['root', '보도자료 doc-5540'],
  ['derived', '복제 기사 ×500'],
  ['derived', '번역 전재 ×2'],
  ['independent', '추가 취재 doc-7c02'],
];

const sifter = h(LayoutPanel, {width: 300, hasDivider: true, padding: 0, label: 'Sifter'},
  panelHead('Sifter · 검색·필터', 'Docs · 1,247'),
  h('div', {style: {padding: 16}},
    sifterSearch({placeholder: '본문 contains 검색 (title · url · doc_id)'}),
    FACETS.map(([name, counts, active]) =>
      h('div', {key: name},
        sectionLabel(name),
        facetChips({counts, active}))),
    sectionLabel('publication_time · 기간'),
    h('div', {style: {display: 'flex', alignItems: 'center', gap: 8}},
      id('2024-06'),
      h('span', {style: {flex: 1, height: 4, borderRadius: 'var(--radius-full)',
        background: 'linear-gradient(90deg, var(--color-border), var(--color-accent))'}}),
      id('2025-03'))));

const stacks = h(LayoutContent, {padding: 0},
  panelHead('Stacks · 문서 목록', '정렬 · publication_time ↓'),
  h('div', {style: {padding: 16}},
    h('div', {style: {marginBottom: 10}},
      pager({offset: 0, limit: 50, shown: 5, total: 42, zoneTotal: 1247})),
    DOCS.map(d => h('div', {key: d.id},
      d.group ? h('div', {style: {margin: '10px 0 6px'}},
        h(Badge, {variant: 'neutral', label: d.group})) : null,
      docCard({docId: d.id, title: d.title, source: d.source,
        meta: `${d.date} · ${d.lang}`, role: d.role, active: d.active})))));

const codex = h(LayoutPanel, {width: 380, hasDivider: true, padding: 0, label: 'Codex'},
  panelHead('Codex · 문서 상세', 'doc-9f2a…c1'),
  h('div', {style: {padding: 16}},
    h(Text, {}, 'A사 FY2024 연차보고서 (Form 10-K) — 공급망 위험 요인'),
    h('div', {style: {marginTop: 6}}, id('doc-9f2a1c7e4b03…c1 · content-hash 기반 ID')),
    h('div', {style: {display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8}},
      h(Badge, {variant: 'neutral', label: 'SEC EDGAR · gov'}),
      h(Badge, {variant: 'neutral', label: 'en'}),
      lineageBadge('root'),
      h(Badge, {variant: 'neutral', label: 'parser v3.2.1'})),

    sectionLabel('버전 히스토리 · 같은 URL, 여러 doc_id'),
    VERSIONS.map(([name, rev, docId, hash]) =>
      h('div', {key: docId, style: {border: '1px solid var(--color-border)',
        borderRadius: 'var(--radius-element)', padding: '10px 12px', marginBottom: 8}},
        h('div', {style: {display: 'flex', alignItems: 'center',
          justifyContent: 'space-between', gap: 8}},
          h(Text, {type: 'supporting'}, name), id(rev)),
        h('div', {style: {marginTop: 4}}, id(docId)),
        h('div', {style: {marginTop: 2}}, id(`content_hash ${hash}`)))),
    h(Text, {type: 'supporting'},
      '변경분은 덮어쓰지 않고 새 doc_id 로 전부 보존 (raw immutable · ADR-301).'),

    sectionLabel('Parsing · Normalized'),
    grid(2, 8, ...PARSE.map(([v, c]) =>
      h('div', {key: c, style: {padding: '8px 10px',
        border: '1px solid var(--color-border)', borderRadius: 'var(--radius-inner)'}},
        h('div', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 16,
          fontWeight: 600, color: 'var(--color-text-primary)'}}, v),
        h('div', {style: {fontSize: 9.5, letterSpacing: '.06em', textTransform: 'uppercase',
          color: 'var(--color-text-secondary)', marginTop: 2}}, c)))),
    h('div', {style: {marginTop: 8}},
      h(Text, {type: 'supporting'},
        '표·각주 유실 없음 · 원문↔정규화 offset 양방향 매핑 (segment_id 결정적).')),

    sectionLabel('Dedup Cluster · 출처 계보'),
    LINEAGE.map(([role, what]) =>
      h('div', {key: what, style: {display: 'flex', alignItems: 'center', gap: 8,
        padding: '6px 0'}},
        lineageBadge(role),
        h(Text, {type: 'supporting'}, what))),
    h('div', {style: {marginTop: 10, padding: '10px 12px',
      border: '1px solid rgba(255,177,59,.3)', background: 'rgba(255,177,59,.06)',
      borderRadius: 'var(--radius-element)'}},
      h(Text, {type: 'label'}, '⚠ 복제 500건 ≠ 독립 500'),
      h('div', {style: {marginTop: 4}},
        h(Text, {type: 'supporting'},
          '하나의 보도자료에서 파생된 복제 기사 500건은 1개 근원 + N개 독립 추가로 '
          + '카운트한다 (blueprint §8.3).')),
      h('div', {style: {marginTop: 6}},
        id('독립 증거 수 = 1(root) + 1(독립추가) = 2  ≠  501')))));

export const render = () => shell({
  route: 'grand-archive',
  eyebrow: 'Grand Archive · Documents',
  context: '문서 탐색',
  title: 'Grand Archive · 문서 탐색',
  subtitle: '원문 · 버전 · parsing · 출처 계보(dedup cluster) lineage',
  hero: 'grand-archive-hero.png',
  slots: {start: sifter, content: stacks, end: codex},
});
