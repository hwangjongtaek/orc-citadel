# mockups — Citadel 8공간 정적 목업

[Astryx](https://astryx.atmeta.com/) + [`theme-citadel`](../theme-citadel/) 로 저작하는 Citadel 8공간 목업.

**저작 소스는 여기(`src/`), 출력은 [`docs/mockups/`](../../docs/mockups/)** — 목업의 정본 위치다. 손으로 HTML 을 고치지 말 것. 고쳐도 다음 빌드에 덮어쓰인다.

**산출물은 정적 HTML 이다.** Astryx 컴포넌트를 `renderToStaticMarkup` 으로 빌드 시점에 구워서, 결과물에는 클라이언트 JS 가 한 줄도 없다 — HTML + CSS 3장 + assets 뿐. React 는 `theme-citadel` 의 `astryx theme build` 와 같은 지위의 **저작 도구**다.

## 빌드

```bash
npm install
npm run build              # 10 페이지 전체 → docs/mockups/
node build.mjs war-table   # 저작 중 한두 페이지만
```

생성물(`docs/mockups/*.html` · `*.css` · `fonts/`)은 커밋한다. `docs/mockups/` 에는 **생성물이 아닌 것도 산다** — 손으로 쓴 `illustration-prompts.md` 와 히어로·초상 PNG 22종(`assets/`). 빌드는 디렉터리를 통째로 지우지 않고 자기가 만드는 파일만 이름으로 덮어쓴다.

회귀 가드는 `prototype/tests/test_mockups_build.py` (node 불필요).

## 구조

```
build.mjs          SSG 드라이버 — 렌더 → HTML, CSS·폰트·assets 복사
src/shell.mjs      공유 셸 (헤더·공간 탭·마스트헤드 히어로 밴드)
src/ui.mjs         Astryx 위의 얇은 헬퍼 + 도메인 시각 요소
src/svg/*.svg      원본 목업에서 옮긴 도메인 SVG
src/pages/*.mjs    페이지 10개
```

`src/ui.mjs` 에 들어가는 것은 두 부류뿐이다 — (1) Astryx 조합 단축, (2) Astryx 에 대응 컴포넌트가 **없는** 도메인 시각 요소. 새 스타일을 여기서 발명하지 말 것. 값은 전부 theme-citadel 토큰을 참조한다.

## 저작 규약

**JSX 를 쓰지 않는다.** `React.createElement`(`h`)로만 저작해 번들러 없음 성질을 유지한다. 빌드 파이프라인은 `node build.mjs` 한 줄이 전부다. JSX/TS 도입은 Phase 3(React 파일럿) 게이트에서 별도로 판단한다.

닫는 괄호가 어긋나기 쉬우니 저작 후 문법 검사를 돌린다:

```bash
for f in src/**/*.mjs; do node --check "$f"; done
```

## 원본 대비 의도적 차이

| 차이 | 이유 |
| --- | --- |
| **공간 탭 추가** | 원본은 페이지끼리 링크가 없어 `index.html` 로만 오갔다. 목업 자체를 순회할 수 있게 셸에 넣었다 (뷰어 현행과 동일) |
| **토큰 공유** | 원본은 페이지마다 `:root` + 컴포넌트 CSS 를 복제했다 (9개 파일 `<style>` 2,541줄 = 전체의 48%). theme-citadel 한 곳으로 접었다 |
| **레이아웃 원시요소** | 손으로 쓴 `grid-template-columns` → Astryx `Layout` 의 `header`/`start`/`content`/`end`/`footer` 슬롯. 패널이 독립 스크롤된다 |
| **히어로 크기 정책** | 원본은 전 페이지가 132px 고정 밴드였다. 히어로가 전부 1920×720(8:3)이라 `cover` 로 넣으면 **세로 23% 만 보인다.** 페이지 유형에 따라 나눴다 (아래) |

## 히어로 크기 정책

`shell()` 이 슬롯 구성에서 자동으로 고른다. `heroFit: 'full' | 'band'` 로 덮어쓸 수 있다.

| 유형 | 조건 | 히어로 | Layout height |
| --- | --- | --- | --- |
| 문서형 | `start`·`end` 패널 없음 (index · Citadel Gate · Watchtower · empty-states) | `aspect-ratio: 8/3` — **그림 전체** | `auto` (자연 스크롤) |
| 앱셸 | 좌·우 패널 있음 (나머지 6공간) | 132px 압축 밴드 | `fill` (패널 독립 스크롤) |

앱셸 페이지에 8:3 히어로를 쓰면 3열 본문이 화면 밖으로 밀린다. 반대로 문서형 페이지를 `height: 'fill'` 로 두면 헤더가 뷰포트 안으로 눌려 8:3 이 도로 잘린다 — 둘은 세트다.

스크림도 갈린다: full 은 아래에서 위로 걷혀(글자만 덮고 그림 본체는 살림), band 는 좌→우 로 걷힌다.

**함정:** 마스트헤드에 `width: 100%` 가 없으면 `LayoutHeader` 의 flex 자식이라 폭이 콘텐츠로 접히고, `aspect-ratio` 가 그 접힌 폭 기준으로 계산돼 히어로가 조각으로 나온다.

## 남은 갭

- **한글 폰트** — 라틴 4서체는 [`../fonts/`](../fonts/) 에서 로컬 vendoring 되어 적용된다. 다만 이 서체들에 한글 글리프가 없어 **Hangul 은 시스템 폰트 폴백**이다(원본 목업도 동일). 한글 서체 도입은 DESIGN.md 에 정의가 없어 범위 밖.
- **도메인 시각화** — 그래프 캔버스·bitemporal plane 은 Astryx 에 대응 컴포넌트가 없어 원본 SVG 를 `src/svg/` 로 옮겨 그대로 쓴다. 관계 엣지 범례도 마찬가지 — DESIGN.md 가 "색만으로 의미 전달 금지·선 형태 병기"를 요구하는데 Badge 로는 실선·이중선·점선을 표현할 수 없다.
- **상호작용** — 원본과 동일하게 정적이다. 탭·드롭다운이 실제로 동작하려면 하이드레이션이 필요하고, 이는 별도 결정 사항이다.

## 원본

재작성 이전의 손으로 쓴 목업(2026-08-03)은 `docs/mockups/` 를 덮어쓰기 전 커밋에 남아 있다. 갭 분석(`docs/handoff-viewer-mockup-gap.md`)의 기준선이 그 판본이다.

```bash
git log --oneline -- docs/mockups/war-table.html
git show <재작성-직전-커밋>:docs/mockups/war-table.html
```
