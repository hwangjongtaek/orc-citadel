# Orc Citadel — 일러스트 생성 프롬프트

> 목업(`docs/mockups/`)에 사용할 일러스트의 **생성 프롬프트 모음**이다. 사용자가 이미지를 생성해 전달하면 `docs/mockups/assets/`에 두고 각 화면에 연결한다.
> 모든 프롬프트는 [`DESIGN.md`](../../DESIGN.md)(Citadel Nightwatch) 팔레트와 [`blueprint.md`](../blueprint.md) §1.4 시각 원칙을 따른다.

## 0. 공통 규약

- **저장 위치:** `docs/mockups/assets/<name>.png`
- **포맷:** PNG, 투명 배경(캐릭터·아이콘·빈 상태 아트) / 불투명(히어로 배너). @2x 권장.
- **가드레일(반드시 준수):**
  - 기존 게임·판타지 IP(Warcraft 등)의 캐릭터·문장·건축·룬을 **모사하지 않는다**.
  - 과도한 녹색 발광·불꽃 파티클·돌 텍스처·장식 프레임 금지. 절제된 다크 전술-아카이브 톤.
  - 데이터 오류를 캐릭터의 실수처럼 희화화하지 않는다. Seer의 추론을 신비한 예언처럼 과장하지 않는다(차분·분석적).
  - 작은 크기에서도 식별되게 2~3개 주요 형태만. 세계관은 정보 구조 이해를 돕는 보조 역할.
- **팔레트 상수(프롬프트에 그대로 사용):**
  `void #07111C, night #0D1B2A, basalt #111820 / #26313A, stone #D6CCB8, parchment #C8B58E, war-green #45E06F, seer-green #20B85A, ember #E97824, signal-amber #FFB13B, crimson #7B2833`
- **공통 스타일 preamble(각 프롬프트 앞에 붙일 것):**

  > `Dark tactical-archive game UI art for "Orc Citadel", a temporal evidence intelligence platform. Basalt (#111820) and black-iron surfaces on a near-black navy background (#07111C–#0D1B2A). Emerald light (#45E06F) reserved ONLY for verified knowledge/graph accents — used sparingly as a focal glow, never filling the frame. Muted stone (#D6CCB8) and parchment (#C8B58E) for foreground. Restrained, serious, audit-grade mood. No excessive glow, no fire particles, no ornate frames, no stone-texture noise. Original design — do NOT imitate Warcraft or any existing game IP.`

## 1. 브랜드 문장 (Crest) — `crest-hero.png`

**용도:** 인덱스/Citadel Gate 히어로의 대형 워드마크 옆. (UI 24px 버전은 인라인 SVG 유지, 이건 고해상 브랜드용.)

> `{공통 preamble} An abstract orc heraldic crest: symmetric iron-forged tusks curving upward around a central shield, with a single small "knowledge flame" ember at the center rendered in emerald #45E06F. Sharp metallic outer edge in iron gray #59636A. Only 2–3 primary shapes, must read clearly at small size. Flat vector emblem, centered, transparent background. Not a face, not a full figure — a mark. Avoid runes or faction sigils of existing franchises.`

- 사양: 512×512, 투명 PNG, 중앙 정렬.

## 2. 히어로 씬 (Citadel Gate) — `gate-hero.png`

**용도:** `citadel-gate.html` 상단 히어로 배경/일러스트. (기존 `orc-citadel-hero.png` 재사용도 가능 — 이건 UI 최적화 와이드 변형.)

> `{공통 preamble} Wide cinematic scene: a dark basalt fortress "Citadel" at night seen from within its great hall. In the center foreground, a glowing "War Table" — a horizontal tactical table displaying a faint constellation of connected nodes and lines in emerald #45E06F (a knowledge graph, not a neon dashboard). Small orc scout silhouettes arrive from distant dark territories at the edges, carrying scrolls (ember #E97824 lantern accents). Signal spires in the far background with faint amber #FFB13B beacons. Weight of the composition is on data and evidence, not characters. Muted, atmospheric, low excessive glow. 16:6 wide banner, opaque background.`

- 사양: 2400×900, 불투명 PNG.

## 3. 캐릭터 (Orc Camp 픽셀 계보) — `char-*.png`

**용도:** onboarding·empty state·processing state·result summary. 매 화면 상시 노출 금지. **Orc Camp의 픽셀 캐릭터 비율·방향**을 재사용하되 Citadel 전용 전문 직책으로.

공통 캐릭터 스타일:
> `{공통 preamble} Pixel-art character sprite (16-bit era proportions, chunky readable pixels), single orc figure, front-facing, standing, transparent background, ~256px tall, no ground shadow baked in. Green-skinned orc but in a scholarly/military archive role, NOT a rage-berserker. Calm, competent, professional posture.`

| 파일 | 역할(기술) | 프롬프트 추가 지시 |
| --- | --- | --- |
| `char-scout.png` | Scout (수집) | `A Scout: light leather gear, a satchel overflowing with rolled scrolls/reports, a small ember #E97824 lantern at the belt. Ready-to-travel stance.` |
| `char-archivist.png` | Archivist/Lorekeeper (정규화·동일성 판정) | `An Archivist-Lorekeeper: robed scholar orc holding a ledger and a quill, parchment #C8B58E scrolls tucked under arm, spectacles. Careful, precise expression.` |
| `char-seer.png` | Seer (LLM 추론) | `A Seer: orc analyst holding a compact glowing orb/lens emitting a restrained seer-green #20B85A light, studying it analytically (not mystically). A dashed emerald thread of reasoning near the orb. Thoughtful, skeptical look — an investigator, not a fortune-teller.` |
| `char-warchief.png` | Warchief / Council (조사 종합) | `A Warchief presiding at a war table: armored but composed orc leader, one hand on the tactical table edge, emerald #45E06F node-lines faintly reflected. Authoritative, deliberative — leading an evidence council, not a battle charge.` |

## 4. 빈 상태 아트 (Empty States) — `empty-*.png`

**용도:** 각 공간의 데이터 없음 상태. 작고 절제된 씬. 투명 배경, ~360px.

| 파일 | 화면 | 프롬프트 추가 지시 |
| --- | --- | --- |
| `empty-wartable.png` | War Table (조사 미선택) | `{공통 preamble} A dim, empty War Table with only a few faint unconnected node dots in iron gray, one waiting to be lit emerald. Quiet "awaiting investigation" mood. Small, centered spot illustration, transparent background.` |
| `empty-watchtower.png` | Watchtower (모든 소스 정상) | `{공통 preamble} A calm watchtower silhouette at night with steady (not blinking) small amber #FFB13B beacons and an orc scout resting — "all sources healthy" mood. Restrained. Transparent background.` |
| `empty-spire.png` | Signal Spire (새 알림 없음) | `{공통 preamble} A single unlit signal spire against the night, one small dormant amber #FFB13B ember at its tip — "no material changes" mood. Minimal, transparent background.` |
| `empty-archive.png` | Grand Archive (검색 결과 없음) | `{공통 preamble} A basalt archive shelf with a few parchment #C8B58E scrolls and one empty slot, a small magnifier — "no documents found" mood. Minimal spot illustration, transparent background.` |

## 5. 처리 상태 아트 (Processing) — `proc-*.png`

**용도:** 긴 작업 진행 표현(수집·조사 루프). 애니메이션은 CSS로, 여기선 정지 프레임.

| 파일 | 상태 | 프롬프트 추가 지시 |
| --- | --- | --- |
| `proc-scout.png` | 수집 중 | `{공통 preamble} A small orc scout mid-stride carrying a report scroll, a faint ember #E97824 motion trail behind — "ingesting" mood. Side profile, transparent background, ~200px.` |
| `proc-seer.png` | 조사/추론 중 | `{공통 preamble} A Seer tracing a dashed emerald #45E06F path between two faint nodes with a fingertip — "reasoning over the graph" mood. Analytical, calm. Transparent background, ~200px.` |

## 6. 연결 계획 (전달 후)

이미지 수령 시 각 목업에 아래처럼 연결한다.
- `index.html` / `citadel-gate.html` 히어로 → `crest-hero.png`, `gate-hero.png`.
- 각 화면 empty state 컴포넌트에 `empty-*.png` + 안내 문구(기능명 병기).
- Council Chamber 진행·Watchtower 수집 중 → `proc-*.png`.
- 캐릭터는 onboarding·result summary 카드에 한정 노출(상시 금지).

> 파일명을 위 규약대로 주시면 `assets/`에 배치하고 `<img>`(또는 배경)로 연결, `prefers-reduced-motion` 및 대체 텍스트를 함께 처리한다.
