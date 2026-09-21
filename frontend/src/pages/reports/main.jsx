/** Campaign Ledger controller — metadata list/polling and sandboxed report selection. */

import React from 'react';
import {createRoot} from 'react-dom/client';

import {shell, APP_URLS} from '@ui/shell.mjs';
import {h} from '@ui/components.mjs';
import {campaignLedgerSlots, REPORT_FILTERS} from '@ui/reports.mjs';
import {Palette, usePaletteHotkey} from '../../lib/palette.jsx';

const urls = APP_URLS;
const ACTIVE = new Set(['queued', 'running']);
const FILTERS = new Set(REPORT_FILTERS.map(([value]) => value));

function selectedFromLocation() {
  return new URLSearchParams(window.location.search).get('investigation');
}

function filterFromLocation() {
  const value = new URLSearchParams(window.location.search).get('status') || 'all';
  return FILTERS.has(value) ? value : 'all';
}

function ledgerHref(investigationId, filter) {
  const params = new URLSearchParams();
  if (filter !== 'all') params.set('status', filter);
  if (investigationId) params.set('investigation', investigationId);
  const query = params.toString();
  return `/reports${query ? `?${query}` : ''}`;
}

function artifactUrls(investigationId) {
  if (!investigationId) return {};
  const safeId = encodeURIComponent(investigationId);
  return {
    html: `/api/investigations/${safeId}/report.html`,
    json: `/api/investigations/${safeId}/report`,
    metadata: `/api/investigations/${safeId}/report-artifact`,
  };
}

async function readJson(response) {
  let body = {};
  try {
    body = await response.json();
  } catch {
    body = {};
  }
  if (response.ok) return body;
  const error = new Error(body.error?.message || `HTTP ${response.status}`);
  error.status = response.status;
  error.code = body.error?.code || body.code;
  throw error;
}

function retryDelay(response) {

  const value = response.headers.get('Retry-After');
  if (!value) return 2000;
  const seconds = Number(value);
  if (Number.isFinite(seconds)) return Math.max(1000, Math.min(5000, seconds * 1000));
  const until = Date.parse(value) - Date.now();
  return Number.isFinite(until) ? Math.max(1000, Math.min(5000, until)) : 2000;
}
function nearestScrollContainer(node) {
  for (let current = node?.parentElement; current; current = current.parentElement) {
    if (current.scrollHeight > current.clientHeight) return current;
  }
  return document.scrollingElement;
}

function useCampaignLedger() {
  const [filter, setFilterState] = React.useState(filterFromLocation);
  const [selectedId, setSelectedId] = React.useState(selectedFromLocation);
  const [cursor, setCursor] = React.useState(null);
  const [cursorHistory, setCursorHistory] = React.useState([]);
  const [reloadList, setReloadList] = React.useState(0);
  const [reloadDetail, setReloadDetail] = React.useState(0);
  const [pollTick, setPollTick] = React.useState(0);
  const [list, setList] = React.useState({state: 'loading', items: [], page: {}});
  const [detail, setDetail] = React.useState({state: selectedId ? 'loading' : 'initial', artifact: null});
  const detailHeadingRef = React.useRef(null);
  const cardRefs = React.useRef(new Map());
  const returnPoint = React.useRef({
    scrollY: 0, scrollContainer: null, scrollTop: 0, investigationId: null,
  });

  React.useEffect(() => {
    const onPopState = () => {
      setSelectedId(selectedFromLocation());
      setFilterState(filterFromLocation());
      setCursor(null);
      setCursorHistory([]);
    };
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  React.useEffect(() => {
    const controller = new AbortController();
    let timer;
    const params = new URLSearchParams({limit: '25'});
    if (filter !== 'all') params.set('status', filter);
    if (cursor) params.set('cursor', cursor);
    setList((previous) => ({...previous,
      state: previous.items.length ? 'ready' : 'loading'}));
    fetch(`/api/investigations?${params}`, {signal: controller.signal})
      .then(async (response) => {
        const delay = retryDelay(response);
        const payload = await readJson(response);
        return {payload, delay};
      })
      .then(({payload, delay}) => {
        const items = Array.isArray(payload.items) ? payload.items : [];
        setList({state: 'ready', items, page: payload.page || {}});
        if (items.some((item) => ACTIVE.has(item.status))) {
          timer = window.setTimeout(() => setPollTick((value) => value + 1), delay);
        }
      })
      .catch((error) => {
        if (error.name !== 'AbortError') setList({state: 'error', items: [], page: {}, error});
      });
    return () => {
      controller.abort();
      if (timer) window.clearTimeout(timer);
    };
  }, [filter, cursor, reloadList, pollTick]);

  const selectedItem = React.useMemo(() =>
    list.items.find((item) => item.investigation_id === selectedId) || null,
  [list.items, selectedId]);

  React.useEffect(() => {
    if (!selectedId) {
      setDetail({state: 'initial', artifact: null});
      return undefined;
    }
    if (selectedItem && (ACTIVE.has(selectedItem.status)
      || ['failed', 'cancelled'].includes(selectedItem.status)
      || selectedItem.artifact_state === 'legacy_json_only')) {
      setDetail({state: 'ready', artifact: null});
      return undefined;
    }

    const controller = new AbortController();
    setDetail({state: 'loading', artifact: null});
    fetch(artifactUrls(selectedId).metadata, {signal: controller.signal})
      .then(readJson)
      .then((payload) => setDetail({state: 'ready', artifact: payload.artifact || payload}))
      .catch((error) => {
        if (error.name === 'AbortError') return;
        if (error.code === 'investigation_not_found') {
          setDetail({state: 'not-found', artifact: null});
        } else if (error.code === 'report_artifact_not_found') {
          setDetail({state: 'legacy', artifact: null});
        } else if (error.code === 'investigation_not_completed') {
          setDetail({state: 'active', artifact: null});
        } else {
          setDetail({state: error.status === 404 ? 'not-found' : 'store-error',
            artifact: null, error});
        }
      });
    return () => controller.abort();
  }, [selectedId, selectedItem?.status, selectedItem?.artifact_state, reloadDetail]);

  React.useEffect(() => {
    if (selectedId && window.matchMedia('(max-width:720px)').matches) {
      window.requestAnimationFrame(() => detailHeadingRef.current?.focus());
    }
  }, [selectedId]);

  const updateLocation = React.useCallback((nextId, nextFilter, mode = 'push') => {
    const href = ledgerHref(nextId, nextFilter);
    window.history[mode === 'replace' ? 'replaceState' : 'pushState']({}, '', href);
  }, []);

  const select = React.useCallback((item) => {
    const node = cardRefs.current.get(item.investigation_id);
    const scrollContainer = nearestScrollContainer(node);
    returnPoint.current = {scrollY: window.scrollY, scrollContainer,
      scrollTop: scrollContainer?.scrollTop || 0, investigationId: item.investigation_id};
    setSelectedId(item.investigation_id);
    updateLocation(item.investigation_id, filter);
  }, [filter, updateLocation]);

  const back = React.useCallback(() => {
    const point = returnPoint.current;
    setSelectedId(null);
    updateLocation(null, filter, 'replace');
    window.requestAnimationFrame(() => {
      window.scrollTo({top: point.scrollY});
      if (point.scrollContainer) point.scrollContainer.scrollTop = point.scrollTop;
      cardRefs.current.get(point.investigationId)?.focus();
    });
  }, [filter, updateLocation]);

  const setFilter = React.useCallback((nextFilter) => {
    setFilterState(nextFilter);
    setCursor(null);
    setCursorHistory([]);
    updateLocation(selectedId, nextFilter, 'replace');
  }, [selectedId, updateLocation]);

  const next = React.useCallback(() => {
    if (!list.page.next_cursor) return;
    setCursorHistory((history) => [...history, cursor]);
    setCursor(list.page.next_cursor);
  }, [cursor, list.page.next_cursor]);

  const previous = React.useCallback(() => {
    setCursorHistory((history) => {
      if (!history.length) return history;
      setCursor(history[history.length - 1]);
      return history.slice(0, -1);
    });
  }, []);

  let effectiveItem = selectedItem;
  if (!effectiveItem && selectedId && detail.state === 'ready' && detail.artifact) {
    effectiveItem = {investigation_id: selectedId, status: 'completed'};
  } else if (!effectiveItem && selectedId && detail.state === 'legacy') {
    effectiveItem = {investigation_id: selectedId, status: 'completed',
      artifact_state: 'legacy_json_only'};
  } else if (!effectiveItem && selectedId && detail.state === 'active') {
    effectiveItem = {investigation_id: selectedId, status: 'running'};
  }

  const visibleDetailState = ['legacy', 'active'].includes(detail.state) ? 'ready' : detail.state;
  return {
    filter, selectedId, selectedItem: effectiveItem, artifact: detail.artifact,
    listState: list.state, items: list.items, detailState: visibleDetailState,
    page: {nextCursor: list.page.next_cursor, hasPrevious: cursorHistory.length > 0,
      label: cursorHistory.length ? `page ${cursorHistory.length + 1}` : '최근순'},
    select, back, setFilter, next, previous,
    retryList: () => setReloadList((value) => value + 1),
    retryDetail: () => setReloadDetail((value) => value + 1),
    detailHeadingRef,
    onCardRef: (investigationId, node) => {
      if (node) cardRefs.current.set(investigationId, node);
      else cardRefs.current.delete(investigationId);
    },
  };
}

function App() {
  const state = useCampaignLedger();
  const [paletteOpen, setPaletteOpen] = React.useState(false);
  usePaletteHotkey(setPaletteOpen);
  const reportUrls = artifactUrls(state.selectedId);

  return h(React.Fragment, {},
    shell({
      route: 'council-chamber',
      eyebrow: 'Council Chamber · Reports',
      context: 'Campaign Ledger · 조사 기록',
      title: 'Campaign Ledger · 조사 보고서',
      subtitle: '완료·진행·실패한 Campaign을 찾고 감사 가능한 HTML 리포트를 열람합니다.',
      hero: 'campaign-ledger-hero.png',
      heroAlt: '완료된 조사 두루마리가 정돈된 Campaign Ledger 기록실',
      alerts: 0,
      urls,
      onSearchOpen: () => setPaletteOpen(true),
      slots: campaignLedgerSlots({
        items: state.items,
        selectedId: state.selectedId,
        selectedItem: state.selectedItem,
        artifact: state.artifact,
        filter: state.filter,
        listState: state.listState,
        detailState: state.detailState,
        page: state.page,
        onFilterChange: state.setFilter,
        onSelect: state.select,
        onPrevious: state.previous,
        onNext: state.next,
        onRetryList: state.retryList,
        onRetryDetail: state.retryDetail,
        onBack: state.back,
        onCardRef: state.onCardRef,
        detailHeadingRef: state.detailHeadingRef,
        selectionHref: (investigationId) => ledgerHref(investigationId, state.filter),
        artifactUrls: reportUrls,
        councilUrl: urls.page('council-chamber'),
        assetBase: '/assets/img/',
      }),
    }),
    h(Palette, {open: paletteOpen, onClose: () => setPaletteOpen(false)}));
}

createRoot(document.getElementById('root')).render(h(App));
