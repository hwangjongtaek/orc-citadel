import React from 'react';

import {clampView, fitView, warGraph, zoomAt} from '@ui/graph.mjs';

const ZOOM_STEP = 1.25;

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
    return {
      x: current.x + (clientX - bounds.left) / bounds.width * current.w,
      y: current.y + (clientY - bounds.top) / bounds.height * current.h,
    };
  }, []);

  const onWheel = React.useCallback((event) => {
    event.preventDefault();
    const factor = event.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP;
    const anchor = pointAt(event.clientX, event.clientY);
    updateView((current) => zoomAt(current, factor, anchor));
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
    updateView(() => clampView({
      x: drag.view.x - deltaX / bounds.width * drag.view.w,
      y: drag.view.y - deltaY / bounds.height * drag.view.h,
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
    handlers: {onWheel, onPointerDown, onPointerMove, onPointerUp: endPointer,
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
  return React.createElement('div', {role: 'dialog', 'aria-modal': 'true',
    'aria-label': 'War Table 그래프 확대 보기',
    style: {position: 'fixed', inset: 0, zIndex: 60, background: 'var(--color-background)',
      display: 'flex', flexDirection: 'column', minHeight: 0}},
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
  React.createElement('div', {style: {padding: '12px 16px', borderTop: '1px solid var(--color-border)'}}, footer));
}
