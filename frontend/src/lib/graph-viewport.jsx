import React from 'react';

import {clampView, fitView, warGraph, zoomAt} from '@ui/graph.mjs';

const ZOOM_STEP = 1.25;
// 트랙패드 pinch 는 이벤트가 연발이라 고정 배율 대신 delta 비례 지수 배율을 쓴다.
// deltaY ±50 clamp → 이벤트당 최대 ×1.65 — 한 제스처가 부드럽게 누적된다.
const PINCH_SENSITIVITY = 0.01;
const PINCH_MAX_DELTA = 50;

const clamp = (value, min, max) => Math.min(Math.max(value, min), max);

const controlStyle = {
  width: 32,
  height: 32,
  border: '1px solid var(--color-border-emphasized)',
  borderRadius: 'var(--radius-element)',
  background: 'var(--color-background-card)',
  color: 'var(--color-text-primary)',
  cursor: 'pointer',
  fontFamily: 'var(--font-family-heading)',
  fontSize: 16,
  fontWeight: 700,
};

function centerOf(view) {
  return {x: view.x + view.w / 2, y: view.y + view.h / 2};
}

// SVG 는 preserveAspectRatio 기본(meet)이라 컨테이너 종횡비가 900:560 과 다르면
// letterbox 여백이 생긴다 — 화면↔그래프 좌표 변환은 이 실제 페인트 영역 기준.
function paintMetrics(bounds, view) {
  const scale = Math.min(bounds.width / view.w, bounds.height / view.h);
  return {
    scale,
    offX: bounds.left + (bounds.width - view.w * scale) / 2,
    offY: bounds.top + (bounds.height - view.h * scale) / 2,
  };
}

export function useGraphViewport() {
  const [view, setView] = React.useState(fitView);
  const surfaceRef = React.useRef(null);
  const viewRef = React.useRef(view);
  const dragRef = React.useRef(null);
  const suppressClickRef = React.useRef(false);

  const updateView = React.useCallback((change) => {
    const next = change(viewRef.current);
    viewRef.current = next;
    setView(next);
  }, []);

  const pointAt = React.useCallback((clientX, clientY) => {
    const surface = surfaceRef.current;
    const current = viewRef.current;
    if (!surface) return centerOf(current);
    const bounds = surface.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return centerOf(current);
    const {scale, offX, offY} = paintMetrics(bounds, current);
    return {
      x: current.x + (clientX - offX) / scale,
      y: current.y + (clientY - offY) / scale,
    };
  }, []);

  // 줌은 pinch 로만 — 두 손가락 스크롤(휠)은 소비하지 않고 페이지에 넘긴다.
  // pinch 는 Chromium/Firefox 가 ctrlKey 달린 wheel 로, Safari 가 gesture 이벤트로
  // 전달한다. React onWheel 은 root passive 라 preventDefault 가 무효 —
  // 네이티브 non-passive 리스너로 부착한다.
  React.useEffect(() => {
    const surface = surfaceRef.current;
    if (!surface) return undefined;

    const pinchZoom = (factor, clientX, clientY) => {
      const anchor = pointAt(clientX, clientY);
      updateView((current) => zoomAt(current, factor, anchor));
    };

    const onWheel = (event) => {
      if (!event.ctrlKey) return;                     // 일반 스크롤은 그래프가 안 먹는다
      event.preventDefault();                         // 브라우저 페이지 줌 억제
      const delta = clamp(-event.deltaY, -PINCH_MAX_DELTA, PINCH_MAX_DELTA);
      pinchZoom(Math.exp(delta * PINCH_SENSITIVITY), event.clientX, event.clientY);
    };

    surface.addEventListener('wheel', onWheel, {passive: false});

    // Safari 전용 pinch (비표준 GestureEvent — 없으면 부착 자체를 안 한다).
    let lastScale = 1;
    const onGestureStart = (event) => {
      event.preventDefault();
      lastScale = event.scale;
    };
    const onGestureChange = (event) => {
      event.preventDefault();
      if (!lastScale) return;
      pinchZoom(event.scale / lastScale, event.clientX, event.clientY);
      lastScale = event.scale;
    };
    const hasGesture = typeof window.GestureEvent === 'function';
    if (hasGesture) {
      surface.addEventListener('gesturestart', onGestureStart);
      surface.addEventListener('gesturechange', onGestureChange);
    }
    return () => {
      surface.removeEventListener('wheel', onWheel);
      if (hasGesture) {
        surface.removeEventListener('gesturestart', onGestureStart);
        surface.removeEventListener('gesturechange', onGestureChange);
      }
    };
  }, [pointAt, updateView]);

  const onPointerDown = React.useCallback((event) => {
    if (event.button !== 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = {
      pointerId: event.pointerId,
      clientX: event.clientX,
      clientY: event.clientY,
      view: viewRef.current,
    };
    suppressClickRef.current = false;
  }, []);

  const onPointerMove = React.useCallback((event) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return;
    const deltaX = event.clientX - drag.clientX;
    const deltaY = event.clientY - drag.clientY;
    if (Math.abs(deltaX) > 3 || Math.abs(deltaY) > 3) suppressClickRef.current = true;
    const {scale} = paintMetrics(bounds, drag.view);
    updateView(() => clampView({
      x: drag.view.x - deltaX / scale,
      y: drag.view.y - deltaY / scale,
      w: drag.view.w,
      h: drag.view.h,
    }));
  }, [updateView]);

  const endPointer = React.useCallback((event) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    dragRef.current = null;
  }, []);

  const onClickCapture = React.useCallback((event) => {
    if (!suppressClickRef.current) return;
    suppressClickRef.current = false;
    event.preventDefault();
    event.stopPropagation();
  }, []);

  const zoom = React.useCallback((factor) => {
    updateView((current) => zoomAt(current, factor, centerOf(current)));
  }, [updateView]);

  const fit = React.useCallback(() => {
    updateView(fitView);
  }, [updateView]);

  return {
    view,
    surfaceRef,
    handlers: {onPointerDown, onPointerMove, onPointerUp: endPointer,
      onPointerCancel: endPointer, onClickCapture, onDoubleClick: fit},
    zoomIn: () => zoom(ZOOM_STEP),
    zoomOut: () => zoom(1 / ZOOM_STEP),
    fit,
  };
}

export function ZoomControls({onZoomIn, onZoomOut, onFit}) {
  return React.createElement('div', {style: {position: 'absolute', right: 12, bottom: 12,
    display: 'flex', gap: 6, zIndex: 1}},
  React.createElement('button', {type: 'button', 'aria-label': '그래프 확대',
    style: controlStyle, onClick: onZoomIn}, '+'),
  React.createElement('button', {type: 'button', 'aria-label': '그래프 축소',
    style: controlStyle, onClick: onZoomOut}, '−'),
  React.createElement('button', {type: 'button', 'aria-label': '그래프 전체 보기',
    style: controlStyle, onClick: onFit}, '⟲'));
}

export function GraphViewport({graphProps, fill = false}) {
  const viewport = useGraphViewport();
  const graph = warGraph({...graphProps, view: viewport.view});
  const svg = fill ? React.cloneElement(graph, {style: {...graph.props.style, height: '100%'}}) : graph;

  return React.createElement('div', {ref: viewport.surfaceRef, ...viewport.handlers,
    style: {position: 'relative', minHeight: 0, height: fill ? '100%' : undefined,
      flex: fill ? 1 : undefined, overflow: 'hidden', touchAction: 'none',
      cursor: 'grab', userSelect: 'none'}},
  svg,
  React.createElement(ZoomControls, {onZoomIn: viewport.zoomIn, onZoomOut: viewport.zoomOut,
    onFit: viewport.fit}));
}

export function GraphOverlay({open, onClose, triggerRef, graphProps, footer}) {
  const closeRef = React.useRef(null);
  const restoreFocusRef = React.useRef(null);

  React.useEffect(() => {
    if (!open) return undefined;
    restoreFocusRef.current = document.activeElement;
    const timer = window.setTimeout(() => closeRef.current && closeRef.current.focus(), 0);
    return () => window.clearTimeout(timer);
  }, [open]);

  React.useEffect(() => {
    if (open || !restoreFocusRef.current) return;
    const target = (triggerRef && triggerRef.current) || restoreFocusRef.current;
    target.focus();
    restoreFocusRef.current = null;
  }, [open, triggerRef]);

  React.useEffect(() => {
    if (!open) return undefined;
    const onKey = (event) => {
      if (event.key !== 'Escape') return;
      event.preventDefault();
      event.stopImmediatePropagation();
      onClose();
    };
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [open, onClose]);

  if (!open) return null;
  // scrim 은 Palette(ui/palette.mjs)와 같은 시각 언어 — 뒤 화면이 dim 으로 비친다.
  return React.createElement('div', {role: 'dialog', 'aria-modal': 'true',
    'aria-label': 'War Table 그래프 확대 보기',
    onClick: (event) => {if (event.target === event.currentTarget) onClose();},
    style: {position: 'fixed', inset: 0, zIndex: 60,
      background: 'rgba(7,17,28,.72)', backdropFilter: 'blur(2px)',
      padding: 28, display: 'flex'}},
  React.createElement('div', {style: {flex: 1, minHeight: 0, minWidth: 0,
    background: 'var(--color-background)',
    border: '1px solid var(--color-border-emphasized)',
    borderRadius: 'var(--radius-element)', overflow: 'hidden',
    display: 'flex', flexDirection: 'column'}},
  React.createElement('div', {style: {display: 'flex', alignItems: 'center', gap: 16,
    justifyContent: 'space-between', padding: '12px 16px', borderBottom: '1px solid var(--color-border)'}},
  React.createElement('div', {},
    React.createElement('div', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 13,
      fontWeight: 600, color: 'var(--color-text-primary)'}}, 'War Table · Temporal Evidence Graph'),
    React.createElement('div', {style: {fontFamily: 'var(--font-family-code)', fontSize: 10,
      color: 'var(--color-text-secondary)', marginTop: 3}}, '확대 보기')),
  React.createElement('button', {ref: closeRef, type: 'button', 'aria-label': '그래프 확대 보기 닫기',
    onClick: onClose, style: {...controlStyle, fontSize: 20, lineHeight: 1}}, '×')),
  React.createElement('div', {style: {display: 'flex', flex: 1, minHeight: 0, padding: 16}},
    React.createElement(GraphViewport, {graphProps, fill: true})),
  React.createElement('div', {style: {padding: '12px 16px', borderTop: '1px solid var(--color-border)'}}, footer)));
}
