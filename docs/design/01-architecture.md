# 01 · 시스템 아키텍처 (Citadel)

> **상태:** Draft · **Spec:** 0.1.0 · **Blueprint 매핑:** §7, §17
> 상위 규약: [`README.md`](./README.md) · 관련: [`03-storage`](./03-storage-and-data-model.md), [`06-graph`](./06-graph-service.md)

전체 플랫폼(Citadel)의 컴포넌트 경계, 데이터 흐름, 기술 스택, 배포 토폴로지를 정의한다. 세부 스키마·계약은 각 하위 문서가 소유하며, 본 문서는 **컴포넌트 간 경계와 책임**을 확정한다.

## 1. 아키텍처 원칙

[`README.md`](./README.md) §3 설계 불변식을 아키텍처로 구체화한다.

1. **Lakehouse-as-SoT.** 그래프·검색 인덱스는 파생물이다. immutable raw + curated table + mutation log에서 전량 재구축 가능해야 한다.
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
| **Parser** | Archivists | 본문/메타 분리, 문단·문장 ID, offset 매핑 | raw → normalized doc | [`04`](./04-ingestion-and-parsing.md) |
| **Deduper** | — | exact/near/semantic 중복·출처 계보 판정 | normalized → dup cluster | [`04`](./04-ingestion-and-parsing.md) |
| **Extractor** | Evidence Extractor | entity mention·claim·evidence 후보 추출 | normalized → candidates + span | [`05`](./05-resolution-and-extraction.md) |
| **Lorekeepers** | Lorekeepers | Entity Resolution, Claim Canonicalization, Contradiction | candidates → resolved entities/claims | [`05`](./05-resolution-and-extraction.md) |
| **Graph Service** | War Table | mutation event 적용, materialized graph, quarantine | resolution decision → graph mutation | [`06`](./06-graph-service.md) |
| **Search Service** | — | BM25 + 벡터 인덱싱·질의 | curated + graph → index/query result | [`08`](./08-search-and-graphrag.md) |
| **Agent Runtime** | Warchief's Council | 조사 루프, 모델 라우팅, budget 관리 | question → report + evidence subgraph | [`07`](./07-llm-and-agents.md) |
| **API Gateway** | Citadel Gate | REST 계약, 인증, 페이지네이션 | client ↔ services | [`09`](./09-api.md) |
| **Chronicle** | Chronicle | bitemporal event history 조회 | mutation log → time-travel query | [`03`](./03-storage-and-data-model.md) |
| **Alerting** | Signal Spire | 결론·confidence 변화 알림 | graph change event → alert | [`11`](./11-observability-and-governance.md) |
| **Observability** | Watchtower | correlation, 대시보드, SLO | 전 stage 이벤트 → metrics | [`11`](./11-observability-and-governance.md) |

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

> **재현성 계약:** 동일 raw corpus + 동일 version tuple → 동일 materialized graph (blueprint §21-2, §16 Phase 1 완료 조건). 이를 위해 S3–S7은 결정적이거나(코드 stage), version-pinned LLM 호출이어야 한다.

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
| 분석·관측 | PostgreSQL + Grafana | ClickHouse + Grafana | 분석 쿼리 지연 |
| API | FastAPI | FastAPI + async workers | 동시 investigation 증가 |
| 배포 | Docker Compose | Kubernetes | 다중 노드 운영 필요 |
| LLM | 계층화 (규칙→소형→중급→고성능) | 동일 + batch inference | → [`07`](./07-llm-and-agents.md) |

**언어·런타임:** Python 3.12 (파이프라인·API·Agent), 저장 포맷 Parquet, 테이블 Iceberg(확장). AGENTS.md의 TDD/Tidy First를 개발 규율로 적용한다.

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
