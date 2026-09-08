/**
 * Citadel Gate 엔트리 — Step 3 골격 (파이프라인 검증용).
 *
 * 목적: ui 공용 컴포넌트 + Astryx + theme-citadel + /api/* fetch 가 브라우저에서
 * 한 줄로 이어지는지 실증한다. 브리핑 대시보드 본구현은 Step 5 (목업 확정본 대로).
 */

import React from 'react';
import {createRoot} from 'react-dom/client';

import {h, Card, Text, Badge, sectionLabel, statTile, grid} from '@ui/components.mjs';

function useApi(path) {
  const [state, set] = React.useState({loading: true, data: null, error: null});
  React.useEffect(() => {
    let live = true;
    fetch(path)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${r.status}`))))
      .then((data) => live && set({loading: false, data, error: null}))
      .catch((error) => live && set({loading: false, data: null, error}));
    return () => { live = false; };
  }, [path]);
  return state;
}

function App() {
  const gate = useApi('/api/gate');
  const tiles = gate.loading
    ? [{value: '…', label: 'Loading', note: '/api/gate'}]
    : gate.error
      ? [{value: '—', label: 'API 오류', note: String(gate.error), tone: 'bad'}]
      : [
          {value: String(gate.data.raw_documents ?? '—'), label: 'Documents · raw'},
          {value: String(gate.data.entities ?? '—'), label: 'Entities'},
          {value: String(gate.data.claims ?? '—'), label: 'Claims'},
        ];
  return h('main', {style: {maxWidth: 1200, margin: '0 auto', padding: 24}},
    h(Card, {}, h('div', {style: {padding: 4, display: 'flex', alignItems: 'center',
      gap: 12, flexWrap: 'wrap'}},
      h('img', {src: '/assets/img/logo-mark.png', alt: '',
        style: {height: 40, width: 'auto'}}),
      h('img', {src: '/assets/img/logo-title.png', alt: 'ORC CITADEL',
        style: {height: 24, width: 'auto'}}),
      h(Badge, {variant: 'warning', label: 'frontend 골격 · Step 3'}),
      h(Text, {type: 'supporting'},
        '브리핑 대시보드 본구현은 Step 5 — 이 페이지는 ui 공용 컴포넌트 · Astryx · '
        + 'theme-citadel · /api 배선의 실증이다.'))),
    sectionLabel('/api/gate 실측'),
    grid(3, 16, ...tiles.map((t) => h('div', {key: t.label}, statTile(t)))));
}

createRoot(document.getElementById('root')).render(h(App));
