# Plans: 비개발자용 프로젝트 소개 및 조사 흐름 HTML 페이지

> Created: 2026-09-20
> Updated: 2026-09-21
> Status: Complete
> Requirements: [requirements.md](./requirements.md)
> Specs: [specs.md](./specs.md)

## Overview

정적 HTML 목업 → shared props-only presentation component → `/about` Vite MPA → Watchtower component reachability 기반 link enhancement → committed dist → 실제 브라우저 검증 순서로 구현했다. 소개 페이지는 기존 8개 공간 밖의 utility page이며, 핵심 설명은 API와 무관하게 즉시 렌더된다.

## Implementation Steps

1. **Static guide** — hero, 가치, 예시 지시, 2-lane flow, Technology Map, provenance, 결과, Now/Next, 실험 도구, 안전 경계를 공용 presenter로 구성한다.
2. **Production entry** — `frontend/about.html`과 `frontend/src/pages/about/main.jsx`에서 같은 presenter를 `APP_URLS`로 조립한다.
3. **Runtime enhancement** — `/api/watchtower`의 `components[]`만 읽고 allowlist URL builder로 도달 가능한 도구 링크만 만든다.
4. **Navigation and route** — Gate 브랜드 영역의 일반 링크, Vite MPA input, viewer `/about` canonical route를 연결한다.
5. **Generated artifacts** — mockup과 `frontend/dist/`를 소스에서 다시 생성한다.
6. **Verification** — route·bundle·mockup 회귀, error/unreachable/reachable 상태, desktop/mobile/320px reflow를 검증한다.

## Task Breakdown

- [x] 공용 소개 presenter와 Technology Map을 완성한다.
- [x] 첫 화면 비교·investigation lifecycle·confidence·Now/Next truth boundary를 명시한다.
- [x] mobile 4:3 center crop과 copy-before-image reflow, semantic section label, AA header text를 적용한다.
- [x] allowlisted `component-link.js`를 About과 Watchtower가 공유하게 한다.
- [x] Gate 안내 링크, Vite `about` entry, viewer `/about` route를 연결한다.
- [x] frontend/mockup generated artifacts를 다시 만든다.
- [x] production·mockup·viewer 회귀 테스트를 갱신한다.
- [x] desktop 1440×1000, mobile 390×844, 320px에서 브라우저 검증한다.

## Testing Strategy

- `uv run pytest tests/test_frontend_dist.py -q` — 9개 entry, `/about` route/503, Gate link, 소개 copy/lifecycle/tool policy.
- `uv run pytest tests/test_mockups_build.py -q` — 정적 HTML, no-JS, hero/mobile CSS, landmark label, asset 계약.
- `uv run pytest tests/test_viewer_static.py -q` — canonical/static route와 MIME·cache 계약.
- Browser desktop 1440×1000 — 단일 `h1`, 9 sections, error state 격리, 가로 overflow 없음.
- Browser mobile 390×844 — copy가 4:3 image 앞에 배치, 기술 지도 1열, reachable 도구 5종 URL/`rel` 확인.
- Browser 320px — utility shell과 전체 문서 가로 overflow 없음, hero picture 320×240.
- About이 실제 로드하는 5개 JS chunk gzip 합계는 122.81 KiB로 150 KiB budget 이내다.

## Rollback Plan

`/about`을 되돌릴 때는 viewer `_MIGRATED`와 Vite input에서 entry를 제거하고, Gate의 `urls.about` 링크와 About 전용 source/HTML을 함께 제거한 뒤 `frontend/dist/`와 두 mockup HTML을 다시 생성한다. Watchtower가 계속 사용하는 `component-link.js`와 보안 수정(`noopener noreferrer`)은 독립 개선이므로 유지한다.

## Progress Tracking

| Step | Status | Notes |
|---|---|---|
| Specs review | Passed | 독립 review에서 BLOCKER/MAJOR 해소 후 Stable 전환 |
| Static mockup | Passed | 공용 presenter, index/Gate link, 1920/960 banner, generated HTML |
| Technology Map | Passed | 7개 현재/실험 단계 + Iceberg/S3/Kafka/Ray 확장 후보와 정본/파생 경계 |
| Production `/about` | Passed | Vite MPA, viewer route, committed dist, API 실패와 component reachability 보강 |
| Accessibility/responsive | Passed | 1 h1, 9 named sections, skip link, AA header text, 720px stepper, 320px no-overflow |
| Verification | Passed | frontend 53, mockup 63, viewer-static 15 tests 및 1440/390/320 browser checks |
