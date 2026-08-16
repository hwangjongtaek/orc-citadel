# 01 · 시스템 아키텍처 (Citadel)

> **상태:** ✅ Stable · **Spec:** 1.0.0 · **Blueprint 매핑:** §7, §17
> 상위 규약: [`README.md`](./README.md) · 관련: [`03-storage`](./03-storage-and-data-model.md), [`06-graph`](./06-graph-service.md)

전체 플랫폼(Citadel)의 컴포넌트 경계, 데이터 흐름, 기술 스택, 배포 토폴로지를 정의한다. 세부 스키마·계약은 각 하위 문서가 소유하며, 본 문서는 **컴포넌트 간 경계와 책임**을 확정한다.

## 1. 아키텍처 원칙

[`README.md`](./README.md) §3 설계 불변식을 아키텍처로 구체화한다.

1. **Lakehouse+Log-as-SoT.** 그래프·검색 인덱스는 파생물이다. SoT는 immutable raw + curated table + mutation log **세 요소**로 구성되며, 이 셋에서 전량 재구축 가능해야 한다.
2. **단계적 도입.** 초기 구성(단일 노드, Postgres 큐)에서 시작하고, **측정된 병목이 분리를 정당화할 때만** 확장 구성(Kafka, Iceberg, K8s)으로 승격한다 (blueprint §7.2).
3. **Stage 격리 + 공통 correlation.** 각 파이프라인 stage는 독립 배포·재실행 가능하며, 공통 correlation ID로 end-to-end 추적된다 (→ [`11`](./11-observability-and-governance.md)).
4. **Idempotent stage.** 모든 stage는 idempotency key로 재실행 안전성을 보장한다.

## 2. 논리 컴포넌트 맵

```text
                    ┌──────────────────────────────────────────────┐
 Outside World      │                  CITADEL                      │
 (Sources)          │                                              │
   │                │  ┌─────────┐   ┌──────────────────────────┐  │
   ├─ APIs / RSS ──►│  │ Scouts  │──►│  Grand Archive (Lakehouse)│  │
   ├─ Filings ─────►│  │(connect │   │  raw │ normalized │ curated│  │
   ├─ News ────────►│  │ ors)    │   └───────────┬──────────────┘  │
   └─ Research ────►│  └────┬────┘               │                 │
                    │       │ Ingestion Queue    ▼                 │
                    │       │            ┌─────────────────┐       │
                    │       └───────────►│ Processing       │       │
                    │                    │ (parse/dedup/    │       │
                    │                    │  extract)        │       │
                    │                    └───────┬─────────┘       │
                    │                            ▼                 │
                    │                    ┌─────────────────┐       │
                    │                    │ Lorekeepers      │       │
                    │                    │ (resolution)     │       │
                    │                    └───────┬─────────┘       │
                    │            ┌───────────────┼───────────────┐ │
                    │            ▼               ▼               ▼ │
                    │      ┌──────────┐  ┌─────────────┐ ┌────────┐│
                    │      │ War Table│  │ Search/Vector│ │Quaran- ││
                    │      │ (Graph)  │  │ Index (OS)   │ │tine    ││
                    │      └────┬─────┘  └──────┬──────┘ └────────┘│
                    │           │               │                 │
                    │           ▼               ▼                 │
                    │      ┌────────────────────────────┐         │
                    │      │ Warchief's Council (Agents) │         │
                    │      └──────────────┬─────────────┘         │
                    │                     ▼                       │
                    │   ┌─────────────────────────────────────┐   │
                    │   │ API (FastAPI) → Report / Explorer UI │   │
                    │   │ Chronicle · Signal Spire            │   │
                    │   └─────────────────────────────────────┘   │
                    └──────────────────────────────────────────────┘
```

## 3. 컴포넌트 책임 (Bounded Context)

| 컴포넌트 | 세계관 | 책임 | 입력 → 출력 | 정본 문서 |
| --- | --- | --- | --- | --- |
| **Collector** | Scouts | 허용된 소스에서 문서 수집, 변경 탐지, rate limit | source config → raw document + fetch metadata | [`04`](./04-ingestion-and-parsing.md) |
| **Archive** | Grand Archive | raw/normalized/curated 3 zone 저장, 테이블 관리 | 각 stage 산출물 → Parquet/Iceberg | [`03`](./03-storage-and-data-model.md) |
| **Provenance Store** | Hall of Witnesses | claim·assertion의 근거(source span·extraction_record) 계보 보관·조회 | extraction/resolution 산출물 → provenance record | [`03`](./03-storage-and-data-model.md) |
| **Parser** | Archivists | 본문/메타 분리, 문단·문장 ID, offset 매핑 | raw → normalized doc | [`04`](./04-ingestion-and-parsing.md) |
| **Deduper** | — | exact/near/semantic 중복·출처 계보 판정 | normalized → dup cluster | [`04`](./04-ingestion-and-parsing.md) |
| **Extractor** | Evidence Extractor | entity mention·claim·evidence 후보 추출 | normalized → candidates + span | [`05`](./05-resolution-and-extraction.md) |
| **Lorekeepers** | Lorekeepers | Entity Resolution, Claim Canonicalization, Contradiction | candidates → resolved entities/claims | [`05`](./05-resolution-and-extraction.md) |
| **Graph Service** | War Table | mutation event 적용, materialized graph, quarantine | resolution decision → graph mutation | [`06`](./06-graph-service.md) |
| **Quarantine** | Quarantine | 저신뢰·충돌 mutation의 격리 보류(논리 분리, 상태 라벨 `:Quarantine`) | 미확정 resolution/mutation → 보류 상태 | [`06`](./06-graph-service.md) |
| **Search Service** | — | BM25 + 벡터 인덱싱·질의 | curated + graph → index/query result | [`08`](./08-search-and-graphrag.md) |
| **Agent Runtime** | Warchief's Council | 조사 루프, 모델 라우팅, budget 관리 | question → report + evidence subgraph | [`07`](./07-llm-and-agents.md) |
| **API Gateway** | Citadel Gate | REST 계약, 인증, 페이지네이션 | client ↔ services | [`09`](./09-api.md) |
| **Chronicle** | Chronicle | bitemporal event history 조회 | mutation log → time-travel query | [`03`](./03-storage-and-data-model.md) |
| **Alerting** | Signal Spire | 결론·confidence 변화 알림 | graph change event → alert | [`11`](./11-observability-and-governance.md) |
| **Observability** | Watchtower | correlation, 대시보드, SLO. **이중 역할**: ingestion monitor(수집 소스 상태·변경 감시, blueprint §1.2)와 플랫폼 전역 observability를 겸한다 | 전 stage 이벤트 → metrics | [`11`](./11-observability-and-governance.md) |

**경계 규칙:** Agent Runtime은 Graph/Search Service의 read API만 사용하고, 그래프 변경은 반드시 Lorekeepers → Graph Service의 mutation event 경로를 거친다. Agent가 그래프를 직접 mutate하지 않는다 (불변식 §3-3).

## 4. 데이터 흐름 (End-to-End)

blueprint §7 파이프라인을 stage 계약으로 확정한다. 각 stage는 `(input_ref, idempotency_key, version_tuple)`을 받아 `(output_ref, correlation_id)`를 낸다.

| # | Stage | idempotency key | 재실행 단위 | 하위 문서 |
| --- | --- | --- | --- | --- |
| S1 | Fetch | `hash(source_id, url, fetch_window)` | URL | [`04`](./04-ingestion-and-parsing.md) |
| S2 | Store raw | `doc_id`(=content hash) | document | [`03`](./03-storage-and-data-model.md) |
| S3 | Parse/Normalize | `doc_id + parser_version` | document | [`04`](./04-ingestion-and-parsing.md) |
| S4 | Dedup | `doc_id + dedup_version` | document/cluster | [`04`](./04-ingestion-and-parsing.md) |
| S5 | Extract candidates | `doc_id + prompt_hash + model_id` | document | [`05`](./05-resolution-and-extraction.md) |
| S6 | Resolve (entity/claim) | `candidate_batch_id + ontology_version` | batch | [`05`](./05-resolution-and-extraction.md) |
| S7 | Graph mutation | `idempotency_key` (stage input 해시; mutation PK는 `mut-`) | event | [`06`](./06-graph-service.md) |
| S8 | Index | `doc_id/element_id + index_version` | element | [`08`](./08-search-and-graphrag.md) |
| S9 | Investigate | `inv_id + step_id` | step | [`07`](./07-llm-and-agents.md) |

> **재현성 계약:** 재현성은 stage 성격에 따라 두 수준으로 구분한다 (blueprint §21-2, §16 Phase 1 완료 조건; [`07`](./07-llm-and-agents.md) §13 정합).
> - **결정적 재현성 (code stage):** S1–S4와 S7 replay는 동일 입력 + 동일 version tuple → **byte-identical 출력**을 보장한다. graph mutation log의 재적용(S7 replay)은 결정적이므로 동일 로그 → 동일 materialized graph.
> - **버전 고정 + golden-regression 재현성 (LLM stage):** S5(extract)·S6(resolve)의 LLM 호출은 결정성을 보장하지 않는다(version-pinned ≠ deterministic). 대신 model_id·prompt_hash·ontology_version을 핀으로 고정하고, golden-regression 스위트([`10`](./10-evaluation-and-testing.md))로 회귀 허용치 내 동등성을 검증한다.
>
> 따라서 "동일 corpus + 동일 version tuple → 동일 graph"는 code 경로에 대해 엄밀히 성립하고, LLM 경로에 대해서는 version-pinned + golden-regression 범위 내에서 성립한다.

### 4.1 큐 실패 시맨틱 (Postgres SKIP-LOCKED)

초기 event stream은 Postgres 큐(`SELECT … FOR UPDATE SKIP LOCKED`)이다(§5, ADR-102). stage 실행 실패 시 다음 계약을 따른다.

| 항목 | 규약 |
| --- | --- |
| **Lease/visibility timeout** | worker가 row를 claim하면 `lease_until = now() + lease_ttl`을 설정한다. `lease_ttl` 경과(worker 크래시·행오버) 시 재가시화(re-visible)되어 다른 worker가 재claim한다. |
| **Retry limit** | 각 메시지는 `attempt_count`를 보유하며 실패 시 증가한다. `attempt_count < max_retries`이면 backoff(지수) 후 재큐잉한다. |
| **DLQ** | `attempt_count ≥ max_retries`이면 dead-letter 큐로 라우팅하고 원본에서 제거한다. DLQ 항목은 correlation_id로 추적되며 수동/배치 재처리 대상이다. |
| **Quarantine 라우팅** | 데이터 결함(파싱 불가·스키마 위반 등 재시도로 해소 불가한 실패)은 DLQ가 아니라 quarantine 상태로 라우팅한다([`06`](./06-graph-service.md)). transient 실패(네트워크·rate limit)만 retry/DLQ 경로를 탄다. |
| **Idempotency 관계** | 재시도·재가시화로 인한 중복 실행은 각 stage의 idempotency key(§4 표)로 흡수한다. 즉 at-least-once 배달 + idempotent 처리 = effectively-once 효과. lease 만료 후 재실행이 동일 output_ref를 재생성해도 부작용이 없어야 한다. |

`lease_ttl`·`max_retries`·backoff 파라미터의 구체값은 stage별 SLO에 맞춰 튜닝하며 실측 후 확정한다(placeholder). 확장 구성(Kafka)으로 승격 시 이 시맨틱은 consumer group + DLQ topic으로 이관된다.

## 5. 기술 스택 (초기 → 확장)

blueprint §7.2를 스펙으로 고정한다. **초기 구성이 기본값**이며 확장은 ADR로 승격한다.

| 용도 | 초기 (Prototype/MVP) | 확장 (Scale/Challenge) | 승격 트리거 |
| --- | --- | --- | --- |
| 원본·Lakehouse | MinIO + Parquet | S3 + Iceberg | 테이블 >수천만 row, 스키마 진화 필요 |
| Batch 처리 | Ray Data (단일 노드) | Ray Data / Spark (클러스터) | 재처리 시간 SLO 초과 |
| Event stream | PostgreSQL queue (SKIP LOCKED) | Kafka / Redpanda | 수집 throughput >Postgres 큐 한계 |
| 메타데이터 | PostgreSQL | PostgreSQL (read replica) | 조회 부하 증가 |
| Knowledge Graph | Neo4j Community | Neo4j/Memgraph (또는 검증된 대안) | 그래프 query p95 SLO 초과 |
| 전문·벡터 검색 | OpenSearch (단일) | OpenSearch cluster | 인덱스 크기·QPS 증가 |
| 분석·관측 | DuckDB(로컬 ad-hoc) / PostgreSQL + Grafana | ClickHouse + Grafana | 분석 쿼리 지연 |
| API | FastAPI | FastAPI + async workers | 동시 investigation 증가 |
| 배포 | Docker Compose | Kubernetes | 다중 노드 운영 필요 |
| LLM | 계층화 (규칙→소형→중급→고성능) | 동일 + batch inference | → [`07`](./07-llm-and-agents.md) |

**언어·런타임:** Python 3.12 (파이프라인·API·Agent), 저장 포맷 Parquet, 테이블 Iceberg(확장). AGENTS.md의 TDD/Tidy First를 개발 규율로 적용한다.

#### 5.1 ClickHouse 분석 승격 구현 메모 (Phase 4)

`analytics_promotion.py` 로 분석·관측 계층(§5 — 초기 DuckDB/PostgreSQL, 확장
ClickHouse)의 **승격 트리거 = 분석 쿼리 지연**을 봉인 (ClickHouse 미설치 — mock/실측
격리):

- `measure_analytics_latency` — 분석 쿼리 경로별 지연 분포 → p95 (executor 주입,
  미주입은 해시 시드 결정 에뮬레이션 — repeatability).
- `evaluate_analytics_promotion` — `ANALYTICS_SLO_MS=200ms` p95 **승격 트리거**:
  초과 시 `escalate_clickhouse=True` (Q4/Q6 게이트와 동일 성격, slo-gate·CI 비차단
  nightly 승격 평가). 미측정 → `not-measured` (honest-gap §6.2).
- `aggregate_metrics` — OLAP 집계 (ClickHouse 가 대체 승격하는 분석 부하의 실제
  형태), `correlation_id` 등으로 drill-down (11 §2.2).

실제 ClickHouse 승격 시 이 진입점의 지연 실측을 트리거 근거로 쓰고 ADR 로 확정한다.

#### 5.2 Collector adaptive scheduling 구현 메모 (Phase 5)

`signal_scheduler.py` 로 §3 Collector(Scouts)·04 §1 의 수집 예산(rate limit·freshness) 을
**신호 수율 기반으로 적응 배분** (10M Challenge 수집 병목 — 소스별 신호 밀도 편차
활용, `signal_source_runner` 메모리: arXiv 인용 대비 전용 반도체 언론 고신호):

- `signal_density`·`trailing_signal_density` — 신호 수율 = (claims+edges)/docs (문서 가중 누적).
- `allocate_signal_budget` — **floor(min_docs) 피보장**(§§4·5 freshness, 멸종 방지) + 잉여
  수율 비례 배분. 미측정은 잉여 제외/전 미측정은 균등(honest-gap §6.2).
- `freshness_lag` — §5 freshness 지연(lag·overdue), `cadence_priority` — 04 §1.1
  `schedule.priority` (density → high/normal/low).
- `adaptive_schedule` — 히스토리 → trailing 수율 → 배분 + priority·lag 부착 결정적 산출.

구체 계약·placeholder 는 04 §4 메모가 정본. 실제 수집 실행은 산출 배분을 호출자가
소비(read-only §3-3).

#### 5.3 hot/cold graph 분리 구현 메모 (Phase 5)

`graph_temperature.py` 로 §5 Knowledge Graph(초기 Neo4j Community, 확장
Neo4j/Memgraph·**물리 분리**) 의 **접근 온도 기반 계층 분리**를 봉인 (Q4 게이트 —
노드 ≥ 1e6 시 교체/분리 트리거, 06 ADR-603):

- `temperature`·`partition_tiers`·`tier_map` — 최근성 → hot/cold/unknown, unknown 은
  보수적 기본(cold) 할당 (미접근≠cold, honest-gap §6.2).
- `hot_resident_count` — hot 상주 예산.
- `cold_archive_decision` — Q4 노드 게이트 초과 시 cold 아카이브(ADR-603 물리 분리).
- `route_query` — hot 상주/cold 아카이브 라우팅 + 조회 SLO(slo-gate 비차단).
- `mark_accessed` — 승격 read-only(새 dict 반환), 실제 접근 기록·아카이브 이동은
  호출자 몫(§3-3).

구체 계약·placeholder 는 06 §9 메모가 정본.

## 6. 배포 토폴로지

### 6.1 초기 (Docker Compose, 단일 호스트)

```text
docker compose:
  minio          # raw + lakehouse object store
  postgres       # metadata + event queue + mutation log
  neo4j          # War Table (materialized graph)
  opensearch     # BM25 + vector
  api            # FastAPI
  worker         # Ray Data / stage runners (parse, dedup, extract, resolve)
  grafana        # 관측 대시보드
```

- `.env` / `.envrc`로 시크릿·엔드포인트 주입 (이미 리포에 존재). MCP는 `.mcp.json`.
- 단일 호스트에서 Prototype(1만)·MVP(10만) 규모를 목표로 한다.

### 6.2 확장 (Kubernetes)

- stateless(API, worker)와 stateful(store) 분리, worker는 stage별 HPA.
- object store는 S3, 테이블은 Iceberg 카탈로그(REST catalog).
- 승격은 blueprint §16 Phase 4 이후, 측정 근거와 함께 ADR로 결정한다.

#### 6.3 분산 batch 구현 메모 (Phase 4 DoD ①)

`distributed_batch.py` 로 분산 batch 계약 봉인 (Ray 미설치 환경 — mock/실측 격리):

- `shard(metas, k)` — 재결정·read-only 파티셔닝 (k-파라미터, 실제 Ray Data 백엔드
  진입점). k>len 은 클램프(빈 파티션 방지), round-robin 으로 밸런스(차 ≤ 1).
- `ParallelismBench` — 병렬 벽시계·speedup 측정 (executor mock 주입 — 실측 대비
  mock). **벤치 벽시계 모델**: 노드별 = `len(shard)×per_node_ms`, 병렬=`max`,
  순차(k=1)=`sum` → speedup=순차/병렬.
- `merge_results` — 노드별 파이프라인 결과 합산 (숫자 합산·list 접합).
- `throughput_docs_per_sec`·`compute_slo_gate` — MVP #9(10 §1.4) 계약 재사용,
  **DoD ① 처리 시간·비용 측정** 계약. SLO 임계 `PER_NODE_SLO_MS=60s` (slo-gate·
  CI 비차단, 10 §1.4).

실제 Ray Data(cluster)·Spark 로의 승격 시 §6.1 배포 토폴로지대로 worker에서 이
진입점을 실측 백엔드로 교체하고 speedup 을 프로파일로 재측정한다 (ADR 트리거).

## 7. 환경 분리

| 환경 | 목적 | 데이터 |
| --- | --- | --- |
| `local` | 개발·TDD | 샘플 수백~수천 문서 |
| `prototype` | 온톨로지·provenance 검증 | 1만 문서 |
| `staging` | end-to-end·회귀 | 골든 데이터셋 + 10만 서브셋 |
| `prod` | 조사 서비스 | 전체 corpus |

## 8. 의사결정 로그

| ID | 결정 | 근거 | 상태 |
| --- | --- | --- | --- |
| ADR-101 | 초기 구성을 기본값으로 고정, 확장은 트리거 기반 승격 | 과도한 인프라로 인한 개발 지연 위험(blueprint §18) 회피 | Accepted |
| ADR-102 | Event stream 초기값을 PostgreSQL 큐(SKIP LOCKED)로 | Kafka 도입 전 단순성 우선, 병목 측정 후 승격 | Accepted |
| ADR-103 | Agent는 그래프 read-only, mutation은 Lorekeepers→Graph Service 경로만 | 불변식 §3-3(event-driven) 강제 | Accepted |
| ADR-104 | Python 3.12 단일 언어 | 파이프라인·LLM 생태계 일관성 | Accepted |
| ADR-105 | 재현성을 2계층으로 정의: code stage(S1–S4, S7 replay)는 결정적, LLM stage(S5/S6)는 version-pinned + golden-regression | version-pinned LLM 호출은 byte-level 결정성을 보장하지 못함(doc07 §13, blueprint §21-2) | Accepted |
| ADR-106 | Postgres SKIP-LOCKED 큐에 lease/visibility timeout·retry limit·DLQ·quarantine 라우팅 시맨틱 명시, idempotency key로 effectively-once 보장 | transient 실패 복원력과 데이터 결함 격리를 분리(§4.1) | Accepted |
