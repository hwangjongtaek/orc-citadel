# Orc Citadel — 로드맵 & 진행 관리

> 이 문서는 프로젝트 **진행 내역을 추적**한다. 스펙 정의는 [`docs/design/`](./design/README.md)(SSOT)에 있고, 여기서는 "무엇을 언제 어디까지 했는가"만 관리한다.
> 규칙: 설계·구현 변경은 (1) 해당 design 문서 수정 (2) `design/README.md` Spec version 반영 (3) 본 문서 §5 Changelog 기록의 3단계를 거친다.

- **최종 갱신:** 2026-08-03
- **현재 단계:** Phase 0 (설계·데이터 검증) — *설계 문서 Review 승격 완료, Stable 확정 대기*
- **Spec version:** 0.1.0 · **Ontology version:** 1.0.0

## 1. 상태 요약 (한눈에)

| 트랙 | 상태 | 비고 |
| --- | --- | --- |
| 상세 설계 (Design SSOT) | 🟡 Review | 12개 문서 Review 승격. 리뷰 패스 완료(BLOCKER 3 + MAJOR 36 해소, 상호 일관성 재검증 전항목 PASS). Stable 확정 대기 |
| 도메인·소스 선정 | ⬜ 예정 | AI 반도체·데이터센터 공급망 확정, source 3~5개 미선정 |
| 1만 문서 샘플 | ⬜ 예정 | Phase 0 완료 조건 |
| Prototype 구현 | ⬜ 예정 | provenance·bitemporal prototype |

범례: ✅ 완료 · 🟡 진행 중 · ⬜ 예정 · ⛔ 블록됨

## 2. 설계 문서 진행 (Design SSOT)

[`docs/design/`](./design/README.md) 12개 문서의 작성 상태. 상태는 각 문서 헤더의 레전드(Draft/Review/Stable)와 동기화한다.

| # | 문서 | 작성 | 리뷰 | 확정 |
| --- | --- | :---: | :---: | :---: |
| — | README (인덱스·규약) | ✅ | ✅ | ✅ |
| 01 | architecture | ✅ | ✅ | ⬜ |
| 02 | ontology | ✅ | ✅ | ⬜ |
| 03 | storage-and-data-model | ✅ | ✅ | ⬜ |
| 04 | ingestion-and-parsing | ✅ | ✅ | ⬜ |
| 05 | resolution-and-extraction | ✅ | ✅ | ⬜ |
| 06 | graph-service | ✅ | ✅ | ⬜ |
| 07 | llm-and-agents | ✅ | ✅ | ⬜ |
| 08 | search-and-graphrag | ✅ | ✅ | ⬜ |
| 09 | api | ✅ | ✅ | ⬜ |
| 10 | evaluation-and-testing | ✅ | ✅ | ⬜ |
| 11 | observability-and-governance | ✅ | ✅ | ⬜ |

**설계 단계 종료 조건:** 12개 문서 전부 Review 통과 + 상호 참조 일관성 검증 + Phase 0 완료 조건(§3)에 매핑되는 스펙 확정.

## 3. 단계별 로드맵 (Blueprint §16 → 실행 계획)

각 Phase의 완료 조건(DoD)은 blueprint에서 가져와 검증 가능한 체크리스트로 만든다. 담당 스펙 문서를 함께 표기한다.

### Phase 0 — 설계·데이터 검증 (1~2주) · *현재*

| 작업 | 담당 스펙 | 상태 |
| --- | --- | :---: |
| 초기 도메인·source 3~5개 선정 | [04](./design/04-ingestion-and-parsing.md) | ⬜ |
| 최소 ontology 정의 | [02](./design/02-ontology.md) | ✅(v1.0.0 초안) |
| 데이터 이용 조건(라이선스) 검토 | [11](./design/11-observability-and-governance.md) | ⬜ |
| 1만 문서 샘플 확보 | [04](./design/04-ingestion-and-parsing.md) | ⬜ |
| provenance·bitemporal 모델 prototype | [03](./design/03-storage-and-data-model.md) | ⬜ |

**DoD:** ① 원문↔graph element 왕복 추적 가능 ② 동일 문서 재처리 시 중복 mutation 없음.

### Phase 1 — 10만 문서 MVP (3~5주)

| 작업 | 담당 스펙 |
| --- | --- |
| raw/normalized/curated 저장 계층 | [03](./design/03-storage-and-data-model.md) |
| parsing·dedup | [04](./design/04-ingestion-and-parsing.md) |
| entity·claim extraction | [05](./design/05-resolution-and-extraction.md) |
| Neo4j graph 적재 | [06](./design/06-graph-service.md) |
| 기본 graph explorer | [09](./design/09-api.md), DESIGN.md |
| 5개 조사 질문 end-to-end | [07](./design/07-llm-and-agents.md), [09](./design/09-api.md) |

**DoD:** ① 10만 문서 전체 재처리 가능 ② 최종 보고서 검증 가능 문장에 source span 연결.

### Phase 2 — Entity·Claim 품질 (6~8주)

| 작업 | 담당 스펙 |
| --- | --- |
| 후보 blocking + Entity Resolution | [05](./design/05-resolution-and-extraction.md) |
| Claim Canonicalization | [05](./design/05-resolution-and-extraction.md) |
| 출처 계보 모델 | [04](./design/04-ingestion-and-parsing.md), [11](./design/11-observability-and-governance.md) |
| contradiction candidate 생성 | [05](./design/05-resolution-and-extraction.md) |
| quarantine·review workflow | [05](./design/05-resolution-and-extraction.md), [06](./design/06-graph-service.md) |
| 골든 데이터셋 구축 | [10](./design/10-evaluation-and-testing.md) |

**DoD:** ① 핵심 품질 지표 자동 계산 ② entity merge 감사·rollback 가능.

### Phase 3 — Research Agent (9~10주)

| 작업 | 담당 스펙 |
| --- | --- |
| Planner·Graph Explorer·Retrieval Agent | [07](./design/07-llm-and-agents.md), [08](./design/08-search-and-graphrag.md) |
| Counter-Evidence Agent | [07](./design/07-llm-and-agents.md) |
| Synthesis·Audit Agent | [07](./design/07-llm-and-agents.md) |
| 조사 budget·종료 조건 | [07](./design/07-llm-and-agents.md) |
| 비용·evidence coverage 대시보드 | [11](./design/11-observability-and-governance.md) |

**DoD:** ① Agent가 그래프 공백 탐색·신규 evidence 추가 ② 반증 탐색 제거 버전 대비 평가 점수 향상.

### Phase 4 — 100만 문서 확장 (11~12주)

| 작업 | 담당 스펙 |
| --- | --- |
| 분산 batch 처리 | [01](./design/01-architecture.md) |
| 증분 graph update | [06](./design/06-graph-service.md) |
| 대량 embedding·LLM batch inference | [07](./design/07-llm-and-agents.md), [08](./design/08-search-and-graphrag.md) |
| ClickHouse 분석 | [11](./design/11-observability-and-governance.md) |
| full rebuild vs partial recomputation benchmark | [10](./design/10-evaluation-and-testing.md) |

**DoD:** ① 100만 문서 처리 시간·비용 공개 ② 신규 문서 SLO 내 graph 반영.

### Phase 5 — 1,000만 문서 Challenge

다국어 ER · hot/cold graph 분리 · impact graph 부분 재계산 · source adaptive scheduling · ontology migration 자동화 · 지속적 Campaign·Signal Spire. (상세 계획은 Phase 4 종료 시 확정.)

## 4. MVP 최종 성공 기준 (Blueprint §21 추적)

| # | 기준 | 검증 스펙 | 상태 |
| --- | --- | --- | :---: |
| 1 | 10만+ 실제 공개 문서 처리 | [04](./design/04-ingestion-and-parsing.md) | ⬜ |
| 2 | 전체 데이터셋 처음부터 재처리 | [01](./design/01-architecture.md), [06](./design/06-graph-service.md) | ⬜ |
| 3 | 모든 authoritative claim에 source span·버전 | [02](./design/02-ontology.md), [03](./design/03-storage-and-data-model.md) | ⬜ |
| 4 | ER·Claim Extraction 평가 수치 공개 | [10](./design/10-evaluation-and-testing.md) | ⬜ |
| 5 | 동일 근원 파생 출처 독립 중복 계산 방지 | [04](./design/04-ingestion-and-parsing.md), [11](./design/11-observability-and-governance.md) | ⬜ |
| 6 | valid/transaction time으로 변화 이력 재현 | [03](./design/03-storage-and-data-model.md) | ⬜ |
| 7 | Research Agent 공백·반대 증거 탐색 | [07](./design/07-llm-and-agents.md) | ⬜ |
| 8 | 보고서 검증 가능 문장 그래프·원문 감사 | [07](./design/07-llm-and-agents.md), [03](./design/03-storage-and-data-model.md) | ⬜ |
| 9 | 문서당 비용·전체 처리 시간 측정 | [10](./design/10-evaluation-and-testing.md), [11](./design/11-observability-and-governance.md) | ⬜ |
| 10 | 모델·프롬프트·ontology 버전 회귀 테스트 | [10](./design/10-evaluation-and-testing.md) | ⬜ |

## 5. Changelog

가장 최신이 위로. 스펙·설계 변경만 기록한다 (구현 커밋은 git 이력).

### 2026-08-03
- **설계 문서 Review 승격 (리뷰 패스 완료).** 12개 문서를 blueprint 충실도·7 불변식·상호참조·구현가능성 기준으로 병렬 심층 리뷰(문서별 11 + 상호 일관성 스윕 1). BLOCKER 3 + MAJOR 36 + MINOR 다수를 문서에 직접 반영 후 독립 재검증(전항목 PASS). 상태 `Draft`→`Review`. Spec은 0.1.0 유지(Stable 변경 아님).
  - **BLOCKER 해소:** (1) 06 Applier에 `unmerge` op 분기 추가(merge 가역성·불변식 3·4) (2) 02 미정의 `TimeInterval` 노드/`VALID_DURING` 엣지 폐기, valid time을 inline 속성 단일 표현(ADR-206) (3) 02 `Assertion` 속성표 신설 + Claim→Assertion materialization 계약(ADR-207).
  - **교차 결정(사용자 확정):** 독립 증거 수 = **출처(source) 단위**(11 §1.4 정본, 04 위임, 09 `independent_source_count`); ER LLM '동일' 판정 → **`POSSIBLY_SAME_AS` 후보만, 확정 병합은 인간확인/결정적 식별자로만**(precision-first, 05 ADR-507).
  - **정합 반영:** 버전축 4→**5축**(`extraction_code_version` 포함); 보고서 문장 `kind`→정본 `modality{fact,asserted,opinion,prediction}`(07↔09); mention ID `men-` 접두사 등록; quarantine 논리 분리(라벨)→확장 시 물리(06 ADR-603); `allow_redistribute` 재배포 게이트(04↔11); alert `campaign_id`→`investigation_id`; retention_class 정책(11); 03 promoted-claim 저장·assertions=projection 재정의; 08 hybrid fusion(RRF k=60)·embedding/reranker 핀(bge-m3); 09 authz·테넌시; 10 slo-gate 분리·held-out partition·회귀 tolerance.
- **설계 SSOT 착수.** `docs/design/` 신설. 백본 문서 작성: README(규약·ID 체계·불변식), 01-architecture, 02-ontology(v1.0.0), 03-storage-and-data-model.
- 하위 스펙 04–11 초안 작성 (수집·해소·그래프·LLM/에이전트·검색·API·평가·관측/거버넌스).
- **상호 참조 일관성 검수 완료.** 불변식 위반 없음. 수정 반영: (a) `graph_mutations.op` enum에 `unmerge` 추가(03/08/09) (b) Signal Spire 트리거 enum 09↔11 통일(정본 11 §4.1) (c) S7 idempotency key를 `mutation_id`→`idempotency_key`(stage input 해시)로 정정(01/11) (d) `MEMBER_OF` 엣지 02 §3 등재 (e) `segments.norm_char_end` 추가(양방향 offset 매핑) (f) `clus-` 접두사·운영 ID·버전 필드명 별칭 정합.
- **UI 목업 세분화.** 설계(blueprint §1.4 공간계층)에 따라 War Table 단일 목업을 8개 Citadel 공간 화면으로 세분화(`docs/mockups/`): index + Citadel Gate·Watchtower·Grand Archive·Hall of Witnesses·War Table·Council Chamber·Chronicle Vault·Signal Spire. 공유 셸 재사용, 렌더링 검증 완료. 일러스트 생성 프롬프트(`docs/mockups/illustration-prompts.md`) 추가.
- **목업 시각화 완료(마무리).** 자산 22종 연결·검증 완료:
  - 브랜드 문장 `crest-hero`(index·Gate), 화면 히어로/masthead 8종(pixel-art, `orc-citadel-hero.png` 스타일).
  - 캐릭터 초상 5종(orc-camp 복사): Council 8-Agent roster 아바타 + Gate 온보딩 + Hall 안내.
  - 빈 상태 6종 → `empty-states.html` 갤러리(no-data 조건부라 갤러리로 통합).
  - 처리 상태 2종: orc-camp 애니메이션 재사용(CSS `steps()`, `prefers-reduced-motion` 정지) — Watchtower 수집·Council 추론.
  - 일러스트 프롬프트 전량 픽셀아트·복붙용(preamble 인라인)으로 통일. 전 목업 asset 참조·링크·파싱 최종 검증 통과.
- 본 로드맵 신설.

## 6. 열린 질문 (Open Questions)

설계 확정 전 해소가 필요한 항목. 해소 시 해당 design 문서 ADR로 이전한다.

| # | 질문 | 관련 스펙 |
| --- | --- | --- |
| Q1 | 초기 source 3~5개 구체 선정(공시/뉴스/정부/연구) 및 각 라이선스 | 04, 11 |
| Q2 | near-duplicate 방법: MinHash vs 임베딩 임계값 실측 필요 | 04 |
| Q3 | Entity Resolution accept/reject 임계값 도메인 실측 | 05, 10 |
| Q4 | 그래프 DB: Neo4j Community 한계 도달 시점(노드 수·query latency) | 06, 01 |
| Q5 | LLM 비용 목표(문서당·investigation당) 실측 기준선 | 07, 10 |
| Q6 | Iceberg 승격 트리거 정량화 | 03, 01 |
