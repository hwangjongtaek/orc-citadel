# 11 · 관측·거버넌스 (Watchtower · Signal Spire)

> **상태:** ✅ Stable · **Spec:** 1.0.0 · **Blueprint 매핑:** §11, §13, §14
> 상위 규약: [README](./README.md) · 관련: [01-architecture](./01-architecture.md), [03-storage](./03-storage-and-data-model.md), [04-ingestion](./04-ingestion-and-parsing.md)

Watchtower(Observability)와 Signal Spire(Alerting)의 계약, 그리고 출처 신뢰도·독립성 모델과 안전·거버넌스 규칙을 확정한다. 본 문서는 파이프라인 **전 stage를 관통하는 correlation·SLO·감사** 계약(→ [01](./01-architecture.md) §3-3, §4)과, 저장 계층의 삭제 전파·provenance 게이트(→ [03](./03-storage-and-data-model.md) §8)를 운영 절차로 구체화한다.

---

## 1. 출처 신뢰도·독립성 (Blueprint §11)

### 1.1 원칙: 단일 점수 환원 금지

출처 신뢰도를 하나의 고정 점수(`source_reputation = 0.7` 같은 스칼라)로 **환원하지 않는다**. 그런 스칼라는 "공식 발표는 직접성은 높지만 이해관계가 있고, 언론 보도는 독립성은 높지만 2차 자료"라는 상충 구조를 뭉개기 때문이다. 대신 서로 독립적으로 판단해야 하는 **차원(dimension)** 을 분리 저장한다.

- **최종 confidence는 source reputation이 아니라 claim별 증거 구조로 계산한다.** 출처 차원은 증거 가중치의 입력일 뿐, 그 자체가 결론이 아니다 (→ [02](./02-ontology.md) §2.4 `Claim.confidence` ≠ `certainty`, ADR-202).

### 1.2 신뢰도 차원 (Source dimensions)

blueprint §11의 7개 판단 축을 독립 차원으로 확정한다. 각 차원은 스칼라로 합산되지 않고 **개별 조회·필터 가능**해야 한다.

| 차원 키 | 축 (blueprint §11) | 값 도메인 | 판정 근거 |
| --- | --- | --- | --- |
| `directness` | 사건의 직접 당사자인가 | `direct_party` / `witness` / `third_party` | 발행 주체 ↔ 사건 관계 |
| `primacy` | 1차 자료 vs 2차 해석 | `primary` / `secondary` / `mixed` | 원문 유형·인용 구조 |
| `cites_others` | 다른 자료를 명시적 인용하는가 | bool + `cited_doc_ids[]` | `CITES` 엣지(→ [02](./02-ontology.md)) |
| `correction_history` | 과거 정정 이력 | count + `correction_refs[]` | supersession 이벤트 |
| `conflict_of_interest` | 주장과 이해관계 | `none` / `financial` / `affiliated` / `unknown` | ownership·소속 매핑 |
| `method_disclosure` | 데이터·방법 공개 여부 | `full` / `partial` / `none` | 원문 구조 분석 |
| `independent_acquisition` | 독립 취득 여부 | `independent` / `derived` / `unknown` | `dup_clusters`(→ [03](./03-storage-and-data-model.md) §4.3) |

### 1.3 `Source.dimensions{}` 스키마

[02](./02-ontology.md) §2.3의 `Source.dimensions{}`를 확정한다. 각 차원은 **값 + 판정 근거(evidence) + 판정 주체(judged_by) + 버전**을 함께 가진다(단일 점수 환원 금지의 스키마적 강제).

```json
{
  "source_id": "src-01J9...",
  "dimensions": {
    "directness":  { "value": "direct_party", "evidence_ref": ["ext-..."], "judged_by": "rule:ownership-map", "assessed_at": "2026-08-03T00:00:00Z" },
    "primacy":     { "value": "primary",      "evidence_ref": ["ext-..."], "judged_by": "llm:claude-sonnet-5", "prompt_hash": "sha256:...", "model_id": "claude-sonnet-5-2026..." },
    "cites_others":{ "value": true,  "cited_doc_ids": ["doc-...", "doc-..."], "judged_by": "pipeline:cite-extractor" },
    "correction_history": { "count": 2, "correction_refs": ["mut-...", "mut-..."] },
    "conflict_of_interest": { "value": "financial", "rationale": "발행 주체가 주장 대상의 지분 보유", "judged_by": "human:analyst-3" },
    "method_disclosure": { "value": "partial", "judged_by": "llm:claude-sonnet-5" },
    "independent_acquisition": { "value": "derived", "cluster_id": "clus-...", "judged_by": "pipeline:dedup" }
  },
  "assessment_version": { "ontology_version": "1.0.0", "schema_version": "0.1.0" }
}
```

- `judged_by`가 `llm:*`인 차원은 재현·감사를 위해 판정에 사용한 `prompt_hash`·`model_id`를 해당 차원 객체에 함께 부착한다(`assessment_version`과 병기). `rule:*`·`human:*` 판정에는 요구하지 않는다.
- `dimensions{}`는 **결론이 아니라 신호**다. 조회 시 UI는 단일 게이지 대신 차원별 값과 근거 수를 함께 노출한다 (blueprint §1.4 접근성: "confidence는 단일 색상 게이지 대신 값·근거 수·독립 출처 수를 함께 표시").

### 1.4 독립 증거 수 보정 (dup_clusters 연동)

동일 근원에서 파생된 복제 기사 500건을 독립 증거 500개로 계산하지 않는다. [03](./03-storage-and-data-model.md) §4.3 `dup_clusters`를 근거로 다음을 계산한다.

```text
independent_evidence_count(claim)
  = distinct( root_source of each supporting document )
  + count( independent_addition_doc_ids that add new evidence )
```

- 클러스터 하나(root + 파생)는 **독립 증거 1**로 축소한다. `independent_addition_doc_ids[]`(독립적 추가 정보 보유 문서)만 추가 카운트한다.
- **구현 (prototype):** `assertion_evidence.AssertionEvidenceProjector.independent_source_count`가 이 공식을 그대로 계산한다. 두 항 — ① 지지 근거 문서의 `root_source` distinct(무클러스터는 자기 자신=root), ② 지지 근거로 등장하는 `independent_addition_doc_ids[]` 문서 수(해당 claim에 새 증거를 더하는 문서만). ②는 root ∉ independent_addition(04 §4.2 disjoint)이므로 ①과 중복 계상되지 않는다.
- **집계 단위는 출처(source) 단위이며 문서(doc) 단위가 아니다.** 카운트 기준은 supporting document의 `root_source`(파생 제거 후 근원 출처)이다.
- **정본 소유:** per-claim 독립 증거 집계 공식은 본 절(§1.4)이 정본이다. [04](./04-ingestion-and-parsing.md)는 cluster → `root_source` 기여 단위 축소만 수행하고 per-claim 집계는 본 절에 위임한다. 이 값은 [09](./09-api.md)에서 `independent_source_count`로 노출된다.
- 이 보정값은 investigation 결과의 `evidence coverage` 대시보드(§2)와 Signal Spire의 "신규 독립 출처" 트리거(§5)에 직접 사용된다.
- 상세 dedup·계보 판정은 [04](./04-ingestion-and-parsing.md) §중복·계보가 소유한다(exact/near/semantic 3수준).

---

## 2. 관측 가능성 (Blueprint §14) — Watchtower

### 2.1 공통 Correlation ID 전파

파이프라인 각 작업에 공통 `correlation_id`를 부여하고 전 stage로 전파한다 (→ [01](./01-architecture.md) §3-3, [03](./03-storage-and-data-model.md) §7.1 `graph_mutations.correlation_id`와 정합).

```text
source fetch (S1)
  → document version (S2, doc_id)
  → parse/normalize (S3)
  → extract candidates (S5)
  → resolution decision (S6, res-…)
  → graph mutation (S7, mut-…, correlation_id 컬럼)
  → investigation result (S9, inv-…)
```

- 위 체인은 발췌이며, S4(dedup·계보)·S8(색인)도 `correlation_id`를 전파하되 다이어그램에서는 생략했다.
- `correlation_id`는 fetch에서 최초 생성되고(→ [03](./03-storage-and-data-model.md) §2.2 `fetch.json.fetch_correlation_id`), 이후 모든 stage 산출물·이벤트·로그·metric에 부착된다. `fetch_correlation_id`는 별도 ID가 아니라 곧 파이프라인 `correlation_id`이며(`corr-` prefix), 이름만 fetch 컨텍스트용으로 붙었을 뿐 동일 값이다.
- **정합 계약:** `graph_mutations` 이벤트의 `correlation_id`는 그 mutation을 유발한 fetch까지 왕복 추적 가능해야 한다. 이로써 "이 그래프 변경은 어느 문서 수집에서 비롯됐나"를 감사할 수 있다 (Trail, blueprint §1.2).
- 한 fetch가 여러 mutation을 낳거나(1:N) 여러 문서가 하나의 canonical claim에 기여(N:1)할 수 있으므로 `correlation_id`는 **전파되되 재작성되지 않는다**. 분기 시 `parent_correlation_id`로 계보를 남긴다.

### 2.2 주요 대시보드

blueprint §14의 대시보드 목록을 지표 계약으로 확정한다.

| # | 대시보드 | 핵심 지표 | 소스 | 대응 화면 |
| --- | --- | --- | --- | --- |
| D1 | Source 수집 상태 | source별 수집 성공률, freshness(마지막 성공 fetch 이후 경과), robots/license 위반 시도 | fetch 로그 | Watchtower |
| D2 | Stage throughput·backlog | stage별 처리량(docs/s), 큐 backlog, 재실행율 | stage runner metric | Watchtower |
| D3 | 모델 호출 | 모델별 호출량·토큰·비용·오류율·p95 지연 | LLM 게이트웨이(→ [07](./07-llm-and-agents.md)) | Watchtower |
| D4 | Schema validation | validation 실패 유형별 건수(provenance 누락/predicate 미등록/reference 무결성/시간 정합) | S7 검증기(→ [02](./02-ontology.md) §4) | Watchtower |
| D5 | Quarantine | quarantine 규모, 사유별 분포, 체류 시간(중앙값·p95), 승격·폐기율 | quarantine graph(→ [05](./05-resolution-and-extraction.md), [06](./06-graph-service.md)) | Hall of Witnesses |
| D6 | 버전별 품질 | ontology·모델 버전별 추출·resolution 품질 변화(회귀) | 골든 평가(→ [10](./10-evaluation-and-testing.md)) | — |
| D7 | Graph 규모·성능 | 노드·엣지 수, graph query p50/p95/p99 | graph service(→ [06](./06-graph-service.md)) | War Table |
| D8 | Investigation | investigation별 evidence coverage, 독립 증거 수(§1.4), 비용·latency | agent runtime(→ [07](./07-llm-and-agents.md)) | Council Chamber |

- 모든 대시보드 metric은 `correlation_id`·`version_tuple`로 분해(drill-down) 가능해야 한다(D6 회귀 분석의 전제).

> **구현 (Phase 3 — Investigation 대시보드, 2026-08-12):** `investigation_dashboard.py` — D8(Council Chamber) 지표 계산. `investigation_dashboard(investigation_id, Coverage(covered·planned·gaps), independent_evidence, budget, elapsed_ms)` → investigation별 **evidence coverage**(covered/planned + gap 목록 — planned 0이면 honest-gap §6.2 measured=False)·**독립 증거 수**(11 §1.4 dup 보정)·**cost**(InvestigationBudget token/step)·**latency_ms**(10 §1.4 cost_per_inv·latency_p95 계약). read-only·결정적·investigation_id 분해(drill-down). `viewer._api_investigate`에 `dashboard` D8 노출. **스키마·계약 변경 없음 → Spec 그대로(0.1.9).** TDD — `test_investigation_dashboard` 신규 5개(coverage·독립·budget token/latency·honest-gap·read-only) + `test_viewer_graph` 신규 1개(D8 노출) — 스위트 588→**594개 통과**(회귀 0). 다음: Phase 3 DoD ①② 통합 검증 + 완결 블록업.
- 초기 구성은 PostgreSQL + Grafana, 확장 시 ClickHouse + Grafana (→ [01](./01-architecture.md) §5, 승격 트리거: 분석 쿼리 지연).

> **구현 메모 (Phase 4 — ClickHouse 분석 승격, 2026-08-12):** `analytics_promotion.py` — 01 §5 분석·관측 계층의 **승격 트리거(분석 쿼리 지연)**를 봉인 (ClickHouse 미설치 — executor mock 주입, #14 mock/실측 격리와 동일). `measure_analytics_latency(queries, executor)` — 분석 쿼리 경로별 지연 분포 → `p95`(정렬 인덱스, neo4j_q4_harness 와 동일 결정법)·`avg·max·n_queries`. `evaluate_analytics_promotion(latency_stats)` — **`ANALYTICS_SLO_MS=200ms` p95 초과 시 `escalate_clickhouse=True`** (01 §5 승격 트리거 — Q4/Q6 게이트와 동일 성격, `classified="slo-gate"` CI 비차단 nightly 승격 평가). 미측정(None/p95 부재) → `escalate=False`·`classified="not-measured"` — honest-gap(§6.2: 미측정이 승격 불필요의 근거가 아님). `aggregate_metrics(rows, key_fn)` — **OLAP 집계**(ClickHouse 가 대체 승격하는 분석 부하의 실제 형태), `correlation_id`·`version_tuple` 로 drill-down(§2.2). read-only(불변식 §3-3)·결정적. **스키마·계약 변경 없음 → Spec 그대로(0.1.9).** TDD — `test_analytics_promotion` 신규 19개(p95·측정 결정성/executor·승격 트리거 경계/비차단·honest-gap·OLAP 집계·read-only·결정성) — 스위트 670→**689개 통과**(회귀 0). 다음: 100만 처리 시간·비용 공개 + SLO graph 반영(01·10, DoD ①②).

### 2.3 SLO 정의

목표치는 **placeholder이며 실측 후 확정**한다(측정 없는 목표는 신뢰하지 않는다, blueprint §20 "수치로 답한다"). 각 SLO는 측정 창(rolling window)과 상태를 명시한다.

SLO-02/03/04는 **실측으로 확정**했다(2026-08-12, `neo4j_q4_harness` 가동 Neo4j Community —[06](./06-graph-service.md) §9). 실데이터 엣지 그래프 조회 **p95=0.66~1.16ms**(970회)·10만 합성 p95=1.08ms·5만 합성 p95=0.6ms — 실측 대비 **대략 40~100배 여유**를 둔 보수적 목표로 확정(운영·성장 버퍼). 그 외(SLO-01/05/06/07/08)는 **아직 실측되지 않아 deferred** — "측정 없는 목표는 신뢰하지 않는다" 원칙에 따라 확정하지 않고, 실측 후 재확정 대상으로 명시한다.

| SLO ID | 지표 | 목표 | 측정 창 | 상태 |
| --- | --- | --- | --- | --- |
| SLO-01 | 신규 문서 → graph 반영 지연(p95) | `≤ 30 min` (deferred) | 7d rolling | **실측 (2026-08-12)** — 신규 RSS 수집 77건 → 실제 반영 `{p95_ms:495,638 (~8.3min), n:77, classified:'ok'}` · 목표치 확정 잠정 |
| SLO-02 | graph query latency p50 | `≤ 10 ms` ✅ 확정 | 1d rolling | **확정** (실측 p95 0.66~1.16ms) |
| SLO-03 | graph query latency p95 | `≤ 50 ms` ✅ 확정 | 1d rolling | **확정** (실측 0.66~1.16ms) |
| SLO-04 | graph query latency p99 | `≤ 100 ms` ✅ 확정 | 1d rolling | **확정** (실측 0.66~1.16ms) |
| SLO-05 | source 수집 성공률 | `≥ 99%` (deferred) | 7d rolling | **실측 (2026-08-12)** — SEC+RSS 50건 `{success_rate:1.0, n=50, measured:True, within_slo:True}` (목표 ≥99% 기계적 판정 기록) · **표본 확대 (2026-08-18, A5 런)** — arXiv windows+RSS 동일 런 `slo_log` 추가 축적 → **n=50 → n=440** `{success_rate:1.0, n=440, measured:True, within_slo:True}` (성공률 1.0 유지, 저표본 한계 완화) · **표본 확대 (2026-08-18, A6 런)** — arXiv windows=10+RSS 동일 런 `slo_log` 추가 축적 → **n=440 → n=1,540** `{success_rate:1.0, n=1,540, measured:True, within_slo:True}` (성공률 1.0 유지, 표본 3.5×) · **표본 확대 (2026-08-18, A7 런)** — arXiv windows=16+RSS 동일 런 `slo_log` 추가 축적 → **n=1,540 → n=2,040** `{success_rate:1.0, n=2,040, measured:True, within_slo:True}` (성공률 1.0 유지, 표본 1.3×) |
| SLO-06 | schema validation 통과율 | `≥ 95%` (deferred) | 7d rolling | 실측 하니스 봉인(2026-08-12) — 실데이터 축적 후 확정 |
| SLO-07 | quarantine 체류 시간(중앙값) | `≤ 3d` (deferred) | 30d rolling | 하니스 봉인(2026-08-12) + **조사 완결(2026-08-18): not-measured(모집단 0)** — 현 실데이터 게이트 quarantine=0 건 실측 확정(5,000·8,000건 `open_q=0`·dwell=0), 비해소 subject 는 추출 단계 폐기·mention 전부 해소 → dwell-time 분포 모집단 부재. 재평가 인프라 구축해도 실측할 quarantine 없음 → **not-measured/모집단-0 유지** |
| SLO-08 | 100만 문서 전체 재처리 시간 | 벤치마크 공개 (deferred) | 릴리스 | 🟢 **측정·완주 (2026-08-18)** — **104,677건 전체 재처리 병렬 완주 벽시계 `334,033ms (~5.6min)` measured=True** (k=10 multiprocessing, speedup 5.10×@깨끗한 순차 16.28ms/doc ∿28.4min) — 이전(2026-08-12) 배치 1,000건 16.83s + 전체 외삽 1.76h(projected) 를 실측 완주로 대체. **게이트 없음(unclassified — 벤치 공개 계약)** |

- SLO-01은 blueprint §16 Phase 4 완료 조건("신규 문서가 목표 SLO 안에 graph에 반영")과 직접 연결된다.
- SLO 위반은 자동으로 Signal Spire 운영 알림이 아니라 **Watchtower 운영 경보**로 라우팅한다(§5.3 결론 알림과 구분).

> **구현 메모 (Phase 6 — SLO-01 실측 하니스 봉인, 2026-08-12):** `reflection_slo_harness.py` — deferred SLO-01 의 **측정 계약·하니스**를 봉인 (목표치 자체는 실데이터 축적 후 확정). 측정 공식(10 §1.4) `graph_commit_ts − fetched_ts`(p95) — `fetched_ts` 는 원문 meta 의 `fetched_at`(collect_sample 에서 수집 시점 기록), `graph_commit_ts` 는 그래프 반영 시각. **단일 프로세스 일괄 처리의 정직한 한계(honest-gap §6.2):** 문서가 수집 직후 곧바로 반영되어 "배치 내 반영 지연"은 사실상 수집-처리 사이클 길이에 의존 → 측정을 **두 축으로 분리**해 과대 주장을 피함. `measure_batch_reflection` — 배치 내 실제 벽시계(주입 clock·commit_fn, epoch ms 축) · `measure_batch_interval_latency` — 배치 간격 시나리오(`ceil(t/inter)*inter − t`, 운영 스케줄러 반영 지연). p95 는 `neo4j_q4_harness.measure_query_latency` 와 동일한 **정렬 인덱스 결정법**(`int(0.95*(len-1))`) 재사용. 판정 `evaluate_slo01` — `SLO01_TARGET_MS=30 min`(11 §2.3) 대비: 미측정 None → `not-measured`+`within_slo=False`(부재가 OK 아님, §6.2), 초과 → `slo-gate`(10 §1.4 — CI 비차단 nightly 경보, `compute_graph_slo`(60s/DoD ②)와 별개 게이트). read-only(불변식 §3-3)·결정적·mock/실측 격리. **스키마·계약 변경 없음 → Spec 그대로(1.0.0).** TDD — `test_reflection_slo_harness` 신규 21개(fetched 파싱·부재 honest-gap·벽시계·commit_fn·배치 간격 시나리오·p95 결정법·slo-gate/not-measured 판정·read-only·결정성) — 스위트 902→**923개 통과**(회귀 0). 다음: 실데이터 축적 시 SLO-01 목표치 확정.

> **구현 메모 (Phase 6 — SLO-05/06/07/08 실측 하니스 봉인, 2026-08-12):** `slo_metrics_harness.py` — deferred SLO-05/06/07/08 의 **측정 계약·하니스**를 봉인 (SLO-01 과 동일 패턴, 목표치 실데이터 축적 후 확정). **SLO-05** `collect_success_rate` — 성공/총 시도(11 §2.3 `≥99%`), 미측정 시도(None) 분모 제외·`n_unknown` 노출(honest-gap §6.2) · **SLO-06** `schema_pass_rate` — 통과/총 검증(`≥95%`), 미실행 None 분모 제외 · **SLO-07** `quarantine_dwell_times·median·median_days` — 체류 시간(종료−진입, ms 중앙값·일 단위, `≤3d`), 진행 중(None)·비정방향 제외, 빈 입력 → None(부재가 OK 아님). **SLO-08** `reprocess_benchmark` — full rebuild 벽시계 공개(10 §1.4·recompute_bench 재사용), 목표가 "벤치마크 공개" 라 임계 게이트 없이 **공개 + measured 여부**(`full_ms` 부재 → measured=False) 명시. 각 판정 `evaluate_slo05/06/07` — 목표 대비 `ok` / `slo-gate`(10 §1.4 CI 비차단 nightly) / `not-measured`(부재). read-only(불변식 §3-3)·결정적·mock/실측 격리. **스키마·계약 변경 없음 → Spec 그대로(1.0.0).** TDD — `test_slo_metrics_harness` 신규 25개(성공률·통과율·체류 중앙값·일 변환·재처리 공개·미측정 None·게이트 판정·read-only·결정성) — 스위트 923→**948개 통과**(회귀 0). 다음: 실데이터 축적 시 SLO-05/06/07/08 목표치 확정.

> **구현 메모 (Phase 6 — Watchtower SLO 운영 경보 라우팅 봉인, 2026-08-12):** §2.3 계약("SLO 위반은 Signal Spire 결론 알림이 아니라 **Watchtower 운영 경보**로 라우팅", ADR-1104 채널 분리)을 코드로 봉인했다. `watchtower_slo_alert.py` — **운영 경보 라우터** (Signal Spire `signal_spire.py` 결론 알림과 별개 채널 `watchtower-operational`). **위반 = `classified=="slo-gate"` 만** (각 SLO 하니스 `evaluate_slo01/05/06/07` 산출 shape 주입, 10 §1.4 CI 비차단 nightly) · **`not-measured` 는 위반이 아님** — honest-gap(§6.2 부재가 OK 가 아님) → 무시하지 않고 `not_measured` 버킷으로 노출해 관측 창 채움 · **fire-once** — `slo:{slo_id}` dedup_key 로 재알림 금지(ADR-1104) · **rollout 창(§2.3)** SLO 별 메타 부착(7d/1d/30d/release) · classified 미지정 입력은 `unclassified` 버킷으로 퉁치지 않고 노출. 알림은 측정 스냅샷(값·목표·within_slo)을 담아 온콜 판단 근거 제공. read-only(불변식 §3-3)·결정적 — alert 는 산출물, 저장·발송은 호출자 몫. **스키마·계약 변경 없음 → Spec 그대로(1.0.0).** TDD — `test_watchtower_slo_alert` 신규 17개(위반 판별·alert 채널/dedup/window·route 라우팅 버킷·fire-once·not-measured not-drop·unclassified·빈/None·read-only·결정성) — 스위트 967→**984개 통과**(회귀 0). 다음: 실데이터 축적으로 SLO 위반 라우팅의 실측 주입, 또는 나머지 deferred.

> **구현 메모 (Phase 6 — SLO nightly 게이트 봉인, DoD ② 운용 루프, 2026-08-12):** Phase 6 DoD ② "지속 수집이 자동 신호·SLO 에 반영되는 운용 루프 가동" 의 **통합 오케스트레이션**을 봉인. `slo_nightly_gate.py` — 각 SLO 하니스 **측정 → 판정(evaluate_slo0*) → Watchtower 운영 경보 라우팅 → error budget** 을 하나의 기계적 nightly 게이트로 연결 (10 §1.4 CI 비차단). `NIGHTLY_SLOS = (SLO-01/05/06/07/08)` — Phase 6 deferred SLO 스코프. `classify_slo(slo_id, measurement)` — 해당 SLO 하니스 판정 재사용, 미지정 id 는 ValueError(조용한 ok 퉁치기 금지). `run_nightly_gate(measurements, router)` — `{slo_id: 실측값|None}` 주입(측정은 nightly 드라이버가 하니스에서 획득, mock/실측 격리), `per_slo`·`violations`(Watchtower 라우팅)·`not_measured`(honest-gap — 위반/분모 둘 다 제외)·`error_budget{violations, measured_count, violation_ratio}`(SLO-08 게이트 제외)·`router`(fire-once 상태 유지, 재사용/교체). read-only(불변식 §3-3)·결정적 — 게이트는 분류·알림 산출물만, 저장·발송·스케줄은 운영 드라이버. **스키마·계약 변경 없음 → Spec 그대로(1.0.0).** TDD — `test_slo_nightly_gate` 신규 14개(측정→판정·slo-gate/ok/not-measured·미지정 id 예외·Watchtower 라우팅·error budget·미측정 분모 제외·빈/None·fire-once·read-only·결정성·NIGHTLY_SLOS) — 스위트 984→**998개 통과**(회귀 0). **실측 주입 (2026-08-12):** 이번 세션 실제 실측값 주입 — SLO-01 `p95_ms=495,638`·SLO-05 `success_rate=1.0`·SLO-06 `pass_rate=1.0`·SLO-07 `None`(구조적 not-measured)·SLO-08 `{full_ms:16830}` → **`ok=[SLO-01/05/06]`·`not_measured=[SLO-07]`·`violations=[]`·`error_budget{violations:0, measured_count:3, ratio:0.0}`** — DoD ② 운용 루프 실측 가동 확인. SLO-08 은 이 게이트의 `evaluate_slo08` 분류 계약상 `unclassified`(공개 목표 — Slack 게이트 미포함) 로 정직 노출.

> **실측 메모 (Phase 6 — SLO-08 부분 실측·전체 외삽, 2026-08-12):** §2.3 SLO-08 "100만 문서 전체 재처리 시간 벤치마크 공개" 의 **실측 실행**. 전체 104,554건 단일 프로세스 재처리는 이 환경에서 ~2h 가 걸려 **3차례 완주 실패**(58min·3h 시도 모두 kill) — 완주 벽시계 영속 기록도 부재(기존 ROADMAP "104,544건 재처리 완주" 는 Q4 signal-slice 재처리이며 full rebuild 총 벽시계가 아님). 그래서 **유한 배치 실측 + 정직 외삽**로 전환. `reprocess_benchmark`(SLO-08 하니스, read-only)에 실제 측정 `full_ms` 주입 실측: **배치 1,000건 부하 후 full rebuild 벽시계 = 16.83s → measured=True·per-doc 16.83ms** (in-memory `CuratedZone`, 결정적 체인 `bulk_pipeline(zone, mutation_log=None)`, 판독 전용). 이 **실측 per-doc 계수로 전체 외삽**: 104,554 × 16.83ms ≈ **1.76h** — 이 값은 **projected(추정)로 measured=False 명시** (전체 완주 측정이 아니므로 §6.2 honest-gap — 배치 실측이 전체 벤치 공개를 대체하지 않음). SLO-08 목표가 "벤치마크 공개" 임은 유지 — **직접 측정한 것(배치)과 외삽(전체)을 명확히 구분 표기**해 과대 주장 없이. 전체 재처리 **완주 벽시계는 분산 batch(01 §6)·부하 인프라 갖춰질 때 재측정** 대상으로 대기. read-only·결정적·mock/실측 격리 유지. **스키마·계약 변경 없음 → Spec 그대로(1.0.0).** 다음: 실측 여건 갖춰질 때 전체 재처리 완주 벽시계 재측정 또는 나머지 deferred.
> **실측 메모 (2026-08-18 — SLO-08 완주 + #9 분모 고정):** 위 전체 외삽(1.76h projected) 을 **실측 완주로 대체** — 104,677건 전체를 로컬 multiprocessing(k=10) 으로 실제 재처리, **병렬 완주 벽시계 334,033ms(~5.6min) measured=True**, speedup 5.10×(깨끗한 순차 16.28ms/doc). per-doc **병렬 = 3.191ms 실측 분모** 로 1M 투영: **병렬(k=10) ≈53.2min · 순차 ≈271min** — 단 #9/MVP 는 **물리 1M 미실행 → measured=False 투영 유지**(실측 분모 기반 투영이 1M 완주를 대체하지 않음, §6.2). SLO-07 은 동일 재실사에서 단일 패스 구조상 해소(종료) 미발생 재확인 — **not-measured(구조적) 유지** (재평가 인프라 필요).

> **구현 메모 (Phase 6 — SLO-05/06/07 실측 관측 로그, DoD ① 선행, 2026-08-12):** deferred SLO-05/06/07 가 "실데이터에 측정 로그가 없어 **측정 불가**"였던 근본 원인(attempt/failure/quarantine 로그 부재 → 분모 0 → vacuous)을 해결 — **다음 수집·처리 런부터 실제로 측정 가능**하게 하는 관측 계층을 신설. `slo_observation_log.py` — sealed 하니스(`slo_metrics_harness` **수정 없음**)의 **입력 셰이프를 생산**하는 비침투적 어댑터 + clock 주입(결정적·mock/실측 격리). **SLO-05** `record_collect(source_id, url, ok)` → `success_results()` → `collect_success_rate`(시도/성공). **SLO-06** `record_schema(kind, valid)` → `schema_results()` → `schema_pass_rate` (verify_* verdict 통과 여부 기록). **SLO-07** `record_quarantine_enter(edge_key, reason)` + **`record_quarantine_exit(edge_key)`** — 기존 코드에 **종료(해소) 이벤트가 없던 것을 신설**해 진입/종료 타임스탬프 짝지어 체류 이벤트 확정 → `dwell_entries()`(=(enter_ms, exit_ms)) → `quarantine_dwell_median` (진행 중·진입 없는 종료·재진입·비정방향은 honest-gap §6.2 로 제외). 로그 부재 → 하니스 `measured=False`/`not-measured` 자동 (부재가 OK 가 아님). 실제 영속·발송(flush)은 운영 드라이버 몫(=메모리 로그만, mock/실측 격리). read-only(불변식 §3-3 — 산출 메서드는 비파괴 조회)·결정적. **스키마·계약 변경 없음 → Spec 그대로(1.0.0)** (신규 모듈만, 기존 하니스·파이프라인 무변경). TDD — `test_slo_observation_log` 신규 9개(수집→성공률 연결·schema→통과율 연결·quarantine 진입/종료→체류 중앙값 연결·진행 중 제외·종료-무진입 무시·재진입 멱등·빈 로그 not-measured·read-only 조회·clock 결정성) — 스위트 998→**1007개 통과**(회귀 0). 다음: 다음 수집 런에서 로그 주입해 SLO-05/06/07 실측·목표 확정(contradiction·lineage 재수집과 동일 실측 여건 대기).

> **구현 메모 (Phase 6 — SLO 관측 로그 배선, DoD ① 선행 완결, 2026-08-12):** 위 관측 계층(`slo_observation_log`) 을 **실제 측정 경계에 배선** — 다음 수집·처리 런부터 로그가 자동 축적되어 SLO-05/06/07 실측이 **코드로 완결**됨 (DoD ①의 실측 경로 완성). 전부 **선택 주입(`slo_log=None` 기본)** → 기존 동작 무변경·Spec 1.0.0 유지. **SLO-05** `collect_large` 의 `collect_arxiv`/`collect_rss`/`collect_sec` — 각 문서 저장(성공)·fetch 실패 지점에서 `record_collect` → 성공률 실측 경로. **SLO-06** `claude_judge.ClaudeJudge(slo_log=)` — `validate_canonical_verdict`·`validate_contradiction_verdict` 검증 결과를 `record_schema` 로 기록 (스텁 폴백=LLM 미검증은 계수 제외 — 실제 스키마 검증만, honest-gap §6.2). **SLO-07** `Gate(slo_log=)` — **quartarined 결정 → 진입, promoted 재평가(해소) → 종료** 이벤트 기록 (`element:<ref>` 키) → 동일 element 진입→해소가 체류 이벤트로 확정 (진입-무해소는 진행 중 제외·진입 없는 해소 무시 — honest-gap). read-only·결정적·mock/실측 격리 유지. **스키마·계약 변경 없음 → Spec 그대로(1.0.0)** (기존 계약 무변경, 선택 주입만). TDD — 배선 테스트 신규 11개(collect_arxiv/rss/sec→SLO-05 성공률, judge canonical/contradiction→SLO-06 통과율, stub 미계수, gate 진입/해소→SLO-07 체류·진입만 미측정·진입→해소 경과 측정·무로그 동작) — 스위트 1007→**1018개 통과**(회귀 0). 다음: 다음 런에서 로그 자동 축적 → SLO-05/06/07 실측·목표 확정.

> **구현 메모 (Phase 6 — 실행 경로 slo_log 배선, DoD ① 경로 완결, 2026-08-12):** 위 모듈·측정 경계 배선은 **선택 주입 계약**이었고 실제 실행 진입점인 `run_pipeline`(pipeline_runner) 이 내부 `Gate()` 를 직접 생성해 `slo_log` **전달 경로가 없던 미배선**을 해소. `run_pipeline(..., slo_log=None)` → 내부 `Gate(slo_log=slo_log)` 로 quarantine 진입/해소 로그가 **실제 파이프라인 실행 시 자동 축적** (SLO-07), `bulk_pipeline(..., slo_log=None)` 도 스레딩. 기본 None → 기존 동작 무변경·**Spec 1.0.0 유지** (선택 인자만, 계약 변경 없음). TDD — 배선 테스트 신규 2개(`run_pipeline(slo_log=)`→Gate 로그 스레딩·무로그 무변경) — 스위트 1018→**1020개 통과**(회귀 0). 다음: 로그 자동 축적 전제 갖춰짐 → 실제 런(수집·재처리·LLM judge)에서 SLO-05/06/07 실측·목표 확정.

> **구현 메모 (Phase 6 — SLO-05/07 부분 배치 실측, DoD ① 경로 실증, 2026-08-12):** 배선된 관측 계층을 유한 배치(1,000건, 기존 104,554 read-only 데이터 재처리, `bulk_pipeline(slo_log=...)`)로 **실제 구동**해 배선의 실동작을 실증. 결과: **SLO-07 `open_quarantine=71`** — quarantine 진입 로그가 실제 `Gate`→`slo_log` 경로로 71건 누적됨(**배선 실증**, 동일 재처리에서 미배선 시 존재 불가). 그러나 **어느 SLO도 `measured=True` 가 되지 않음**(honest-gap §6.2 정직 표기): SLO-07 `dwell_resolved=0` — in-memory 단일 렌더에선 quarantine **해소(종료)가 발생하지 않아** 체류 미확정(진입 71건은 진행 중 성분으로 not-measured). SLO-05 `collect_attempts=0` — 기존 문서 재처리는 **fetch·수집 시도가 없어**(저장 dedup/불변식 §3-2) 성공률 분모 부재. SLO-06 `schema_checks=0` — 결정적 체인 `judge=None`은 verify_* verdict 미검증 → 통과율 분모 부재. **배선은 실증됐으나 측정값은 실측 필요 여건에 좌우됨**: SLO-05 는 신규 수집 런(네트워크 fetch), SLO-06 은 실제 LLM judge 구동, SLO-07 은 quarantine 해소를 유발하는 재평가(다문서·최신 zones 여건)가 있어야 진짜 `measured` 가 된다 — 부재는 결과로 유지(not-measured). 현재 DoD ① 실측 여건: SLO-05/06 신규 런·LLM, SLO-07 은 분산·후속 재평가 인프라와 함께 대기.

> **실측 메모 (Phase 6 — SLO-01 measured=True, 2026-08-12):** deferred SLO-01(신규 문서 → graph 반영 지연 p95, `≤ 30 min`) 을 **진짜 실측**. **정직 경계:** 기존 원문 `fetched_at` 은 과거(8/18 이전) — '수집→반영 지연' 이 아닌 '문서 나이' 가 되어 통과로 오인될 수 있음(§6.2) → **신규 RSS 수집**(`fetched_at≈now`, SOURCES 3개) 으로 신규 문서 77건 확보, 실제 반영 경로 `bulk_pipeline`(read-only `:memory:` `CuratedZone`) 구동. 측정 공식(§2.3) `graph_commit_ts − fetched_ts`(p95) — 배치 **단일 주기 반영 경계**(06 §7.2 incremental commit) 로 각 문서 지연 = 반영 완료 시각 − 본인 `fetched_at`. 결과 **`{p95_ms:495,638 (~8.3min), n:77, classified:'ok'}`** — `evaluate_slo01`(하니스 봉인 923) 목표 내, **SLO-01 `measured=True`**. p95 8.3min 은 3개 RSS 소스를 순차 수집하는 동안 먼저 수집된 문서가 배치 반영 완료까지 대기한 실제 경계 — 단일 주기 (실측). 표본 77건·단일 반영 주기이므로 후속 수집 런에서 더 넓은 표본으로 목표치 확정. read-only·결정적. 코드 변경 없음 → **Spec 1.0.0 유지**.

> **실측 메모 (Phase 6 — SLO-05 measured=True 전환·표본 확대, 2026-08-12):** 신규 수집 런으로 SLO-05 를 **진짜 측정**. `collect_sec` — 성공(`ok=True`)·실패(`ok=False`) **양쪽을 기록하는 유일한 경로**(arxiv 는 성공만 기록 → vacuous 100% 회피). 1차 런 `limit=1` — SEC EDGAR 1건 실제 네트워크 fetch 성공 → 관측 계층 누적 → sealed 하니스 `collect_success_rate` **`{success_rate:1.0, n_success:1, n_attempt:1, n_unknown:0, measured:True}`** — **SLO-05 `measured=True`** (배선 커밋 3ecb063 의 실데이터 실증). **표본 확대 런 `limit=5, ciks=[1045810(NVDA), 1046179(TSM)]`** — 두 출처 실제 fetch 로 시도 10건 → **`{success_rate:1.0, n_success:10, n_attempt:10, n_unknown:0, measured:True}`** (counts `{saved:7, skipped:3, errors:0}` — content-hash 중복 저장 3건도 실제 fetch 성공 시도이므로 성공으로 계수, 부재 없는 진짜 시도/성공). `n_unknown=0` 이라 honest-gap(§6.2) 기준 **부재가 아닌 진짜 측정값**. **목표 판정 런** — `slo_log` 주입으로 SEC(2 CIK)+RSS(3 source) 재수집 → 시도 **50건** → `collect_success_rate` **`{success_rate:1.0, n_success:50, n_attempt:50, n_unknown:0, within_slo:True}`** — 목표 `≥99%` 기계적 충족 기록 (SEC content-hash 중복 10건·RSS 양쪽 기록 경로로 시도 확대). 50건 채널 성공률 1.0 은 여전히 표본 — 일반화 한계(§6.2)를 인지하고 후속 수집 런에서 표본 더 확대.

> **실측 메모 (Phase 6 — SLO-05 표본 확대 n=440→1,540, A6 런, 2026-08-18):** A6 수집 확대 런(아래)의 `slo_log` 주입으로 SLO-05 시도/성공 1,100건 추가 축적 → sealed 하니스 `collect_success_rate` **`{success_rate:1.0, n_success:1,540, n_attempt:1,540, n_unknown:0, within_slo:True}`** measured=True — **표본 n=440 → n=1,540 (3.5×)**. arXiv windows=10(과거 연대)|RSS 3 source 의 실제 fetch 시도/성공이 전부 축적되어 1,540 시도·성공률 1.0 을 유지. `n_unknown=0` — 부재 없는 진짜 시도/성공(성공만 기록하는 arXiv vacuous 성분이 RSS 의 실패-기록 경로와 함께 섞여도, 시도 자체가 성공률 분모로 정직 계수). 성공률 1.0 추정치는 여전히 표본 기반 — 일반화 한계를 인지하고 후속 수집 런에서 계속 확대 가능.

> **실측 메모 (Phase 6 — SLO-05 표본 확대 n=1,540→2,040, A7 런, 2026-08-18):** A7 수집 확대 런(아래)의 `slo_log` 주입으로 SLO-05 시도/성공 500건 추가 축적 → sealed 하니스 `collect_success_rate` **`{success_rate:1.0, n_success:2,040, n_attempt:2,040, n_unknown:0, within_slo:True}`** measured=True — **표본 n=1,540 → n=2,040 (1.3×)**. arXiv windows=16(과거 연대)|RSS 3 source 의 실제 fetch 시도/성공이 추가 축적되어 2,040 시도·성공률 1.0 유지. `n_unknown=0` — 부재 없는 진짜 시도/성공. 성공률 1.0 추정치는 여전히 표본 기반 — 일반화 한계를 인지하고 후속 수집 런에서 계속 확대 가능. **동반 수집 포화 관측:** A7 arXiv 는 skip 1,998/2,000 — **수집이 자연 포화에 접근**(rary 성장 신규 급감, 실질 신규는 RSS 유한·미수집 연대 여백에 의존). SLO-05 표본은 시도/성공 계수이므로 **수집 확대 없이도 다음 런 RSS refresh 로 계속 축적 가능**(표본 확장은 수집 성장과 독립).

> **실측 메모 (Phase 6 — SLO-06 measured=True 전환, 2026-08-12):** 실제 LiteLLM judge 로 SLO-06 을 **진짜 측정**. `.env` 의 `LLM_PROVIDER=litellm`/`LLM_BASE_URL`/`LLM_MODEL=bunker-flash` config (`build_llm_client` 경유) 로 실제 proxy 라우팅 판정 — 실제 원문의 결정적 체인(extract→resolve→claim) 으로 candidate 쌍 생성, `ClaudeJudge(slo_log=)` 로 canonical·contradiction **20건 실제 판정** → 관측 로그 누적 → sealed 하니스 `schema_pass_rate` 판정 **`{pass_rate:1.0, n_pass:20, n_total:20, n_unknown:0, measured:True}`** — **SLO-06 `measured=True`** (프로바이더 config 커밋 e3fc602 의 실데이터 실증). read-only(`:memory:` zone)·유한 상한(20, smoke `_BoundedJudge` 와 동일 cap)·`n_unknown=0`(진짜 검증만 계수 — honest-gap §6.2). usage 4420/1678 tokens·20 calls (S42). **표본 확대 런** — `_BoundedJudge` cap 20→40, 동일 실제 원문 체인으로 canonical·contradiction **40건 실제 판정** → **`{pass_rate:1.0, n_pass:40, n_total:40, n_unknown:0, measured:True}`** (usage 8858/3455·40 calls) — **SLO-06 measured=True 유지·표본 2배**. 더 넓은 샘플·실데이터 골든(contradiction 미자연발생)은 차기 실측 여건에서.

> **실측 메모 (Phase 6 — SLO-07 quarantine 원인 분해, 구조적 not-measured 확정, 2026-08-12):** 실제 파이프라인(`run_pipeline(slo_log=)`) 500건 구동으로 quarantine 진입을 실제 측정 → **`open_quarantine=71`, `dwell_resolved=0`** (단일 패스). quarantine 원인을 직접 분해한 결과 **71건 전부 `unknown_predicate:partners`** — predicate `partners` 가 `CONTROLLED_PREDICATES`(02 §4-2 폐쇄성) 에 없어 quarantine 되는 **고정 원인**. 즉 SLO-07 해소(진입→종료 짝)는 현 체인 구조에서 **구조적으로 발생 불가**하다: (1) Gate 결정성 — 동일 claim 재평가는 동일 결과, (2) 단일 패스 — element 를 1회만 평가, (3) quarantine 원인이 전부 고정(unknown_predicate) 이라 **후속 라운드가 해소시킬 의존 상태 차이가 없음**. 이 71건은 **permanent quarantine**(정당 — 미지 predicate 는 authoritative 진입 금지, 02 §4-2) 로 체류 시간이란 개념 자체가 적용 안 됨. **SLO-07 `not-measured` 는 측정 부재가 아니라 구조적 성질** — real quarantine 체류가 발생하려면 **quarantine 이 promoted 로 해소되는 element**(의존 상태가 평가 사이에 변하는 것 — 예: 미해소 subject→재평가, contradiction 재평가) 가 필요하며, 이는 **다중 라운드 파이프라인/분산 후속 재평가 인프라** 와 함께 와야 한다. 현 단일 패스는 해소를 생산하지 않으므로 honest-gap(§6.2) 기준 **not-measured 유지**가 정직 표기다 (부재/구조적 부재를 측정으로 오인 금지). 현재 `unknown_predicate:partners` quarantine 은 predicate 어휘 확장(02 §4-2) 또는 폐기 정책의 별도 결정 사항으로, SLO-07 실측 여건과 독립적.
>
> **정합화 해소 (Phase 6, predicate 정합화):** 이후 원인 추적 결과 `unknown_predicate:partners` 는 **온톨로지 어휘 부족이 아니라 extractor 의 stale 축약 방출** — 온톨로지 02 §5.1·05·08·gate `CONTROLLED_PREDICATES` 는 전부 공식 `partners_with` 를 표준으로 봉인했으나, `extract_claims.py` 파트너십 규칙만 축약 `partners` 를 방출해 §4-2 폐쇄성 게이트 실패 유발. 해당 규칙 predicate 를 `"partners"` → `"partners_with"` 로 **정합화** (어휘 변경 아님 — frozen Spec 과 일치). 재처리 시 `unknown_predicate` quarantine 제거·해당 claim 정상 승격. **SLO-07 의 고정 원인 성분이 제거**되었으나, real quarantine 체류(진입→해소) 의 측정은 여전히 해소를 유발하는 재평가(다중 라운드·분산 후속 재평가 인프라, 06 §7.2) 가 있어야 하므로 **SLO-07 not-measured 구조적 대기 유지**.
> **실측 조사 메모 (2026-08-18 — SLO-07 "not-measured" 재정의: 인프라 문제 → 모집단 0):** "재평가 인프라 구축" 이 SLO-07 실측을 가능케 하는지 조사한 결과 **반전**. 실데이터(5,000·8,000건 슬라이스) 에서 `open_quarantine=0·dwell=0` 임을 실측 확정 — 모든 mention 해소·promote(2,347건), claims 전체 promote(430), edges 0. 근본 원인: **① 비해소 subject claim 은 `extract_claims` 가 추출 단계에서 폐기**(`if not subject_id: continue`, precision-first 05 §3·02 §4-3) → 게이트 `missing_subject` quarantine 은 도달 불가 ② 이전 유일 quarantine 모집단(71건 `unknown_predicate:partners`) 은 predicate 정합화로 소멸. → **재평가 인프라를 구축해도 실데이터에서 dwell 측정할 quarantine 가 없음**(§6.2 — 합성 테스트로 measured 처럼 보이는 것 방지). SLO-07 임계(≤3d) 는 0 건 quarantine 이므로 위반 아님 으로 확정 유지, shear dwell-time **분포는 모집단 0 → measured 전환 불가**. quarantine 인공 유발(추출/게이트 임계 하향) 은 precision-first §3-4·05 §3 위배로 채택 안 함. **not-measured(모집단 0 — 데이터 셰이프 특성)** 라벨로 교정. next: real quarantine 모집단 을 만드는 저신뢰·주변 재평가 경로(LLM judge 탐색) 또는 다른 인프라 방향.

---

## 3. Idempotency·재시도 운영 (불변식 §3-6)

모든 stage 작업은 idempotency key를 가지며, retry해도 동일 graph mutation을 중복 생성하지 않는다 (→ [README](./README.md) §3-6, [01](./01-architecture.md) §4 stage별 key, [03](./03-storage-and-data-model.md) §7.1 `idempotency_key` unique).

### 3.1 재시도·dead-letter 정책

| 항목 | 규칙 |
| --- | --- |
| Idempotency key | stage별로 [01](./01-architecture.md) §4 표에 정의(예: S7 = `graph_mutations.idempotency_key`(stage input 해시; `mut-` PK와 별개), S5 = `doc_id+prompt_hash+model_id`) |
| Retry | exponential backoff + jitter, stage별 최대 재시도 횟수 상한. source별 rate limit 준수(→ [04](./04-ingestion-and-parsing.md)) |
| Dead-letter | 상한 초과 시 DLQ로 이동, 원본 payload·오류·`correlation_id` 보존. **폐기하지 않는다** |
| 중복 mutation 방지 | 동일 `idempotency_key` 재수신 시 `graph_mutations`가 **no-op**(→ [03](./03-storage-and-data-model.md) §7.2) |
| 재실행 검증 | 동일 raw corpus + 동일 version tuple → 동일 materialized graph(재현성, blueprint §21-2). integration test로 강제(→ [10](./10-evaluation-and-testing.md)) |

- **중복 mutation 방지 확인 계약:** retry·부분 재처리 후 `graph_mutations`를 `idempotency_key`로 그룹핑했을 때 중복 적용이 0건임을 D4/D2 대시보드에서 관측 가능해야 한다.
- retry율·dead-letter율은 blueprint §12.4 시스템 성능 지표로 D2에 노출한다.

---

## 4. Signal Spire (알림)

### 4.1 트리거 (Blueprint §5.3)

Signal Spire는 **결론과 confidence의 중요한 변화**만 알린다(운영 경보와 구분). 트리거는 다음으로 한정한다.

| 트리거 | 조건 | 근거 데이터 |
| --- | --- | --- |
| `contradicting_evidence` | 기존 결론을 뒤집는 반대 증거 발견 | 신규 `CONTRADICTS` 엣지(→ [02](./02-ontology.md)) |
| `claim_changed` | 기업·인물의 기존 주장이 변경됨 | `SUPERSEDES` 이벤트 |
| `plan_to_execution` | 계획으로만 발표된 내용의 실행 증거 발견 | `Event.status` planned→confirmed |
| `new_independent_source` | 서로 독립적인 새 출처 추가 | 독립 증거 수 증가(§1.4) |
| `confidence_threshold` | confidence가 임계값 이상 변함 | claim confidence Δ |

### 4.2 1회 점화 (과잉 알림 금지)

- Signal Spire는 중요한 변화에 한해 **한 번 점화(fire-once)** 하며 무한 반복하지 않는다 (blueprint §1.4 모션 원칙: "중요한 변화에 한해 한 번 점화").
- 동일 (investigation, trigger_type, target) 조합은 **dedup key**로 묶어 이미 점화된 변화를 재알림하지 않는다. 상태가 재차 유의미하게 변할 때만(예: confidence가 반대 방향으로 임계 재돌파) 새 알림을 만든다.
- 알림은 investigation을 Campaign으로 등록한 사용자에게만, 관련 War Table subgraph 갱신 시 후보로 생성된다 (blueprint §5.3).

### 4.3 Alert 스키마

```json
{
  "alert_id": "alt-01J9...",
  "investigation_id": "inv-01J9...",
  "trigger_type": "contradicting_evidence",
  "severity": "material",
  "dedup_key": "inv-01J9...:contradicting_evidence:clm-01J9...",
  "target": { "claim_id": "clm-01J9...", "canonical_claim_id": "ccl-01J9..." },
  "delta": {
    "before": { "confidence": 0.83, "conclusion": "supports" },
    "after":  { "confidence": 0.41, "conclusion": "contested" }
  },
  "cause": {
    "mutation_ids": ["mut-01J9..."],
    "correlation_id": "...",
    "new_document_ids": ["doc-..."],
    "independent_evidence_count": 3
  },
  "fired_at": "2026-08-03T09:00:00Z",
  "fire_count": 1,
  "acknowledged": false
}
```

- alert의 대상 식별 필드는 `investigation_id`(technical-first)이며 `campaign_id`를 쓰지 않는다. [09](./09-api.md)의 investigation 계약과 동일 필드명으로 정합한다(→ [09](./09-api.md) ADR-903). "Campaign"은 사용자가 investigation을 관찰 대상으로 등록하는 UI 개념이며, 알림 스키마 필드는 `investigation_id`로 통일한다.
- `cause`는 provenance 게이트를 통과한 근거만 담는다. **알림 역시 감사 가능**해야 하며, 사용자는 알림에서 mutation → evidence → 원문 span까지 추적할 수 있어야 한다(Trail).
- `severity`는 결론 변화 크기 기준(`material`/`minor`)이며, 색·아이콘이 아니라 값과 delta로 표현한다(blueprint §1.4 접근성).

> **구현 메모 (Phase 5 — Signal Spire 알림, 2026-08-12):** `signal_spire.py` — §4 트리거·fire-once·alert 스키마를 봉인 (Phase 4 결정적·read-only 원칙). **5 종 트리거 (§4.1):** `trigger_contradicting_evidence`(신규 CONTRADICTS)·`trigger_claim_changed`(SUPERSEDES)·`trigger_plan_to_execution`(Event.status planned→confirmed, 02 ontology)·`trigger_new_independent_source`(독립 증거 수 증가 — §1.4)·`trigger_confidence_threshold`(Δ ≥ `CONFIDENCE_DELTA_TRIGGER=0.10`, 10 실측 조정). **1 회 점화 fire-once (§4.2, ADR-1104):** `SignalSpire` 가 점화된 `dedup_key` 기억해 재알림 금지 — 동일 `(investigation_id, trigger_type, target)` 재점화는 `None`(과잉 알림 방지), 상태가 재차 변해 다른 dedup_key 로만 새 알림. **Alert 스키마 (§4.3):** `make_alert` — `investigation_id`(technical-first, campaign_id 미사용 — ADR-903)·`severity`(material/minor)·`dedup_key`(자동 `inv:trigger:target`)·`delta`·`cause`(provenance gate 통과 근거만)·`fire_count`·`acknowledged`. `evaluate_and_fire` — 평가→fire-once→alert 일괄 래퍼. 실제 mutation event 는 주입, 결정성은 순수 이벤트 평가로 봉인. read-only(불변식 §3-3) — **알림은 산출물일 뿐 저장·발송은 호출자 몫.** **스키마·계약 변경 없음 → Spec 그대로(0.1.9).** TDD — `test_signal_spire` 신규 28개(5 트리거 조건·정밀성·fire-once 재알림 금지·alert 스키마·evaluate 일괄·read-only·결정성) — 스위트 719→**747개 통과**(회귀 0). 다음: Phase 5 는 1,000만 Challenge — signal source adaptive scheduling(04 §?).

---

## 5. 안전·거버넌스 (Blueprint §13)

### 5.1 수집·개인정보·retention

| 규칙 | 강제 지점 |
| --- | --- |
| 공개적으로 허용된 자료만 수집 | fetch 시 `robots_allowed`·`license` 검사(→ [03](./03-storage-and-data-model.md) §2.2 `fetch.json`), 위반 시 수집 거부 + D1 기록 |
| 개인정보·민감정보 최소화 | 추출 단계에서 불필요 PII 저장 억제, 민감 필드 태깅 |
| Retention 정책 | 모든 source·document는 `retention_class`를 부여받고(§5.1.1), 클래스별 TTL 만료 시 삭제 전파(§5.2) 자동 트리거 |
| 사람 대상 부정적 주장 | **복수 독립 출처 + 높은 검증 기준**. 단일 출처면 authoritative graph 진입 금지 → quarantine(§1.4 독립 증거 수 연동) |

#### 5.1.1 `retention_class` 정의

각 source·document는 수집 시 `retention_class`를 부여받는다. **저장 위치:** source config에 source 단위 기본값을 두고, 개별 문서가 더 강한 클래스를 요구하면 [03](./03-storage-and-data-model.md) `documents` 레코드의 `retention_class` 컬럼으로 override한다(문서 단위가 source 기본값보다 우선). **강제 지점:** Watchtower의 retention sweeper(일일 배치)가 TTL 경과 대상을 스캔해 §5.2 삭제 전파 절차를 발행한다.

| `retention_class` | 대상 | TTL(placeholder) | 만료 시 동작 |
| --- | --- | --- | --- |
| `standard` | 공개 문서·일반 출처 | 무기한(정책 재평가까지) | 없음 |
| `sensitive_pii` | 개인정보·민감정보 포함 문서 | `≤ 180d` (TBD) | §5.2 삭제 전파 자동 트리거 |
| `legal_hold` | 법적 보존 의무 대상 | 해제까지 삭제 금지 | 삭제 요청도 보류(hold 우선, §5.2보다 우선) |
| `ephemeral` | 임시 취득·저신뢰 원천 | `≤ 30d` (TBD) | §5.2 삭제 전파 자동 트리거 |

- TTL 수치는 placeholder이며 법무·정책 검토 후 확정한다(§2.3 SLO와 동일 원칙).
- `legal_hold`은 삭제 요청(§5.2)보다 우선하여, hold 해제 전까지는 삭제 전파를 보류하고 그 사실을 append-only 이벤트로 기록한다(감사성 유지).
- retention 만료로 발행된 삭제는 §5.2의 raw→normalized→curated→graph 역방향 전파를 그대로 따르며 idempotent하다.

### 5.2 삭제 요청 파생 전파 (03 §8.4 구체화)

삭제 요청·원천 문서 제거는 파생 데이터까지 전파해야 한다 (blueprint §13, [03](./03-storage-and-data-model.md) §8.4). raw→normalized→curated→graph **역방향** 절차를 확정한다.

```text
Deletion request (doc_id | source_id | subject entity)
  1. raw zone       : content.bin tombstone (객체 삭제/무효화, fetch.json에 deletion_ref 기록)
  2. normalized     : 해당 doc_id의 documents/segments 파생 무효화
  3. curated        : mentions / claim_candidates / evidence_candidates / dup_clusters 재계산
                      (근원 문서 삭제 시 클러스터의 root 재지정 또는 클러스터 해체)
  4. graph          : provenance_ref가 삭제 대상만을 가리키는 element에 대해
                      `delete` / `quarantine` mutation 발행 (append-only, → 03 §7)
```

- **전파 규칙:** graph element의 `provenance_ref`가 **오직 삭제 대상 문서만** 가리키면 `delete` mutation, 다른 유효 근거가 남으면 해당 근거만 제거하고 element는 재평가(→ quarantine 후 재검증).
- 삭제는 raw immutability와 충돌하지 않는다: 원본을 물리적으로 지우되 **삭제 사실 자체는 append-only 이벤트로 기록**(tombstone)하여 "무엇을 왜 지웠는가"는 감사 가능하게 남긴다.
- 삭제 전파는 idempotent해야 한다(재요청 시 no-op). integration test로 검증한다(blueprint §15 "삭제 요청의 파생 데이터 전파", → [10](./10-evaluation-and-testing.md)).

### 5.3 무출처 사실 저장 금지 (불변식 §3-2)

- source span 없는 모델 생성 사실은 authoritative graph에 저장하지 않는다. provenance 게이트 미충족 element는 quarantine으로 라우팅한다 (→ [03](./03-storage-and-data-model.md) §8.3, [02](./02-ontology.md) §4-1).
- 그래프에 없는 정보를 모델 사전 지식으로 보충한 경우 별도 표시하고 기본적으로 최종 결론에 포함하지 않는다 (blueprint §10).

### 5.4 불확실성 표시·감사 로그

| 규칙 | 구현 |
| --- | --- |
| 결론에 불확실성·출처 한계·미조사 영역 표시 | investigation 결과에 evidence coverage(§2 D8)·독립 증거 수·미조사 subclaim 필수 노출(blueprint §5.2) |
| 그래프 변경·수동 교정 감사 로그 | 모든 변경은 `graph_mutations`에 `actor`(pipeline/llm/human)·`version_tuple`·`correlation_id`와 함께 기록(→ [03](./03-storage-and-data-model.md) §7.1). human review는 원 모델 출력·수정·이유를 함께 저장(불변식 §3-7) |
| source별 크롤링정책·라이선스·재배포 관리 | source config의 `compliance` 스키마(→ [04](./04-ingestion-and-parsing.md))에 crawl policy·license·`allow_redistribute`(bool) 필드. 원문 재배포는 `allow_redistribute = true`인 source로만 한정(blueprint §18 데이터 라이선스 위험) |

### 5.5 감사(Trail) 계약

모든 authoritative claim·결론 문장·알림은 다음 경로로 원문까지 왕복 추적 가능해야 한다(blueprint §1.2 Trail, §21-8).

```text
report sentence | alert → claim → evidence (source_span)
  → extraction_record (ext-…) → normalized doc (doc_id, parser_version)
  → raw content.bin (content_hash) → fetch.json (url, license, correlation_id)
```

---

## 6. 의사결정 로그 (ADR-11xx)

| ID | 결정 | 근거 | 상태 |
| --- | --- | --- | --- |
| ADR-1101 | 출처 신뢰도를 단일 점수로 환원하지 않고 7개 차원(`Source.dimensions{}`)으로 분리 저장, 최종 confidence는 claim별 증거 구조로 계산 | 상충하는 신뢰 신호 보존, confidence 과대평가 방지(blueprint §11, §18) | Accepted |
| ADR-1102 | `correlation_id`를 fetch에서 생성해 전 stage로 전파(재작성 금지, 분기 시 `parent_correlation_id`), `graph_mutations`와 정합 | end-to-end Trail 감사·SLO drill-down(blueprint §14, [03](./03-storage-and-data-model.md) §7.1) | Accepted |
| ADR-1103 | 삭제 전파를 raw→normalized→curated→graph 역방향 절차로 확정, 원본은 물리 삭제하되 삭제 사실은 append-only tombstone으로 기록 | 파생 데이터까지 전파 + 감사성 유지(blueprint §13, [03](./03-storage-and-data-model.md) §8.4) | Accepted |
| ADR-1104 | Signal Spire는 결론 변화만 알리고 fire-once(dedup key), 운영 경보(SLO 위반)와 채널 분리 | 과잉 알림 금지(blueprint §5.3, §1.4) | Accepted |
| ADR-1105 | 독립 증거 수는 `dup_clusters` 기반 root source 축소로 보정 | 동일 근원 복제의 confidence 과대평가 차단(blueprint §8.3, §11) | Accepted |
| ADR-1106 | SLO 목표치는 placeholder로 두고 실측 후 확정(측정 창·상태 명시) | 측정 기반 운영, 근거 없는 목표 배제(blueprint §20) | Accepted |
| ADR-1107 | Retention을 `retention_class` enum(`standard`/`sensitive_pii`/`legal_hold`/`ephemeral`)으로 확정 — source config 기본값 + `documents` override에 저장, 클래스별 TTL 만료 시 Watchtower sweeper가 §5.2 삭제 전파 자동 트리거, `legal_hold`은 삭제 요청보다 우선 | 개인정보·민감정보 최소화 및 삭제 전파 계약 명시, 법적 보존 의무 충돌 방지(blueprint §13) | Accepted |
