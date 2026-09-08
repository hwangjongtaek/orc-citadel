# ui — 목업·앱 공용 컴포넌트 (단일 소스)

[specs/ui-overhaul-astryx](../../specs/ui-overhaul-astryx/specs.md) TS-2 의 산출물. 셸·컴포넌트·도메인 SVG 를 **1벌**로 두고, 두 소비자가 같은 모듈을 import 한다:

- **목업** `design-system/mockups/` — 하드코딩 샘플 데이터로 SSG (`docs/mockups/` 커밋)
- **앱** `frontend/` — `/api/*` 실데이터로 CSR (Vite)

컴포넌트 수정 1회가 목업·앱 양쪽에 동시에 반영된다 — 목업↔실UI 갭이 구조적으로 생길 수 없다.

## 저작 규약 (mockups 규약 승계)

- **no-JSX** — `React.createElement`(`h`)로만 저작한다. 목업 빌드가 번들러 없이 소비해야 하기 때문. JSX 는 `frontend/` 내부에서만.
- **props-only·프레젠테이셔널** — 데이터 fetch·상태를 여기서 소유하지 않는다. 상호작용은 콜백 props 로 받는다(목업에선 미배선 → 클라이언트 JS 0 유지).
- **새 스타일 발명 금지** — 값은 전부 theme-citadel 토큰 참조.
- 저작 후 `node --check` 문법 검사.

## node_modules 심링크

이 디렉터리는 자체 `package.json` 이 없다. `node_modules -> ../mockups/node_modules` 심링크로 react·`@astryxdesign/core` 를 해석한다 — 목업 빌드(`renderToStaticMarkup`)와 컴포넌트가 **같은 react 인스턴스**를 쓰게 하기 위해서다(이중 설치 시 인스턴스 불일치 위험). `frontend/`(Vite)는 `resolve.dedupe` 로 자신의 react 로 통일한다.

## 파일

| 파일 | 내용 |
| --- | --- |
| `shell.mjs` | 페이지 셸 — 헤더(로고·2계층 내비·⌘K 검색)·히어로 밴드·Layout 배선 |
| `components.mjs` | Astryx 조합 단축 + 도메인 시각 요소 (confidence·coverage·evidenceCard·statTile…) |
| `svg/` | Astryx 에 대응물이 없는 도메인 SVG (graph·bitemporal plane) |
