/** Watchtower · 수집 관제 — KPI 5타일 + Pipeline throughput | Sources | Failure·DLQ | SLO. */

import {LayoutContent} from '@astryxdesign/core/Layout';
import {shell} from '../../../ui/shell.mjs';
import {
  h, Card, Badge, Text, sectionLabel, statTile, id, grid,
  Table, TableHeader, TableHeaderCell, TableBody, TableRow, TableCell,
} from '../../../ui/components.mjs';

export const title = 'Watchtower · 수집 관제 — Orc Citadel';

const KPI = [
  {label: 'Sources Active', value: '18', unit: '/ 21 enabled',
    note: 'robots·license 통과 · 위반 시도 0', tone: 'good'},
  {label: '평균 Freshness 지연', value: '14', unit: 'min · p95 41m',
    note: '지연 2 source · vs schedule.cron', tone: 'warn'},
  {label: 'Ingestion Backlog', value: '3,240', unit: 'docs',
    note: 'S1→S3→S4 미처리 문서 · 재실행 12'},
  {label: '실패율 (24h)', value: '1.8', unit: '%',
    note: 'fetch·parse·dedup 합산 실패', tone: 'warn'},
  {label: 'Dead-letter 유입', value: '12', unit: '/ 24h',
    note: '실시간 수집 42 docs/min', tone: 'bad'},
];

const STAGES = [
  ['S1', 'Fetch', '42', '1,120', '0.9%'],
  ['S3', 'Parse / Normalize', '38', '1,640', '2.4%'],
  ['S4', 'Dedup', '40', '480', '0.3%'],
];

const SOURCES = [
  ['SEC EDGAR', 'cron 0 */6 * * *', 'gov', '08:12 · 12분 전', '정상', '99.4%', '12', 'gov-public'],
  ['A사 IR', 'RSS · content_hash', 'official', '07:50 · 34분 전', '정상', '98.1%', '34', 'proprietary'],
  ['반도체 전문지', 'cron 0 * * * *', 'press', '06:30 · 1시간 54분 전', '지연', '94.2%', '210', 'proprietary'],
  ['arXiv', 'API · updated 필드', 'research', '08:00 · 24분 전', '정상', '99.8%', '8', 'cc-by'],
  ['거래소 시세 API', 'API · timestamp cursor', 'exchange', '08:24 · 방금', '실시간', '99.9%', '3', '재배포 제한'],
  ['공정위 공시', 'cron 0 */4 * * *', 'gov', '05:00 · 3시간 24분 전', '지연', '96.5%', '88', 'gov-public'],
];

const FAILURES = [
  ['파싱 실패 · malformed PDF', 'DLQ', 'error',
    'doc-3b71…a9 · 반도체 전문지 · corr-01J9F2…',
    '재시도 3/3 소진 → dead-letter · parser_version 상향 후 재처리 대기'],
  ['인코딩 판정 실패', 'DLQ', 'error',
    'doc-c04e…12 · 공정위 공시 · corr-01J9E8…',
    'HTTP·meta·통계 감지 모두 실패 · 원문 bytes 보존'],
  ['429 backoff', 'retrying', 'warning',
    'A사 IR · corr-01J9F3… · rps 초과',
    'exponential backoff + jitter · 재시도 2/5 · 다음 시도 +8s'],
];

const SLOS = [
  ['신규 문서 → graph 반영 지연 (p95)', 'SLO-01', '22 min', '≤ 30 min', '7d rolling', 'ok'],
  ['Source 수집 성공률', 'SLO-05', '98.6%', '≥ 99%', '7d rolling · 목표 미달', 'warn'],
  ['Schema validation 통과율', 'SLO-06', '99.2%', '≥ 99%', '7d rolling', 'ok'],
];

const FRESH = {정상: 'success', 지연: 'warning', 실시간: 'success'};

const stageCard = ([sid, name, rate, backlog, fail]) =>
  h(Card, {key: sid}, h('div', {style: {padding: 4}},
    h('div', {style: {display: 'flex', alignItems: 'center', gap: 8}},
      h(Badge, {variant: 'neutral', label: sid}),
      h(Text, {type: 'label'}, name)),
    h('div', {style: {display: 'flex', alignItems: 'baseline', gap: 4, marginTop: 8}},
      h('span', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 24,
        fontWeight: 600, color: 'var(--color-text-primary)'}}, rate),
      h(Text, {type: 'supporting'}, 'docs/min')),
    h('div', {style: {display: 'flex', gap: 16, marginTop: 8}},
      h('div', {}, h(Text, {type: 'label'}, 'backlog'),
        h('div', {}, id(backlog))),
      h('div', {}, h(Text, {type: 'label'}, '실패'),
        h('div', {}, id(fail))))));

const body = h(LayoutContent, {padding: 4},
  h('div', {style: {display: 'grid', gridTemplateColumns: 'repeat(5, minmax(0,1fr))',
    gap: 16}}, KPI.map(k => h('div', {key: k.label}, statTile(k)))),

  sectionLabel('Pipeline · Stage Throughput — S1 Fetch · S3 Parse/Normalize · S4 Dedup'),
  grid(3, 16, ...STAGES.map(stageCard)),
  h('div', {style: {marginTop: 10, padding: '10px 12px',
    border: '1px solid var(--color-border)', borderRadius: 'var(--radius-element)'}},
    h(Text, {type: 'label'}, 'Correlation ID'),
    h('div', {style: {marginTop: 4}}, id('corr-01J9F3QMR7…8K2 (예시)')),
    h('div', {style: {marginTop: 4}},
      h(Text, {type: 'supporting'},
        'fetch(S1) → doc-8f3a…c1 (S2) → parse(S3) → dedup(S4) · 재작성 없이 전 stage 전파'))),

  // FR-6: 운영 drill-down 은 Grafana 가 담당 — Watchtower 는 브리핑용 요약 + 딥링크.
  h('div', {style: {marginTop: 10, padding: '10px 12px', display: 'flex',
    alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap',
    background: 'rgba(255,177,59,.05)', border: '1px solid rgba(255,177,59,.25)',
    borderRadius: 'var(--radius-element)'}},
    h('div', {},
      h(Text, {type: 'label'}, 'Grafana · Pipeline Observability'),
      h('div', {style: {marginTop: 4}},
        h(Text, {type: 'supporting'},
          '런 단위 drill-down(정확도·지연·correlation 분해)은 Grafana 대시보드가 담당 — '
          + '소스: postgres pipeline_run_metrics · pipeline_slo_observations (nightly flush)'))),
    h('a', {href: '#', style: {fontFamily: 'var(--font-family-heading)', fontSize: 11.5,
      fontWeight: 600, color: 'var(--astryx-theme-citadel-signal-amber)',
      textDecoration: 'none', whiteSpace: 'nowrap'}}, 'Grafana에서 열기 →')),

  sectionLabel('Sources · 수집 상태 — 마지막 수집 vs schedule.cron freshness'),
  h(Card, {}, h(Table, {},
    h(TableHeader, {}, h(TableRow, {},
      ...['Source', 'Type', '마지막 수집', 'Freshness', '성공률', 'Backlog', 'License']
        .map(c => h(TableHeaderCell, {key: c}, c)))),
    h(TableBody, {}, SOURCES.map(([name, sched, type, last, fresh, rate, backlog, lic]) =>
      h(TableRow, {key: name},
        h(TableCell, {}, h('div', {},
          h(Text, {}, name), h('div', {}, id(sched)))),
        h(TableCell, {}, h(Badge, {variant: 'neutral', label: type})),
        h(TableCell, {}, id(last)),
        h(TableCell, {}, h(Badge, {variant: FRESH[fresh] || 'warning', label: fresh})),
        h(TableCell, {}, id(rate)),
        h(TableCell, {}, id(backlog)),
        h(TableCell, {}, h(Text, {type: 'supporting'}, lic))))))),

  h('div', {style: {display: 'grid', gridTemplateColumns: '1.9fr 1fr', gap: 24,
    alignItems: 'start', marginTop: 8}},
    h('div', {},
      sectionLabel('Failure · Dead-letter — 최근 실패 · 재시도'),
      FAILURES.map(([reason, state, tone, doc, note]) =>
        h('div', {key: doc, style: {border: '1px solid var(--color-border)',
          borderLeft: `3px solid ${tone === 'error' ? 'var(--color-error)'
            : 'var(--astryx-theme-citadel-signal-amber)'}`,
          borderRadius: 'var(--radius-element)', padding: '10px 12px', marginBottom: 10}},
          h('div', {style: {display: 'flex', alignItems: 'center',
            justifyContent: 'space-between', gap: 8}},
            h(Text, {}, reason), h(Badge, {variant: tone, label: state})),
          h('div', {style: {marginTop: 4}}, id(doc)),
          h('div', {style: {marginTop: 4}}, h(Text, {type: 'supporting'}, note)))),
      h('div', {style: {display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px',
        background: 'rgba(69,224,111,.05)', border: '1px solid rgba(69,224,111,.22)',
        borderRadius: 'var(--radius-element)'}},
        h(Text, {type: 'supporting'},
          '원본은 유실 없이 보존 — raw 는 immutable · 오류·correlation ID 와 함께 DLQ 보관, '
          + '버전 상향 후 동일 key 로 재실행'))),

    h('div', {},
      sectionLabel('SLO · 수집 목표 — placeholder · 측정 후 확정'),
      SLOS.map(([name, sid, cur, target, window, tone]) =>
        h('div', {key: sid, style: {border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius-element)', padding: '11px 12px', marginBottom: 10}},
          h('div', {style: {display: 'flex', alignItems: 'center',
            justifyContent: 'space-between', gap: 8}},
            h(Text, {type: 'supporting'}, name), id(sid)),
          h('div', {style: {display: 'flex', alignItems: 'baseline',
            justifyContent: 'space-between', marginTop: 6}},
            h('span', {style: {fontFamily: 'var(--font-family-code)', fontSize: 15,
              color: tone === 'warn' ? 'var(--astryx-theme-citadel-signal-amber)'
                : 'var(--color-text-primary)'}}, cur),
            h('span', {style: {fontFamily: 'var(--font-family-code)', fontSize: 11,
              color: 'var(--color-text-secondary)'}}, `목표 ${target}`)),
          h('div', {style: {display: 'flex', alignItems: 'center', gap: 8, marginTop: 6}},
            h(Badge, {variant: 'purple', label: 'TBD'}),
            h(Text, {type: 'supporting'}, window)))))));

export const render = () => shell({
  route: 'watchtower',
  eyebrow: 'Watchtower · Ingestion',
  context: '수집 관제',
  title: 'Watchtower · 수집 관제',
  subtitle: 'source 상태 · freshness · ingestion backlog · failure',
  hero: 'watchtower-hero.png',
  slots: {content: body},
});
