# 07 · LLM·에이전트 (Warchief's Council · Seers)

> **상태:** Review · **Spec:** 0.1.4 · **Blueprint 매핑:** §9
> 상위 규약: [README](./README.md) · 관련: [01-architecture](./01-architecture.md), [05-resolution](./05-resolution-and-extraction.md), [06-graph](./06-graph-service.md), [08-search](./08-search-and-graphrag.md)

LLM·에이전트 계층(Seers, Warchief's Council)의 사용 영역, 모델 계층화·라우팅, Agent 명세, 조사 루프(investigation loop), evidence-first 생성 계약, prompt/모델 버전 관리, structured output 계약을 정의한다. 본 문서는 blueprint §9를 구현 계약으로 확정하며, README §3 설계 불변식(특히 §3-3 agent는 graph mutate 직접 금지, §3-5 evidence-first)과 [01-architecture](./01-architecture.md) Agent Runtime 경계(§3, S9, ADR-103)를 위반할 수 없다.

**핵심 원칙(요약):**

1. **Agent는 graph read-only.** 조사에 필요한 provisional 변경조차 Lorekeepers → Graph Service의 mutation event 경로를 거친다 ([01](./01-architecture.md) ADR-103, README §3-3).
2. **Evidence-first.** 검증된 subgraph를 먼저 확정하고, 그 범위 안에서만 보고서 문장을 생성한다 (README §3-5).
3. **계층화.** 최고 비용 모델을 모든 데이터에 쓰지 않는다. deterministic code → 소형 → 검색 → 중급 LLM → 고성능 LLM → 고성능 reasoning 순으로 승급한다 (blueprint §9.2).
4. **재현성.** 모든 LLM 산출물은 버전 5축(README §2.3: ontology/schema/prompt/model/extraction_code_version)을 부착하며, 모델 교체는 골든셋 회귀 후 단계 승격한다 (blueprint §9.5, → [10](./10-evaluation-and-testing.md)).

---

## 1. LLM 사용 영역 (§9.1)

LLM은 다음 영역에서만 사용한다. 각 영역은 특정 stage/Agent와 tier에 대응한다.

| # | 사용 영역 | 담당 Agent / stage | 기본 tier | 정본 문서 |
| --- | --- | --- | --- | --- |
| 1 | 질문 → 조사 가능한 하위 주장(subclaim) 분해 | Investigation Planner | 고성능 reasoning | 본 문서 §3 |
| 2 | 복합 엔터티·claim 구조화 추출 | Evidence Extractor | 중급 LLM (batch) | [05](./05-resolution-and-extraction.md) §Claim 추출 |
| 3 | Entity Resolution 모호 사례 판정 | Source Independence Judge 계열 · Lorekeepers LLM judge | 고성능 LLM | [05](./05-resolution-and-extraction.md) §ER |
| 4 | Claim Canonicalization (equivalent/more-specific/…) | Lorekeepers LLM judge | 중급~고성능 LLM | [05](./05-resolution-and-extraction.md) §Canonicalization |
| 5 | 모순 vs 시간·범위 차이 판정 | Counter-Evidence Agent · Lorekeepers | 고성능 LLM | [05](./05-resolution-and-extraction.md) §Contradiction |
| 6 | 미발견 반증·그래프 공백 탐색 | Counter-Evidence Agent | 고성능 reasoning | 본 문서 §3 |
| 7 | 검색·그래프·SQL 도구 사용 계획 | Investigation Planner · Retrieval Agent | 고성능 reasoning / 중급 | [08](./08-search-and-graphrag.md) |
| 8 | 근거 연결된 최종 보고서 작성 | Synthesis Agent | 고성능 reasoning | 본 문서 §4 |
| 9 | 문장 → claim+source span 역추적·무출처 차단 | Audit Agent | 중급 LLM + deterministic 검증 | 본 문서 §4 |

> **비목표(blueprint §3.2):** LLM의 사전 지식만으로 사실을 추가하지 않는다. source span 없는 모델 생성 사실은 authoritative graph에 저장하지 않는다 (README §3-2, blueprint §13). 그래프에 없는 정보를 사전 지식으로 보충할 경우 반드시 별도 표시하고 기본적으로 결론에서 제외한다 (blueprint §10).

---

## 2. 모델 계층화·라우팅 (§9.2)

### 2.1 단계별 우선 수단 표

blueprint §9.2를 스펙으로 고정한다. **우선 처리 수단이 충분하면 상위 tier로 승급하지 않는다.** provider-neutral 계층(소형/중급/고성능)을 유지하되, 현재 구현의 Claude 모델을 매핑한다.

| 단계 | 처리 목적 | 우선 처리 수단 | tier | Claude 모델 id | 비용 특성 |
| --- | --- | --- | --- | --- | --- |
| L0 | 해시·언어·포맷 판별 | deterministic code | — | (LLM 미사용) | 결정적, 최저 |
| L1 | 기본 분류·NER·mention 추출 | 소형 모델 또는 규칙 | 소형 | `claude-haiku-4-5` | 저비용, 고throughput |
| L2 | 후보 검색·reranking | BM25 + embedding + reranker | 검색 (비생성) | (embedding/reranker; → [08](./08-search-and-graphrag.md)) | 중저 |
| L3 | 구조화 추출 (claim/evidence 후보) | batch 가능한 중간급 LLM | 중급 | `claude-sonnet-5` | 중, batch 50% 절감 |
| L4 | 모호한 병합·모순 판정 | 고성능 LLM | 고성능 | `claude-opus-4-8` | 고 |
| L5 | 조사 종합·반증·계획 | 고성능 reasoning model | 고성능 reasoning | `claude-opus-4-8` (adaptive thinking, `effort: high`~`xhigh`) | 최고 |

> **주석:** L4·L5는 모두 최상위 tier(`claude-opus-4-8`)이나 **호출 형태**로 구분한다 — L4는 단발 판정(structured output, low~medium effort), L5는 tool 사용·다단계 reasoning(adaptive thinking + high/xhigh effort, task budget). 모델 id는 [README §2.3](./README.md) 버전 5축의 `model_id` 필드로 산출물에 기록된다. provider·id는 교체 가능하며, blueprint가 "소형/중급/고성능"으로 지정한 계층 의미는 provider-neutral로 유지한다.

> **model_id 핀 정책:** 본 문서 본문·ADR은 3개 tier를 모두 **alias**(`claude-haiku-4-5` / `claude-sonnet-5` / `claude-opus-4-8`)로 표기해 표기를 통일한다. 재현성(§6)이 요구하는 결정적 스냅샷 핀은 산출물의 `model_id` 필드에 배포 시점 dated snapshot(가용한 경우, 예: `claude-haiku-4-5-20251001`; dated snapshot이 없는 alias는 alias 그대로)으로 기록한다. 문서는 alias, 산출물은 배포-시점 핀 — 두 층을 분리한다.

### 2.2 LLM routing 기준

routing 결정은 세 축의 함수다 (blueprint §9.2 마지막 문장). 상위 tier 승급은 **기대 정보 가치 > 예상 호출 비용**일 때만 허용한다.

| 축 | 정의 | routing 영향 |
| --- | --- | --- |
| **예상 정보 가치** (`expected_info_gain`) | 이 호출이 confidence·evidence coverage를 얼마나 개선할 것으로 추정되는가 | 높을수록 상위 tier 허용 |
| **현재 불확실성** (`current_uncertainty`) | 대상 claim/판정의 confidence 분산, 독립 증거 부족도 | 높을수록 상위 tier·reasoning 승급 |
| **호출 비용** (`call_cost`) | tier별 token 단가 × 예상 token, budget 잔량 | 높을수록 하위 tier·batch·캐시 유도 |

의사결정 규칙:

```text
route(task):
  if task.deterministic:                      return L0
  if task in {classify, ner} and not ambiguous: return L1        # 소형
  if task == candidate_search:                return L2          # BM25+embed+rerank
  if task == structured_extraction:
      return L3 (batch)                                          # 중급, batch
  if task in {ambiguous_merge, contradiction_judgment}:
      # 불확실성이 낮고 정보가치가 작으면 중급으로 시도, 실패 시 승급
      return L4 if uncertainty_high or value_high else L3
  if task in {plan, counter_evidence, synthesize}:
      return L5 (reasoning, adaptive thinking)                   # 고성능 reasoning
  # 승급 게이트: 하위 tier 산출물의 confidence가 임계 미만이면 1단계 승급
  if result.confidence < τ_tier and budget_remaining > cost(next_tier):
      escalate()
```

- **batch 우선:** L3 대량 추출은 Message Batches(비latency-민감, 50% 절감)로 처리한다. 대화형 조사 경로(L5)는 streaming.
- **prompt caching:** 조사 세션 내 고정 prefix(ontology 요약, tool 정의, 시스템 프롬프트)는 cache_control로 캐시한다. 모델·tool 교체는 캐시를 무효화하므로 세션 중 tier 전환은 subagent로 분리한다.

### 2.3 승급 임계·추정법 (ADR-706)

승급 게이트의 `τ_tier`(하위 tier 산출물 confidence 임계)와 정보가치·비용 추정 방식을 초기 기본값으로 고정한다. **모든 값은 placeholder이며 골든셋([10](./10-evaluation-and-testing.md)) 실측으로 조정한다.**

| 파라미터 | 정의 | 초기 기본값 |
| --- | --- | --- |
| `τ_L1→L3` | 소형(L1) 산출물 confidence 하한, 미만 시 L3 재시도 | 0.75 |
| `τ_L3→L4` | 중급(L3) 판정 confidence 하한, 미만 시 L4 승급 | 0.70 |
| `τ_L4→L5` | 고성능 단발(L4) 판정 confidence 하한, 미만 시 L5 reasoning 승급 | 0.65 |

- **`expected_info_gain` 추정(coverage-delta 휴리스틱):** 호출 전후 evidence coverage(§4.3 A) 예상 증가분 `Δcoverage`와 대상 claim confidence 분산의 곱으로 근사한다 — `expected_info_gain ≈ Δcoverage_est × var(confidence)`. `Δcoverage_est`는 미충족 subclaim이 이 호출로 채워질 것으로 추정되는 비율(planner의 gap 라벨 기준).
- **`call_cost` 추정(토큰 추정):** `call_cost ≈ (예상 input_token + 예상 output_token) × tier_단가`. 예상 token은 prompt 템플릿 고정분 + 대상 span/subgraph 크기로 산정하고, 남은 budget 대비 정규화한다.
- **승급 결정:** `expected_info_gain > call_cost` 이고 `budget_remaining > cost(next_tier)`일 때만 승급한다(§2.2 규칙과 동일).

---

## 3. Agent 명세 (§9.3)

Warchief's Council의 8개 Agent를 소절로 정의한다. **공통 불변식:** 모든 Agent는 Graph Service·Search Service의 **read API만** 사용하며, 그래프 변경은 Lorekeepers → Graph Service의 mutation event 경로만 거친다 ([01](./01-architecture.md) §3 경계 규칙, ADR-103, README §3-3). 모든 산출물에 버전 5축(README §2.3)과 correlation ID를 부착한다.

**도구 표기:** `graph:read`(War Table 조회), `search`(BM25+vector, → [08](./08-search-and-graphrag.md)), `sql:read`(curated lakehouse 조회). 그래프 변경은 **agent tool이 아니라** Lorekeepers → Graph Service handoff로만 이뤄진다(§7.1, ADR-103) — Agent는 후보를 제안할 뿐 mutate tool을 호출하지 않는다.

### 3.1 Agent I/O 요약 표

| Agent | 입력 | 출력 | 사용 도구 | 모델 tier | 핵심 불변식 |
| --- | --- | --- | --- | --- | --- |
| Investigation Planner | question, scope(기간·지역·source·depth) | subclaim 트리, 필요 evidence 유형, 알려진 지식/공백 구분 | `graph:read` | 고성능 reasoning (L5) | 그래프 기존 지식과 공백을 명시적으로 분리 |
| Graph Explorer | subclaim, 시간 조건 | 관련 subgraph, 관계 경로, 출처 독립성 요약 | `graph:read` | 중급 (L3) | read-only; provisional graph만 읽음 |
| Retrieval Agent | 공백 목록, entity/시간/관계 제약 | 후보 문서·span 목록 | `search`, `sql:read` | 중급 (L3) / L2 도구 | 전체 문서 아닌 span 단위 반환 |
| Evidence Extractor | 신규 문서 span | claim/evidence 후보(강제 JSON schema) + source span 필수 | `search`(문맥) | 중급 batch (L3) | source span 없는 추출 폐기 |
| Counter-Evidence Agent | 현재 결론·claim | 반대 가설, 부정 검색 질의, 모순 후보 | `search`, `graph:read` | 고성능 reasoning (L5) | 반박은 근거+판정 이유와 함께 |
| Source Independence Judge | 문서 클러스터, 계보 후보 | 독립 근거 수 보정, root/derived 구분 | `graph:read`, `sql:read` | 고성능 LLM (L4) | 복제본을 독립 증거로 계산 금지 |
| Synthesis Agent | 검증 확정된 subgraph | 보고서(`modality`: fact/asserted/opinion/prediction 구분) | `graph:read` | 고성능 reasoning (L5) | 검증 subgraph 밖 문장 생성 금지 |
| Audit Agent | 보고서 문장 + subgraph | 문장별 claim+source span 매핑, 무출처 문장 차단 리스트 | `graph:read`, `sql:read` | 중급 LLM + deterministic (L3) | 모든 검증가능 문장이 span으로 역추적되어야 통과 |

### 3.2 Investigation Planner

- **역할:** 질문의 범위·시간대를 해석하고, 답변에 필요한 하위 claim과 증거 유형을 정의하며, 그래프의 기존 지식과 공백을 구분한다.
- **입력:** `{question, scope: {time_range?, region?, source_types?, depth?}}` (→ [09-api](./09-api.md) 조사 요청).
- **출력(strict JSON):** `{subclaims: [{id, text, required_evidence_types[], known: bool, gap_reason?}], plan: {tool_calls[]}}`.
- **도구:** `graph:read`(기존 subgraph 존재 여부 확인).
- **tier:** L5 (고성능 reasoning, adaptive thinking).
- **불변식:** subclaim마다 `known`/`gap` 라벨 필수. mutation 없음.

### 3.3 Graph Explorer

- **역할:** War Table에서 subclaim 관련 subgraph를 조회하고 시간 조건·출처 독립성·관계 경로를 분석한다.
- **입력:** `{subclaim, time_constraint?}` → **출력:** `{subgraph, relation_paths[], independence_summary}`.
- **도구:** `graph:read` (materialized + quarantine 구분 표시, → [06](./06-graph-service.md)).
- **tier:** L3. **불변식:** read-only. provisional graph를 authoritative와 구분해 반환.

### 3.4 Retrieval Agent

- **역할:** 전문(BM25)·벡터 검색을 결합해 그래프 공백을 채울 가능성이 높은 문서·span을 찾는다.
- **입력:** `{gaps[], entity_filter?, time_filter?, relation_filter?, source_type_filter?}` → **출력:** `{candidates: [{doc_id, span, score, retrieval_path}]}`.
- **도구:** `search`(hybrid, → [08](./08-search-and-graphrag.md)), `sql:read`.
- **tier:** L3(질의 계획) + L2 도구(실행). **불변식:** 전체 문서가 아닌 필요한 span·주변 그래프만 반환 (blueprint §10).

> **구현 (MVP #7 — SEARCH 단계, 2026-08-12):** `retrieval.py` — Retrieval Agent. 조사 루프의 SEARCH(§4, `gap → 후보 문서·span`)를 read-only로 구축. corpus는 멘션 `context_window`(문장 텍스트), 질의 용어 BM25 근사 선형 스코어로 후보 span 정렬·k 상한·결정적(08 GraphRAG 중 BM25 경로). 출력 `{doc_id, segment_id, span, score, retrieval_path}` (§3.4 불변식 — 전체 문서 아닌 span만 반환). `InvestigationRunner`의 gap subclaim에 배선(gap → retrieved 후보), `viewer._api_investigate` 응답에 `retrieved` 노출. **read-only·결정적.** TDD — `test_retrieval` 신규 5개 + `test_investigation_runner` SEARCH 배선 1개 + `test_viewer_graph` 노출 1개 — 스위트 507→**514개 통과**(회귀 0).

### 3.5 Evidence Extractor

- **역할:** 신규 문서에서 claim·evidence 후보를 추출하고 정확한 source span을 필수로 반환한다.
- **입력:** `{normalized_doc, target_spans[]}` → **출력:** [05](./05-resolution-and-extraction.md) claim 추출 schema (subject/predicate/object, qualifier, 사실·주장·의견·예측 구분, 확실성, valid time, source span, claim speaker, extraction confidence).
- **도구:** `search`(주변 문맥). **tier:** L3 (batch).
- **불변식:** source span 없는 후보는 폐기(README §3-2). 산출물은 Lorekeepers 경로로 전달되어 resolution·canonicalization을 거친다 — Extractor는 graph를 직접 쓰지 않는다.

### 3.6 Counter-Evidence Agent

- **역할:** 현재 결론과 반대되는 가설을 세우고 부정 검색, 다른 출처 유형·시간 범위를 탐색해 반증·모순 후보를 만든다.
- **입력:** `{current_conclusion, claims[]}` → **출력:** `{hypotheses[], negative_queries[], contradiction_candidates[]}`.
- **도구:** `search`, `graph:read`. **tier:** L5.
- **불변식:** 반박 여부를 binary로만 남기지 않고 근거·판정 이유 포함 (blueprint §8.8). 모순 vs 시간차 vs 범위차를 구분해 라벨(→ [05](./05-resolution-and-extraction.md)).

### 3.7 Source Independence Judge

- **역할:** 여러 자료가 동일 근원 문서에서 파생되었는지 판단하고 독립 근거 수를 보정한다.
- **입력:** `{doc_cluster, provenance_candidates}` → **출력:** `{root_source, derived_sources[], independent_additions[], corrected_independent_count}`.
- **도구:** `graph:read`, `sql:read`(문서 계보·중복 클러스터). **tier:** L4.
- **불변식:** 복제 기사를 독립 증거로 중복 계산 금지 (blueprint §8.3, §11, 최종 성공기준 §21-5).

### 3.8 Synthesis Agent

- **역할:** **검증된 subgraph만** 사용해 보고서를 작성하고 문장을 `modality`(fact/asserted/opinion/prediction)로 명시 구분한다. 모델 사전 지식 기반 추론은 별도 modality 값이 아니라 `model_prior` 플래그로 표기하며 기본적으로 결론에서 제외한다(별도 `inference` modality는 신설하지 않음 — [09-api](./09-api.md) §3 정합).
- **입력:** `{verified_subgraph}` → **출력:** [09-api](./09-api.md) §3 Report 스키마와 동일한 필드명 — `{report: {sections: [{title, statements: [{text, modality: fact|asserted|opinion|prediction, claim_ref, speaker_id?}]}]}, confidence}`. (`forecast`→`prediction`, `claim`→`asserted`로 정본화; 이전 `kind`·`supporting_claim_ids[]` 표기 폐기.)
- **도구:** `graph:read`. **tier:** L5.
- **불변식(§3-5):** 검증 subgraph 밖의 문장을 생성하지 않는다. `fact`/`asserted` 문장은 반드시 `claim_ref`를 참조한다(무출처는 `claim_ref=null` 이면서 `prediction`/`opinion`만 허용, [09-api](./09-api.md) §3 Audit 계약).

### 3.9 Audit Agent

- **역할:** 최종 보고서의 모든 검증 가능 문장을 claim·source span으로 역추적하고 무출처 문장·과도한 일반화를 차단한다.
- **입력:** `{report.statements[], verified_subgraph}`(Synthesis 출력 §3.8과 동일 필드명) → **출력:** `{trace: [{statement_ref, claim_ref, source_span, verified: bool}], blocked_statements[]}`.
- **도구:** `graph:read`, `sql:read`(provenance chain, → [03](./03-storage-and-data-model.md) §provenance). **tier:** L3 LLM + deterministic span 대조.
- **불변식(§3-5):** 모든 검증가능 문장이 span으로 역추적되어야 보고서가 통과한다. 실패 문장은 `blocked_statements`로 반환되고 보고서에서 제거되거나 "unsupported"로 명시 표기된다.

---

## 4. 조사 루프 (§9.4)

blueprint §9.4 파이프라인을 **상태 기계(state machine)**로 확정한다. Agent Runtime은 stage S9 (`inv_id + step_id` idempotency)로 실행되며 각 step은 재실행 안전하다 ([01](./01-architecture.md) §4).

> **step ID 스킴:** 각 조사 step은 investigation(`inv-`) 범위 내 transient ID `step-<seq>`를 가진다(순번, 예: `step-014` — [09-api](./09-api.md) agent_process 노출과 일치). `step-`은 조사 세션 내에서만 유효한 transient 식별자로, 영속 저장은 investigation step record의 correlation ID(`corr-`)로 승격된다(→ [11](./11-observability-and-governance.md)).

### 4.1 상태 전이

```text
                 ┌─────────────────────────────────────────────────────┐
                 ▼                                                     │
[PLAN] ─▶ [RETRIEVE_SUBGRAPH] ─▶ [IDENTIFY_GAPS] ─▶ [SEARCH] ─▶ [EXTRACT]
                                        ▲                            │
                                        │                            ▼
                                        │                        [RESOLVE]
                                        │                            │  (Lorekeepers 경로)
                                        │                            ▼
                                        │                   [UPDATE_PROVISIONAL]
                                        │                            │
                                        │                            ▼
                                        │                   [COUNTER_EVIDENCE]
                                        │                            │
                                        └──── (미충족) ◀── [STOPPING?] ──(충족)──▶ [SYNTHESIZE] ─▶ [AUDIT] ─▶ done
                                                                                                      │
                                                                                        (audit 실패) ─┘  # 무출처 문장 → 재조사 or 제거
```

### 4.2 상태별 정의

| 상태 | 담당 Agent | 입력→출력 | 비고 |
| --- | --- | --- | --- |
| PLAN | Investigation Planner | question → subclaim 트리 | L5 |
| RETRIEVE_SUBGRAPH | Graph Explorer | subclaim → 기존 subgraph | read-only |
| IDENTIFY_GAPS | Planner/Explorer | subgraph → 공백 목록 | evidence coverage 계산 |
| SEARCH | Retrieval Agent | gaps → 후보 문서·span | hybrid retrieval |
| EXTRACT | Evidence Extractor | span → claim/evidence 후보 | strict JSON, batch |
| RESOLVE | (Lorekeepers) | 후보 → resolved entities/claims | Agent는 제안, apply는 Lorekeepers ([05](./05-resolution-and-extraction.md)) |
| UPDATE_PROVISIONAL | (Graph Service) | resolution decision → provisional graph mutation event | append-only event ([06](./06-graph-service.md)) |
| COUNTER_EVIDENCE | Counter-Evidence Agent | 현재 결론 → 반증·모순 후보 | 새 gap 생성 시 IDENTIFY_GAPS로 복귀 |
| STOPPING? | Runtime | 종료 조건 평가 | §4.3 |
| SYNTHESIZE | Synthesis Agent | verified subgraph → 보고서 | evidence-first |
| AUDIT | Audit Agent | 보고서 → trace | 실패 시 재조사/제거 |

> **불변식:** RESOLVE·UPDATE_PROVISIONAL는 Agent가 아닌 Lorekeepers → Graph Service가 수행한다. Agent는 후보를 **제안**하고 read-back으로 결과를 확인할 뿐, 그래프를 직접 mutate하지 않는다 (ADR-103, README §3-3). provisional 변경도 append-only mutation event로 기록되어 rollback 가능하다 (README §3-3, [06](./06-graph-service.md)).

### 4.3 종료 조건 (조합)

단순 iteration 횟수가 아니라 다음을 **조합**해 평가한다 (blueprint §9.4). `STOP = (A ∧ B ∧ C) ∨ D` 형태로, 예산(D)은 항상 hard stop.

| # | 조건 | 정의 | 임계(초기 기본값) |
| --- | --- | --- | --- |
| A | evidence coverage | 핵심 subclaim 중 충분한 지지 증거를 가진 비율 | ≥ 0.9 |
| B | 신규 독립 증거 발견률 감소 | 최근 N step의 신규 독립 증거 증가율 | < ε (예: 0.05) |
| C | contradiction 조사 완료 | 발견된 모순 후보가 모두 판정(모순/시간차/범위차)됨 | 미해결 = 0 |
| D | budget (hard stop) | 누적 비용·시간·step 수 | budget 소진 시 즉시 종료 |
| — | confidence 변화 폭 | 최근 step 간 결론 confidence 변화 | < δ (초기 기본값 0.02) 이면 수렴 신호(A·B 보강) |

- **종료 로직:** `A ∧ B ∧ C` 충족 → 정상 종료(SYNTHESIZE). `D` 도달 → 조기 종료(현재까지 verified subgraph로 SYNTHESIZE, 불확실성 명시). confidence 변화 폭은 A·B 수렴 판단의 보조 신호로 사용한다.
- **task budget:** L5 조사 루프는 token task budget(고성능 reasoning의 self-pacing)을 설정해 예산 내에서 우아하게 마무리하게 한다. `max_tokens`는 별도 hard ceiling.

> **Prototype 구현 노트 (2026-08-03, S43–S47):** 조사 루프의 read-only 지형을 prototype으로 확인했다 — Graph Explorer(§3.3)·Counter-Evidence(§3.6)·Synthesis/Audit(§3.8/§3.9)의 출력(vector: subgraph/independence, hypotheses/negative_queries/contradiction_candidates, evidence-first report/audit violations)이 커리티드 존·소비 계층(S28–S31) 위에서 결정적·read-only로 동작(불변식 §3-3). evidence coverage(§4.2)와 종료 조건(coverage ≥ 0.80·no_new_evidence·budget)도 구현(S43/S46). LLM routing·expected_info_gain 보정치(§2.3, ADR-706)·task budget token 활용은 Phase 1 실측에서 조정. 계약 변경 없음 — 구현은 이 정본을 충실 반영.

---

## 5. Evidence-first 생성 계약 (불변식 §3-5)

blueprint §17 "Evidence-first Generation"을 스펙 강제 규칙으로 승격한다 (README §3-5). 보고서를 먼저 생성한 뒤 출처를 붙이지 않는다.

**계약 3단계:**

1. **검증 subgraph 확정.** SYNTHESIZE 진입 전, 조사 루프는 verified subgraph를 확정한다 — provenance를 가지며 schema/독립성 검사를 통과한 claim·evidence·assertion만 포함한다 (README §3-2, [03](./03-storage-and-data-model.md) §provenance).
2. **범위 내 생성.** Synthesis Agent는 이 subgraph의 요소만 참조해 문장을 생성한다. 각 문장은 [09-api](./09-api.md) §3 스키마의 `claim_ref`(→ provenance)를 부착하며, subgraph 밖 사실을 도입하지 않는다. 모델 사전 지식으로 채운 내용은 `model_prior` 플래그로 표기하고 기본적으로 결론에서 제외한다 (blueprint §10).
3. **역추적 감사.** Audit Agent가 모든 **검증 가능한** 문장을 `claim → source span → normalized doc version → raw document → source URL`의 provenance chain으로 역추적한다 (blueprint §6.5). 역추적 실패 문장(무출처·과도한 일반화)은 차단되어 보고서에서 제거되거나 "unsupported"로 명시 표기된다.

**출력 계약:** 최종 조사 결과는 blueprint §1의 3요소를 함께 제공한다 — (1) 조사 보고서, (2) Evidence Graph(verified subgraph), (3) 모든 주장·원문 구절 간 provenance(Audit trace). 검증가능 문장에 source span이 연결되지 않으면 보고서는 완료로 간주하지 않는다 (blueprint §16 Phase 1·§21-8 완료 조건).

---

## 6. Prompt·모델 버전 관리 (§9.5)

### 6.1 저장 필드 (README §2.3 5축과 정합)

모든 LLM 산출물(extraction record, resolution decision, investigation step)에는 다음 버전 튜플을 부착한다 (blueprint §9.5). README §2.3의 버전 5축(ontology/schema/prompt/model/extraction_code_version)을 세부 필드로 전개한다.

```json
{
  "model_provider": "anthropic",
  "model_id": "claude-sonnet-5",
  "prompt_template_hash": "sha256:...",
  "output_schema_version": "0.1.0",
  "ontology_version": "1.0.0",
  "extraction_code_version": "0.1.0",
  "inference_params": { "temperature": 0.0, "effort": "medium", "thinking": "adaptive" },
  "tool_version": "search:1.2.0,graph:1.0.0"
}
```

| 필드 | README §2.3 5축 매핑 | 목적 |
| --- | --- | --- |
| `model_provider` + `model_id` | model | 모델 재현·교체 추적 |
| `prompt_template_hash` | prompt | 프롬프트 변경 감지 (템플릿 sha256) |
| `output_schema_version` | schema | structured output 스키마 버전 (→ [03](./03-storage-and-data-model.md)) |
| `ontology_version` | ontology | 온톨로지 정합성 (→ [02-ontology](./02-ontology.md) §거버넌스) |
| `extraction_code_version` | extraction_code_version | 추출·판정 코드 버전 (graph_mutations.version_tuple 5번째 축, → [03](./03-storage-and-data-model.md) §7.1) |
| `inference_params` | (model 부속) | temperature/effort/thinking 등 결정론 파라미터 |
| `tool_version` | (schema 부속) | 사용 tool 계약 버전 |

> **정합 규칙:** blueprint §9.5의 필드는 README §2.3의 5축을 상위 개념으로 하며 상충하지 않는다. `inference_params`·`tool_version`은 각각 model·schema 축의 세부 항목이다.

### 6.2 모델·프롬프트 교체 절차

모델 교체 시 골든 데이터셋으로 회귀 테스트한 후 단계적으로 승격한다 (blueprint §9.5, §12.5, → [10](./10-evaluation-and-testing.md)).

```text
propose(new model/prompt)
  → 골든셋 회귀 (entity/claim/canonicalization/contradiction/조사 20~50)
  → 품질 지표 비교 (precision/recall, 인용 연결률, 반증 발견률)
  → 회귀 통과 시 staging 승격 → prod 승격
  → 승격 이력을 버전 튜플·ROADMAP에 기록
```

- 골든셋: entity mention 1,000 / entity pair 1,000 / claim·evidence span 500 / claim pair 500 / 계보 클러스터 200 / 조사 질문 20~50 (blueprint §12.5).
- 승격은 [README §2.6](./README.md) 변경 관리 3단계(문서·Spec version·ROADMAP)를 거친다.

---

## 7. Structured Output 계약

추출·판정 계열 LLM 호출(Evidence Extractor L3, 각종 judge L4)은 **강제 JSON schema**로 산출한다 (blueprint §8.6 "자유 형식 요약 금지").

- **강제 방식:** `output_config.format`(json_schema, `additionalProperties: false` + `required`) 또는 strict tool use(`strict: true`)를 사용한다. prefill 방식은 현행 모델에서 금지되므로 사용하지 않는다.
- **파싱:** 산출 JSON은 항상 파서로 역직렬화하며 raw string 매칭을 하지 않는다. schema validation·provenance 검사 실패 시 quarantine으로 보낸다 (blueprint §8.9, → [05](./05-resolution-and-extraction.md), [06](./06-graph-service.md)).
- **스키마 버전:** 산출 스키마는 `output_schema_version`으로 버전 관리되며 [03](./03-storage-and-data-model.md) 저장 스키마와 정합해야 한다 (contract test 대상, blueprint §15). **TBD:** 각 tool별(Extractor claim schema, judge decision schema, Synthesis report schema 등) 구체 JSON schema 본문은 미확정 — `0.1.0` 초기 버전으로 [03](./03-storage-and-data-model.md)·[09](./09-api.md)와 함께 확정 예정.

### 7.1 tool 사용 계획

Agent Runtime은 도구를 계층별로 노출한다. Agent가 그래프를 mutate하는 tool은 **존재하지 않는다** (ADR-103).

| tool | 접근 | 사용 Agent | tool_choice 정책 |
| --- | --- | --- | --- |
| `graph:read` | War Table read API (→ [06](./06-graph-service.md)) | Planner, Explorer, Counter-Evidence, Judge, Synthesis, Audit | auto |
| `search` | BM25+vector hybrid (→ [08](./08-search-and-graphrag.md)) | Retrieval, Counter-Evidence, Extractor | auto |
| `sql:read` | curated lakehouse read (→ [03](./03-storage-and-data-model.md)) | Retrieval, Judge, Audit | auto |

> **주석:** 그래프 변경 tool은 표에 없다 — provisional 변경은 Agent가 호출하는 tool이 아니라 Lorekeepers → Graph Service **handoff 채널**로 처리된다(RESOLVE/UPDATE_PROVISIONAL, §4.2). Agent는 후보를 제안하고 read-back으로 확인만 한다 (ADR-103, ADR-702).

- **계획:** Planner·Retrieval Agent가 도구 사용 순서를 계획한다 — entity lookup + temporal constraint + relation traversal + claim similarity + source-type filter로 질문을 분해한다 (blueprint §10). 최종 context는 전체 문서가 아닌 span·claim·provenance·주변 그래프로 구성한다.
- **server-tool 미사용:** 외부 web search 등 server-side tool은 조사 결론에 사용하지 않는다 — 모든 근거는 수집·검증된 corpus에서 온다 (blueprint §3.2, §13).

---

## 8. 의사결정 로그 (ADR-7xx)

| ID | 결정 | 근거 | 상태 |
| --- | --- | --- | --- |
| ADR-701 | 모델 tier를 소형=`claude-haiku-4-5` / 중급=`claude-sonnet-5` / 고성능·reasoning=`claude-opus-4-8`로 매핑(alias 표기 통일, 산출물 핀은 §2.1 정책), provider-neutral 계층 의미 유지 | 최고 비용 모델 남용 방지, 비용 폭증 위험 대응 (blueprint §9.2, §18) | Accepted |
| ADR-702 | Agent는 그래프 read-only, mutation은 Lorekeepers→Graph Service 경로만 (ADR-103 재확인) | event-driven·rollback 가능성 강제 (README §3-3) | Accepted |
| ADR-703 | Evidence-first 강제: verified subgraph 확정 후에만 문장 생성, Audit Agent 역추적 미통과 문장 차단 | 무출처 사실 방지, 감사 가능성 (README §3-5, blueprint §17, §21-8) | Accepted · **구현(P1 C)**: pipeline→조사 루프→보고서 end-to-end 드라이버(5개 질문) + `ApiFacade.get_evidence_provenance`가 extraction_record char span을 trail에 연결(DoD ②) (`tests/test_investigation_e2e.py`·`api_facade.py`, 2026-08-11) |
| ADR-704 | 추출·판정은 강제 JSON schema(`output_config.format`/strict tool use), prefill 금지 | 자유 요약 금지·contract test 정합 (blueprint §8.6, §15) | Accepted |
| ADR-705 | 모델·프롬프트 교체는 골든셋 회귀 통과 후 단계 승격, 버전 튜플·ROADMAP 기록 | 재현성·회귀 방지 (blueprint §9.5, §12.5, → [10](./10-evaluation-and-testing.md)) | Accepted |
| ADR-706 | routing 승급 임계 `τ_tier`(0.75/0.70/0.65)·종료 수렴 `δ`(0.02)를 초기 기본값으로 고정, `expected_info_gain`=coverage-delta 휴리스틱·`call_cost`=토큰 추정으로 산정(§2.3, §4.3) | 미측정 양 의존 제거해 라우팅/종료 구현 가능화; placeholder는 [10](./10-evaluation-and-testing.md) 실측 조정 | Accepted |
| ADR-707 | 보고서 문장 분류를 정본 `modality {fact,asserted,opinion,prediction}`로 통일(`kind` 폐기, `forecast`→`prediction`, `claim`→`asserted`), 필드명 09 정합(`report.statements[].claim_ref`); 모델 추론은 `inference` modality 신설 대신 `model_prior` 플래그 | 07↔09/02 vocab·필드 drift 제거, contract test 정합 (G5, → [09](./09-api.md) §3, [02](./02-ontology.md) §5.3) | Accepted |
