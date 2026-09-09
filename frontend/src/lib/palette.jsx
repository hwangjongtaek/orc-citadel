/**
 * ⌘K 통합 검색 팔레트 컨테이너 — fetch·디바운스·키보드·오버레이 상태 (TS-3).
 * 프레젠테이션은 ui/palette.mjs(공용), 여기는 앱 전용 배선이다.
 *
 * /api/search 는 entities·claims·documents 를 이미 cross-zone 으로 반환한다
 * (각 ≤10) — API 변경 없음. 결과 딥링크는 각 공간의 기존 URL 부트스트랩:
 * /table?subject= · /witnesses?claim= · /archive?doc=
 */

import React from 'react';

import {h} from '@ui/components.mjs';
import {searchPalette} from '@ui/palette.mjs';

const GROUPS = [
  {api: 'entities', label: 'Entities · War Table에서 보기',
   map: (e) => ({key: `e:${e.entity_id}`,
     primary: e.name || e.entity_id,
     secondary: e.mention_type || 'entity',
     href: `/table?subject=${encodeURIComponent(e.entity_id)}`})},
  {api: 'claims', label: 'Claims · 근거 열람 (Witnesses)',
   map: (c) => ({key: `c:${c.claim_id}`,
     primary: [c.predicate, c.object_literal || c.subject_id]
       .filter(Boolean).join(' · ') || c.claim_id,
     secondary: c.claim_id,
     href: `/witnesses?claim=${encodeURIComponent(c.claim_id)}`})},
  {api: 'documents', label: 'Documents · 원문 (Archive)',
   map: (d) => ({key: `d:${d.doc_id}`,
     primary: d.title || d.doc_id,
     secondary: d.source_id || 'doc',
     href: `/archive?doc=${encodeURIComponent(d.doc_id)}`})},
];

/** ⌘K / Ctrl+K 전역 토글. */
export function usePaletteHotkey(setOpen) {
  React.useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [setOpen]);
}

export function Palette({open, onClose}) {
  const [q, setQ] = React.useState('');
  const [data, setData] = React.useState(null);
  const [activeKey, setActiveKey] = React.useState(null);
  const inputRef = React.useRef(null);

  // 디바운스 검색 — 타이핑 중 과호출 방지 (10만 문서 ILIKE 는 서버 축).
  React.useEffect(() => {
    if (!open) return undefined;
    const v = q.trim();
    if (!v) { setData(null); setActiveKey(null); return undefined; }
    const t = setTimeout(() => {
      fetch(`/api/search?q=${encodeURIComponent(v)}`)
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${r.status}`))))
        .then(setData)
        .catch(() => setData({error: true}));
    }, 180);
    return () => clearTimeout(t);
  }, [q, open]);

  // 열릴 때 포커스, 닫힐 때 초기화.
  React.useEffect(() => {
    if (open) setTimeout(() => inputRef.current && inputRef.current.focus(), 0);
    else { setQ(''); setData(null); setActiveKey(null); }
  }, [open]);

  const groups = React.useMemo(() => {
    if (!data || data.error) return [];
    return GROUPS
      .map((g) => ({label: g.label, items: (data[g.api] || []).map(g.map)}))
      .filter((g) => g.items.length);
  }, [data]);
  const flat = React.useMemo(() => groups.flatMap((g) => g.items), [groups]);

  // 키보드 내비 — ↑↓ 이동 · ⏎ 열기 · esc 닫기.
  React.useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') { e.preventDefault(); onClose(); return; }
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        if (!flat.length) return;
        const idx = flat.findIndex((it) => it.key === activeKey);
        const next = e.key === 'ArrowDown'
          ? (idx + 1) % flat.length
          : (idx - 1 + flat.length) % flat.length;
        setActiveKey(flat[next].key);
        return;
      }
      if (e.key === 'Enter') {
        const it = flat.find((i) => i.key === activeKey) || flat[0];
        if (it) window.location.href = it.href;
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, flat, activeKey, onClose]);

  if (!open) return null;
  const status = !q.trim() ? '검색어를 입력하세요 — entity · claim · document'
    : data == null ? '검색 중…'
    : data.error ? '검색 실패 — 뷰어 API 상태를 확인하세요'
    : '결과 없음';
  return searchPalette({query: q, groups, activeKey, status, inputRef,
    onQueryChange: setQ, onBackdrop: onClose});
}
