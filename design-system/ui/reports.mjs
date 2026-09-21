/** Campaign Ledger presentation — props-only, fetch-free, and shared by mockup/app. */

import React from 'react';
import {LayoutContent, LayoutPanel} from '@astryxdesign/core/Layout';

import {
  h, Badge, Card, Text, Button, panelHead, sectionLabel, id, coverage, emptyState,
} from './components.mjs';

export const REPORT_FILTERS = [
  ['all', '전체 · All'],
  ['active', '진행 중 · Active'],
  ['completed', '완료 · Completed'],
  ['unsuccessful', '실패·취소 · Unsuccessful'],
];

const STATUS = {
  queued: ['대기 · queued', 'neutral'],
  running: ['진행 중 · running', 'warning'],
  completed: ['완료 · completed', 'success'],
  failed: ['실패 · failed', 'error'],
  cancelled: ['취소됨 · cancelled', 'warning'],
};

const styles = `
  .campaign-ledger-master { width:min(392px,100vw); }
  .campaign-ledger-question {
    display:-webkit-box; -webkit-box-orient:vertical; -webkit-line-clamp:2;
    overflow:hidden;
  }
  .campaign-ledger-mobile-back { display:none; }
  .campaign-ledger-skeleton {
    min-height:14px; border-radius:var(--radius-inner);
    background:linear-gradient(90deg,var(--color-background-muted),var(--color-border),var(--color-background-muted));
    background-size:200% 100%; animation:ledger-pulse 1.4s ease-in-out infinite;
  }
  @keyframes ledger-pulse { from { background-position:100% 0; } to { background-position:-100% 0; } }
  @media (max-width:720px) {
    .campaign-ledger-master, .campaign-ledger-detail { width:100% !important; max-width:none !important; }
    .campaign-ledger-master[data-detail-open="true"] { display:none !important; }
    .campaign-ledger-detail[data-detail-open="false"] { display:none !important; }
    .campaign-ledger-mobile-back { display:inline-flex; margin-bottom:12px; }
    .campaign-ledger-frame { min-height:68vh !important; }
  }
  @media (prefers-reduced-motion:reduce) { .campaign-ledger-skeleton { animation:none; } }
`;

const fmtTime = (value) => {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? String(value) : date.toLocaleString('ko-KR');
};

const ratio = (value) => {
  if (typeof value === 'number') return value <= 1 ? value : value / 100;
  if (value && typeof value.ratio === 'number') return value.ratio;
  return null;
};

function coverageSummary(value) {
  const r = ratio(value);
  const pct = r == null ? null : Math.max(0, Math.min(100, Math.round(r * 100)));
  const covered = value && (value.covered ?? value.completed ?? value.subclaims_covered);
  const planned = value && (value.planned ?? value.total ?? value.subclaims_planned);
  const count = covered != null && planned != null
    ? `${covered}/${planned}` : 'covered/planned 미제공';
  return {pct, label: `coverage ${count}${pct == null ? '' : ` (${pct}%)`}`};
}

const generationLabel = (item) => {
  const mode = item?.artifact?.generation_mode;
  if (mode === 'llm_assisted') return 'LLM';
  if (mode === 'deterministic_fallback') return 'fallback';
  if (item?.artifact_state === 'legacy_json_only') return 'legacy JSON';
  return 'not ready';
};

const actionStyle = (primary = false) => ({
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
  padding: '8px 11px', borderRadius: 'var(--radius-element)', textDecoration: 'none',
  border: `1px solid ${primary ? 'var(--color-accent)' : 'var(--color-border)'}`,
  background: primary ? 'rgba(69,224,111,.08)' : 'transparent',
  color: primary ? 'var(--color-accent)' : 'var(--color-text-primary)',
  fontFamily: 'var(--font-family-heading)', fontSize: 12, fontWeight: 600,
});

function CampaignCard({item, selected, href, onSelect, onCardRef}) {
  const [label, tone] = STATUS[item.status] || [String(item.status || 'unknown'), 'neutral'];
  const cov = coverageSummary(item.coverage);
  const time = item.completed_at
    ? `완료 · ${fmtTime(item.completed_at)}` : `생성 · ${fmtTime(item.created_at)}`;
  return h('a', {
    ref: (node) => onCardRef?.(item.investigation_id, node),
    key: item.investigation_id,
    href,
    onClick: onSelect ? (event) => { event.preventDefault(); onSelect(item); } : undefined,
    'aria-current': selected ? 'true' : undefined,
    'data-investigation-id': item.investigation_id,
    style: {
      display: 'block', textDecoration: 'none', color: 'inherit', marginBottom: 8,
      border: `1px solid ${selected ? 'var(--color-accent)' : 'var(--color-border)'}`,
      background: selected ? 'rgba(69,224,111,.05)' : 'var(--color-background-card)',
      borderRadius: 'var(--radius-element)', padding: 12,
    },
  },
  h('div', {style: {display: 'flex', justifyContent: 'space-between', gap: 8,
    alignItems: 'center', flexWrap: 'wrap'}},
  h(Badge, {variant: tone, label}),
  id(item.investigation_id)),
  h('div', {className: 'campaign-ledger-question', style: {marginTop: 8,
    fontFamily: 'var(--font-family-heading)', fontSize: 12.5, lineHeight: 1.45,
    fontWeight: 600, color: 'var(--color-text-primary)'}},
  item.question || '질문 없음'),
  h('div', {style: {display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8}},
  h(Badge, {variant: 'neutral', label: item.mode || 'mode 미제공'}),
  h(Badge, {variant: item.artifact ? 'success' : 'neutral', label: generationLabel(item)})),
  h('div', {style: {marginTop: 8, display: 'grid', gap: 4}},
  h(Text, {type: 'supporting'}, time),
  h(Text, {type: 'supporting'}, cov.label),
  ['queued', 'running'].includes(item.status) && item.current_step
    ? h(Text, {type: 'supporting'}, `현재 단계 · ${item.current_step.stage || item.current_step.step_id || '진행 중'}`)
    : null),
  cov.pct == null ? null
    : h('div', {style: {marginTop: 8}}, coverage(cov.pct, cov.pct < 80 ? 'warn' : null)));
}

function LoadingList() {
  return h('div', {'aria-busy': 'true', 'aria-label': '조사 목록 불러오는 중'},
    [0, 1, 2].map((key) => h('div', {key, style: {padding: 12, marginBottom: 8,
      border: '1px solid var(--color-border)', borderRadius: 'var(--radius-element)'}},
    h('div', {className: 'campaign-ledger-skeleton', style: {width: '42%'}}),
    h('div', {className: 'campaign-ledger-skeleton', style: {width: '92%', marginTop: 12}}),
    h('div', {className: 'campaign-ledger-skeleton', style: {width: '66%', marginTop: 7}}))));
}

function StoreError({onRetry}) {
  return h(Card, {}, h('div', {style: {padding: 4}},
    h(Badge, {variant: 'error', label: 'STORE ERROR'}),
    h('h3', {style: {margin: '10px 0 6px', fontFamily: 'var(--font-family-heading)',
      fontSize: 15, color: 'var(--color-text-primary)'}}, '저장소 연결 실패'),
    h(Text, {type: 'supporting'}, '조사 기록을 불러오지 못했습니다. 빈 목록이 아닙니다.'),
    onRetry ? h('div', {style: {marginTop: 10}},
      h(Button, {variant: 'secondary', onClick: onRetry}, '다시 시도')) : null));
}

function LedgerList(props) {
  const {items, selectedId, filter, listState, page, fixtureLabel, onFilterChange,
    onSelect, onPrevious, onNext, onRetryList, selectionHref, onCardRef} = props;
  let list;
  if (listState === 'loading') list = h(LoadingList);
  else if (listState === 'error') list = h(StoreError, {onRetry: onRetryList});
  else if (!items.length) list = emptyState({
    title: '조사 기록 없음',
    description: '이 필터에 해당하는 Campaign이 없습니다. 저장소 오류와 구분된 빈 결과입니다.',
    isCompact: true,
  });
  else list = h('nav', {'aria-label': 'Campaign 목록'}, items.map((item) =>
    h(CampaignCard, {key: item.investigation_id, item,
      selected: selectedId === item.investigation_id,
      href: selectionHref(item.investigation_id), onSelect, onCardRef})));

  return h(LayoutPanel, {
    className: 'campaign-ledger-master', width: 'min(392px, 100vw)',
    hasDivider: true, padding: 0, label: 'Campaign Ledger',
    'data-detail-open': selectedId ? 'true' : 'false',
  },
  h('style', {}, styles),
  panelHead('Campaign Ledger', `${items.length}건 · 최근 생성 순`),
  h('div', {style: {padding: '12px 16px', borderBottom: '1px solid var(--color-border)'}},
  fixtureLabel ? h('div', {style: {display: 'flex', gap: 8, alignItems: 'center', marginBottom: 10}},
    h(Badge, {variant: 'neutral', label: fixtureLabel}),
    h(Text, {type: 'supporting'}, '실제 조사 기록이 아닌 레이아웃 검증용 예시')) : null,
  h('label', {style: {display: 'grid', gap: 4, fontFamily: 'var(--font-family-heading)',
    fontSize: 10, color: 'var(--color-text-secondary)'}},
  'Status · 조사 상태',
  h('select', {value: onFilterChange ? filter : undefined,
    defaultValue: onFilterChange ? undefined : filter,
    'aria-label': '조사 상태 필터',
    onChange: onFilterChange ? (event) => onFilterChange(event.target.value) : undefined,
    style: {width: '100%', padding: '8px 10px',
      background: 'var(--color-background-muted)', color: 'var(--color-text-primary)',
      border: '1px solid var(--color-border)', borderRadius: 'var(--radius-element)'}},
  REPORT_FILTERS.map(([value, label]) => h('option', {key: value, value}, label))))),
  h('div', {style: {padding: 12}},
  h('div', {'aria-live': 'polite', style: {marginBottom: 8}},
    h(Text, {type: 'supporting'}, listState === 'ready'
      ? `${items.length}건 표시` : listState === 'loading' ? '불러오는 중' : '불러오기 실패')),
  list,
  h('div', {style: {display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    marginTop: 12}},
  h(Button, {variant: 'secondary', disabled: !page?.hasPrevious, onClick: onPrevious}, '이전'),
  h(Text, {type: 'supporting'}, page?.label || '최근순'),
  h(Button, {variant: 'secondary', disabled: !page?.nextCursor, onClick: onNext}, '다음'))));
}

function DetailLoading() {
  return h('div', {'aria-busy': 'true', 'aria-label': '리포트 metadata 불러오는 중',
    style: {padding: '20px 4px'}},
  h('div', {className: 'campaign-ledger-skeleton', style: {width: '30%'}}),
  h('div', {className: 'campaign-ledger-skeleton', style: {width: '85%', marginTop: 14, minHeight: 22}}),
  h('div', {className: 'campaign-ledger-skeleton', style: {width: '62%', marginTop: 9}}));
}

function TerminalWithoutArtifact({item, jsonUrl}) {
  if (item.artifact_state === 'legacy_json_only') {
    return h(Card, {}, h('div', {style: {padding: 4}},
      h(Badge, {variant: 'neutral', label: 'LEGACY JSON ONLY'}),
      h('h3', {style: {margin: '10px 0 6px'}}, 'HTML artifact가 없는 이전 조사'),
      h(Text, {type: 'supporting'}, 'cutover 이전 완료 기록입니다. HTML을 생성했다고 가장하지 않습니다.'),
      h('a', {href: jsonUrl, target: '_blank', rel: 'noopener noreferrer',
        style: {...actionStyle(false), marginTop: 12}}, '기존 JSON 리포트 열기')));
  }
  const failed = item.status === 'failed';
  return h(Card, {}, h('div', {style: {padding: 4}},
    h(Badge, {variant: failed ? 'error' : 'warning',
      label: failed ? 'FAILED · HTML 없음' : 'CANCELLED · HTML 없음'}),
    h('h3', {style: {margin: '10px 0 6px'}},
      failed ? '조사가 실패했습니다' : '조사가 취소되었습니다'),
    h(Text, {type: 'supporting'}, item.error?.message || item.error_json?.message
      || item.termination || (failed ? '완료 artifact가 생성되지 않았습니다.' : '사용자 취소로 완료되지 않았습니다.'))));
}

function ActiveDetail({item}) {
  const cov = coverageSummary(item.coverage);
  return h(Card, {}, h('div', {style: {padding: 4}},
    h(Badge, {variant: item.status === 'running' ? 'warning' : 'neutral',
      label: STATUS[item.status]?.[0] || item.status}),
    h('h3', {style: {margin: '10px 0 6px'}},
      item.status === 'queued' ? 'worker 배정 대기 중' : '조사가 진행 중입니다'),
    h(Text, {type: 'supporting'}, item.current_step
      ? `현재 단계 · ${item.current_step.stage || item.current_step.step_id || '진행 중'}`
      : '현재 단계 없음 · 상태 갱신을 기다립니다.'),
    h('div', {style: {marginTop: 8}}, h(Text, {type: 'supporting'}, cov.label)),
    cov.pct == null ? null : h('div', {style: {marginTop: 8}}, coverage(cov.pct, 'warn')),
    h('div', {style: {marginTop: 10}},
      h(Text, {type: 'supporting'}, '취소는 Council Chamber에서만 할 수 있습니다.'))));
}

function ArtifactPanel({artifact}) {
  const audit = artifact.audit_summary || {};
  const version = artifact.version_tuple && typeof artifact.version_tuple === 'object'
    ? JSON.stringify(artifact.version_tuple) : artifact.version_tuple;
  const model = [artifact.provider, artifact.model_id].filter(Boolean).join(' · ') || 'LLM 미사용';
  const rows = [
    ['Audit', `linked ${audit.linked ?? '—'}/${audit.verifiable ?? '—'} · blocked ${audit.blocked ?? '—'}`],
    ['Generation', `${artifact.generation_mode || '—'}${artifact.fallback_reason ? ` · ${artifact.fallback_reason}` : ''}`],
    ['Template', `${artifact.template_version || '—'} · schema ${artifact.output_schema_version || '—'}`],
    ['Model', model],
    ['Content', artifact.content_hash || '—'],
    ['Source', artifact.source_report_hash || '—'],
    ['Draft', artifact.draft_hash || '—'],
    ['Version tuple', version || '—'],
  ];
  return h(React.Fragment, {},
    sectionLabel('Artifact Integrity · 생성 계보'),
    h(Card, {}, h('dl', {style: {margin: 0, display: 'grid', gap: 9}}, rows.map(([name, value]) =>
      h('div', {key: name, style: {display: 'grid', gridTemplateColumns: '110px minmax(0,1fr)', gap: 8}},
        h('dt', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 10,
          color: 'var(--color-text-secondary)'}}, name),
        h('dd', {style: {margin: 0, overflowWrap: 'anywhere'}}, id(String(value))))))));
}

function StateReferences({assetBase}) {
  const state = (tone, title, detail) => h(Card, {key: title},
    h('div', {style: {padding: 4, minHeight: 88}},
      h(Badge, {variant: tone, label: title}),
      h('div', {style: {marginTop: 10}}, h(Text, {type: 'supporting'}, detail))));
  return h(React.Fragment, {},
    sectionLabel('State Variants · 대체 상태 레퍼런스'),
    h('div', {style: {display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(180px,1fr))', gap: 10}},
      state('neutral', 'NO SELECTION', '리포트를 선택하면 감사된 HTML 문서를 엽니다.'),
      state('neutral', 'LOADING', '목록 또는 artifact metadata를 불러오는 중입니다.'),
      state('warning', 'ACTIVE', 'queued/running · 현재 단계와 coverage만 표시합니다.'),
      state('error', 'FAILED', '완료되지 않아 JSON과 HTML artifact가 없습니다.'),
      state('warning', 'CANCELLED', '취소되어 완료 artifact가 없습니다.'),
      state('error', 'STORE ERROR', '저장소 연결 실패 · 빈 결과와 구분합니다.'),
      state('neutral', 'LEGACY JSON ONLY', 'cutover 이전 기록 · 기존 JSON만 엽니다.')),
    h('div', {style: {marginTop: 10}}, emptyState({
      art: 'empty-report-not-found.png', assetBase,
      title: '리포트를 찾을 수 없습니다',
      description: '요청한 investigation ID나 저장된 artifact가 없습니다.',
      isCompact: true,
    })));
}

function DetailBody(props) {
  const {detailState, item, artifact, onRetryDetail, artifactUrls, assetBase} = props;
  if (detailState === 'initial') return emptyState({
    title: '리포트를 선택하세요',
    description: '리포트를 선택하면 감사된 HTML 문서를 엽니다.',
    isCompact: true,
  });
  if (detailState === 'loading') return h(DetailLoading);
  if (detailState === 'not-found') return emptyState({
    art: 'empty-report-not-found.png', assetBase,
    title: '리포트를 찾을 수 없습니다',
    description: '요청한 investigation ID가 없거나 저장된 HTML artifact를 찾을 수 없습니다.',
    isCompact: true,
  });
  if (detailState === 'store-error') return h(StoreError, {onRetry: onRetryDetail});
  if (!item) return null;
  if (['queued', 'running'].includes(item.status)) return h(ActiveDetail, {item});
  if (['failed', 'cancelled'].includes(item.status) || item.artifact_state === 'legacy_json_only') {
    return h(TerminalWithoutArtifact, {item, jsonUrl: artifactUrls.json});
  }
  if (!artifact) return h(StoreError, {onRetry: onRetryDetail});
  return h(React.Fragment, {},
    h('div', {style: {marginTop: 14, padding: '10px 12px',
      border: '1px solid var(--color-border)', borderRadius: 'var(--radius-element)',
      background: 'var(--color-background-muted)'}},
      h('div', {style: {display: 'flex', gap: 8, alignItems: 'center'}},
        h(Badge, {variant: 'neutral', label: 'SANDBOXED'}),
        h(Text, {type: 'supporting'}, '스크립트 없이 격리된 미리보기 · 저장된 HTML만 표시'))),
    sectionLabel('Generated HTML · 감사된 문서'),
    h('iframe', {
      className: 'campaign-ledger-frame', src: artifactUrls.html,
      title: `조사 리포트: ${item.question || item.investigation_id}`,
      sandbox: '', loading: 'lazy', referrerPolicy: 'no-referrer',
      style: {display: 'block', width: '100%', minHeight: 760,
        border: '1px solid var(--color-border)', borderRadius: 'var(--radius-container)',
        background: '#07111C', colorScheme: 'dark'},
    }),
    h(ArtifactPanel, {artifact}));
}

function ReportDetail(props) {
  const {selectedId, item, artifact, detailState, detailHeadingRef, onBack,
    onRetryDetail, artifactUrls, councilUrl, assetBase, showStateReferences} = props;
  const status = item ? STATUS[item.status] || [item.status || 'unknown', 'neutral'] : null;
  return h(LayoutContent, {className: 'campaign-ledger-detail', padding: 0,
    label: '선택한 Campaign 보고서', 'data-detail-open': selectedId ? 'true' : 'false'},
  panelHead('Report Viewer · 보고서', selectedId ? `selected · ${item?.status || 'loading'}` : '선택 대기'),
  h('div', {style: {padding: 16}},
  selectedId ? h('button', {className: 'campaign-ledger-mobile-back', onClick: onBack,
    'aria-label': 'Campaign 목록으로 돌아가기', style: actionStyle(false)}, '← 목록으로') : null,
  selectedId ? h(React.Fragment, {},
    h('div', {style: {display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap'}},
      status ? h(Badge, {variant: status[1], label: status[0]}) : null,
      artifact ? h(Badge, {variant: 'neutral', label: artifact.generation_mode || 'artifact'}) : null,
      id(selectedId)),
    h('h2', {ref: detailHeadingRef, tabIndex: -1, style: {margin: '10px 0 6px',
      fontFamily: 'var(--font-family-heading)', fontSize: 18, lineHeight: 1.35,
      color: 'var(--color-text-primary)', outline: 'none'}}, item?.question || '선택한 조사 리포트'),
    h(Text, {type: 'supporting'}, item
      ? `${item.status || '상태 미제공'} · 생성 ${fmtTime(item.created_at)}${item.completed_at ? ` · 완료 ${fmtTime(item.completed_at)}` : ''}`
      : 'investigation metadata 확인 중'),
    h('div', {style: {display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 12}},
      artifact && artifactUrls?.html
        ? h('a', {href: artifactUrls.html, target: '_blank', rel: 'noopener noreferrer',
            style: actionStyle(true)}, '전체 보고서 열기') : null,
      h('a', {href: councilUrl, style: actionStyle(false)}, 'Council Chamber로 돌아가기'))) : null,
  h(DetailBody, {detailState, item, artifact, onRetryDetail, artifactUrls, assetBase}),
  showStateReferences ? h(StateReferences, {assetBase}) : null));
}

/** Build Astryx start/content slots for the shared shell. */
export function campaignLedgerSlots({
  items = [], selectedId = null, selectedItem = null, artifact = null,
  filter = 'all', listState = 'ready', detailState = 'initial', page = {},
  fixtureLabel, onFilterChange, onSelect, onPrevious, onNext, onRetryList,
  onRetryDetail, onBack, onCardRef, detailHeadingRef,
  selectionHref = (investigationId) => `?investigation=${encodeURIComponent(investigationId)}`,
  artifactUrls = {}, councilUrl = '/council', assetBase = '/assets/img/',
  showStateReferences = false,
}) {
  return {
    start: h(LedgerList, {items, selectedId, filter, listState, page, fixtureLabel,
      onFilterChange, onSelect, onPrevious, onNext, onRetryList, selectionHref, onCardRef}),
    content: h(ReportDetail, {selectedId, item: selectedItem, artifact, detailState,
      detailHeadingRef, onBack, onRetryDetail, artifactUrls, councilUrl, assetBase,
      showStateReferences}),
  };
}

/** Render the complete master/detail surface when a shell is not composing slots. */
export function CampaignLedger(props) {
  const slots = campaignLedgerSlots(props);
  return h(React.Fragment, {}, slots.start, slots.content);
}
