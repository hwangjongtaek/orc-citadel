# fonts — DESIGN.md 4역할 폰트 vendoring

[`DESIGN.md`](../../DESIGN.md) typography 절이 지정한 네 서체를 **로컬 woff2 + `@font-face`** 로 굽는다.

**왜 vendoring 인가.** 뷰어·목업 모두 **외부 CDN 금지**가 규약이다(오프라인 전제). Astryx 테마는 `font-family` 이름만 선언하고 "폰트 로딩은 소비자 책임"이라 명시하므로, 그 소비자 몫을 여기서 한 번 처리한다. 생성물(`dist/`)을 커밋해 런타임·배포에 node 가 필요 없다 — [`theme-citadel`](../theme-citadel/) 과 같은 정책.

## 빌드

```bash
npm install
npm run build
```

## 담는 것

`DESIGN.md` 가 실제로 쓰는 (서체 × 굵기)만 가져온다. 전 굵기를 받으면 6MB 가 넘는다.

| 역할 | 서체 | 굵기 | 쓰임 |
| --- | --- | --- | --- |
| display | Cinzel | 700 | 워드마크 |
| heading | Space Grotesk | 500 · 600 | 제목 · 라벨 · 배지 |
| body | Inter | 400 · 600 | 본문 · 테이블 |
| code | JetBrains Mono | 400 | ID · hash · timestamp · source span |

서브셋은 `latin` + `latin-ext` 만 (키릴·그리스는 이 도메인에서 안 쓴다). **12 faces · 217KB.**

네 서체 모두 **SIL OFL-1.1** 이라 재배포가 허용된다. 라이선스 원문을 `dist/LICENSE-*.txt` 로 동봉한다.

## 한계 — 한글은 폴백이다 (정직)

Cinzel·Space Grotesk·Inter·JetBrains Mono 는 **한글 글리프가 없다.** UI 본문 상당수가 한글이라 Hangul 은 시스템 폰트로 폴백한다. 원본 목업(`docs/mockups/*.html`)도 같은 서체 조합이라 동일했다. 즉 이 vendoring 이 실제로 바꾸는 것은 **워드마크·라벨·ID·수치 등 라틴 글리프**다.

한글 서체(Pretendard·Noto Sans KR 등) 도입은 `DESIGN.md` 에 정의가 없어 범위 밖이다. 필요하면 별도 결정 사항 — 용량이 크므로(수 MB) subset 전략을 함께 정해야 한다.

## 저작 시 함정

**`unicode-range` 를 빼면 안 된다.** 서브셋이 둘이라 같은 `font-family` + `font-weight` 선언이 두 번 나오는데, 범위가 없으면 **뒤엣것(latin-ext)이 앞(latin)을 덮어 기본 라틴 글리프가 통째로 사라진다.** 조용히 깨지는 종류라 눈치채기 어렵다. 값은 손으로 적지 않고 fontsource 의 굵기별 CSS 를 파싱해 가져온다.

## 소비

```html
<link rel="stylesheet" href="/assets/fonts/fonts.css" />
```

`theme-citadel` 이 `--font-family-body` 등에 이름을 선언하고, 이 파일이 그 이름에 실제 파일을 물린다. 둘 다 있어야 동작한다.

## 회귀 가드

`prototype/tests/test_fonts_vendored.py` — DESIGN.md 역할·굵기 충족, `unicode-range` 존재 및 latin/latin-ext 범위 비중첩, woff2 실재, 외부 호스트 참조 0, OFL 동봉, 목업 링크 연결. node 불필요.
