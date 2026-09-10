/**
 * War Table 그래프 캔버스 — 결정적 SVG (specs TS-5 · DESIGN.md hairball 가드).
 *
 * hairball 금지 전략: 노드를 전부 뿌리지 않는다.
 *   중심 = subject · 1링 = predicate 그룹(집계 ×N) · 2링 = 선택 그룹의 claim
 *   (페이지당 CLAIMS_PER_PAGE, "+N" 노드로 다음 페이지) — 항상 ≤ 100 노드.
 * 배치는 인덱스 기반 각도 슬롯이라 결정적이고, 슬롯 간격이 라벨 폭을 보장해
 * 충돌 회피를 계산 없이 얻는다. 선택 노드만 primary 발광 (DESIGN.md).
 * props-only — 데이터 fetch·상태는 소비자(frontend) 몫.
 */

import {h} from './components.mjs';

export const CLAIMS_PER_PAGE = 12;

export const GRAPH_VIEW = Object.freeze({x: 0, y: 0, w: 900, h: 560});
export const GRAPH_ZOOM_LIMITS = Object.freeze({min: .5, max: 4});

const W = GRAPH_VIEW.w, H = GRAPH_VIEW.h, CX = W / 2, CY = H / 2;
const R_GROUP = 150, R_CLAIM = 245, R_LABEL = 258;

const rad = (deg) => (deg * Math.PI) / 180;

const clamp = (value, min, max) => Math.min(Math.max(value, min), max);

/** 기본 캔버스를 모두 보이는 결정적 viewBox. */
export function fitView() {
  return GRAPH_VIEW;
}

/** 줌 한계와 그래프 경계 안으로 viewBox 를 정규화한다. */
export function clampView({x, y, w} = GRAPH_VIEW) {
  const scale = clamp(W / w, GRAPH_ZOOM_LIMITS.min, GRAPH_ZOOM_LIMITS.max);
  const width = W / scale;
  const height = H / scale;
  const minX = Math.min(0, W - width);
  const maxX = Math.max(0, W - width);
  const minY = Math.min(0, H - height);
  const maxY = Math.max(0, H - height);

  return {
    x: clamp(x, minX, maxX),
    y: clamp(y, minY, maxY),
    w: width,
    h: height,
  };
}

/** 주어진 그래프 좌표를 커서 앵커로 유지하며 확대·축소한다. */
export function zoomAt(view, factor, {x, y}) {
  const current = clampView(view);
  const scale = clamp(W / current.w * factor, GRAPH_ZOOM_LIMITS.min, GRAPH_ZOOM_LIMITS.max);
  const width = W / scale;
  const height = H / scale;

  return clampView({
    x: x - (x - current.x) * width / current.w,
    y: y - (y - current.y) * height / current.h,
    w: width,
    h: height,
  });
}
const at = (r, deg) => [CX + r * Math.cos(rad(deg)), CY + r * Math.sin(rad(deg))];

const COLORS = {
  edge: 'var(--color-border-emphasized)',
  node: 'var(--color-background-muted)',
  nodeStroke: 'var(--color-border-emphasized)',
  text: 'var(--color-text-secondary)',
  textOn: 'var(--color-text-primary)',
  accent: 'var(--color-accent)',
};

/**
 * @param subjectLabel    중심 노드 라벨 (entity 실명)
 * @param groups          [{predicate, count, claims:[{id,label}]}] — count 내림차순 정렬 권장
 * @param expanded        펼친 predicate (null 이면 그룹만)
 * @param page            펼친 그룹의 페이지 (0-base)
 * @param selectedClaimId 선택 claim (발광)
 * @param view            선택 viewBox {x,y,w,h}; 생략 시 전체 그래프
 * @param onSelectGroup(predicate) / onSelectClaim(id) / onMore() 콜백
 */
export function warGraph({subjectLabel, groups, expanded, page = 0, selectedClaimId,
                          truncated, view, onSelectGroup, onSelectClaim, onMore}) {
  const kids = [];
  const n = Math.max(groups.length, 1);

  groups.forEach((g, i) => {
    const deg = -90 + (360 / n) * i;
    const [gx, gy] = at(R_GROUP, deg);
    const grpR = 16 + Math.min(16, Math.sqrt(g.count) * 2);
    const isOpen = g.predicate === expanded;

    // 중심 → 그룹 (구조 엣지 ABOUT — 관계 의미는 evidence 레벨에서만)
    kids.push(h('line', {key: `ge-${g.predicate}`, x1: CX, y1: CY, x2: gx, y2: gy,
      stroke: COLORS.edge, strokeWidth: 1.2}));

    // 펼친 그룹의 claim 부채꼴
    if (isOpen) {
      const start = page * CLAIMS_PER_PAGE;
      const shown = g.claims.slice(start, start + CLAIMS_PER_PAGE);
      const rest = g.claims.length - (start + shown.length);
      const slots = shown.length + (rest > 0 ? 1 : 0);
      shown.concat(rest > 0 ? [{id: '__more__', label: `+${rest}`}] : [])
        .forEach((c, j) => {
          const cdeg = deg + (j - (slots - 1) / 2) * 13;
          const [cx, cy] = at(R_CLAIM, cdeg);
          const [lx, ly] = at(R_LABEL, cdeg);
          const east = Math.cos(rad(cdeg)) >= 0;
          const isMore = c.id === '__more__';
          const isSel = c.id === selectedClaimId;
          kids.push(h('line', {key: `ce-${c.id}-${j}`, x1: gx, y1: gy, x2: cx, y2: cy,
            stroke: COLORS.edge, strokeWidth: .7, strokeDasharray: isMore ? '2 3' : null}));
          kids.push(h('circle', {key: `cn-${c.id}-${j}`, cx, cy, r: isSel ? 9 : 6.5,
            fill: COLORS.node,
            stroke: isSel ? COLORS.accent : COLORS.nodeStroke,
            strokeWidth: isSel ? 2 : 1,
            style: isSel ? {filter: 'drop-shadow(0 0 6px rgba(69,224,111,.8))'} : null,
            cursor: 'pointer',
            onClick: isMore ? onMore : (onSelectClaim && (() => onSelectClaim(c.id)))}));
          kids.push(h('text', {key: `cl-${c.id}-${j}`, x: lx, y: ly + 3,
            textAnchor: east ? 'start' : 'end',
            fontFamily: 'var(--font-family-code)', fontSize: 9.5,
            fill: isSel ? COLORS.accent : COLORS.text,
            cursor: 'pointer',
            onClick: isMore ? onMore : (onSelectClaim && (() => onSelectClaim(c.id)))},
            isMore ? `+${rest} 더 보기` : `${c.id.slice(0, 12)}…`));
        });
    }

    // 그룹 노드 (predicate ×N)
    kids.push(h('circle', {key: `gn-${g.predicate}`, cx: gx, cy: gy, r: grpR,
      fill: 'var(--color-background-card)',
      stroke: isOpen ? COLORS.accent : COLORS.nodeStroke,
      strokeWidth: isOpen ? 1.8 : 1.2, cursor: 'pointer',
      onClick: onSelectGroup && (() => onSelectGroup(g.predicate))}));
    kids.push(h('text', {key: `gl-${g.predicate}`, x: gx, y: gy - 2,
      textAnchor: 'middle', fontFamily: 'var(--font-family-heading)', fontSize: 11,
      fontWeight: 600, fill: isOpen ? COLORS.accent : COLORS.textOn,
      cursor: 'pointer',
      onClick: onSelectGroup && (() => onSelectGroup(g.predicate))}, g.predicate));
    kids.push(h('text', {key: `gc-${g.predicate}`, x: gx, y: gy + 11,
      textAnchor: 'middle', fontFamily: 'var(--font-family-code)', fontSize: 9,
      fill: COLORS.text}, `×${g.count}`));
  });

  // 중심 subject — 마지막에 그려 위로
  kids.push(h('circle', {key: 'subj', cx: CX, cy: CY, r: 36,
    fill: 'var(--color-background-card)', stroke: COLORS.accent, strokeWidth: 1.6}));
  kids.push(h('text', {key: 'subj-t', x: CX, y: CY - 2, textAnchor: 'middle',
    fontFamily: 'var(--font-family-heading)', fontSize: 12, fontWeight: 600,
    fill: COLORS.textOn},
    subjectLabel.length > 12 ? `${subjectLabel.slice(0, 11)}…` : subjectLabel));
  kids.push(h('text', {key: 'subj-s', x: CX, y: CY + 12, textAnchor: 'middle',
    fontFamily: 'var(--font-family-code)', fontSize: 8.5, fill: COLORS.text},
    'SUBJECT'));

  if (truncated) {
    kids.push(h('text', {key: 'trunc', x: W - 12, y: H - 10, textAnchor: 'end',
      fontFamily: 'var(--font-family-code)', fontSize: 9, fill: COLORS.text},
      '서버 절단(truncated) — 상위 100 claim 만 수신 (honest-gap)'));
  }

  const visibleView = view ? clampView(view) : fitView();
  return h('svg', {viewBox: `${visibleView.x} ${visibleView.y} ${visibleView.w} ${visibleView.h}`,
    width: '100%',
    style: {display: 'block', minWidth: 0},
    role: 'img', 'aria-label': `${subjectLabel} temporal evidence subgraph`},
    ...kids);
}
