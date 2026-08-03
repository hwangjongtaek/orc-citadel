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

## 2. 화면별 씬(히어로) 프롬프트 (복붙용)

각 화면 상단 히어로/배경 이미지의 생성 프롬프트. **preamble을 각 프롬프트에 포함**했으므로 아래 코드블록을 그대로 복사해 쓰면 된다(반복 무관). 모두 `gate-hero.png`와 동일한 시네마틱 다크 전술-아카이브 스타일.

- **파일명:** `docs/mockups/assets/<screen>-hero.png`
- **사양:** 1920×720 (16:6 와이드), 불투명 PNG. **상단은 어둡게** — 워드마크/제목을 오버레이할 여백(스크림)을 위해.
- **연결:** 각 화면의 히어로/헤더 배경으로 `center bottom / cover` + 다크 스크림(→ `citadel-gate.html` §hero 참고).

### 2.0 Citadel Gate — `gate-hero.png` ✅ (제공·연결 완료)

```text
Dark tactical-archive game UI art for "Orc Citadel", a temporal evidence intelligence platform. Basalt (#111820) and black-iron surfaces on a near-black navy background (#07111C to #0D1B2A). Emerald light (#45E06F) reserved ONLY for verified knowledge/graph accents, used sparingly as a focal glow, never filling the frame. Muted stone (#D6CCB8) and parchment (#C8B58E) for foreground. Restrained, serious, audit-grade mood. No excessive glow, no fire particles, no ornate frames, no stone-texture noise. Original design — do NOT imitate Warcraft or any existing game IP.

Wide cinematic scene: a dark basalt fortress "Citadel" at night seen from within its great hall. In the center foreground, a glowing "War Table" — a horizontal tactical table displaying a faint constellation of connected nodes and lines in emerald #45E06F (a knowledge graph, not a neon dashboard). Small orc scout silhouettes arrive from distant dark territories at the edges, carrying scrolls with ember #E97824 lantern accents. Signal spires in the far background with faint amber #FFB13B beacons. Weight of the composition is on data and evidence, not characters.

Wide cinematic 16:6 banner, ~1920x720, opaque background, dark upper region to leave room for overlaid title text.
```

### 2.1 Watchtower — `watchtower-hero.png`

```text
Dark tactical-archive game UI art for "Orc Citadel", a temporal evidence intelligence platform. Basalt (#111820) and black-iron surfaces on a near-black navy background (#07111C to #0D1B2A). Emerald light (#45E06F) reserved ONLY for verified knowledge/graph accents, used sparingly as a focal glow, never filling the frame. Muted stone (#D6CCB8) and parchment (#C8B58E) for foreground. Restrained, serious, audit-grade mood. No excessive glow, no fire particles, no ornate frames, no stone-texture noise. Original design — do NOT imitate Warcraft or any existing game IP.

Wide cinematic scene inside the Citadel's Watchtower at night: a tall dark basalt observation tower where armored orc sentinels keep watch over a wall of small glowing status panels showing incoming source feeds. Far below, from distant dark territories along a river, tiny orc scout silhouettes approach carrying scrolls lit by faint ember #E97824 lanterns. A few steady (not blinking) amber #FFB13B signal beacons on distant spires. Emerald #45E06F appears only on a small feed-status readout. Vigilant, orderly ingestion-monitoring mood.

Wide cinematic 16:6 banner, ~1920x720, opaque background, dark upper region to leave room for overlaid title text.
```

### 2.2 Grand Archive — `grand-archive-hero.png`

```text
Dark tactical-archive game UI art for "Orc Citadel", a temporal evidence intelligence platform. Basalt (#111820) and black-iron surfaces on a near-black navy background (#07111C to #0D1B2A). Emerald light (#45E06F) reserved ONLY for verified knowledge/graph accents, used sparingly as a focal glow, never filling the frame. Muted stone (#D6CCB8) and parchment (#C8B58E) for foreground. Restrained, serious, audit-grade mood. No excessive glow, no fire particles, no ornate frames, no stone-texture noise. Original design — do NOT imitate Warcraft or any existing game IP.

Wide cinematic scene of the Citadel's Grand Archive: a vast dark basalt library hall with towering black-iron shelves of rolled parchment #C8B58E scrolls, ledgers and stacked document tablets receding into shadow. Dim pools of lantern light; one hooded archivist orc consulting a scroll at a reading stand. A single faint emerald #45E06F thread of light traces a lineage between a few shelves, used sparingly. Immense, quiet, ordered preservation / document-lakehouse mood.

Wide cinematic 16:6 banner, ~1920x720, opaque background, dark upper region to leave room for overlaid title text.
```

### 2.3 Hall of Witnesses — `hall-of-witnesses-hero.png`

```text
Dark tactical-archive game UI art for "Orc Citadel", a temporal evidence intelligence platform. Basalt (#111820) and black-iron surfaces on a near-black navy background (#07111C to #0D1B2A). Emerald light (#45E06F) reserved ONLY for verified knowledge/graph accents, used sparingly as a focal glow, never filling the frame. Muted stone (#D6CCB8) and parchment (#C8B58E) for foreground. Restrained, serious, audit-grade mood. No excessive glow, no fire particles, no ornate frames, no stone-texture noise. Original design — do NOT imitate Warcraft or any existing game IP.

Wide cinematic scene of the Citadel's Hall of Witnesses: a solemn dark basalt chamber with a single central lit pedestal holding an open parchment #C8B58E document, one line of its text softly glowing. Two thin threads of light rise from the pedestal to two facing evidence stands — one emerald #45E06F (supporting) and one dull red #E05252 (contradicting). Grave, precise, focused-on-a-single-claim evidence-inspection / provenance mood.

Wide cinematic 16:6 banner, ~1920x720, opaque background, dark upper region to leave room for overlaid title text.
```

### 2.4 War Table — `war-table-hero.png`

```text
Dark tactical-archive game UI art for "Orc Citadel", a temporal evidence intelligence platform. Basalt (#111820) and black-iron surfaces on a near-black navy background (#07111C to #0D1B2A). Emerald light (#45E06F) reserved ONLY for verified knowledge/graph accents, used sparingly as a focal glow, never filling the frame. Muted stone (#D6CCB8) and parchment (#C8B58E) for foreground. Restrained, serious, audit-grade mood. No excessive glow, no fire particles, no ornate frames, no stone-texture noise. Original design — do NOT imitate Warcraft or any existing game IP.

Wide cinematic close view of the Citadel's War Table: a large horizontal black-basalt tactical table displaying a temporal knowledge graph of connected nodes and edges glowing emerald #45E06F, with a few edges in dull red #E05252 (contradiction) and amber #FFB13B (qualifier). One orc leans over the table studying a single highlighted path; iron markers and parchment scrolls at the table edge. A restrained knowledge map, not a neon dashboard. Analytical, commanding core-workspace mood.

Wide cinematic 16:6 banner, ~1920x720, opaque background, dark upper region to leave room for overlaid title text.
```

### 2.5 Council Chamber — `council-chamber-hero.png`

```text
Dark tactical-archive game UI art for "Orc Citadel", a temporal evidence intelligence platform. Basalt (#111820) and black-iron surfaces on a near-black navy background (#07111C to #0D1B2A). Emerald light (#45E06F) reserved ONLY for verified knowledge/graph accents, used sparingly as a focal glow, never filling the frame. Muted stone (#D6CCB8) and parchment (#C8B58E) for foreground. Restrained, serious, audit-grade mood. No excessive glow, no fire particles, no ornate frames, no stone-texture noise. Original design — do NOT imitate Warcraft or any existing game IP.

Wide cinematic scene of the Citadel's Council Chamber: several orc figures of a war-council gathered around the glowing emerald #45E06F War Table in a dark basalt round chamber, mid-deliberation. One robed seer holds a small restrained emerald orb; a warchief leans on the table; scrolls and ledgers before them. Warm ember #E97824 lantern light falls on the figures while emerald stays only on the table graph. Deliberative, serious, evidence-driven multi-agent investigation mood — a council, not a battle.

Wide cinematic 16:6 banner, ~1920x720, opaque background, dark upper region to leave room for overlaid title text.
```

### 2.6 Chronicle Vault — `chronicle-vault-hero.png`

```text
Dark tactical-archive game UI art for "Orc Citadel", a temporal evidence intelligence platform. Basalt (#111820) and black-iron surfaces on a near-black navy background (#07111C to #0D1B2A). Emerald light (#45E06F) reserved ONLY for verified knowledge/graph accents, used sparingly as a focal glow, never filling the frame. Muted stone (#D6CCB8) and parchment (#C8B58E) for foreground. Restrained, serious, audit-grade mood. No excessive glow, no fire particles, no ornate frames, no stone-texture noise. Original design — do NOT imitate Warcraft or any existing game IP.

Wide cinematic scene of the Citadel's Chronicle Vault: a deep dark basalt vault with a long horizontal time-rail receding into shadow, lined with rows of stacked stone record-tablets and ledgers layered like sediment. Faint markers spaced sparingly along the rail — emerald #45E06F for verified events, amber #FFB13B for changes, iron-gray for superseded versions — suggesting two overlaid timelines. Layered, archival, still bitemporal-history mood.

Wide cinematic 16:6 banner, ~1920x720, opaque background, dark upper region to leave room for overlaid title text.
```

### 2.7 Signal Spire — `signal-spire-hero.png`

```text
Dark tactical-archive game UI art for "Orc Citadel", a temporal evidence intelligence platform. Basalt (#111820) and black-iron surfaces on a near-black navy background (#07111C to #0D1B2A). Emerald light (#45E06F) reserved ONLY for verified knowledge/graph accents, used sparingly as a focal glow, never filling the frame. Muted stone (#D6CCB8) and parchment (#C8B58E) for foreground. Restrained, serious, audit-grade mood. No excessive glow, no fire particles, no ornate frames, no stone-texture noise. Original design — do NOT imitate Warcraft or any existing game IP.

Wide cinematic scene of the Citadel's Signal Spire at night: a single tall dark basalt spire whose amber #FFB13B beacon has just ignited once at its tip, casting a restrained glow over the dark citadel and the distant territories below. Other spires remain unlit. One thin thread of emerald #45E06F light runs from the citadel's graph toward the spire, marking a single material change. A single meaningful signal, calm and sparse — not a fireworks display. Alert-center mood.

Wide cinematic 16:6 banner, ~1920x720, opaque background, dark upper region to leave room for overlaid title text.
```

## 3. 캐릭터 — `char-*.png` (Orc Camp 초상 복사)

**결정:** 캐릭터는 신규 생성하지 **않고**, 자매 프로젝트 [`orc-camp`](https://github.com/hwangjongtaek/orc-camp)의 확립된 캐릭터 초상(`asset-packs/orc-camp-default/portraits/*.webp`, 512×512)을 **복사**해 사용한다. blueprint §1.4 "Orc Camp의 픽셀 캐릭터 비율·방향·prestige 개념을 재사용할 수 있다"에 근거하며, 세계관 일관성(동일 캐릭터군)을 유지한다.

- **라이선스/출처:** orc-camp `asset-packs/orc-camp-default/`의 자산 팩(PixelLab.ai 유료 플랜 생성). 해당 `LICENSE.md` 기준 **상업·재배포 허용, 귀속 선택**. 두 리포 모두 동일 소유자.
- **배경:** 초상은 **불투명 어두운 배경**(검정)이므로 **프레임/라운드 아바타 컨테이너**에 넣어 사용한다(자유 배치보다 avatar 프레임 권장). 512×512 → CSS에서 축소.
- **용도:** onboarding·result summary·Council 8-Agent roster 아바타·Hall of Witnesses 안내. 매 화면 상시 노출 금지.

| 파일 (Citadel) | Citadel 역할(기술) | orc-camp 원본 초상 |
| --- | --- | --- |
| `char-warchief.png` | Warchief / Council (조사 종합) | `orc-high-warchief-mascot` |
| `char-seer.png` | Seer (LLM 추론) | `orc-claude-storm-shaman` |
| `char-archivist.png` | Lorekeeper / Archivist (정규화·동일성 해소) | `orc-codex-field-engineer` |
| `char-scout.png` | Scout (수집) | `orc-unknown` (grunt) |
| `char-sentinel.png` | Sentinel (Watchtower 관제·경계) | `orc-iron-commander` |

> **재생성이 필요할 때만** 위 프롬프트 대신 orc-camp의 PixelLab 캐릭터를 재수출한다(orc-camp `sprites/`·`portraits/`가 정본). Citadel에서 신규 캐릭터 프롬프트로 생성하지 않는다 — 세계관 캐릭터 정체성은 orc-camp가 소유.

## 4. 빈 상태 아트 (Empty States) — `empty-*.png`

**용도:** 각 공간의 데이터 없음 상태. 작고 절제된 씬. 투명 배경, ~360px.

| 파일 | 화면 | 프롬프트 추가 지시 |
| --- | --- | --- |
| `empty-wartable.png` | War Table (조사 미선택) | `{공통 preamble} A dim, empty War Table with only a few faint unconnected node dots in iron gray, one waiting to be lit emerald. Quiet "awaiting investigation" mood. Small, centered spot illustration, transparent background.` |
| `empty-watchtower.png` | Watchtower (모든 소스 정상) | `{공통 preamble} A calm watchtower silhouette at night with steady (not blinking) small amber #FFB13B beacons and an orc scout resting — "all sources healthy" mood. Restrained. Transparent background.` |
| `empty-spire.png` | Signal Spire (새 알림 없음) | `{공통 preamble} A single unlit signal spire against the night, one small dormant amber #FFB13B ember at its tip — "no material changes" mood. Minimal, transparent background.` |
| `empty-archive.png` | Grand Archive (검색 결과 없음) | `{공통 preamble} A basalt archive shelf with a few parchment #C8B58E scrolls and one empty slot, a small magnifier — "no documents found" mood. Minimal spot illustration, transparent background.` |
| `empty-witnesses.png` | Hall of Witnesses (claim 미선택) | `{공통 preamble} An empty witness stand / evidence pedestal in a dim basalt hall, one parchment #C8B58E scroll awaiting examination, no claim selected — "select a claim to inspect its evidence" mood. Minimal spot illustration, transparent background.` |
| `empty-chronicle.png` | Chronicle Vault (이력 없음) | `{공통 preamble} A quiet vault with a horizontal time-rail fading into the dark, only one or two faint event pins, no version history yet — "no recorded changes" mood. Minimal spot illustration, transparent background.` |

## 5. 처리 상태 아트 (Processing) — `proc-*.png`

**용도:** 긴 작업 진행 표현(수집·조사 루프). 애니메이션은 CSS로, 여기선 정지 프레임.

| 파일 | 상태 | 프롬프트 추가 지시 |
| --- | --- | --- |
| `proc-scout.png` | 수집 중 | `{공통 preamble} A small orc scout mid-stride carrying a report scroll, a faint ember #E97824 motion trail behind — "ingesting" mood. Side profile, transparent background, ~200px.` |
| `proc-seer.png` | 조사/추론 중 | `{공통 preamble} A Seer tracing a dashed emerald #45E06F path between two faint nodes with a fingertip — "reasoning over the graph" mood. Analytical, calm. Transparent background, ~200px.` |

## 6. 페이지별 삽화 매핑 (SSOT)

각 목업 페이지가 사용하는 삽화와 **프롬프트 위치(§)**, 배치 지점. 우선순위 ★ = 먼저 필요.

| 페이지 (`docs/mockups/`) | 삽화 파일 | 프롬프트 위치 | 배치 지점 · 용도 | 우선 |
| --- | --- | --- | --- | :---: |
| `index.html` | `crest-hero.png` | §1 | 상단 워드마크 옆 브랜드 문장 | ★ |
| `citadel-gate.html` | `gate-hero.png` | §2 | 히어로 배경/일러스트 | ★ |
| `citadel-gate.html` | `crest-hero.png` | §1 | 히어로 워드마크 | |
| `citadel-gate.html` | `char-scout.png`, `char-seer.png` | §3 | 온보딩 안내(최초 방문·result summary, 상시 금지) | |
| `watchtower.html` | `watchtower-hero.png` | §2.1 | 헤더/히어로 배경 | |
| `watchtower.html` | `char-sentinel.png` | §3 | 관제 헤더/빈 상태 아바타 | |
| `watchtower.html` | `empty-watchtower.png` | §4 | "모든 소스 정상" 빈 상태 | |
| `watchtower.html` | `proc-scout.png` | §5 | 수집 진행(ingesting) 표시 | |
| `grand-archive.html` | `grand-archive-hero.png` | §2.2 | 헤더/히어로 배경 | |
| `grand-archive.html` | `empty-archive.png` | §4 | "검색 결과 없음" 빈 상태 | |
| `hall-of-witnesses.html` | `hall-of-witnesses-hero.png` | §2.3 | 헤더/히어로 배경 | |
| `hall-of-witnesses.html` | `empty-witnesses.png` | §4 | "claim 미선택" 빈 상태 | |
| `hall-of-witnesses.html` | `char-archivist.png` | §3 | 안내/헤더 스팟(선택) | |
| `war-table.html` | `war-table-hero.png` | §2.4 | 헤더/히어로 배경(또는 빈 상태) | |
| `war-table.html` | `empty-wartable.png` | §4 | "조사 미선택" 빈 상태 | ★ |
| `war-table.html` | `proc-seer.png` | §5 | 조사 진행(reasoning) 표시 | |
| `council-chamber.html` | `council-chamber-hero.png` | §2.5 | 헤더/히어로 배경 | |
| `council-chamber.html` | `char-scout.png`·`char-archivist.png`·`char-seer.png`·`char-warchief.png` | §3 | 8-Agent roster 아바타(Scout→Retrieval/수집, Archivist→Lorekeeper, Seer→추론계열, Warchief→Council) | |
| `council-chamber.html` | `proc-seer.png` | §5 | 조사 루프 진행 표시 | |
| `chronicle-vault.html` | `chronicle-vault-hero.png` | §2.6 | 헤더/히어로 배경 | |
| `chronicle-vault.html` | `empty-chronicle.png` | §4 | "이력 없음" 빈 상태 | |
| `signal-spire.html` | `signal-spire-hero.png` | §2.7 | 헤더/히어로 배경 | |
| `signal-spire.html` | `empty-spire.png` | §4 | "새 알림 없음" 빈 상태 | |

> **읽는 법:** "프롬프트 위치" 열의 §번호가 이 문서 안에서 해당 이미지의 실제 생성 프롬프트가 있는 섹션이다. 예: `empty-wartable.png` → §4 표의 해당 행 프롬프트.

## 7. 연결 계획 (이미지 전달 후)

- 파일명을 위 §0 규약대로 `assets/<name>.png`로 주시면 배치 후 `<img>`(또는 CSS 배경)로 연결한다.
- 빈 상태·처리 상태는 해당 컴포넌트에 삽입하고 기능명 병기 안내 문구를 함께 둔다.
- 캐릭터는 onboarding·result summary·roster 아바타에 한정(상시 노출 금지, blueprint §1.4).
- 접근성: 모든 삽화에 `alt` 텍스트, 처리 상태 애니메이션은 `prefers-reduced-motion`에서 정지 프레임으로 대체.
