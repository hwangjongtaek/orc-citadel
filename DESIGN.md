---
version: alpha
name: Citadel Nightwatch
description: >-
  Orc Citadel의 다크 전술-아카이브 테마. 어두운 석재(Basalt) 표면 위에서
  검증된 evidence trail과 지식 그래프만 빛나게 하는 Temporal Evidence
  Intelligence UI를 위한 디자인 토큰. 세계관은 정보 구조를 이해시키는
  역할이며 정확성·가독성·감사 가능성을 방해하지 않는다.

colors:
  # Surfaces — Basalt & Night (어두운 석재 셸)
  citadel-void: "#07111C"      # 앱 최외곽 배경
  citadel-night: "#0D1B2A"     # 주요 페이지 배경
  surface: "#111820"           # 패널·사이드바 (basalt-900)
  surface-variant: "#26313A"   # 패널 경계·비활성 표면 (basalt-700)

  # Foreground — Stone & Parchment
  on-surface: "#D6CCB8"        # 기본 전경·제목 (carved stone)
  on-surface-muted: "#59636A"  # 보조 텍스트·아이콘 (iron-500)
  parchment: "#C8B58E"         # 문서·기록 메타데이터, 원문 인용

  # Graph & Evidence — Emerald (브랜드 장식색이 아닌 "검증" 신호)
  primary: "#45E06F"           # war-green — 검증된 연결·선택된 그래프 경로
  secondary: "#20B85A"         # seer-green — LLM 추론·발견 후보

  # Signals — Ember & Amber
  ember: "#E97824"             # 활성 상태·주의·실시간 수집(ingestion) 신호
  signal-amber: "#FFB13B"      # 신규 정보·Signal Spire·qualifies

  # Brand
  crimson: "#7B2833"           # 브랜드 배너·중요 섹션 표식

  # Status
  error: "#E05252"             # contradiction — 반박·모순·실패
  uncertain: "#A78BFA"         # 미확정 관계·quarantine
  superseded: "#59636A"        # 대체된 이전 버전 (흐린 iron)

typography:
  # Display — 워드마크/마케팅 전용 (석재에 새긴 인상)
  headline-display:
    fontFamily: Cinzel
    fontSize: 56px
    fontWeight: 700
    lineHeight: 1.05
    letterSpacing: 0.04em
  # Headlines — 제품 UI 제목 (장식 적은 굵은 sans)
  headline-lg:
    fontFamily: Space Grotesk
    fontSize: 32px
    fontWeight: 600
    lineHeight: 1.15
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Space Grotesk
    fontSize: 22px
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: -0.01em
  # Body — 본문·테이블 (높은 가독성)
  body-lg:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: 400
    lineHeight: 1.6
  body-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.6
  body-sm:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.5
  # Labels — 배지·탭·상태 라벨
  label-lg:
    fontFamily: Space Grotesk
    fontSize: 14px
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: 0.02em
  label-md:
    fontFamily: Space Grotesk
    fontSize: 12px
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: 0.04em
  label-sm:
    fontFamily: Space Grotesk
    fontSize: 11px
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: 0.08em
  # Data — ID·hash·query·timestamp·source span (monospace 필수)
  data-md:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.5

rounded:
  none: 0px
  sm: 4px
  md: 8px
  lg: 12px
  xl: 16px
  full: 9999px

spacing:
  base: 8px
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
  "2xl": 48px
  gutter: 24px
  margin: 32px
  content-max: 1200px

components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.citadel-void}"
    rounded: "{rounded.md}"
    padding: 12px
    fontStyle: "{typography.label-lg}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    borderColor: "{colors.surface-variant}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.md}"
    padding: 12px
  panel:
    backgroundColor: "{colors.surface}"
    borderColor: "{colors.surface-variant}"
    rounded: "{rounded.lg}"
    padding: 16px
  input:
    backgroundColor: "{colors.surface-variant}"
    borderColor: "{colors.surface-variant}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.md}"
    padding: 12px
  graph-node:
    backgroundColor: "{colors.surface}"
    borderColor: "{colors.surface-variant}"
    textColor: "{colors.on-surface-muted}"
    rounded: "{rounded.full}"
  graph-node-selected:
    backgroundColor: "{colors.surface}"
    borderColor: "{colors.primary}"
    textColor: "{colors.on-surface}"
    glowColor: "{colors.primary}"
    rounded: "{rounded.full}"
  edge-supports:
    strokeColor: "{colors.primary}"
    strokeStyle: solid
  edge-contradicts:
    strokeColor: "{colors.error}"
    strokeStyle: double
  edge-qualifies:
    strokeColor: "{colors.signal-amber}"
    strokeStyle: dashed
  edge-uncertain:
    strokeColor: "{colors.uncertain}"
    strokeStyle: dashed
  edge-superseded:
    strokeColor: "{colors.superseded}"
    strokeStyle: dotted
  evidence-card:
    backgroundColor: "{colors.surface}"
    borderColor: "{colors.surface-variant}"
    accentColor: "{colors.parchment}"
    rounded: "{rounded.md}"
    padding: 16px
  source-span:
    backgroundColor: "{colors.surface-variant}"
    textColor: "{colors.parchment}"
    fontStyle: "{typography.data-md}"
    rounded: "{rounded.sm}"
  signal-spire-alert:
    backgroundColor: "{colors.surface}"
    accentColor: "{colors.signal-amber}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.md}"
  chronicle-entry:
    backgroundColor: "{colors.citadel-night}"
    accentColor: "{colors.parchment}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.md}"
---

# Citadel Nightwatch — Orc Citadel Design System

Orc Citadel의 시각 언어를 정의하는 DESIGN.md. UI는 "판타지 스킨을 씌운 관리자 페이지"가 아니라 **Citadel 안에서 세계의 보고를 검증하고 전황도(War Table)를 갱신하는 지식 작업 공간**처럼 느껴져야 한다. 시각적 무게 중심은 장식이나 캐릭터가 아니라 **데이터와 근거**다. 상세 콘셉트는 [`docs/blueprint.md`](docs/blueprint.md) §1.4 참조.

## Overview

**Brand & Style.** 차분하고 밀도 높은 다크 전술-아카이브 인터페이스. 어두운 석재(Basalt)와 흑철(Black iron) 위에서 검증된 연결과 신규 신호만 빛난다.

- **Tone:** 진중하고 감사 가능하며, 근거를 앞세운다. 신비주의·과장 없이 불확실성을 정직하게 표시한다.
- **Audience:** 공급망·정책·기업 정보를 조사하는 분석가와 연구자. 정확성과 추적 가능성을 신뢰의 근거로 삼는다.
- **Emotional response:** "이 결론이 어떤 증거에서 왔는지 즉시 추적할 수 있다"는 통제감.
- **Foundational rule:** 특정 규칙·토큰이 정의되지 않은 경우, 가독성과 대비를 우선하고 어두운 표면 위 절제된 강조를 기본값으로 삼는다.

## Colors

팔레트는 **고대비 중성 석재(neutrals) + 단일 검증 신호(emerald)** 구조다. 화면 전체를 녹색으로 채우지 않는다. 에메랄드는 브랜드 장식색이 아니라 **지식 그래프와 검증된 evidence trail** 전용이며, 어두운 배경 위에서 중요한 연결과 상호작용만 빛나게 한다.

- `primary` (war-green) — 검증된 관계·선택된 그래프 경로에만 사용. 일반 버튼 남용 금지.
- `secondary` (seer-green) — LLM이 추론한 발견 후보. 확정 전 상태.
- `ember` / `signal-amber` — 실시간 수집과 신규 정보. 무한 반복 점멸 금지.
- `parchment` — 원문 인용·Scout Report·Chronicle entry의 기록 표면.
- `error` / `uncertain` / `superseded` — 상태 색은 색만으로 의미를 전달하지 않는다. 아이콘·선 형태·라벨을 병기한다.

```yaml
colors:
  citadel-night: "#0D1B2A"
  surface: "#111820"
  on-surface: "#D6CCB8"
  primary: "#45E06F"      # 검증된 연결
  error: "#E05252"        # 모순
  uncertain: "#A78BFA"    # 미확정
```

## Typography

- **Display (`headline-display`)** — `ORC CITADEL` 워드마크와 마케팅 대형 제목. 석재에 새긴 듯한 디스플레이. 긴 보고서·원문에는 사용하지 않는다.
- **Headlines (`headline-lg`/`headline-md`)** — 제품 UI 제목. 장식이 적은 굵은 sans-serif.
- **Body (`body-*`)** — 본문·테이블. 높은 가독성의 sans-serif.
- **Labels (`label-*`)** — 탭·배지·상태 라벨. 넓은 letter-spacing으로 게임적 상태 표현.
- **Data (`data-md`)** — ID, hash, query, timestamp, source span은 반드시 monospace.

> 픽셀 폰트는 워드마크·작은 배지·게임적 상태 표현에만 제한한다. 한 화면에서 두 개를 초과하는 font weight를 쓰지 않는다.

## Layout

**Layout & Spacing.** 엄격한 8px 스페이싱 스케일. 데스크톱은 최대 폭 1200px의 고정 그리드, 모바일은 유동 그리드를 사용한다.

핵심 화면인 War Table은 **3+1 패널 구조**를 기본으로 한다.

```text
┌──────────────────────────────────────────────────────────────────┐
│ Citadel Header · Campaign · Time · Search · Signal Spire          │
├───────────────┬──────────────────────────────┬───────────────────┤
│ Campaign Map  │          War Table           │ Evidence Inspector│
│ (좌 패널)      │   Temporal Knowledge Graph   │ (우 패널)          │
├───────────────┴──────────────────────────────┴───────────────────┤
│ Chronicle · ingestion & investigation event timeline (하단)       │
└──────────────────────────────────────────────────────────────────┘
```

- **Desktop:** War Table 중심, 좌측 Campaign / 우측 Evidence / 하단 Chronicle.
- **Tablet:** Evidence Inspector를 drawer로 전환.
- **Mobile:** 그래프 전체 조작 대신 `claim 목록 → evidence → source trail`의 선형 탐색을 우선한다.

각 화면은 Citadel의 공간(Watchtower, Grand Archive, Hall of Witnesses, War Table, Council Chamber, Chronicle Vault, Signal Spire)에 대응하지만, **URL·API 명칭에는 기술 용어를 우선한다** (예: UI `War Table`, 경로 `/investigations/:id/graph`).

## Elevation & Depth

그림자에 의존하지 않는 **평면 + 경계 + 선택적 발광** 모델로 시각 위계를 전달한다.

- **Basalt tonal layers:** `citadel-void` → `citadel-night` → `surface` → `surface-variant` 순의 명도 단계로 깊이를 표현한다.
- **Black iron borders:** 패널·탭·도구 모음의 구조적 구분은 그림자 대신 `surface-variant` 경계선으로 처리한다.
- **Selective glow:** 발광은 장식이 아니라 상태다. 선택된 claim의 검증 trail(`primary`)과 실시간 수집(`ember`)에만 짧게 적용하고 무한 반복하지 않는다.
- 텍스처와 발광은 배너·빈 상태·온보딩 등 감성적 맥락에서만 적극 사용한다. 데이터 테이블·긴 문서·설정 화면은 단색 표면과 절제된 테두리를 유지한다.
- `prefers-reduced-motion`에서는 점등·이동·파티클을 제거한다.

## Shapes

일관된 rounded 스케일을 사용하고 **한 화면에서 rounded와 sharp corner를 혼용하지 않는다**.

```yaml
rounded:
  sm: 4px      # 배지·source-span 칩
  md: 8px      # 버튼·입력·카드 기본
  lg: 12px     # 패널
  full: 9999px # 그래프 노드·아바타
```

브랜드 문장(crest)은 UI 컴포넌트와 별개로, 날카로운 철제 외곽·대칭 엄니·중앙 지식 불꽃의 독자적 형태를 사용한다. 문장은 브랜드 식별 전용이며 데이터 상태 아이콘으로 재사용하지 않는다.

## Components

컴포넌트 원자의 스타일 가이드. 값은 위 토큰을 참조한다.

- **Buttons** — `button-primary`는 검증된 주요 액션(예: 조사 실행)에, `button-secondary`는 보조 액션에. `primary`(emerald)는 화면당 가장 중요한 단일 액션에만.
- **Panel / Input** — 어두운 `surface` 위 `surface-variant` 경계. 그림자 없음.
- **Graph node** — 크기는 시각적 인기가 아니라 **조사 내 중요도와 evidence coverage**를 반영한다. 선택하지 않은 노드는 낮은 대비를 유지하고, `graph-node-selected`만 `primary` 발광으로 강조한다.
- **Edge (관계 엣지)** — 아래 *Evidence Relationship States* 참조. 색 외에 선 형태로도 구분한다.
- **Evidence card / Source span** — 원문 provenance. `source-span`은 monospace(`data-md`)로 표시하고 그래프에서 Hall of Witnesses 패널로 자연스럽게 이어진다.
- **Signal Spire alert** — 중요한 변화에 한해 `signal-amber`로 한 번 점화.
- **Confidence indicator** — 단일 색상 게이지 금지. **값 + 근거 수 + 독립 출처 수 + 계산 근거**를 함께 표시한다.

Variants는 hover·active·pressed 등 UI 상태별로 관련 key 이름(`button-primary-hover`)의 별도 엔트리로 정의한다.

## Evidence Relationship States

*(도메인 확장 섹션)* War Table 엣지의 관계 유형. **색상만으로 의미를 전달하지 않으며** 선 형태·표식·라벨을 병기한다. `supports`를 "진실", `contradicts`를 "거짓"으로 단순화하지 않는다.

| 상태          | 토큰                   | 선 형태 (strokeStyle) | 그래프 표현            |
| ------------- | ---------------------- | --------------------- | ---------------------- |
| `supports`    | `edge-supports`        | 실선 (solid)          | 실선 + 확인 표식       |
| `contradicts` | `edge-contradicts`     | 이중선 (double)       | 이중선/절단선 + 반박 표식 |
| `qualifies`   | `edge-qualifies`       | 점선 (dashed)         | 점선 + 범위 표식       |
| `uncertain`   | `edge-uncertain`       | 점선 (dashed)         | 점선 + 물음표 표식     |
| `superseded`  | `edge-superseded`      | 점선 (dotted)         | 흐린 선 + 시간 화살표  |

시간 슬라이더 조작 시 노드를 사라지게 하는 대신 valid time과 transaction time의 상태 변화를 구분해 보여준다.

## Do's and Don'ts

생성·구현 중 지켜야 할 가드레일.

- **Do** 본문·인터랙티브 요소에 WCAG AA 이상(정상 텍스트 4.5:1) 대비를 유지한다.
- **Do** 관계 유형을 색상 + 아이콘 + 선 패턴 + 텍스트로 중복 표현한다 (색맹 접근성).
- **Do** 선택하지 않은 그래프 전체를 낮은 대비로 두고, 선택한 claim의 support·contradiction trail만 밝게 강조한다.
- **Do** 세계관 명칭에 기능명을 병기한다 (예: `War Table · Graph`, `Chronicle · History`). 모바일에서도 단독 표시 금지.
- **Do** confidence·agent inference를 원문·claim과 시각적으로 명확히 분리한다.
- **Don't** 100개 이상 노드를 한 번에 렌더링하지 않는다. investigation subgraph와 progressive disclosure를 사용한다 (hairball 금지).
- **Don't** `supports = 진실`, `contradicts = 거짓`으로 단순화하지 않는다.
- **Don't** LLM Agent의 추론을 신비한 예언처럼 포장하지 않는다. 근거와 불확실성을 함께 노출한다.
- **Don't** 과도한 녹색 발광·불꽃·돌 텍스처·장식 프레임을 사용하지 않는다.
- **Don't** 긴 보고서·원문에 픽셀/디스플레이 폰트를 사용하지 않는다.
- **Don't** 한 화면에서 두 개를 초과하는 font weight 또는 rounded/sharp 혼용을 하지 않는다.
