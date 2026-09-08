/**
 * frontend 빌드 — Vite MPA (specs/ui-overhaul-astryx TS-1).
 *
 * - 공간당 HTML 엔트리 1개. 클라이언트 라우터 없음 — stdlib 뷰어가 history
 *   fallback 없이 라우트 → dist HTML 매핑만 하면 된다.
 * - `base: '/app/'` — 뷰어가 dist 를 `/app/*` 로 서빙한다.
 * - dist 는 커밋한다(theme-citadel 정책). 청크 이름을 해시 없이 고정해
 *   재빌드 diff 소음을 줄인다 — 로컬 서빙이라 캐시 무효화 부담이 없다.
 * - `@ui` = design-system/ui (목업과 공유하는 컴포넌트 1벌). ui 의
 *   node_modules 심링크가 mockups 의 react 를 가리키므로 dedupe 로
 *   frontend 의 react 인스턴스 하나로 통일한다.
 */

import {fileURLToPath} from 'node:url';

import react from '@vitejs/plugin-react';
import {defineConfig} from 'vite';

const at = (p) => fileURLToPath(new URL(p, import.meta.url));

export default defineConfig({
  base: '/app/',
  plugins: [react()],
  resolve: {
    dedupe: ['react', 'react-dom'],
    alias: {'@ui': at('../design-system/ui')},
  },
  server: {
    fs: {allow: [at('..')]},
    proxy: {
      '/api': 'http://127.0.0.1:8791',
      '/assets': 'http://127.0.0.1:8791',
    },
  },
  build: {
    outDir: 'dist',
    rollupOptions: {
      input: {gate: at('gate.html')},
      output: {
        entryFileNames: 'js/[name].js',
        chunkFileNames: 'js/[name].js',
        assetFileNames: 'a/[name][extname]',
      },
    },
  },
});
