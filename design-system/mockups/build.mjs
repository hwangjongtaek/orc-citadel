/**
 * 목업 SSG 드라이버.
 *
 * Astryx 컴포넌트를 `renderToStaticMarkup` 으로 정적 HTML 로 굽는다.
 * 번들러·클라이언트 JS 없음 — 산출물은 HTML + CSS 3장 + assets 뿐이다.
 *
 *   node build.mjs
 */

import {renderToStaticMarkup} from 'react-dom/server';
import {mkdirSync, copyFileSync, writeFileSync, readdirSync, rmSync, cpSync} from 'node:fs';
import {dirname, join} from 'node:path';
import {fileURLToPath} from 'node:url';

const ROOT = dirname(fileURLToPath(import.meta.url));
const REPO = join(ROOT, '..', '..');

/**
 * 출력은 `docs/mockups/` — 목업의 정본 위치다.
 *
 * 이 디렉터리에는 생성물이 아닌 것도 산다: 손으로 쓴 `illustration-prompts.md` 와
 * 히어로·초상 PNG 22종(`assets/`). **디렉터리를 통째로 지우면 안 된다.**
 * 생성하는 파일만 이름으로 덮어쓴다.
 */
const DIST = join(REPO, 'docs', 'mockups');

const ALL_PAGES = [
  'index', 'citadel-gate', 'war-table', 'hall-of-witnesses', 'council-chamber',
  'watchtower', 'grand-archive', 'chronicle-vault', 'signal-spire', 'empty-states',
];

// `node build.mjs war-table` — 저작 중 한두 페이지만 굽는다. 인자 없으면 전체.
const only = process.argv.slice(2);
const PAGES = only.length ? ALL_PAGES.filter(p => only.includes(p)) : ALL_PAGES;

const CSS = [
  [join(ROOT, 'node_modules/@astryxdesign/core/src/reset.css'), 'reset.css'],
  [join(ROOT, 'node_modules/@astryxdesign/core/dist/astryx.css'), 'astryx.css'],
  [join(REPO, 'design-system/theme-citadel/dist/theme.css'), 'theme-citadel.css'],
];

// 로컬 vendoring 폰트 — 외부 CDN 금지 규약(오프라인 전제). theme 은 이름만 선언한다.
const FONTS = join(REPO, 'design-system/fonts/dist');

// `assets/` 는 이미 출력 디렉터리 안에 산다(SSOT). 복사하지 않는다.
const ASSETS = join(DIST, 'assets');

function page(title, body) {
  return `<!doctype html>
<html lang="ko">
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>${title}</title>
<link rel="stylesheet" href="./fonts/fonts.css" />
<link rel="stylesheet" href="./reset.css" />
<link rel="stylesheet" href="./astryx.css" />
<link rel="stylesheet" href="./theme-citadel.css" />
<style>
  html, body { height: 100%; margin: 0; background: var(--color-background-body); }
  a { color: inherit; }
  ::selection { background: rgba(69,224,111,.25); }

  /* 도메인 SVG(그래프 캔버스·bitemporal plane)가 참조하는 조판 클래스.
     Astryx 에 대응 컴포넌트가 없어 원본 목업의 SVG 를 그대로 옮겼다. */
  .node-label { font-family: var(--font-family-heading); font-weight: 600; font-size: 12px; fill: var(--color-text-primary); }
  .node-type  { font-family: var(--font-family-heading); font-weight: 600; font-size: 9px; letter-spacing: .1em; text-transform: uppercase; fill: var(--color-text-secondary); }
  .node-sub   { font-family: var(--font-family-body); font-size: 11px; fill: var(--color-text-secondary); }
  .edge-label { font-family: var(--font-family-heading); font-size: 9.5px; letter-spacing: .06em; text-transform: uppercase; fill: var(--color-text-secondary); }
  .ax         { font-family: var(--font-family-heading); font-size: 10px; letter-spacing: .08em; text-transform: uppercase; fill: var(--color-text-secondary); }
  .tick-lbl   { font-family: var(--font-family-code); font-size: 10px; fill: var(--color-text-secondary); }
  .box-title  { font-family: var(--font-family-heading); font-weight: 600; font-size: 12px; fill: var(--color-text-primary); }
  .box-sub    { font-family: var(--font-family-code); font-size: 10px; fill: var(--color-text-secondary); }
  .wt-graph, .plane-svg { width: 100%; height: 100%; display: block; }
</style>
<body data-astryx-theme="citadel">${body}</body>
</html>
`;
}

// 전체 빌드일 때만 이전 생성물을 걷어낸다 — 손으로 쓴 파일은 건드리지 않는다.
if (!only.length) {
  for (const name of ALL_PAGES) rmSync(join(DIST, `${name}.html`), {force: true});
  for (const [, name] of CSS) rmSync(join(DIST, name), {force: true});
  rmSync(join(DIST, 'fonts'), {recursive: true, force: true});
}
mkdirSync(DIST, {recursive: true});

for (const [src, name] of CSS) copyFileSync(src, join(DIST, name));
cpSync(FONTS, join(DIST, 'fonts'), {recursive: true});

const assetCount = readdirSync(ASSETS).filter(f => !f.startsWith('.')).length;

let total = 0;
for (const name of PAGES) {
  const mod = await import(`./src/pages/${name}.mjs`);
  const html = page(mod.title, renderToStaticMarkup(mod.render()));
  writeFileSync(join(DIST, `${name}.html`), html);
  total += html.length;
  console.log(`  ${name}.html  ${(html.length / 1024).toFixed(1)}KB`);
}

const faceCount = readdirSync(join(DIST, 'fonts', 'files')).length;
console.log(`\n${PAGES.length} pages · ${(total / 1024).toFixed(1)}KB · ${assetCount} assets `
  + `· 3 stylesheets · ${faceCount} font faces`);
