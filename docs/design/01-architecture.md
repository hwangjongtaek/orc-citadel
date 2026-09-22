# 01 · 시스템 아키텍처 (Citadel)

> **상태:** ✅ Stable · **Spec:** 1.7.0 · **Blueprint 매핑:** §7, §17
> 상위 규약: [`README.md`](./README.md) · 관련: [`03-storage`](./03-storage-and-data-model.md), [`06-graph`](./06-graph-service.md)

전체 플랫폼(Citadel)의 컴포넌트 경계, 데이터 흐름, 기술 스택, 배포 토폴로지를 정의한다. 세부 스키마·계약은 각 하위 문서가 소유하며, 본 문서는 **컴포넌트 간 경계와 책임**을 확정한다.

## 1. 아키텍처 원칙

[`README.md`](./README.md) §3 설계 불변식을 아키텍처로 구체화한다.

1. **Lakehouse+Log-as-SoT.** 그래프·검색 인덱스는 파생물이다. SoT는 immutable raw + curated table + mutation log **세 요소**로 구성되며, 이 셋에서 전량 재구축 가능해야 한다.
2. **측정 기반 승격.** 2026-09-22 Q6/Q7 측정 게이트를 통과해 단일 호스트 Docker Compose의 normalized/curated는 **Lakekeeper REST catalog + Apache Iceberg**, 수집·승격 event stream은 **Redpanda Community Edition**으로 승격했다. Kubernetes·ClickHouse 등 나머지 확장은 각자의 측정된 병목이 정당화할 때만 도입한다 (ADR-107, [`03`](./03-storage-and-data-model.md) ADR-309).
3. **Stage 격리 + 공통 correlation.** 각 파이프라인 stage는 독립 배포·재실행 가능하며, 공통 correlation ID로 end-to-end 추적된다 (→ [`11`](./11-observability-and-governance.md)).
4. **Idempotent stage.** 모든 stage는 idempotency key로 재실행 안전성을 보장한다.

## 2. 논리 컴포넌트 맵

```text
                    ┌─────────────────────────────────────────────────┐
 Outside World      │                    CITADEL                      │
 (Sources)          │                                                 │
   │                │  ┌─────────┐   acked S1/S2 refs   ┌──────────┐ │
   ├─ APIs / RSS ──►│  │ Scouts  │─────────────────────►│ Redpanda │ │
   ├─ Filings ─────►│  │connectors│                     │ S1–S7    │ │
   ├─ News ────────►│  └────┬────┘                     └────┬─────┘ │
   └─ Research ────►│       │ durable raw shard              │       │
                    │       ▼                                ▼       │
                    │  ┌──────────────────────────┐  ┌─────────────┐ │
                    │  │ Grand Archive            │◄─│ Processing  │ │
                    │  │ raw zstd Parquet         │  │ parse/dedup/│ │
                    │  │ normalized/curated       │  │ extract/    │ │
                    │  │ Iceberg + Lakekeeper     │  │ resolve     │ │
                    │  └────────────┬─────────────┘  └──────┬──────┘ │
                    │               │                       ▼        │
                    │               │                ┌─────────────┐ │
                    │               │                │ Lorekeepers │ │
                    │               │                │ resolution  │ │
                    │               │                └──────┬──────┘ │
                    │            ┌──┴───────────────────────┼──────┐ │
                    │            ▼                          ▼      ▼ │
                    │      ┌──────────┐  ┌─────────────┐ ┌────────┐│
                    │      │ War Table│  │Search/Vector│ │Quaran- ││
                    │      │ (Graph)  │  │ Index (OS)  │ │tine    ││
                    │      └────┬─────┘  └──────┬──────┘ └────────┘│
                    │           │               │                  │
                    │           ▼               ▼                  │
                    │      ┌────────────────────────────┐          │
                    │      │ Warchief's Council (Agents) │          │
                    │      └──────────────┬─────────────┘          │
                    │                     ▼                        │
                    │   ┌─────────────────────────────────────┐    │
                    │   │ API (FastAPI) → Report / Explorer UI │    │
                    │   │ Chronicle · Signal Spire            │    │
                    │   └─────────────────────────────────────┘    │
                    └─────────────────────────────────────────────────┘
```

## 3. 컴포넌트 책임 (Bounded Context)

| 컴포넌트 | 세계관 | 책임 | 입력 → 출력 | 정본 문서 |
| --- | --- | --- | --- | --- |
| **Collector** | Scouts | 허용된 소스에서 문서 수집, 변경 탐지, rate limit | source config → raw document + fetch metadata | [`04`](./04-ingestion-and-parsing.md) |
| **Archive** | Grand Archive | raw source-shard와 normalized/curated Iceberg 저장, Lakekeeper catalog 관리 | 각 stage 산출물 → zstd Parquet raw / Iceberg table | [`03`](./03-storage-and-data-model.md) |
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

**S1–S7 event boundary.** 각 stage에는
`orc.events.s{1..7}.<stage-slug>.v1` primary와 동일 이름의 `.retry`,
`.dlq`, `.quarantine` 토픽을 선언한다(7 stage × 4 route = 28개). envelope는
`event_version/event_id/stage/event_type/status/input_ref/output_ref/idempotency_key/
correlation_id/attempt_count/occurred_at/payload`만 갖는 **reference-only JSON**이며
raw bytes나 table row를 운반하지 않는다. producer는 Redpanda의 broker acknowledgement가
성공해야 반환한다.

> **재현성 계약:** 재현성은 stage 성격에 따라 두 수준으로 구분한다 (blueprint §21-2, §16 Phase 1 완료 조건; [`07`](./07-llm-and-agents.md) §13 정합).
> - **결정적 재현성 (code stage):** S1–S4와 S7 replay는 동일 입력 + 동일 version tuple → **byte-identical 출력**을 보장한다. graph mutation log의 재적용(S7 replay)은 결정적이므로 동일 로그 → 동일 materialized graph.
> - **버전 고정 + golden-regression 재현성 (LLM stage):** S5(extract)·S6(resolve)의 LLM 호출은 결정성을 보장하지 않는다(version-pinned ≠ deterministic). 대신 model_id·prompt_hash·ontology_version을 핀으로 고정하고, golden-regression 스위트([`10`](./10-evaluation-and-testing.md))로 회귀 허용치 내 동등성을 검증한다.
>
> 따라서 "동일 corpus + 동일 version tuple → 동일 graph"는 code 경로에 대해 엄밀히 성립하고, LLM 경로에 대해서는 version-pinned + golden-regression 범위 내에서 성립한다.

### 4.1 Redpanda 전달·실패 시맨틱

수집·승격 event stream의 현행 구현은 단일 호스트 **Redpanda CE**다(ADR-107).
모든 S1 connector는 raw shard가 durable해진 직후 local SQLite outbox가 raw metadata를
reconcile하고, `document_fetched`와 `raw_stored` reference envelope를
`acks=all`·idempotent producer로 발행한다. broker acknowledgement 뒤에만 stage ack를
기록하므로 raw commit 뒤 process/broker 실패도 다음 dispatch에서 복구된다.
`ResultCapReached`는 `S1/result_cap_reached`, `status=terminal` 이벤트로 명시해 결과
상한을 성공처럼 조용히 끊지 않는다.

| 항목 | 규약 |
| --- | --- |
| **Consumer group** | S2 primary+retry는 안정 group `orc-citadel-s2-promotion-v1`이 최대 1,000건 bounded batch로 소비한다. 파티션이 병렬성 경계다. |
| **Reference-only 승격** | 검증된 `raw://<source_id>/doc-<24hex>`의 정확한 `(source_id, doc_id)` row만 `promote_raw_refs` 입력으로 허용하고 source는 path-safe slug로 제한한다. 같은 content가 여러 source에 있을 때 normalized의 단일 `source_id/url`은 `(source_id, url)` 사전순 최소 raw provenance로 결정해 delivery order에 따라 뒤집히지 않는다. 중복 reference는 idempotent replay해 normalized→curated 사이 부분 실패를 복구하며, 이미 완료된 논리 결과는 zero summary를 반환하고 row 수를 늘리지 않는다. |
| **Durability와 offset** | `enable.auto.commit=false`, `enable.auto.offset.store=false`. normalized/curated Iceberg durable write와 필요한 outbound broker acknowledgement가 모두 끝난 뒤에만 offset을 수동 commit한다. S3 `normalization_completed`도 durable Iceberg write 뒤 acked publish한다. |
| **Retry / DLQ** | unexpected/transient 실패는 `attempt_count`를 먼저 증가시킨다. 증가값이 `< max_retries`면 S2 retry, `>= max_retries`면 S2 DLQ다. retry/DLQ publish acknowledgement 전에는 입력 offset을 commit하지 않는다. |
| **Quarantine** | invalid envelope/reference와 재시도로 해소할 수 없는 데이터 결함은 S2 quarantine으로 보낸다. inbound envelope는 1 MiB·JSON depth 32 상한을 먼저 적용해 poison record도 작은 quarantine event로 바꾼 뒤 commit한다. quarantine은 DLQ가 아니며, 해당 publish acknowledgement 전에는 offset을 commit하지 않는다. |
| **Effectively-once 효과** | Redpanda는 at-least-once이고 stage writes는 idempotent다. 재배달은 같은 `doc_id`/version key를 replay하므로 부분 커밋을 복구하면서 durable logical row를 중복 생성하지 않는다. |

실제 Redpanda smoke에서 S2 원본 1건과 동일 duplicate 1건을 소비한 뒤
`mentions=1`, `dup_signatures=1`, `counts_stable=true`를 확인했다. 이는 reference
재배달이 durable Iceberg row를 늘리지 않는 effectively-once 효과의 실행 증거다.

조사 job의 PostgreSQL `FOR UPDATE SKIP LOCKED` claim/lease queue는 이 event stream과
별개이며 그대로 유지한다([`03`](./03-storage-and-data-model.md) §4.4). 수집·승격에는
Redpanda 도입 전 PostgreSQL queue가 존재한 적이 없다(ADR-102 정정).

## 5. 기술 스택 (현행 → 조건부 확장)

blueprint §7.2의 단계 도입 원칙을 유지하되 Q6/Q7 승격 완료 상태를 현행으로 고정한다.

| 용도 | 현행 (단일 호스트 Compose) | 조건부 확장 | 다음 승격 트리거 |
| --- | --- | --- | --- |
| Raw / Lakehouse | raw source-sharded zstd Parquet(prod shared filesystem, MinIO 대체 backend 동일 레이아웃) + normalized/curated Apache Iceberg + Lakekeeper REST catalog | S3 호환 object store·catalog HA | object-store/catalog 가용성 SLO 또는 다중 호스트 필요 |
| Batch 처리 | Ray Data 진입점 + bounded local workers | Ray Data / Spark cluster | 재처리 시간 SLO 초과 |
| Event stream | Redpanda CE, S1–S7 primary/retry/DLQ/quarantine | Redpanda cluster 또는 Kafka 호환 cluster | 단일 broker 가용성·throughput SLO 초과 |
| 운영 메타데이터 | PostgreSQL; investigation 전용 SKIP LOCKED queue 포함 | PostgreSQL read replica | 조회 부하 증가 |
| Knowledge Graph | Neo4j Community | Neo4j/Memgraph(검증된 대안) | graph query p95 SLO 초과 |
| 전문·벡터 검색 | OpenSearch(single) | OpenSearch cluster | 인덱스 크기·QPS 증가 |
| 분석·관측 | DuckDB(local ad-hoc) / PostgreSQL + Grafana | ClickHouse + Grafana | 분석 쿼리 지연 |
| API | FastAPI | FastAPI + async workers | 동시 investigation 증가 |
| 배포 | Docker Compose | Kubernetes | 다중 노드 운영 필요 |
| LLM | 계층화(규칙→소형→중급→고성능) | 동일 + batch inference | → [`07`](./07-llm-and-agents.md) |

**언어·런타임:** Python 3.12(파이프라인·API·Agent), PyIceberg table writes,
Parquet raw shards, Kafka-compatible Redpanda client. AGENTS.md의 TDD/Tidy First를
개발 규율로 적용한다.

#### 5.1 ClickHouse 분석 승격 구현 메모 (Phase 4)

`analytics_promotion.py` 로 분석·관측 계층(§5 — 초기 DuckDB/PostgreSQL, 확장
ClickHouse)의 **승격 트리거 = 분석 쿼리 지연**을 봉인 (ClickHouse 미설치 — mock/실측
격리):

- `measure_analytics_latency` — 분석 쿼리 경로별 지연 분포 → p95 (executor 주입,
  미주입은 해시 시드 결정 에뮬레이션 — repeatability).
- `evaluate_analytics_promotion` — `ANALYTICS_SLO_MS=200ms` p95 **승격 트리거**:
  초과 시 `escalate_clickhouse=True` (측정 기반 승격 gate와 동일 성격, slo-gate·CI 비차단
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

### 6.1 현행 (Docker Compose, 원격 단일 호스트)

2026-09-22 prod overlay는 **13개 Compose service**를 선언한다. 그중
`redpanda-init`은 S1–S7의 28개 topic을 멱등 생성하고 종료하는 one-shot bootstrap이며,
나머지는 장기 실행 서비스다.

```text
docker compose:
  postgres             # metadata + mutation log + investigation-only queue
  redpanda              # S1–S7 event stream
  redpanda-init         # primary/retry/DLQ/quarantine topic bootstrap (one-shot)
  minio                 # Iceberg warehouse object store (raw 대체 backend는 미배치)
  lakekeeper            # Iceberg REST catalog
  neo4j                 # War Table materialized graph
  opensearch            # BM25 + vector
  grafana               # observability
  duckdb-ui             # ad-hoc/read-only operational view
  prototype             # viewer/API
  investigation-worker  # PostgreSQL investigation jobs
  scheduler             # collection dispatch + metrics only
  promotion-consumer    # always-on S2 primary/retry → Iceberg promotion
```

`promotion-consumer`는 MinIO·Lakekeeper health와 topic bootstrap 완료 뒤 시작한다.
host client용 external advertised listener는 **`127.0.0.1:19092`**로 고정한다.
`localhost`는 macOS에서 IPv6 `::1`로 resolve되어 IPv4 listener에 닿지 않을 수 있으므로
사용하지 않는다.
nightly `scheduler`는 collection dispatch와 metrics만 소유하며 **직접 promotion,
zone rebuild, snapshot을 호출하지 않는다**. 수집이 durable raw reference를 publish하고,
promotion-consumer가 그 reference만 Iceberg로 승격한다.

배포 통로는 SSH rsync(`scripts/deploy.sh`), 절차 정본은 운영 runbook
(`docs/operating/deployment.md`)이다. 새 원격 prod 데이터는 빈 상태에서 신규
수집분만 누적한다(기존 원격 volume 및 로컬 corpus 이관 없음). `.env`/`.envrc`로
시크릿·endpoint를 주입하며 MCP 설정은 `.mcp.json`이다.

### 6.2 로컬 개발·폴백

로컬도 raw source-sharded zstd Parquet와 PyIceberg를 사용한다. local catalog는
persistent SQLite catalog + file warehouse를 쓸 수 있지만 table format과 zone API는
prod Lakekeeper 경로와 같다. APScheduler/launchd 폴백도 collection dispatch와
metrics만 담당하고 promotion은 consumer 경계를 우회하지 않는다.

- `misfire_grace_seconds=86400`은 깨어난 뒤 당일 collection/metrics dispatch만
  보충한다. 슬립·다운 중 실행을 보장하지 않으며 이틀 이상 결측은 남는다.
- 활성 scheduler는 한 개다. 복제·다중 호스트는 §6.3의 별도 승격 지점이다.
- 데이터는 `data/`에 두며 gitignore한다. 운영 설치·기동·점검·백업·복원의 정본은
  `docs/operating/`이다.

### 6.3 확장 (Kubernetes)

- stateless(API, worker)와 stateful(store)를 분리하고 worker는 stage별 HPA를 둔다.
- object store, Lakekeeper/Iceberg, Redpanda를 HA 구성으로 승격한다.
- 단일 호스트의 가용성·throughput SLO가 다중 노드를 정당화할 때 별도 ADR로 결정한다.

#### 6.4 분산 batch 구현 메모 (Phase 4 DoD ①)

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
| `prod` | **원격 단일 호스트 Compose 상시 운용** (§6.1) — Redpanda event stream·Lakekeeper/Iceberg·지속 수집·승격·SLO·조사 | 빈 상태에서 신규 수집분만 누적 (원격 `10.0.0.11`, 기존 원격·로컬 corpus 이관 없음) |

## 8. 의사결정 로그

| ID | 결정 | 근거 | 상태 |
| --- | --- | --- | --- |
| ADR-101 | 초기 구성을 기본값으로 고정하고 확장은 측정 트리거로 승격 | 과도한 인프라로 인한 개발 지연 위험(blueprint §18) 회피. Q6/Q7은 2026-09-22 측정 근거로 승격 완료 | Accepted |
| ADR-102 | PostgreSQL `FOR UPDATE SKIP LOCKED` queue는 **durable investigation job 경로에만** 유지한다. 수집·승격 event stream의 초기값이었다는 기존 서술을 철회한다 | 구현 확인 결과 수집·승격은 Redpanda 도입 전 scheduler 직접 호출이었고 PostgreSQL queue를 사용하지 않았다. 조사 claim/lease/audit 계약은 별도이며 변경하지 않는다 | Accepted · Corrected 2026-09-22 |
| ADR-103 | Agent는 그래프 read-only, mutation은 Lorekeepers→Graph Service 경로만 | 불변식 §3-3(event-driven) 강제 | Accepted |
| ADR-104 | Python 3.12 단일 언어 | 파이프라인·LLM 생태계 일관성 | Accepted |
| ADR-105 | 재현성을 2계층으로 정의: code stage(S1–S4, S7 replay)는 결정적, LLM stage(S5/S6)는 version-pinned + golden-regression | version-pinned LLM 호출은 byte-level 결정성을 보장하지 못함(doc07 §13, blueprint §21-2) | Accepted |
| ADR-106 | PostgreSQL investigation queue에 lease/visibility timeout·retry limit·late-completion 거부를 적용한다 | durable investigation worker의 경쟁 claim·고아 재claim·감사 추적을 보존. 수집 event stream 계약이 아님 | Accepted · Scope corrected 2026-09-22 |
| ADR-107 | 수집·승격 event stream으로 **Redpanda CE**를 채택하고 S1–S7 각각 primary/retry/DLQ/quarantine topic, acked reference-only envelope, manual offset-after-durability 계약을 적용한다 | 단일 호스트에서 Kafka API 호환성을 유지하면서 JVM/ZooKeeper 운영 부담을 피하고, 수집과 Iceberg promotion을 분리한다. D3 확정 및 K1–K5 완료 | Accepted · Implemented 2026-09-22 |
