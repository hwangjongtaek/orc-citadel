# 10 · 평가·테스트

> **상태:** Review · **Spec:** 0.1.3 · **Blueprint 매핑:** §12, §15
> 상위 규약: [`README`](./README.md) · 관련: [`05-resolution`](./05-resolution-and-extraction.md), [`07-llm`](./07-llm-and-agents.md), [`11-observability`](./11-observability-and-governance.md)

Orc Citadel의 **평가 지표(evaluation metrics)**, **골든 데이터셋(golden dataset)**, **회귀 테스트(regression)**, **테스트 전략(test strategy)**, **CI 게이트**를 확정한다. blueprint §12(평가 체계)·§15(테스트 전략)을 구현 계약으로 승격한 문서이며, 모델·프롬프트·온톨로지 버전 변경의 **승격 게이트(promotion gate)** SSOT다 ([`README`](./README.md) §2.3, [`07-llm`](./07-llm-and-agents.md) §9.5).

핵심 원칙: 프로젝트의 가치는 기능 수가 아니라 **"KG는 얼마나 정확한가 · 잘못된 병합을 어떻게 발견/복구하는가 · 각 문장을 원문까지 추적할 수 있는가"에 수치로 답하는 것**이다 (blueprint §20). 따라서 평가는 데모의 부가물이 아니라 파이프라인의 1급 산출물이다 (blueprint §18 "평가 부재" 위험).

---

## 1. 평가 지표 정의 (§12)

blueprint §12의 4범주를 지표별 **정의·계산식·목표/게이트**로 확정한다. 목표값은 초기 도메인(AI 반도체·데이터센터 공급망) MVP 기준선이며, 실측 후 [`README`](./README.md) §2.6 절차로 조정한다. `TP`/`FP`/`FN`/`TN`은 골든셋 대조 결과다.

공통 정의:
- **Precision** `P = TP / (TP + FP)`, **Recall** `R = TP / (TP + FN)`, **F1** `= 2PR / (P + R)`.
- 목표/게이트에서 **`gate:`** 는 CI/승격 차단 임계값(미달 시 block), **`slo-gate:`** 는 운영 SLO 회귀 경보 임계값(비차단 nightly alert, §6.3), **`target:`** 은 지향값(추적·경보만)이다. `slo-gate:`/`target:`은 CI/승격을 막지 않는다.

### 1.1 데이터 품질 (§12.1)

| 지표 | 정의 | 계산식 | 목표·게이트 |
| --- | --- | --- | --- |
| 파싱 성공률 (parse success) | 본문·구조 추출에 성공한 문서 비율 | `parsed_ok / fetched_total` | `gate: ≥ 0.97` |
| 시각 추출 정확도 (time extraction) | 공개·수정 시각(`publication_time`/`revision_time`)이 정답과 일치하는 비율 | `correct_timestamps / total_docs_with_gold_time` (day 정밀도 허용) | `target: ≥ 0.95` |
| Dup precision | near-dup 판정 쌍 중 실제 중복 비율 | `TP_dup / (TP_dup + FP_dup)` | `gate: ≥ 0.98` (오클러스터는 독립성 왜곡) |
| Dup recall | 실제 중복 쌍 중 탐지 비율 | `TP_dup / (TP_dup + FN_dup)` | `target: ≥ 0.90` |
| Span 보존율 (span preservation) | 추출 element가 원문 offset 왕복(round-trip)에 성공한 비율 | `roundtrip_ok / total_elements` (`text[char_start:char_end]` 재현 일치) | `gate: = 1.0` (불변식 §3-2) |
| 계보 정확도 (lineage accuracy) | `dup_cluster`의 `root_doc_id`·독립 추가 분류가 정답과 일치하는 비율 | `correct_cluster_labels / total_gold_clusters` | `target: ≥ 0.90` |

`span 보존율`은 provenance 불변식의 직접 측정치이므로 `= 1.0`을 강한 게이트로 둔다 (offset mapping unit test와 연동, → [`03`](./03-storage-and-data-model.md) §8, §5.1).

### 1.2 KG 품질 (§12.2)

| 지표 | 정의 | 계산식 | 목표·게이트 |
| --- | --- | --- | --- |
| Entity extraction P/R | mention 추출의 정밀도·재현율 | `P/R` (span+type 일치 기준) | `gate: F1 ≥ 0.85` |
| Entity resolution P/R | `SAME_AS` 병합 판정의 정밀도·재현율 | `P/R` (골든 entity pair 대조) | **`gate: P ≥ 0.97`**, `target: R ≥ 0.85` |
| 오병합률 (wrong-merge rate) | 서로 다른 실체를 병합한 비율 | `FP_merge / total_merges` | **`gate: ≤ 0.02`** |
| Relation/Claim 추출 정확도 | `(subject, predicate, object)` 삼항 정확도 | `correct_triples / total_gold_triples` (부분점수 없음) | `gate: ≥ 0.80` |
| Temporal 정확도 (temporal interval) | `valid_from`/`valid_to`/`time_precision` 정합 비율 | `correct_intervals / total_gold_intervals` (precision 등급 일치) | `target: ≥ 0.85` |
| Canonicalization 정확도 | claim→`CanonicalClaim` 매핑 및 관계(equivalent/specific/…) 정확도 | `correct_pair_labels / total_gold_claim_pairs` | `gate: ≥ 0.85` |
| Contradiction P/R | `CONTRADICTS` 판정의 정밀도·재현율 | `P/R` (골든 claim pair 대조) | `gate: P ≥ 0.90`, `target: R ≥ 0.75` |
| Provenance 완전성 비율 | provenance가 완전한 authoritative element 비율 | `elements_with_valid_provenance / authoritative_elements` | `gate: = 1.0` (불변식 §3-2) |

> **Entity merge는 precision > recall.** 잘못된 병합은 연결된 모든 claim을 오염시키고 그래프 전역에 오류를 전파하므로 (blueprint §12.2, §18, 불변식 §3-4), resolution·오병합 게이트는 recall보다 precision을 강하게 잡는다. 불확실한 쌍은 병합하지 않고 `POSSIBLY_SAME_AS` 후보로 유지한다 (→ [`05`](./05-resolution-and-extraction.md)). 이는 recall 손실을 감수하는 **의도된 트레이드오프**다.

**구현 (MVP #4 — 평가 수치 공개, 2026-08-12):** `metrics_report.py` — ER·Claim Extraction 평가 수치를 검증 가능한 리포트로 공개. `generate_metrics_report(zone)`이 골든셋(`golden_pairs`) 존재 시에만 해당 축을 `measured=True`로 계산하고(§1.2 gate), 골든이 없는 축은 **vacuous pass 없이 `measured=False` 미측정으로 명시**(honest gap — §6.2: pass는 골든 존재 시에만 판정). **실측 (curated.duckdb, 골든 22건)**: claim extraction(canonicalization) **F1=1.00 P=1.00 R=1.00** (tp=22 fp=0 fn=0, gate 0.85 ✅) 공개. contradiction·entity resolution은 골든 contradicts 쌍 / entity pair 골든세트(§2.1) 미확보로 미측정 — Phase 2 골든 확장(§2.1) 후 측정. **read-only·결정적.** TDD — `test_metrics_report` 신규 7개 — 스위트 500→**507개 통과**(회귀 0).

**구현 (Phase 2 — 골든 확장 회귀 봉인, 2026-08-12):** 골든 contradicts 쌍 + 해당 conflict_candidates 존재 시 `metrics_report`의 **contradiction 축이 measured=True로 전환**되는 메커니즘을 회귀로 봉인. `_contradiction()`은 골든 contradicts 쌍 존재 시 measured로 전환하도록 이미 설계돼 있었고(§6.2 pass 기준 — measured 전환은 골든 contradicts 쌍이 필요, unrelated/hard-negative만으로는 전환 금지), 이를 Red→Green 테스트로 보호. 실측 단위: 골든 contradicts + conflict 존재 → **tp 계산(measured=True)**, conflict 부재 → **fn(recall 하락→hard block)**, 골든 unrelated가 conflict에 존재 → **fp(precision 압박)**. **read-only·결정적.** TDD — `test_metrics_report` 신규 증분 3개 — 스위트 507→**517개 통과**(회귀 0). 다음: entity pair 골든세트(§2.1)로 ER·오병합률(≤0.02, ADR-1001) 측정.

**구현 (Phase 2 — ER 골든 확장 measured 전환, 2026-08-12):** entity pair 골든세트(§2.1)로 `metrics_report`의 **entity_resolution 축 measured 전환** — ER P/R·**오병합률(≤0.02, ADR-1001 precision-first)** 실측. 골든 저장: `golden_entity_pairs` 테이블(§2.1 Entity pair 판정 — same/not_same/uncertain, split·gold_version·labeled_by/at human review as data §3-7) · `persist_golden_entity_pair`·`golden_entity_pairs`(결정적 golden_id ON CONFLICT no-op, 03 §5). 평가: `EvalHarness.entity_resolution_metrics` — 골든 두 entity_key가 **같은 canonical entity로 병합됐는지** 대조(ADR-507 결정적 규칙 — 공유 외부식별자 exact match · `build_entity_merge`가 zone의 해소 entity rows를 `entity_key→entity_id` 맵으로 재구성, 식별자 있으면 `id:<sorted ids>`·표면형은 `surface:<type>:<surface>`). same 병합=tp·오분리=fn, **not_same 오병합=fp(그래프 전역 오염 — 게이트 hard block)**, uncertain=병합 가정 판정 안 함(POSSIBLY_SAME_AS 유지, ADR-507·게이트 제외). `metrics_report._entity_resolution`이 same/not_same 골든 존재 시 measured, gate P ≥ 0.97 ∧ 오병합률 ≤ 0.02 · `format()`에 오병합률 노출. **스키마 변경 → Spec 0.1.5→0.1.6.** TDD — `test_metrics_report` 신규 3개(ER measured·오병합 hard block·오분리 fn) — 스위트 517→**520개 통과**(회귀 0). 다음: contradiction·ER 골든을 실제 curated.duckdb에 채워 전 축 실측, merge 감사(DoD ②) 구축.

**구현 (Phase 2 — 계보 골든 확장 measured 전환, 2026-08-12):** 계보 골든셋(§2.1, dup/independent)로 `metrics_report`의 **lineage 축 measured 전환** — dup P/R 실측. 골든 저장: `golden_lineage_pairs` 테이블 + `persist_golden_lineage_pair`·`golden_lineage_pairs`(dup/independent, split·gold_version·labeled_by/at, 결정적 golden_id ON CONFLICT no-op, 03 §5). 평가: `EvalHarness.lineage_metrics` — 골든 두 doc이 **같은 `dup_clusters` 클러스터 멤버인지** 대조(design 04 §4, `_build_cluster_membership`이 zone 계보 rows→`{doc_id: cluster_id}` 맵). dup 동클러스터=tp·오분리=fn, **independent 오축소=fp(복제 K건을 독립 K으로 세는 과대평가 방지)**. gate **Dup precision ≥ 0.98 · target R ≥ 0.90**(§1.1). `metrics_report._lineage` measured (골든 존재 시) · honest-gap(부재 시 §6.2). **스키마 변경 → Spec 0.1.8→0.1.9.** TDD — `test_metrics_report` 신규 4개(lineage measured·오축소 fp·오분리 fn·honest gap) — 스위트 531→**535개 통과**(회귀 0). 실데이터 dup_clusters 0건 → lineage 는 실제 데이터에선 honest-gap 유지.

### 1.3 조사 품질 (§12.3)

Evaluation은 최종 조사 질문(§2.1 golden question) 실행 결과를 채점한다. Synthesis/Audit Agent 출력을 대상으로 한다 (→ [`07-llm`](./07-llm-and-agents.md)).

| 지표 | 정의 | 계산식 | 목표·게이트 |
| --- | --- | --- | --- |
| 하위질문 coverage | 계획된 subclaim 중 evidence로 뒷받침된 비율 | `covered_subclaims / planned_subclaims` | `gate: ≥ 0.80` |
| 인용 연결률 (citation linkage) | 보고서 검증가능 문장 중 claim/source span이 연결된 비율 | `linked_sentences / verifiable_sentences` | `gate: = 1.0` (evidence-first, 불변식 §3-5) |
| 인용 지지율 (citation support) | 인용이 실제로 해당 문장을 지지하는 비율 | `supporting_citations / total_citations` (사람/LLM judge) | `gate: ≥ 0.95` |
| 독립증거 수 정확성 | 보고된 독립 증거 수가 정답과 일치 | `1 − mean(|reported_indep − gold_indep| / max(gold_indep, 1))` (gold=0인 경우: reported=0이면 1, 아니면 0으로 처리) | `target: ≥ 0.90` |
| 반증 발견률 (counter-evidence recall) | 골든에 존재하는 반대 증거 중 발견 비율 | `found_counter / total_gold_counter` | `target: ≥ 0.70` |
| 사실/주장/추론 구분 정확도 | 문장 `modality` 분류 정확도(fact/asserted/opinion/prediction) | `correct_modality / total_sentences` | `gate: ≥ 0.85` |
| Confidence 변화 적절성 | 숨은 evidence 추가 시 confidence 변화 방향·크기 적절성 | ablation: 지지 추가→상승·반증 추가→하락 **부호(방향) 일치율** | `target: ≥ 0.85` (부호 일치율 기준 — 방향이 우선, 크기는 부차) |

`인용 연결률 = 1.0`은 무출처 문장 차단(Audit Agent)의 직접 게이트다 (blueprint §9.3 Audit, §13).

> **LLM-as-judge 보정(calibration).** `인용 지지율`처럼 LLM judge가 채점하는 blocking 지표는, 게이트로 쓰기 전 **human agreement baseline**(judge↔human 라벨 일치도: Cohen's κ 또는 accuracy)을 골든 `dev` 파티션(§2.4)에서 측정한다. 합의도 미달 시 judge 점수를 게이트로 승격하지 않고 **사람 채점으로 강등**한다. 보정치(κ·accuracy)는 회귀 리포트에 함께 남긴다.

> **구현 (Phase 3 — 조사 품질 평가 하네스, 2026-08-12):** `investigation_quality.py` — golden question(§2.1 조사 질문) 대비 조사 품질 **전 지표**를 채점하는 read-only 하네스. `GoldenQuestion`(planned_subclaims·gold_counter·gold_independent_count) + `InvestigationQualityHarness` — coverage(covered/planned, gate ≥ 0.80)·인용 연결률(linked/verifiable, gate = 1.0 — reported prediction 무출처 허용, evidence-first §3-5)·인용 지지율(judge verdict 주입, gate ≥ 0.95)·독립증거 수 정확성(1 − |r−g|/max(g,1), gold=None 미확보→measured=False, gold=0 과대평가 방지, target ≥ 0.90)·**반증 발견률(found/total_gold_counter, target ≥ 0.70 — DoD ② 직접 지표)**·modality 정확도(gate ≥ 0.85)·confidence 부호 일치율(지지 추가→상승·반증 추가→하락 부호, target ≥ 0.85, 방향 우선·크기 부차). **honest-gap** 도입(§6.2): 골든이 없는 축은 모든 계산이 순수 함수·결정적이며, LLM judge 점수는 호출자가 주입(하네스는 대조만 — §1.3 judge 보정 게이트 승격 경로 유지). **스키마·계약 변경 없음 → Spec 그대로(`0.1.9`).** TDD — `test_investigation_quality` 신규 20개(coverage 운·honest-gap·연결률·지지율·독립증거 gold=0·반증 recall·modality·부호 일치·score_question 통합·read-only·결정성) — 스위트 535→**555개 통과**(회귀 0). 다음: Planner(07 §3.2)로 골든 question 실측·DoD ② AB 검증.

> **구현 (Phase 3 — DoD ② AB 검증, 2026-08-12):** `test_investigation_dod` — Phase 3 DoD ① "그래프 공백 탐색·신규 evidence 추가" + DoD ② "반증 탐색 제거 버전 대비 평가 점수 향상"을 §1.3 하네스로 계량 봉인. DoD ② A/B: baseline(반증 제거 — `CounterEvidenceAgent` 미탐·contradiction 없음, 반증 발견률 0/3 = 0.0) 대비 counter-evidence 버전(그래프 CONTRADICTS 반증 3/3 발견, 반증 발견률 1.0 **≥ 0.70 target PASS**)으로 **점수 향상** 확정. 인용 연결률(evidence-first §3-5)은 반증 추가에도 **1.0 유지**(반증이 연결률을 해치지 않음). 골든 반증 부재 질문은 반증 축 honest-gap(§6.2 — vacuous pass 금지). DoD ①: 조사(InvestigationCoverage)가 그래프 evidence를 탐색해 coverage ≥ 0.80 + Audit 역추적(연결률 = 1.0). read-only·결정적. **Spec 그대로(0.1.9).** TDD — `test_investigation_dod` 신규 4개 — 스위트 594→**598개 통과**(회귀 0). Phase 3 완결.

### 1.4 시스템 성능 (§12.4)

성능 지표는 CI 회귀가 아니라 **부하 테스트(load test, §4.5)·운영 SLO**로 검증한다. `slo-gate:`는 목표 SLO 대비 회귀 감지 기준이며 **CI/승격을 차단하지 않고 nightly 경보로만 라우팅**한다 (§6.3, → [`11-observability`](./11-observability-and-governance.md) §2.3).

| 지표 | 정의 | 계산식 | 목표·게이트 |
| --- | --- | --- | --- |
| 수집/파싱 throughput | 초당 처리 문서 수 | `docs_processed / elapsed_sec` | `target: ≥ 50 docs/s` (MVP) |
| 100만 재처리 시간 | 전체 dataset full rebuild 소요 | wall-clock (분산 batch) | `target:` 공개·추적 (blueprint §21-2) |
| 그래프 반영 지연 | 신규 문서 수집→graph 반영 latency | `graph_commit_ts − fetched_ts` (p95) | `slo-gate: p95 ≤ SLO` (→ [`11`](./11-observability-and-governance.md)) |
| 문서당 LLM 비용 | 문서 1건 처리 LLM 비용 | `sum(llm_cost) / docs_processed` | `target:` 추적·경보 |
| 문서당 총 처리비용 (total cost/doc) | 문서 1건 처리 총비용(LLM + compute + storage) | `(sum(llm_cost) + compute_cost + storage_cost) / docs_processed` | `target:` 추적·공개 (blueprint §20/§21-9) |
| Investigation 비용/latency | 조사 1건당 비용·지연 | `cost_per_inv`, `latency_p95` | `target:` budget 내 |
| 캐시 적중률 | LLM/검색 캐시 hit 비율 | `cache_hits / cache_lookups` | `target: ≥ 0.60` |
| Retry/DLQ 비율 | 재시도·dead-letter 이벤트 비율 | `(retries + dlq) / total_jobs` | `slo-gate: ≤ 0.05` |
| Graph query p50/95/99 | 그래프 조회 지연 분위수 | percentile latency | `slo-gate: p99 ≤ SLO` |

**구현 (MVP #9, 2026-08-12):** `pipeline_bench.py` — throughput·문서당 시간·문서당 LLM 비용을 순수 함수로 계산 (`throughput`·`per_doc_stats`·`llm_cost_per_doc`), `pipeline_runner`가 각 성공 문서의 벽시계를 `PipelineResult.per_doc_elapsed_ms`로 수집. **실측 (실신호 본문 138건, 결정적 체인 단일 프로세스)**: throughput **13.9 docs/s** (MVP 목표 50 미달 — 단일 프로세스 in-memory이며 분산 batch는 Phase 4), per-doc p50 **22.6ms**·p90 118.9ms·p99 195.9ms·max 201ms, 문서당 LLM 비용 0 (결정적 체인 LLM 미사용). `slo-gate:` 분류 유지 (CI 차단 아님, nightly 경보) — 50 docs/s 달성은 부하·분산 단계에서 재측정.

---

## 2. 골든 데이터셋 (§12.5)

모델·온톨로지 변경의 **회귀 기준(ground truth)**이다. 초기 도메인에서 전문가·수작업 검토로 구축하며, 불변식 §3-7 **"human review as data"**의 산출물이다.

### 2.1 구성 (composition)

blueprint §12.5를 확정한다.

| 세트 | 규모 | 대상 지표 | 채점 단위 |
| --- | --- | --- | --- |
| Entity mention | 1,000 | entity extraction P/R (§1.2) | span+type |
| Entity pair 판정 | 1,000 | entity resolution P/R, 오병합률 | same / not-same / uncertain |
| Claim/Evidence span | 500 | claim 추출 정확도, span 보존율 | 삼항 + source span |
| Claim pair | 500 | canonicalization, contradiction P/R | equivalent/specific/general/supports/contradicts/unrelated/superseded |
| 계보 클러스터 | 200 | dup P/R, 계보 정확도 | root / derived / independent |
| 조사 질문 (golden question) | 20~50 | 조사 품질 전 지표 (§1.3) | 보고서 + evidence graph |

- Claim pair 라벨은 [`02`](./02-ontology.md) §canonicalization·contradiction 분류 체계와 1:1 대응한다.
- 각 세트는 **긍정·부정·경계(hard negative)** 예시를 함께 포함해 precision 게이트를 실질적으로 압박한다.

### 2.2 생성 절차 (human review as data)

불변식 §3-7: 사람의 교정은 **원 모델 출력 + 수정 결과 + 이유**를 함께 저장하는 학습/평가 데이터다. 골든셋은 별도 수작업이 아니라 **[`05`](./05-resolution-and-extraction.md) §quarantine review workflow에서 파생**한다.

```text
1. Pipeline 산출     : mention/claim/merge 후보 + 모델 출력·confidence·version tuple
2. Quarantine/Review : 저confidence·미등록 predicate·ambiguous merge가 review 큐로 (→ 05)
3. Human 결정        : accept/reject/correct + rationale 저장 (review_history[], → 03 §8.2)
4. Golden 승격       : 검토 완료 레코드를 golden set으로 태깅 (원 출력·정답·이유 3자 보존)
5. Sampling 균형     : 도메인/타입/난이도별 층화 표본으로 편향 방지
```

- review 데이터를 골든으로 재사용하므로 **평가셋은 실제 실패 사례에 집중**되어 회귀 민감도가 높다.
- 골든 정답과 그것을 만든 원 모델 출력을 함께 보존해, 후속 모델과 **동일 입력**으로 비교(회귀)가 가능하다 (blueprint §17 Human Review as Data).

### 2.3 저장·버저닝

- 각 골든 레코드는 생성 당시 **`ontology_version`으로 태깅**한다 ([`02`](./02-ontology.md) §6.3, [`README`](./README.md) §2.3). 온톨로지 major bump 시 호환성을 평가하고 필요 시 재라벨·migration한다.
- 골든셋은 curated zone과 별도 버전 관리(레코드별 `gold_version`·`labeled_by`·`labeled_at`)하며, 회귀 실행은 **골든 버전 + 파이프라인 version tuple** 조합을 리포트에 남긴다.
- 골든 정답 수정도 append-only 이력으로 남긴다(정답 자체의 감사 가능성).

### 2.4 평가 파티션 (held-out split — 튜닝 ↔ 게이트 분리)

임계값·프롬프트 튜닝에 쓴 데이터를 그대로 승격 게이트로 재사용하면 게이트가 과대평가된다(**tuning↔gate leakage**). 이를 막기 위해 각 골든 세트를 레코드 단위로 고정 분할하고, 분할 결과를 각 레코드에 `split ∈ {dev, test}`로 태깅해 append-only로 고정한다 (ADR-1007).

| 파티션 | 비율(placeholder) | 용도 | 접근 규칙 |
| --- | --- | --- | --- |
| `dev` (튜닝셋) | ~40% | 임계값·프롬프트 튜닝, 오류 분석, LLM-judge calibration(§1.3) | 반복 조회 허용 |
| `test` (held-out 게이트셋) | ~60% | §3 승격 게이트·§6.2 hard-gate 판정 | 튜닝 중 조회 금지 — 게이트 실행 시에만 |

- **승격 게이트 판정(§3.1·§6.2)은 `test` 파티션에서만** 수행한다. `dev`에서 조정한 임계값을 건드리지 않은 `test`에서 검증해 leakage 없이 승격을 결정한다.
- **grouping split:** 05 quarantine review(§2.2)에서 유입되는 신규 레코드 중 **동일 entity·동일 root 문서에서 파생된 레코드는 같은 파티션에 배정**해 train/test 누수를 차단한다(레코드 무작위 분할 금지).
- 각 세트는 §2.1의 층화(도메인/타입/난이도) 균형을 파티션별로 유지한다.
- 분할 비율·경계는 `gold_version`에 바인딩하며, 재분할은 신규 `gold_version`으로만 반영한다(과거 게이트 결과 재현성 보존). 비율은 실측 후 [`README`](./README.md) §2.6 절차로 조정한다.

---

## 3. 회귀 테스트

**모델 / 프롬프트 / 온톨로지 버전이 바뀔 때**마다 골든셋 회귀를 실행하고, 통과해야만 단계 승격한다 ([`07-llm`](./07-llm-and-agents.md) §9.5, [`README`](./README.md) §2.3, blueprint §9.5).

### 3.1 승격 게이트 (promotion gate)

```text
model/prompt/ontology 변경
  → 동일 골든셋으로 신·구 버전 회귀 실행
  → §1 게이트 지표 비교 (P/R/F1, 오병합률, span/provenance 완전성)
  → 게이트 통과 && 회귀 없음(회귀 허용치 초과 하락 없음)
  → 단계 승격(canary → 전면)  |  미달 시 승격 차단(block)
```

- **골든 gate 미달 시 승격 차단**이 원칙이다. 특히 entity resolution `P`·오병합률·span/provenance 완전성은 hard block이다 (§1.1–1.2).
- 프롬프트 교체는 `prompt_template_hash`, 모델 교체는 `model_id`, 온톨로지는 `ontology_version`, 스키마는 `schema_version`, 추출 코드는 `extraction_code_version` 변경으로 감지한다 (version 5축, [`README`](./README.md) §2.3).
- 회귀 리포트는 **지표별 delta**와 **신규 실패 사례**를 포함하며 ADR/ROADMAP에 링크한다 (blueprint §20 산출물 "모델·프롬프트 변경 평가 리포트").
- **구현 (MVP #10 — version 봉인):** 파이프라인 산출물에 부착되는 version 5축은 `versioning.VERSION_TUPLE` 한 곳에 **봉인(seal)** 한다 (ADR-1003). `versioning.extraction_version_tuple()`은 새 dict 를 반환해 호출부 변조를 막고, `version_guard(vt)`는 미등록 축·봉인 상수 불일치(하드코딩 파편·무단 변경)를 감지해 재추출·오염 없이 사용 가능한지 검증한다 (02 §6.3). 파이프라인(`pipeline_runner`)은 하드코딩 5축 문자열 대신 이 봉인을 참조 — version 변경 시 bumper() 의 변경 + 이 §3 골든셋 회귀가 트리거된다.

### 3.2 회귀 판정 규칙

- 절대 게이트: §1의 `gate:` 임계값 미달 시 block (판정은 §2.4 `test` 파티션).
- 상대 게이트: 지표가 **직전 승격(last-promoted baseline) 대비 아래 per-metric 허용치를 초과해 하락**하면 block. 허용치는 초기 placeholder이며 골든셋 분산 실측 후 `dev` 파티션(§2.4)에서 재조정한다 (ADR-1008).

| 지표 | 상대 허용치(placeholder) | 근거 |
| --- | --- | --- |
| entity resolution `P`, 오병합률 | `0`p (하락 불허, hard) | 오병합은 그래프 전역 오염 — 무관용 |
| 인용 연결률, span/provenance 완전성 | `0`p (하락 불허, hard) | `= 1.0` 불변식 게이트(§3-2/§3-5) |
| entity/claim F1, contradiction `P` | `≤ 1.0%p` 하락 | 핵심 품질 회귀 방지 |
| canonicalization·temporal·coverage 등 기타 `gate:` 지표 | `≤ 2.0%p` 하락 | 측정 노이즈 허용폭 |
| `target:` 지표 | 비차단(추세 경보만) | 지향값 |

- 온톨로지 변경: controlled vocabulary 확장(minor)은 신규 predicate 세트만 부분 평가, 의미 변경(major)은 전량 재평가 ([`02`](./02-ontology.md) §6).

---

## 4. 테스트 전략 (§15)

blueprint §15의 5범주를 **대상·도구·게이트** 표로 확정한다. TDD 규율(§5)에 따라 각 stage는 테스트 선행으로 개발한다.

### 4.1 Unit

| 대상 | 도구 | 게이트 |
| --- | --- | --- |
| 문서 fingerprint (content hash, MinHash/SimHash) | pytest | 결정성·충돌 특성 검증, merge-block |
| Temporal interval normalize (부분/미상 → `time_precision`) | pytest + property-based (Hypothesis) | 경계·null 케이스, merge-block |
| Provenance offset mapping (원문 ↔ 정규화 offset 왕복) | pytest | round-trip = 1.0, merge-block ([`03`](./03-storage-and-data-model.md) §3.2) |
| Graph mutation validation (schema/provenance/predicate 폐쇄성) | pytest | 제약 위반 reject 검증 ([`02`](./02-ontology.md) §4) |
| Confidence aggregation (증거 구조 기반 집계) | pytest | 단조성·경계값 검증 |

### 4.2 Contract

| 대상 | 도구 | 게이트 |
| --- | --- | --- |
| LLM structured output schema | JSON Schema / Pydantic validation | 스키마 위반 출력 reject, merge-block |
| Source adapter (커넥터 응답 계약) | 계약 테스트 + recorded fixtures | 필드·타입 계약 유지 |
| OpenSearch/graph query shape | 계약 테스트 (query→result 형태) | 결과 shape 불변 |
| Ontology 호환 (element `ontology_version` ↔ 현재) | pytest ([`02`](./02-ontology.md) §6.3) | 비호환 조회 감지, merge-block |

### 4.3 Integration

| 대상 | 도구 | 게이트 |
| --- | --- | --- |
| 수집 → graph 반영 (end-to-end) | pytest + ephemeral MinIO/PG/Neo4j (docker-compose) | 원문→graph 왕복 추적 성공 (blueprint §16 Phase0) |
| 변경 문서 → 새 버전 생성 | integration | 동일 URL 변경분이 새 `doc_id`로 보존 ([`03`](./03-storage-and-data-model.md) §2) |
| Entity merge + rollback | integration | `merge_entity`↔`unmerge` 이벤트 rollback 검증 (불변식 §3-3,4) |
| 삭제 전파 (raw→…→graph) | integration | 파생 데이터까지 `delete`/`quarantine` 전파 (blueprint §13) |
| Idempotency (재실행 중복 mutation 없음) | integration | 동일 `idempotency_key` no-op (불변식 §3-6) |

### 4.4 Evaluation

| 대상 | 도구 | 게이트 |
| --- | --- | --- |
| 골든셋 기반 추출·resolution 평가 | 골든 harness (§1, §2) | §1 게이트 지표 (nightly/PR) |
| 프롬프트·모델 변경 회귀 | 회귀 harness (§3) | 승격 게이트 (block on fail) |
| 반증 ablation (counter-evidence on/off) | ablation runner | 반증 제거 버전 대비 조사 점수 향상 (blueprint §16 Phase3 완료조건) |
| Graph 유무 비교 (with/without KG) | A/B eval | graph 사용이 조사 품질을 향상시킴 (blueprint §20) |

### 4.5 Load

| 대상 | 도구 | 게이트 |
| --- | --- | --- |
| 10만 batch ingestion | Ray Data + 부하 harness | MVP 전체 재처리 완료 (blueprint §16 Phase1) |
| 100만 batch ingestion | 분산 batch | 처리 시간·비용 측정·공개 (Phase4) |
| 대량 graph mutation | mutation load runner | throughput·지연 SLO 내 |
| 동시 investigation | 부하 harness | 동시성 하 latency/비용 SLO |
| Full rebuild vs partial recomputation | benchmark | 증분이 full 대비 유의미 절감 (Phase4 완료조건) |

---

## 5. TDD 적용 (AGENTS.md)

파이프라인 stage 개발은 Kent Beck **TDD(Red→Green→Refactor)**와 **Tidy First**를 따른다 ([AGENTS.md](../../AGENTS.md)).

### 5.1 Stage 개발 사이클

```text
Red    : stage 계약을 정의하는 가장 작은 실패 테스트 작성
         (예: "should reject claim without provenance_ref")
Green  : 통과할 최소 구현만 작성 (over-engineering 금지, AGENTS §2)
Refactor: 테스트 green 상태에서 중복 제거·의도 명확화
```

- **결함 수정:** 먼저 결함을 재현하는 API-레벨 실패 테스트를 쓰고, 가장 작은 재현 테스트를 추가한 뒤 둘 다 green으로 만든다 (AGENTS TDD §).
- **평가 지표도 테스트로:** "정확도를 올린다" 대신 "골든셋에서 게이트 미달 시 실패하는 테스트를 통과시킨다"로 목표를 검증 가능하게 만든다 (AGENTS §4 Goal-Driven).

### 5.2 구조 변경 / 행동 변경 커밋 분리 (Tidy First)

- **구조 변경(structural):** 이름 변경·메서드 추출·이동 등 동작 불변 리팩터링. 실행 전후 테스트 동일 통과로 무해함을 검증.
- **행동 변경(behavioral):** 기능 추가·수정.
- 둘을 **같은 커밋에 섞지 않는다.** 필요 시 구조 변경을 먼저 하고 별도 커밋한다. 커밋 메시지에 구조/행동 여부를 명시한다 (AGENTS Commit Discipline).
- 커밋 조건: 전체 테스트 통과 + 린터 무경고 + 단일 논리 단위.

---

## 6. CI 게이트

merge/승격을 차단하는 게이트를 명시한다.

### 6.1 Merge-block (PR 필수 통과)

- **Unit / Contract 전량 통과** (§4.1–4.2).
- **Integration 핵심 경로:** 수집→graph 왕복 추적, idempotency, entity merge rollback (§4.3).
- **Span 보존율 = 1.0 · Provenance 완전성 = 1.0** (불변식 §3-2, §1.1–1.2).
- 린터·타입체크 무경고 (AGENTS Commit Discipline).
- 스키마·계약 변경 시 문서·`README` spec version·ROADMAP 3단계 반영 확인 ([`README`](./README.md) §2.6).

### 6.2 Promotion-block (모델/프롬프트/온톨로지 승격)

- **골든셋 회귀 통과** + §1 hard-gate(entity resolution `P` ≥ 0.97, 오병합률 ≤ 0.02, contradiction `P` ≥ 0.90, 인용 연결률 = 1.0) 충족 (§3.1). 게이트 판정은 §2.4 `test`(held-out) 파티션에서 수행한다.
- 상대 게이트: §3.2 per-metric 허용치를 초과해 직전 승격 대비 하락하는 지표 없음(entity resolution `P`·오병합률은 하락 불허).
- 회귀 리포트 첨부 (delta + 신규 실패 사례).

### 6.3 Nightly (비차단, 경보)

- Evaluation 전량(반증 ablation, graph 유무 비교, 조사 품질 §1.3).
- Load(§4.5)·성능 지표(§1.4) 추세 — SLO 회귀 시 경보 (→ [`11-observability`](./11-observability-and-governance.md)).

---

## 7. 의사결정 로그

| ID | 결정 | 근거 | 상태 |
| --- | --- | --- | --- |
| ADR-1001 | Entity resolution/merge 게이트를 **precision-first**(P ≥ 0.97, 오병합률 ≤ 0.02)로, recall은 target | 오병합이 그래프 전역 오염, 불확실은 `POSSIBLY_SAME_AS` 유지 (blueprint §12.2/§18, 불변식 §3-4) | Accepted |
| ADR-1002 | 골든셋을 별도 수작업이 아닌 **05 quarantine review에서 파생**(human review as data) | 실패 사례 집중·회귀 민감도·정답/원출력/이유 3자 보존 (불변식 §3-7, blueprint §17) | Accepted |
| ADR-1003 | 모델/프롬프트/온톨로지 변경 시 **골든 회귀를 승격 필수 게이트**로, 미달 시 block | 재현성·품질 회귀 방지 (blueprint §9.5/§21-10, [`README`](./README.md) §2.3) | Accepted |
| ADR-1004 | Span 보존율·provenance 완전성을 **= 1.0 merge-block 게이트**로 | provenance 불변식의 직접 강제 (불변식 §3-2, blueprint §13) | Accepted |
| ADR-1005 | 골든 레코드에 **`ontology_version` 태깅**, 온톨로지 major bump 시 호환성 평가 | 온톨로지 버전과 평가 정합 ([`02`](./02-ontology.md) §6.3) | Accepted |
| ADR-1006 | 파이프라인 stage를 **TDD + Tidy First(구조/행동 커밋 분리)**로 개발 | 재현성·회귀 안전성·품질 (AGENTS.md) | Accepted |
| ADR-1007 | 골든셋을 **`dev`(튜닝)·`test`(held-out 게이트)로 grouping split**하고 승격 게이트는 `test`에서만 판정(§2.4) | 튜닝셋=게이트셋 재사용에 의한 게이트 과대평가(leakage) 방지, entity·doc 단위 grouping으로 train/test 누수 차단 (blueprint §20) | Accepted |
| ADR-1008 | 상대 회귀 허용치를 **per-metric placeholder**(resolution `P`·오병합률 0p, F1·contradiction `P` ≤1%p, 기타 gate ≤2%p)로 명시하고 `dev`에서 실측 재조정(§3.2) | 단일 "예: 1%p" 비구속·모호 → 지표별 명시로 상대 게이트 실효화 | Accepted |
| ADR-1009 | §1.4 시스템 성능 지표를 CI 차단 `gate:`가 아닌 **`slo-gate:`(비차단 nightly 경보)**로 재분류 | 성능은 부하·운영 SLO로 검증(§6.3), CI 회귀 게이트 아님 — `gate:` 토큰 의미(§1.4 intro) 정합 | Accepted |

> **Q3 ER 임계 재실측 게이트 (2026-08-03 확정):** 현재 ER은 **결정적 외부식별자 exact match만 자동 병합**(05 ADR-507)이라 스코어 임계값 자체가 없어 Q3를 회피 해소했다. 만약 추후 **embedding/LLM 기반 ER**(POSSIBLY 후보 → 확정 병합)을 도입하는 경우에만 임계값 실측이 필요해지며, 그때의 판정 게이트:
> - §2.4 `dev` 파티션에서 임계값(cosine·확신)을 튜닝하고, **`test`(held-out) 파티션에서만 게이트 판정** (ADR-1007).
> - 게이트는 ADR-1001 precision-first 유지: **entity resolution `P ≥ 0.97`, 오병합률 ≤ 0.02**(하락 불허, hard).
> - 실측 시점은 데이터 다변화(S9 여러 source/predicate의 ER 후보) 이후. 현재 실데이터(29 claim, confidence 균일 0.8, S41)는 구분력이 없어 임계 실측이 무의미함을 확인.
