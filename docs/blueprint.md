# Orc Citadel

> **The Camp works. The Citadel remembers.**
>
> 수백만 개의 공개 문서에서 시간과 출처가 보존된 주장 지식 그래프를 구축하고, LLM 에이전트가 그래프의 공백과 모순을 조사해 지속적으로 확장하는 Temporal Evidence Intelligence 플랫폼

## 1. 프로젝트 개요

**Orc Citadel**은 Global Evidence Observatory 콘셉트를 구현하는 프로젝트의 정식 명칭이다. 뉴스, 기업 공시, 정부 문서, 연구 논문, 공식 발표와 같은 대량의 공개 자료를 수집하고 분석하여 다음 요소를 연결한다.

- 누가 어떤 주장을 했는가
- 주장이 어떤 대상과 사건에 관한 것인가
- 어떤 자료가 주장을 지지하거나 반박하는가
- 여러 출처가 실제로 서로 독립적인가
- 사실과 주장이 시간에 따라 어떻게 변했는가
- 현재 결론의 불확실성과 아직 조사되지 않은 영역은 무엇인가

일반적인 검색·RAG 서비스가 관련 문서를 찾아 답변을 생성하는 데 집중한다면, Orc Citadel은 **문서에서 검증 가능한 주장을 추출하고 그 관계를 시간 기반 Knowledge Graph로 축적하는 것**을 핵심으로 한다.

최종 결과는 단순한 자연어 답변이 아니라 다음 세 가지를 함께 제공해야 한다.

1. 조사 결과 보고서
2. 결론을 구성한 Evidence Graph
3. 모든 주장과 원문 구절 사이의 provenance

### 1.1 제품 정체성

Orc Citadel은 [`orc-camp`](https://github.com/hwangjongtaek/orc-camp)와 같은 오크 세계관을 공유한다.

- **Orc Camp**는 AI 에이전트가 일하는 현장이다.
- **Orc Citadel**은 에이전트가 수집한 세계의 정보가 모이고 검증되어 집단지성으로 축적되는 중앙 본부다.
- `Global Evidence Observatory`는 제품명이 아니라 Orc Citadel이 구현하는 기능적 콘셉트다.

```text
Orc Camp
└── AI agents live and work here.

Orc Citadel
└── Evidence, memory, and intelligence converge here.
```

Citadel은 단순히 세계를 감시하는 망루가 아니다. 외부의 보고를 수집하고, 출처를 보존하고, 주장 사이의 관계를 연결하고, 반대 증거를 검토하여 시간이 지나도 판단 근거를 재현할 수 있게 하는 최고 지식·정보 기관이다.

### 1.2 세계관 용어와 기술 개념

세계관 명칭은 사용자 경험과 시각적 표현에 사용한다. API, 데이터 스키마와 운영 문서에서는 괄호 안의 기술 용어를 함께 사용하여 의미가 모호해지지 않게 한다.

| 세계관 명칭            | 기술 개념                         | 역할                                            |
| ---------------------- | --------------------------------- | ----------------------------------------------- |
| **Citadel**            | 전체 플랫폼                       | 수집·저장·그래프·조사·감사를 통합하는 중앙 본부 |
| **Scouts**             | Source connectors / collectors    | 외부 자료와 변경 사항을 수집                    |
| **Scout Reports**      | Raw documents                     | 출처에서 수집한 원본 문서와 버전                |
| **Watchtower**         | Ingestion monitor                 | source 신선도, 수집 실패와 신규 사건을 감시     |
| **Grand Archive**      | Data lakehouse                    | 원본·정규화·curated 데이터를 보존               |
| **Hall of Witnesses**  | Evidence and provenance store     | 주장과 원문 구절, 출처 계보를 연결              |
| **War Table**          | Temporal Evidence Knowledge Graph | 엔터티·사건·주장·증거·시간 관계를 탐색          |
| **Chronicle**          | Bitemporal event history          | 사실과 주장 및 시스템 인식의 변경 이력을 보존   |
| **Lorekeepers**        | Resolution pipeline               | Entity Resolution과 Claim Canonicalization 수행 |
| **Seers**              | LLM reasoning agents              | 모순, 공백, 반증과 새로운 조사 경로를 추론      |
| **Warchief's Council** | Multi-agent investigation         | 서로 다른 역할의 Agent가 증거를 검토하고 종합   |
| **Signal Spire**       | Change alerts                     | 결론과 confidence의 중요한 변화를 알림          |
| **Campaign**           | Investigation                     | 하나의 질문에 대한 범위와 조사 실행 이력        |
| **Trail**              | Provenance chain                  | 결과에서 원문까지 이어지는 감사 경로            |

### 1.3 제품 문구

대표 설명은 다음과 같이 사용한다.

> **Orc Citadel is a temporal evidence intelligence platform that gathers reports from across the world, connects claims and evidence on the War Table, and preserves every change in the Chronicle.**

짧은 태그라인은 다음을 기본값으로 한다.

> **The Camp works. The Citadel remembers.**

기능 중심 문구가 필요한 경우 다음을 사용한다.

> **Where every claim faces its evidence.**

### 1.4 시각 컨셉과 UI 디자인 원칙

#### 기준 배너

![Orc Citadel banner](./orc-citadel-banner.png)

이 배너는 향후 UI 디자인의 시각적 기준점이다. 화면을 그대로 모사하기보다 다음 핵심 요소를 디자인 토큰, 정보 구조와 상호작용으로 번역한다.

1. **Citadel:** 정보와 의사결정이 모이는 무게감 있는 중앙 구조
2. **War Table:** 엔터티·주장·증거·시간 관계가 빛나는 핵심 작업 공간
3. **Scouts:** 외부 세계에서 자료를 가져오는 수집 주체
4. **Archivists와 Lorekeepers:** 원문 보존, 정규화와 동일성 판정
5. **Seer:** 그래프의 공백과 모순을 찾는 LLM 추론 주체
6. **Signal Spires:** 신규 사건과 결론 변화를 전달하는 상태 신호
7. **Distant Territories:** Citadel이 관찰하는 다양한 외부 source와 도메인

#### 디자인 서사

UI는 “판타지 스킨을 씌운 관리자 페이지”가 아니라 **Citadel 안에서 세계의 보고를 검증하고 전황도를 갱신하는 지식 작업 공간**처럼 느껴져야 한다.

```text
Outside World
→ Scouts gather reports
→ Grand Archive preserves originals
→ Lorekeepers resolve identities
→ War Table connects evidence
→ Council challenges conclusions
→ Chronicle records changes
→ Signal Spire announces material updates
```

시각적 무게 중심은 장식이나 캐릭터가 아니라 데이터와 근거다. 오크 세계관은 정보 구조를 이해시키고 제품의 개성을 만드는 역할을 하며, 정확성·가독성과 감사 가능성을 방해해서는 안 된다.

#### 공간 계층

배너의 요새 구조를 제품의 화면 계층으로 변환한다.

| 공간              | UI 영역       | 정보 밀도와 역할                                   |
| ----------------- | ------------- | -------------------------------------------------- |
| Citadel Gate      | 홈·온보딩     | 현재 시스템 상태와 주요 Campaign 진입점            |
| Watchtower        | 수집 관제     | source 상태, ingestion backlog, freshness, failure |
| Grand Archive     | 문서 탐색     | 원문, 버전, parsing 결과와 데이터 lineage          |
| Hall of Witnesses | Evidence 검사 | source span, 독립성, 지지·반박 근거 비교           |
| War Table         | 그래프 탐색   | Knowledge Graph와 investigation의 중심 화면        |
| Council Chamber   | 조사 실행     | Agent 계획, 토론, 반증과 최종 종합                 |
| Chronicle Vault   | 시간 탐색     | 사건·주장·시스템 인식의 bitemporal history         |
| Signal Spire      | 알림 센터     | 결론 변화, 신규 모순과 중요 source 업데이트        |

모든 주요 화면은 Citadel의 한 공간에 대응하지만 URL과 API 명칭에는 기술 용어를 우선한다. 예를 들어 UI 표시는 `War Table`, 경로는 `/graph` 또는 `/investigations/:id/graph`로 구성할 수 있다.

#### 색상 체계

배너에서 추출한 색상 관계를 아래와 같이 정의한다. 실제 구현 단계에서 WCAG 대비를 검증한 뒤 값은 미세 조정할 수 있다.

| Token              |    제안값 | 용도                           |
| ------------------ | --------: | ------------------------------ |
| `--citadel-void`   | `#07111C` | 앱 최외곽 배경                 |
| `--citadel-night`  | `#0D1B2A` | 주요 페이지 배경               |
| `--basalt-900`     | `#111820` | 패널·사이드바                  |
| `--basalt-700`     | `#26313A` | 패널 경계·비활성 표면          |
| `--iron-500`       | `#59636A` | 보조 텍스트·아이콘             |
| `--stone-200`      | `#D6CCB8` | 기본 전경·제목                 |
| `--parchment-300`  | `#C8B58E` | 문서·기록 메타데이터           |
| `--ember-500`      | `#E97824` | 활성 상태·주의·수집 신호       |
| `--signal-amber`   | `#FFB13B` | 새로운 정보·Signal Spire       |
| `--war-green`      | `#45E06F` | 검증된 연결·선택된 그래프 경로 |
| `--seer-green`     | `#20B85A` | LLM 추론·발견 후보             |
| `--banner-crimson` | `#7B2833` | 브랜드 배너·중요 섹션 표식     |
| `--contradiction`  | `#E05252` | 반박·모순·실패                 |
| `--uncertain`      | `#A78BFA` | 미확정 관계·quarantine         |

에메랄드 색상은 브랜드 장식색이 아니라 **지식 그래프와 검증된 evidence trail**에 우선 사용한다. 화면 전체를 녹색으로 채우지 않고, 어두운 석재 배경 위에서 중요한 연결과 상호작용만 빛나게 한다.

상태 색상은 색만으로 의미를 전달하지 않는다. 아이콘, 선 형태, 라벨과 패턴을 함께 사용한다.

| 상태        | 색상              | 그래프 표현                    |
| ----------- | ----------------- | ------------------------------ |
| supports    | War green         | 실선 + 확인 표식               |
| contradicts | Contradiction red | 이중선 또는 절단선 + 반박 표식 |
| qualifies   | Signal amber      | 점선 + 범위 표식               |
| uncertain   | Uncertain violet  | 점선 + 물음표 표식             |
| superseded  | Iron gray         | 흐린 선 + 시간 화살표          |

#### 소재와 표면

- **Basalt:** 앱 셸과 주요 패널의 안정적인 어두운 표면
- **Black iron:** 경계선, 탭, 도구 모음과 구조적 구분
- **Carved stone:** 페이지 제목, 중요한 숫자와 섹션 헤더
- **Parchment:** 원문 인용, Scout Report와 Chronicle entry
- **Emerald light:** 그래프 노드, 선택 경로와 검증된 관계
- **Ember light:** 실시간 처리, 신규 수집과 경고
- **Crimson cloth:** 브랜드 구획과 Citadel의 상징적 강조

텍스처는 배너·빈 상태·온보딩처럼 감성적 맥락에서만 적극 사용한다. 데이터 테이블, 긴 문서와 설정 화면에서는 단색 표면과 절제된 테두리를 사용해 가독성을 우선한다.

#### 타이포그래피

- `ORC CITADEL` 워드마크와 마케팅용 대형 제목은 석재에 새긴 듯한 디스플레이 스타일을 사용한다.
- 제품 UI 제목은 장식이 적은 굵은 sans-serif를 사용한다.
- 본문과 테이블은 높은 가독성의 sans-serif를 사용한다.
- ID, hash, query, timestamp와 source span은 monospace를 사용한다.
- 픽셀 폰트는 워드마크, 작은 배지와 게임적 상태 표현에만 제한한다.
- 긴 보고서나 원문에 픽셀 폰트를 사용하지 않는다.

#### 아이콘과 문장

배너의 문장은 기존 게임 IP와 구별되는 독자적인 **추상적 오크 엄니·방패 형태**를 사용한다.

- 기존 게임이나 판타지 프랜차이즈의 로고, 룬과 진영 문장을 모사하지 않는다.
- 날카로운 철제 외곽, 대칭적인 엄니와 중앙의 지식 불꽃을 핵심 모티프로 삼는다.
- 작은 크기에서도 구분되도록 2~3개 주요 형태만 사용한다.
- 문장은 브랜드 식별용이며 데이터 상태 아이콘으로 재사용하지 않는다.

#### War Table 그래프 디자인

War Table은 배너와 제품 모두의 시각적 중심이다.

- 그래프는 현대적인 네온 대시보드가 아니라 어두운 전술 테이블 위에 표시되는 지식 지도처럼 표현한다.
- 노드 크기는 시각적 인기보다 조사 내 중요도와 evidence coverage를 반영한다.
- 선택하지 않은 그래프 전체는 낮은 대비로 유지한다.
- 선택한 claim의 support·contradiction trail만 밝게 강조한다.
- 원문 provenance를 확인할 때 그래프에서 Hall of Witnesses 패널로 자연스럽게 이어져야 한다.
- 시간 슬라이더를 움직이면 노드가 사라지는 대신 valid time과 transaction time의 상태 변화를 구분해 보여준다.
- 대규모 그래프를 한 번에 렌더링하지 않고 investigation subgraph와 progressive disclosure를 사용한다.

권장 기본 레이아웃은 다음과 같다.

```text
┌──────────────────────────────────────────────────────────────────┐
│ Citadel Header · Campaign · Time · Search · Signal Spire         │
├───────────────┬──────────────────────────────┬───────────────────┤
│ Campaign Map  │                              │ Evidence Inspector│
│               │          War Table           │                   │
│ Subclaims     │     Temporal Knowledge       │ Source spans      │
│ Entities      │           Graph              │ Independence      │
│ Filters       │                              │ Agent reasoning   │
├───────────────┴──────────────────────────────┴───────────────────┤
│ Chronicle · ingestion and investigation event timeline           │
└──────────────────────────────────────────────────────────────────┘
```

#### 캐릭터 사용 원칙

Scouts, Lorekeepers와 Seers는 시스템 상태를 이해시키는 보조 캐릭터다.

- 캐릭터를 매번 노출하지 않고 onboarding, empty state, processing state와 결과 요약에 사용한다.
- 데이터 오류를 캐릭터의 실수처럼 희화화하지 않는다.
- 중요 경고에는 캐릭터보다 명확한 상태 메시지와 해결 방법을 우선한다.
- Orc Camp의 픽셀 캐릭터 비율·방향·prestige 개념을 재사용할 수 있다.
- Citadel 전용 역할은 기존 캐릭터의 상위 조직 또는 전문 직책으로 설계한다.

#### 모션과 상태 변화

- 활성 Scout는 작은 이동 또는 보고서 전달 동작으로 ingestion을 표현한다.
- 새 evidence가 그래프에 반영될 때 관련 trail만 짧게 점등한다.
- Signal Spire는 중요한 변화에 한해 한 번 점화하며 무한 반복하지 않는다.
- 긴 Agent 작업은 War Table의 탐색 경로와 현재 하위 질문으로 진행 상황을 표현한다.
- `prefers-reduced-motion`에서는 점등, 이동과 파티클 효과를 제거한다.
- 장시간 빛나는 애니메이션과 과도한 불꽃 파티클은 사용하지 않는다.

#### 반응형 원칙

- 데스크톱에서는 War Table을 중심으로 좌측 Campaign, 우측 Evidence, 하단 Chronicle의 3+1 패널 구조를 사용한다.
- 태블릿에서는 Evidence Inspector를 drawer로 전환한다.
- 모바일에서는 그래프 전체 조작보다 claim 목록→evidence→source trail의 선형 탐색을 우선한다.
- 모바일에서도 세계관 용어만 단독으로 표시하지 않고 `War Table · Graph`, `Chronicle · History`처럼 기능명을 병기한다.

#### 접근성과 신뢰성

- 본문과 인터랙티브 요소는 WCAG AA 이상의 명도 대비를 목표로 한다.
- 색상 외에 아이콘, 텍스트와 선 패턴으로 관계 유형을 구분한다.
- 그래프의 모든 핵심 관계를 목록·테이블 형태로도 탐색할 수 있게 한다.
- 원문, claim, confidence와 Agent inference를 시각적으로 명확히 분리한다.
- confidence는 단일 색상 게이지 대신 값, 근거 수, 독립 출처 수와 계산 근거를 함께 표시한다.
- 장식적 세계관 문구보다 실제 기술 상태와 오류 원인을 우선 표시한다.

#### 피해야 할 방향

- 기존 Warcraft 또는 다른 게임의 캐릭터, 문장, 건축물을 직접 모사하는 디자인
- 모든 화면을 픽셀 게임 맵처럼 구성하여 업무 효율을 떨어뜨리는 디자인
- 과도한 녹색 발광, 불꽃, 돌 텍스처와 장식 프레임
- 그래프 노드 수가 많을수록 멋있어 보이게 만드는 hairball 시각화
- supports를 “진실”, contradicts를 “거짓”으로 단순화하는 표현
- LLM Agent의 추론을 신비한 예언처럼 포장하여 근거와 불확실성을 숨기는 표현
- 세계관 명칭만 사용해 처음 온 사용자가 기능을 이해하지 못하게 하는 UI

#### 디자인 완료 기준

초기 UI 디자인은 다음 조건을 충족해야 한다.

1. 배너를 보지 않아도 같은 제품군이라는 색상·형태 언어가 느껴진다.
2. War Table이 제품의 핵심 작업 공간으로 명확히 보인다.
3. 사용자는 결과 문장에서 원문 evidence까지 3회 이내 상호작용으로 이동할 수 있다.
4. support, contradiction, uncertainty와 supersession을 색 없이도 구분할 수 있다.
5. 100개 이상의 노드가 있는 investigation에서도 현재 선택 경로가 명확하다.
6. 장식 요소를 제거해도 정보 구조와 사용성이 유지된다.
7. Orc Camp와 세계관은 공유하지만 독립된 제품으로 식별된다.

## 2. 프로젝트가 해결할 문제

대규모 공개 정보 환경에는 다음 문제가 존재한다.

- 동일한 보도자료가 수백 개 기사로 복제되어 독립된 근거처럼 보인다.
- 서로 다른 표기로 인해 같은 인물·기업·제품이 별개의 대상으로 인식된다.
- 과거에는 참이었던 사실과 현재의 사실이 충돌하는 것처럼 보인다.
- 사실, 당사자의 주장, 기자의 해석, 미래 예측이 섞여 있다.
- 검색 결과 상위 문서만으로는 반대 증거나 누락된 관점을 발견하기 어렵다.
- 생성형 모델이 작성한 보고서는 문장 단위로 출처를 감사하기 어렵다.
- 새로운 증거가 나타나도 기존 결론이 자동으로 갱신되지 않는다.

Orc Citadel은 문서를 최종 단위로 취급하지 않는다. 문서 내부의 주장, 증거, 사건, 엔터티와 출처 계보를 구조화하고, 새 자료가 들어올 때 영향을 받는 그래프와 결론만 증분 갱신한다.

## 3. 목표와 비목표

### 3.1 목표

- 최소 100만 건, 장기적으로 1,000만 건 이상의 문서를 처리한다.
- 모든 추출 결과를 정확한 원문 위치로 역추적할 수 있게 한다.
- Entity Resolution과 Claim Canonicalization을 통해 중복을 통제한다.
- valid time과 transaction time을 모두 보존한다.
- 주장에 대한 지지, 반박, 한정, 대체 관계를 표현한다.
- LLM이 조사 계획, 구조화 추출, 모순 판정과 반증 탐색을 수행한다.
- 규칙, 임베딩, 소형 모델과 고성능 LLM을 계층적으로 사용한다.
- 전체 파이프라인을 재실행하고 동일 버전의 결과를 재현할 수 있게 한다.
- 정확도, 처리량, 지연시간과 LLM 비용을 함께 측정한다.

### 3.2 비목표

- 모든 분야를 동시에 포괄하는 범용 지식 베이스
- 출처 없이 LLM의 사전 지식만으로 사실을 추가하는 시스템
- 그래프 조회 결과를 포장하기만 하는 일반적인 GraphRAG 챗봇
- 모델의 confidence 값만으로 사실 여부를 확정하는 시스템
- 법률·의료·투자 결정을 자동으로 내리는 고위험 의사결정 시스템
- 수집 권한이나 라이선스를 우회하는 크롤러

## 4. 초기 도메인 제안

첫 버전에서는 **AI 반도체와 데이터센터 공급망**처럼 범위가 명확하고 공개 자료가 풍부한 하나의 산업을 선택한다.

주요 데이터는 다음과 같다.

- 기업 연차·분기 보고서와 거래소 공시
- 기업 보도자료와 공식 블로그
- 정부 정책·규제 문서
- 산업 뉴스와 인터뷰
- 공개 연구 보고서
- 제품 발표와 기술 문서

이 도메인은 기업, 인물, 제품, 기술, 공급 관계, 투자, 계약, 규제와 지역적 사건이 복합적으로 연결되므로 Knowledge Graph의 장점을 보여주기 좋다.

대표 조사 질문은 다음과 같다.

- 특정 기업의 단일 공급자 의존도는 실제로 감소했는가?
- 기업이 발표한 투자 계획 중 실제 집행이 확인된 것은 무엇인가?
- 규제 변경이 어떤 기업과 제품에 직접 또는 간접 영향을 미치는가?
- 동일 사건을 기업, 정부와 언론이 각각 어떻게 설명하는가?
- 공급망 위험에 대한 경고는 독립된 복수 근거에 기반하는가?

## 5. 사용자 경험

### 5.1 조사 요청

사용자는 자연어로 질문하고 필요하면 기간, 지역, 출처 종류와 조사 깊이를 지정한다.

```text
2024년 이후 A사의 AI 가속기 공급망 다변화가 실제로 진행되었는지 조사하라.
공식 발표와 실제 계약·공시를 구분하고 반대 증거도 포함하라.
```

### 5.2 조사 결과

결과 화면은 다음 영역으로 구성한다.

- 현재 결론과 confidence
- 사실, 주장, 추론, 예측이 구분된 보고서
- 주장별 지지·반박 증거
- 사건과 주장 변화의 타임라인
- 출처 계보와 독립성
- 탐색 가능한 Evidence Graph
- 아직 증거가 부족한 질문
- Agent가 수행한 조사 과정과 사용 비용

### 5.3 지속적 관찰

사용자는 조사 주제를 Campaign으로 등록할 수 있다. Scouts가 새 문서를 수집하면 관련 War Table subgraph만 갱신하고 다음 경우 Signal Spire 알림 후보를 만든다.

- 기존 결론을 뒤집는 반대 증거가 발견됨
- 기업이나 인물의 기존 주장이 변경됨
- 이전에 계획으로만 발표된 내용의 실행 증거가 발견됨
- 서로 독립적인 새로운 출처가 추가됨
- confidence가 임계값 이상 변함

## 6. Knowledge Graph 설계

### 6.1 주요 노드

| 노드            | 의미                               | 주요 속성                             |
| --------------- | ---------------------------------- | ------------------------------------- |
| `Person`        | 개인                               | canonical name, aliases, identifiers  |
| `Organization`  | 기업·정부·기관                     | legal name, aliases, jurisdiction     |
| `Product`       | 제품·서비스                        | name, version, manufacturer           |
| `Technology`    | 기술·표준                          | name, category                        |
| `Location`      | 국가·도시·시설                     | coordinates, administrative hierarchy |
| `Event`         | 계약·발표·사고·규제 등             | event type, time range, status        |
| `Document`      | 수집된 문서 버전                   | URL, content hash, publication time   |
| `Source`        | 문서 발행 주체                     | publisher, source type, ownership     |
| `Claim`         | 출처가 제시한 명제                 | canonical form, modality, confidence  |
| `Evidence`      | 주장을 평가하는 원문 구절·데이터   | source span, extraction version       |
| `Assertion`     | 시간과 provenance를 가진 관계 주장 | subject, predicate, object, time      |
| `Investigation` | 사용자의 조사 단위                 | question, scope, status               |

### 6.2 주요 관계

| 관계               | 의미                                  |
| ------------------ | ------------------------------------- |
| `MENTIONS`         | 문서가 엔터티를 언급함                |
| `PUBLISHED_BY`     | 문서가 출처에 의해 발행됨             |
| `MADE_CLAIM`       | 인물·기관이 주장을 제시함             |
| `ABOUT`            | 주장이나 사건이 대상을 가리킴         |
| `SUPPORTS`         | 증거가 주장을 지지함                  |
| `CONTRADICTS`      | 증거 또는 주장이 다른 주장을 반박함   |
| `QUALIFIES`        | 기존 주장의 적용 범위를 제한함        |
| `SUPERSEDES`       | 새로운 주장·사실이 이전 버전을 대체함 |
| `DERIVED_FROM`     | 문서·주장이 다른 출처에서 파생됨      |
| `CITES`            | 문서가 다른 문서를 명시적으로 인용함  |
| `PARTICIPATED_IN`  | 엔터티가 사건에 참여함                |
| `PRECEDES`         | 사건 사이의 시간적 선후 관계          |
| `SAME_AS`          | 두 엔터티가 동일함이 확인됨           |
| `POSSIBLY_SAME_AS` | 동일 후보이나 아직 확정되지 않음      |

### 6.3 Claim을 독립 노드로 두는 이유

`A사 -[DEPENDS_ON]-> B사`처럼 관계만 저장하면 그것이 사실인지, 누가 언제 주장했는지, 어떤 근거가 있는지 표현하기 어렵다. Orc Citadel의 War Table에서는 관계를 다음과 같이 reification한다.

```text
(A사)-[:MADE_CLAIM]->(Claim-123)
(Claim-123)-[:SUBJECT]->(A사)
(Claim-123)-[:OBJECT]->(B사)
(Evidence-456)-[:SUPPORTS]->(Claim-123)
(Evidence-789)-[:CONTRADICTS]->(Claim-123)
(Claim-123)-[:VALID_DURING]->(2025-Q1)
```

Claim은 최소한 다음 정보를 가진다.

```json
{
  "claim_id": "claim-123",
  "subject_id": "org-a",
  "predicate": "depends_on",
  "object_id": "org-b",
  "canonical_text": "A사는 AI 가속기 부품을 B사에 주로 의존한다.",
  "modality": "asserted",
  "valid_from": "2025-01-01",
  "valid_to": null,
  "observed_at": "2025-02-15T09:00:00Z",
  "confidence": 0.83,
  "extraction_model": "model-version",
  "ontology_version": "1.2.0"
}
```

### 6.4 Bitemporal 모델

Orc Citadel의 Chronicle은 두 가지 시간을 구분한다.

- `valid time`: 현실에서 사실이나 주장이 유효했던 기간
- `transaction time`: Orc Citadel이 해당 정보를 관찰하고 저장한 기간

이를 통해 다음 질문에 답할 수 있다.

- 2025년 3월에 실제 CEO는 누구였는가?
- 2025년 3월 당시 시스템은 CEO가 누구라고 알고 있었는가?
- 뒤늦게 발견된 정정 자료가 과거 결론을 어떻게 변경했는가?

기존 assertion을 덮어쓰지 않고 새로운 버전을 추가하며, supersession 관계로 변경 원인을 남긴다.

### 6.5 Provenance

모든 Claim, Evidence와 Assertion은 다음 경로로 원문까지 추적 가능해야 한다.

```text
Graph element
→ extraction record
→ normalized document version
→ source span
→ immutable raw document
→ source URL and retrieval metadata
```

최소 provenance 필드는 다음과 같다.

- 원문 문서 ID와 버전
- 문단·문장·문자 offset
- 원문 content hash
- 수집 시각과 공개 시각
- 추출 모델·프롬프트·스키마 버전
- 전처리 코드 버전
- 승인 또는 교정 이력

## 7. 대규모 데이터 아키텍처

```text
Sources
  → Scouts / Ingestion Queue
  → Scout Reports / Immutable Raw Storage
  → Parse / Normalize / Language Detection
  → Exact and Near-Duplicate Detection
  → Grand Archive / Lakehouse Tables
  → Entity and Claim Candidate Extraction
  → Lorekeepers / Entity Resolution / Claim Canonicalization
  → War Table / Temporal Evidence Knowledge Graph
  → Search and Vector Index
  → Warchief's Council / Research Agents
  → Chronicle / Report / Graph Explorer
  → Signal Spire / Alerts
```

### 7.1 저장 계층

#### Raw zone

- 수집한 원본을 수정하지 않고 저장한다.
- URL, 응답 헤더, 수집 시각, 라이선스와 content hash를 함께 기록한다.
- 같은 URL의 변경된 버전을 모두 보존한다.

#### Normalized zone

- HTML boilerplate 제거 결과
- 문서 구조와 문단
- 표·목록·각주
- 언어와 문자 인코딩
- 공개 시각과 수정 시각

#### Curated zone

- 엔터티 mention
- claim·evidence 후보
- canonical entity mapping
- 이벤트와 시간 표현
- 출처 계보와 중복 클러스터

파일 포맷은 Parquet, 테이블 포맷은 Apache Iceberg를 우선 검토한다. 작은 초기 버전에서는 로컬 MinIO와 DuckDB로 시작할 수 있다.

### 7.2 서비스별 권장 기술

| 용도            | 초기 구성          | 확장 구성                       |
| --------------- | ------------------ | ------------------------------- |
| 원본·Lakehouse  | MinIO + Parquet    | S3 + Iceberg                    |
| Batch 처리      | Ray Data           | Ray Data 또는 Spark             |
| Event stream    | PostgreSQL queue   | Kafka 또는 Redpanda             |
| 메타데이터      | PostgreSQL         | PostgreSQL                      |
| Knowledge Graph | Neo4j Community    | Neo4j/Memgraph 또는 검증된 대안 |
| 전문·벡터 검색  | OpenSearch         | OpenSearch cluster              |
| 분석·관측       | PostgreSQL/Grafana | ClickHouse + Grafana            |
| API             | FastAPI            | FastAPI + async workers         |
| 배포            | Docker Compose     | Kubernetes                      |

기술을 한꺼번에 도입하지 않는다. 데이터 규모와 측정된 병목이 분리를 정당화할 때만 구성 요소를 추가한다.

### 7.3 데이터 규모

| 단계      |    문서 수 | 기대 결과                     |
| --------- | ---------: | ----------------------------- |
| Prototype |     10,000 | 온톨로지와 provenance 검증    |
| MVP       |    100,000 | end-to-end 조사와 전체 재처리 |
| Scale     |  1,000,000 | 증분 처리와 비용 최적화       |
| Challenge | 10,000,000 | 분산 처리와 부분 재계산       |

1,000만 문서에서 원문 텍스트가 평균 5KB라면 텍스트만 약 50GB다. HTML 원본, 문서 버전, Parquet 중간 결과, 임베딩, 검색 인덱스와 그래프를 포함하면 실제 저장량은 수백 GB가 될 수 있다.

## 8. 처리 파이프라인

### 8.1 수집

- 허용된 API, RSS, sitemap과 공개 다운로드를 우선한다.
- robots 정책과 이용 조건을 준수한다.
- source별 rate limit과 backoff를 적용한다.
- 수집 작업은 idempotent하게 설계한다.
- 문서 수정 탐지를 위해 content hash와 fetch metadata를 저장한다.

### 8.2 파싱과 정규화

- 본문, 제목, 작성자, 공개·수정 시각을 분리한다.
- 표와 각주를 유실하지 않는다.
- 문단과 문장 ID를 안정적으로 생성한다.
- 원문 offset과 정규화 텍스트 사이의 매핑을 유지한다.

### 8.3 중복과 출처 계보

중복 처리는 세 수준으로 수행한다.

1. content hash 기반 exact duplicate
2. MinHash/SimHash 또는 임베딩 기반 near duplicate
3. LLM 기반 의미적 파생·인용 관계 판정

복제 기사 500건이 하나의 보도자료에서 파생된 경우 독립 증거 500개로 계산하지 않는다. 문서 클러스터에 `root source`, `derived sources`, `independent additions`를 구분한다.

### 8.4 Entity 후보 추출

- deterministic parser와 NER로 mention을 먼저 추출한다.
- alias, 식별자, 주변 문맥과 source 정보를 저장한다.
- LLM은 복합 엔터티, 암시적 참조와 역할을 보완한다.

### 8.5 Entity Resolution

전체 엔터티 쌍을 비교하지 않는다.

```text
Candidate blocking
→ lexical and identifier matching
→ embedding reranking
→ rule-based acceptance/rejection
→ ambiguous cases to LLM judge
→ uncertain matches to quarantine
```

잘못된 merge는 대규모 오류를 전파하므로 merge operation 자체를 이벤트로 저장하고 되돌릴 수 있어야 한다. `SAME_AS` 확정 전에는 `POSSIBLY_SAME_AS` 관계를 사용할 수 있다.

### 8.6 Claim 추출

LLM은 문서 전체를 자유 형식으로 요약하지 않고 source span에 근거한 구조화 출력을 생성한다.

추출 스키마에는 다음이 포함된다.

- subject, predicate, object
- qualifier와 수량
- 사실·주장·의견·예측 구분
- 긍정·부정과 확실성
- valid time
- 원문 span
- claim speaker
- extraction confidence

### 8.7 Claim Canonicalization

표현은 다르지만 의미가 같은 claim을 canonical claim에 연결한다. 시스템은 최소한 다음 관계를 구분한다.

- equivalent
- more specific
- more general
- supports
- contradicts
- unrelated
- temporally superseded

후보군은 동일하거나 관련된 subject, predicate, time window로 먼저 축소한 후 LLM에게 판정시킨다.

### 8.8 Contradiction Detection

모든 claim 쌍을 직접 비교하지 않는다. 그래프 규칙으로 충돌 후보를 만든다.

```text
same subject
+ same or incompatible predicate
+ mutually exclusive object/value
+ overlapping valid time
→ contradiction candidate
```

LLM은 후보가 실제 모순인지, 시간 차이인지, 적용 범위 차이인지 판정한다. 반박 여부는 binary 값만 저장하지 않고 근거와 판정 이유를 남긴다.

### 8.9 그래프 반영

- 추출 결과를 바로 authoritative graph에 넣지 않는다.
- schema validation과 provenance 검사를 통과해야 한다.
- confidence가 낮거나 ontology에 없는 관계는 quarantine graph에 적재한다.
- 승인된 변경은 append-only event로 기록한다.
- materialized graph는 event log에서 재구축할 수 있게 한다.

## 9. LLM 시스템 설계

### 9.1 역할

LLM은 다음 영역에서 사용한다.

- 질문을 조사 가능한 하위 주장으로 분해
- 복합 엔터티와 claim의 구조화 추출
- Entity Resolution의 모호한 사례 판정
- Claim Canonicalization
- 모순과 시간·범위 차이 구분
- 발견되지 않은 반증과 그래프 공백 탐색
- 검색·그래프·SQL 도구 사용 계획
- 근거가 연결된 최종 보고서 작성

### 9.2 모델 계층화

모든 데이터에 최고 비용 모델을 사용하지 않는다.

| 단계                | 우선 처리 수단              |
| ------------------- | --------------------------- |
| 해시·언어·포맷 판별 | deterministic code          |
| 기본 분류·NER       | 소형 모델 또는 규칙         |
| 후보 검색           | BM25 + embedding + reranker |
| 구조화 추출         | batch 가능한 중간급 LLM     |
| 모호한 병합·모순    | 고성능 LLM                  |
| 조사 종합·반증      | 고성능 reasoning model      |

LLM routing은 예상 정보 가치, 현재 불확실성, 호출 비용을 기준으로 한다.

### 9.3 Agent 구성

#### Investigation Planner

- 질문의 범위와 시간대를 해석한다.
- 답변에 필요한 하위 claim과 증거 유형을 정의한다.
- 이미 그래프에 존재하는 지식과 공백을 구분한다.

#### Graph Explorer

- Knowledge Graph에서 관련 subgraph를 조회한다.
- 시간 조건, 출처 독립성과 관계 경로를 분석한다.

#### Retrieval Agent

- 전문 검색과 벡터 검색을 결합한다.
- 그래프 공백을 채울 가능성이 높은 문서를 찾는다.

#### Evidence Extractor

- 신규 문서에서 claim과 evidence를 추출한다.
- 정확한 source span을 필수로 반환한다.

#### Counter-Evidence Agent

- 현재 결론과 반대되는 가설을 세운다.
- 부정 검색, 다른 출처 유형과 시간 범위를 탐색한다.

#### Source Independence Judge

- 여러 자료가 동일한 근원 문서에서 파생되었는지 판단한다.
- 독립 근거 수를 보정한다.

#### Synthesis Agent

- 검증된 subgraph만 사용해 보고서를 작성한다.
- 사실, 당사자 주장, 시스템 추론과 예측을 명시적으로 구분한다.

#### Audit Agent

- 최종 보고서의 모든 검증 가능한 문장을 claim과 source span으로 역추적한다.
- 무출처 문장이나 과도한 일반화를 차단한다.

### 9.4 조사 루프

```text
Question
→ plan subclaims
→ retrieve relevant subgraph
→ identify missing evidence
→ search documents
→ extract evidence
→ resolve entities and claims
→ update provisional graph
→ search counter-evidence
→ evaluate stopping condition
→ synthesize and audit
```

종료 조건은 단순 iteration 횟수가 아니라 다음을 조합한다.

- 핵심 하위 claim의 evidence coverage
- 신규 독립 증거 발견률 감소
- contradiction 조사 완료 여부
- confidence 변화 폭
- 비용과 시간 budget

### 9.5 Prompt와 모델 버전 관리

추출 결과에는 항상 다음 버전을 저장한다.

- model provider와 model ID
- prompt template hash
- structured output schema version
- ontology version
- temperature와 주요 inference parameter
- tool version

모델 교체 시 골든 데이터셋으로 회귀 테스트한 후 단계적으로 승격한다.

## 10. 검색과 GraphRAG

Orc Citadel의 검색은 세 경로를 함께 사용한다.

1. BM25: 정확한 명칭과 희귀 표현
2. Vector search: 의미적으로 유사한 문장과 주장
3. Graph traversal: 엔터티, 사건, 시간과 증거 관계

질문을 무조건 벡터 검색으로 전달하지 않는다. Agent가 질문을 다음처럼 분해한다.

```text
Entity lookup
+ temporal constraint
+ relation traversal
+ claim similarity search
+ source-type filter
```

최종 context에는 전체 문서가 아니라 필요한 source span, claim, provenance와 주변 그래프를 포함한다. 그래프에 없는 정보를 모델의 사전 지식으로 보충하는 경우 반드시 별도로 표시하고 기본적으로 최종 결론에는 포함하지 않는다.

## 11. 출처 신뢰도와 독립성

출처 신뢰도를 하나의 고정 점수로 환원하지 않는다. 다음 차원을 별도로 관리한다.

- 해당 사건의 직접 당사자인가
- 1차 자료인가, 2차 해석인가
- 다른 자료를 명시적으로 인용하는가
- 과거 정정 이력이 있는가
- 주장과 이해관계가 있는가
- 구체적인 데이터와 방법을 공개하는가
- 다른 출처와 독립적으로 정보를 취득했는가

공식 자료는 직접성은 높지만 이해관계가 있을 수 있고, 언론 보도는 독립성은 높지만 2차 자료일 수 있다. 최종 confidence는 source reputation만이 아니라 claim별 증거 구조를 기반으로 계산한다.

## 12. 평가 체계

### 12.1 데이터 품질

- 파싱 성공률
- 공개·수정 시각 추출 정확도
- exact/near-duplicate precision과 recall
- 원문 span 보존율
- 출처 계보 정확도

### 12.2 Knowledge Graph 품질

- entity extraction precision/recall
- entity resolution precision/recall
- 잘못된 merge 비율
- relation·claim extraction 정확도
- temporal interval 정확도
- claim canonicalization 정확도
- contradiction detection precision/recall
- provenance가 완전한 graph element 비율

Entity merge는 false positive의 피해가 더 크므로 일반적으로 precision을 recall보다 우선한다.

### 12.3 조사 품질

- 하위 질문 coverage
- claim별 인용 연결률
- 인용이 실제 문장을 지지하는 비율
- 독립 증거 수의 정확성
- 반대 증거 발견률
- 사실·주장·추론 구분 정확도
- 숨겨진 evidence를 추가했을 때 confidence 변화의 적절성

### 12.4 시스템 성능

- 초당 수집·파싱 문서 수
- 100만 문서 전체 재처리 시간
- 신규 문서의 그래프 반영 지연시간
- 문서당 LLM 처리 비용
- investigation당 비용과 latency
- 캐시 적중률
- retry와 dead-letter 비율
- graph query p50/p95/p99 latency

### 12.5 골든 데이터셋

초기 도메인에서 전문가 또는 수작업 검토를 통해 다음 세트를 만든다.

- entity mention 1,000개
- entity pair 판정 1,000개
- claim/evidence span 500개
- equivalent·specific·contradictory claim pair 500개
- 출처 계보 클러스터 200개
- 최종 조사 질문 20~50개

골든 데이터셋은 모델과 ontology 변경의 회귀 테스트에 사용한다.

## 13. 안전과 거버넌스

- 공개적으로 허용된 자료만 수집한다.
- 개인정보와 민감 정보는 최소화하고 별도의 retention 정책을 둔다.
- 삭제 요청과 원천 문서 제거를 그래프 파생 데이터까지 전파할 수 있어야 한다.
- 모델이 생성한 신규 사실은 source span 없이는 authoritative graph에 저장하지 않는다.
- 사람에 대한 부정적 주장은 복수 출처와 높은 검증 기준을 요구한다.
- 결론에는 불확실성, 출처 한계와 알려지지 않은 부분을 표시한다.
- 그래프 변경과 수동 교정을 감사 로그에 남긴다.
- 크롤링 정책, 데이터 라이선스와 재배포 가능 여부를 source별로 관리한다.

## 14. 관측 가능성과 운영

파이프라인의 각 작업에 공통 correlation ID를 부여한다.

```text
source fetch
→ document version
→ parse job
→ extraction job
→ resolution decision
→ graph mutation
→ investigation result
```

주요 대시보드는 다음과 같다.

- source별 수집 성공률과 신선도
- stage별 처리량과 backlog
- 모델별 호출량, 비용과 오류율
- schema validation 실패 유형
- quarantine 규모와 체류 시간
- ontology·모델 버전별 품질 변화
- graph 규모와 query latency
- investigation별 evidence coverage

전체 작업은 idempotency key를 가져야 하며, retry해도 동일 graph mutation이 중복 생성되지 않아야 한다.

## 15. 테스트 전략

### Unit Test

- 문서 fingerprint
- temporal interval normalization
- provenance offset mapping
- graph mutation validation
- confidence aggregation

### Contract Test

- LLM structured output schema
- source adapter
- OpenSearch/graph DB query result shape
- ontology version compatibility

### Integration Test

- 문서 수집부터 graph 반영까지
- 변경된 문서의 새로운 version 생성
- entity merge와 rollback
- 삭제 요청의 파생 데이터 전파

### Evaluation Test

- 골든 데이터셋 기반 추출·resolution 평가
- 프롬프트·모델 변경 회귀 테스트
- 반증 탐색 ablation test
- graph 사용 유무에 따른 조사 성능 비교

### Load Test

- 10만·100만 문서 batch ingestion
- 대량 graph mutation
- 동시 investigation 요청
- 전체 rebuild와 부분 recomputation 비교

## 16. 단계별 로드맵

### Phase 0 — 설계 및 데이터 검증, 1~2주

- 초기 도메인과 source 3~5개 선정
- 최소 ontology 정의
- 데이터 이용 조건 검토
- 1만 문서 샘플 확보
- provenance와 bitemporal 모델 prototype

완료 조건:

- 원문에서 graph element까지 왕복 추적 가능
- 동일 문서를 다시 처리해도 중복 mutation이 없음

### Phase 1 — 10만 문서 MVP, 3~5주

- raw/normalized/curated 저장 계층
- parsing과 dedup
- entity·claim extraction
- Neo4j 기반 graph 적재
- 기본 graph explorer
- 5개 조사 질문 end-to-end 지원

완료 조건:

- 10만 문서를 전체 재처리할 수 있음
- 최종 보고서의 검증 가능 문장에 source span이 연결됨

### Phase 2 — Entity와 Claim 품질, 6~8주

- 후보 blocking과 Entity Resolution
- Claim Canonicalization
- 출처 계보 모델
- contradiction candidate 생성
- quarantine과 review workflow
- 골든 데이터셋 구축

완료 조건:

- 핵심 품질 지표를 자동 계산
- entity merge를 감사하고 rollback 가능

### Phase 3 — Research Agent, 9~10주

- Planner, Graph Explorer와 Retrieval Agent
- Counter-Evidence Agent
- Synthesis와 Audit Agent
- 조사 budget과 종료 조건
- 비용·evidence coverage 대시보드

완료 조건:

- Agent가 그래프 공백을 찾아 신규 evidence를 추가
- 반증 탐색을 제거한 버전보다 평가 점수가 향상

### Phase 4 — 100만 문서 확장, 11~12주

- 분산 batch 처리
- 증분 graph update
- 대량 embedding·LLM batch inference
- ClickHouse 기반 분석
- full rebuild와 partial recomputation benchmark

완료 조건:

- 100만 문서 처리 시간과 비용 공개
- 신규 문서가 목표 SLO 안에 graph에 반영됨

### Phase 5 — 1,000만 문서 Challenge

- 다국어 entity resolution
- hot/cold graph 분리
- impact graph 기반 부분 재계산
- source별 adaptive scheduling
- ontology migration 자동화
- 지속적 Citadel 관찰 Campaign과 Signal Spire 변경 알림

## 17. 주요 기술적 의사결정

### Graph DB와 Source of Truth

Graph DB를 유일한 원본으로 삼지 않는다. immutable raw document, curated lakehouse table과 append-only mutation log를 source of truth로 유지하고 graph는 재구축 가능한 serving representation으로 취급한다.

### Event-driven Graph Mutation

엔터티 merge, claim 생성, supersession과 삭제를 event로 저장한다. 이는 rollback, replay, audit와 새로운 graph engine으로의 migration을 가능하게 한다.

### Precision-first Entity Resolution

잘못된 merge는 연결된 모든 claim을 오염시킨다. 불확실한 경우 병합하지 않고 후보 관계로 유지한다.

### Human Review as Data

사람의 검토는 단순 수정 UI가 아니라 학습·평가 데이터 생성 과정이다. 모든 결정에 원래 모델 출력, 수정 결과와 이유를 함께 저장한다.

### Evidence-first Generation

보고서를 먼저 생성한 뒤 출처를 붙이지 않는다. 검증된 claim과 evidence subgraph를 먼저 확정하고 그 범위 안에서만 문장을 생성한다.

## 18. 주요 위험과 대응

| 위험            | 영향                  | 대응                                     |
| --------------- | --------------------- | ---------------------------------------- |
| LLM 추출 오류   | 그래프 오염           | source span 필수, quarantine, 골든 평가  |
| Entity 오병합   | 광범위한 관계 오염    | precision 우선, reversible merge         |
| 비용 폭증       | 확장 불가             | 후보 축소, batch inference, 모델 routing |
| 동일 출처 복제  | confidence 과대평가   | 문서 계보와 독립성 그래프                |
| ontology 폭발   | 유지보수 불가         | versioning, proposal→review→promotion    |
| 시간 정보 누락  | 허위 모순             | partial interval과 unknown 상태 지원     |
| 데이터 라이선스 | 공개 제한             | source별 정책, 원문 재배포 분리          |
| 평가 부재       | 데모 이상의 발전 불가 | 초기부터 골든 데이터셋 구축              |
| 과도한 인프라   | 개발 지연             | 단계별 도입과 측정 기반 분리             |

## 19. 공개 데모 시나리오

### 데모 1: 주장 변화

한 기업의 공급망 관련 공식 발언이 2년간 어떻게 변했는지 타임라인으로 보여준다.

### 데모 2: 출처 독립성

동일한 보도자료에서 파생된 기사들을 하나의 근원 클러스터로 축소하고, 실제 독립 근거 수가 어떻게 달라지는지 보여준다.

### 데모 3: 모순 발견

공식 발표와 후속 공시·계약 데이터가 충돌하는 사례를 Evidence Graph로 제시한다.

### 데모 4: 신규 증거 영향

새 문서를 ingestion한 후 기존 claim confidence와 최종 결론이 어떤 경로로 갱신되는지 실시간으로 보여준다.

### 데모 5: 감사 가능한 답변

보고서의 문장을 선택하면 관련 claim, evidence, 원문 구절, 문서 버전과 extraction model까지 역추적한다.

## 20. 포트폴리오 산출물

- 아키텍처와 ontology 설계 문서
- 재현 가능한 로컬 개발 환경
- 공개 가능한 소규모 샘플 데이터셋
- Entity Resolution·Claim Extraction 골든 데이터셋
- 데이터·모델 lineage 대시보드
- 10만·100만 문서 처리 benchmark
- Graph Explorer와 조사 보고서 UI
- 모델·프롬프트 변경 평가 리포트
- 전체 rebuild와 증분 업데이트 비교 글
- 잘못된 merge를 탐지하고 복구한 사례 연구

프로젝트의 가치는 기능 수보다 다음 질문에 수치로 답할 수 있을 때 드러난다.

- 얼마나 많은 데이터를 처리했는가?
- 한 문서 처리 비용은 얼마인가?
- Knowledge Graph는 얼마나 정확한가?
- 잘못된 병합을 어떻게 발견하고 복구하는가?
- 최종 결론의 각 문장을 원문까지 추적할 수 있는가?
- Graph와 반증 Agent가 실제로 조사 품질을 향상시키는가?

## 21. 최종 성공 기준

MVP는 다음 조건을 모두 충족할 때 완료된 것으로 본다.

1. 10만 건 이상의 실제 공개 문서를 처리한다.
2. 전체 데이터셋을 처음부터 재처리할 수 있다.
3. 모든 authoritative claim에 source span과 버전 정보가 있다.
4. Entity Resolution과 Claim Extraction 평가 수치를 공개한다.
5. 동일 근원에서 파생된 출처를 독립 증거로 중복 계산하지 않는다.
6. valid time과 transaction time을 사용해 변화 이력을 재현한다.
7. Research Agent가 그래프 공백과 반대 증거를 탐색한다.
8. 최종 보고서의 검증 가능 문장을 그래프와 원문으로 감사할 수 있다.
9. 문서당 처리 비용과 전체 처리 시간을 측정한다.
10. 모델·프롬프트·ontology 버전 변경에 대한 회귀 테스트가 존재한다.

장기적인 성공은 1,000만 문서를 저장했다는 사실이 아니라, **새 증거가 들어왔을 때 어떤 결론이 왜 바뀌었는지를 정확하고 재현 가능하게 설명하는 것**이다.
