/**
 * node 전용 SVG 로더 — 목업 SSG 빌드에서만 import 한다.
 *
 * `components.mjs` 는 브라우저 번들(frontend)에 들어가므로 node API 를 둘 수
 * 없어 파일 로딩을 여기로 분리했다. 앱은 Vite 의 `?raw` import 로 같은
 * `ui/svg/*.svg` 를 문자열로 받아 `svgBlock` 에 넘긴다.
 */

import {readFileSync} from 'node:fs';
import {dirname, join} from 'node:path';
import {fileURLToPath} from 'node:url';

import {svgBlock} from './components.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));

/** `ui/svg/<name>.svg` 를 읽어 svgBlock 으로 감싼다 (구 rawSvg 와 동일 계약). */
export function rawSvg(name, opts = {}) {
  return svgBlock(readFileSync(join(HERE, 'svg', `${name}.svg`), 'utf8'), opts);
}
