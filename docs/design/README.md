# Orc Citadel — 상세 설계 (Design SSOT)

> 이 디렉터리는 [`docs/blueprint.md`](../blueprint.md)의 비전을 **구현 가능한 상세 설계**로 분해한 문서 집합이다.
> 프로젝트 진행 중 스키마·계약·의사결정의 **Single Source of Truth(SSOT)** 역할을 한다.
> 진행 내역은 [`docs/ROADMAP.md`](../ROADMAP.md)에서 관리한다.

- **Spec version:** `1.0.0` (Stable 확정 — 11개 문서 승격, 2026-08-12)
- **Ontology version 기준선:** `1.0.0` (→ [`02-ontology.md`](./02-ontology.md))
- **최종 갱신:** 2026-08-12

## 1. 문서 지도

| # | 문서 | 범위 | 상태 | Blueprint 매핑 |
| --- | --- | --- | --- | --- |
| — | [`README.md`](./README.md) | SSOT 인덱스·규약·용어 | Stable | §1.2 |
| 01 | [`01-architecture.md`](./01-architecture.md) | 시스템 아키텍처·컴포넌트·데이터 흐름·기술 스택·배포 토폴로지 | ✅ Stable | §7, §17 |
| 02 | [`02-ontology.md`](./02-ontology.md) | 노드/엣지 타입·속성·제약·온톨로지 버저닝·거버넌스 | ✅ Stable | §6 |
| 03 | [`03-storage-and-data-model.md`](./03-storage-and-data-model.md) | 저장 계층(raw/normalized/curated)·테이블 스키마·ID 체계·이벤트 로그·bitemporal·provenance | ✅ Stable | §6.4, §6.5, §7.1 |
| 04 | [`04-ingestion-and-parsing.md`](./04-ingestion-and-parsing.md) | Scouts/커넥터·fetch·중복 탐지·파싱·정규화 | ✅ Stable | §8.1–§8.3 |
| 05 | [`05-resolution-and-extraction.md`](./05-resolution-and-extraction.md) | Entity Resolution·Claim 추출·Canonicalization·Contradiction·Quarantine | ✅ Stable | §8.4–§8.9 |
| 06 | [`06-graph-service.md`](./06-graph-service.md) | 그래프 DB 스키마·mutation 이벤트·materialization·quarantine graph | ✅ Stable | §8.9, §17 |
| 07 | [`07-llm-and-agents.md`](./07-llm-and-agents.md) | 모델 계층화·라우팅·Agent 명세·조사 루프·prompt/version 관리 | ✅ Stable | §9 |
| 08 | [`08-search-and-graphrag.md`](./08-search-and-graphrag.md) | BM25·벡터·그래프 검색·retrieval 계획·context 구성 | ✅ Stable | §10 |
| 09 | [`09-api.md`](./09-api.md) | REST API 계약·인증·에러 모델·페이지네이션 | ✅ Stable | §5 |
| 10 | [`10-evaluation-and-testing.md`](./10-evaluation-and-testing.md) | 골든 데이터셋·평가 지표 정의·회귀·테스트 전략 | ✅ Stable | §12, §15 |
| 11 | [`11-observability-and-governance.md`](./11-observability-and-governance.md) | correlation ID·대시보드·SLO·안전·라이선스·retention | ✅ Stable | §11, §13, §14 |

관련 문서: [`../../DESIGN.md`](../../DESIGN.md) (Citadel Nightwatch 디자인 시스템), [`../mockups/war-table.html`](../mockups/war-table.html) (War Table 목업).

## 2. SSOT 규약

### 2.1 언어·표기

- 문서 본문은 **한국어 + 영문 기술 용어 병기**를 기본으로 한다 (blueprint/README와 동일 스타일).
- 세계관 명칭과 기술 개념은 §5 용어집에 따라 병기한다. **API·스키마·경로에는 기술 용어를 우선**한다 (예: UI `War Table` ↔ 경로 `/investigations/:id/graph`).
- 코드·스키마·식별자·JSON 예시는 코드 블록으로 표기한다.

### 2.2 식별자(ID) 체계

모든 엔터티는 `<prefix>-<body>` 형식의 문자열 ID를 가진다.

| 대상 | prefix | body 생성 규칙 | 예시 |
| --- | --- | --- | --- |
| Document (버전) | `doc` | `sha256(raw_bytes)[:24]` — **내용 기반 결정적** | `doc-9f2a...c1` |
| Source (발행 주체) | `src` | ULID | `src-01J9...` |
| Person | `per` | ULID | `per-01J9...` |
| Organization | `org` | ULID | `org-01J9...` |
| Product | `prd` | ULID | `prd-01J9...` |
| Technology | `tec` | ULID | `tec-01J9...` |
| Location | `loc` | ULID | `loc-01J9...` |
| Event | `evt` | ULID | `evt-01J9...` |
| Claim | `clm` | ULID | `clm-01J9...` |
| Canonical Claim | `ccl` | ULID | `ccl-01J9...` |
| Evidence | `evd` | ULID | `evd-01J9...` |
| Mention | `men` | ULID | `men-01J9...` |
| Assertion | `asr` | ULID | `asr-01J9...` |
| Investigation (Campaign) | `inv` | ULID | `inv-01J9...` |
| Dup Cluster (출처 계보) | `clus` | ULID | `clus-01J9...` |
| Mutation Event (graph) | `mut` | ULID | `mut-01J9...` |
| Extraction Record | `ext` | ULID | `ext-01J9...` |
| Resolution Decision | `res` | ULID | `res-01J9...` |

- **결정적 ID**(`doc`)는 idempotency의 근거다. 동일 raw bytes를 다시 수집하면 같은 `doc` ID가 생성되어 중복 mutation을 방지한다 (→ §8.1, 완료 조건 §16 Phase 0).
- **ULID**를 UUIDv4 대신 채택하는 이유: 시간 정렬 가능성(생성 순서 보존)으로 이벤트 로그·페이지네이션에 유리.
- ID는 불변이다. 엔터티 병합 시 `SAME_AS`/canonical 매핑으로 표현하고 ID를 재작성하지 않는다 (→ [`05`](./05-resolution-and-extraction.md), [`06`](./06-graph-service.md)).
- 위 표는 **영속 도메인·시스템 엔터티**를 다룬다. 운영·일시(transient) 식별자(비동기 job `job-`, correlation `corr-`, 조사 step `step-`, structured query `sq-`, alert `alt-`)는 각 하위 문서가 로컬로 정의한다.

### 2.3 버전 축(Version Axes)

추출·저장 결과에는 항상 다음 버전 튜플을 부착한다 (blueprint §9.5).

```json
{
  "ontology_version": "1.0.0",
  "schema_version": "0.1.0",
  "prompt_template_hash": "sha256:...",
  "model_id": "claude-sonnet-5",
  "extraction_code_version": "git:abcdef1",
  "inference_params": { "temperature": 0.0, "top_p": 1.0 }
}
```

- `ontology_version` — semver. Breaking change는 major, 하위호환 추가는 minor (→ [`02-ontology.md`](./02-ontology.md) §거버넌스).
- `schema_version` — 저장 테이블·이벤트 스키마 버전 (→ [`03`](./03-storage-and-data-model.md)). LLM structured output schema 버전은 이 축에 매핑되며 문서에 따라 `output_schema_version`으로 표기될 수 있다 (→ [`07`](./07-llm-and-agents.md) §6.1).
- `extraction_code_version` — 전처리·추출 코드 버전. [`03`](./03-storage-and-data-model.md) §8.2의 `preprocess_code_version`은 이 축의 저장 컬럼명이다(동일 의미).
- 모델·프롬프트 교체는 골든 데이터셋 회귀 후 단계 승격 (→ [`10`](./10-evaluation-and-testing.md)).

### 2.4 시간 표기

- 모든 timestamp는 **UTC ISO-8601** (`2025-02-15T09:00:00Z`).
- Bitemporal 두 축을 구분한다: `valid_time`(현실 유효 기간), `transaction_time`(시스템 관찰·저장 기간) — 정의·스키마는 [`03`](./03-storage-and-data-model.md) §6 (Bitemporal 모델) 참조.
- 부분/미상 구간은 `null` + `time_precision`(`year`/`quarter`/`month`/`day`/`unknown`)으로 표현한다 (허위 모순 방지, blueprint §18).

### 2.5 문서 상태 레전드

| 상태 | 의미 |
| --- | --- |
| **Draft** | 초안. 구조·핵심 결정 확정, 세부는 유동적. |
| **Review** | 리뷰 중. 구현 착수 전 확정 대기. |
| **Stable** | 확정. 변경 시 spec version 증가 + ROADMAP 기록. |

### 2.6 변경 관리

- 스키마·계약 변경은 반드시 (1) 해당 문서 수정 (2) `README.md`의 Spec version/갱신일 반영 (3) [`ROADMAP.md`](../ROADMAP.md) Changelog 기록의 3단계를 거친다.
- 결정 사항은 각 문서 하단 **의사결정 로그(ADR-lite)** 표에 근거와 함께 남긴다.

## 3. 설계 불변식 (Design Invariants)

Blueprint §17을 스펙 수준의 강제 규칙으로 승격한 것이다. 모든 하위 설계는 이를 위반할 수 없다.

1. **Graph는 SoT가 아니다.** immutable raw document + curated lakehouse table + append-only mutation log가 SoT이며, 그래프는 재구축 가능한 serving representation이다. (→ [`03`](./03-storage-and-data-model.md), [`06`](./06-graph-service.md))
2. **모든 authoritative graph element는 provenance를 가진다.** source span 없는 모델 생성 사실은 authoritative graph에 저장하지 않는다. (→ [`03`](./03-storage-and-data-model.md) §provenance)
3. **Event-driven mutation.** 엔터티 merge·claim 생성·supersession·삭제는 event로 저장하며 rollback/replay/audit 가능하다. (→ [`06`](./06-graph-service.md))
4. **Precision-first resolution.** 불확실한 병합은 하지 않고 `POSSIBLY_SAME_AS` 후보로 유지한다. (→ [`05`](./05-resolution-and-extraction.md))
5. **Evidence-first generation.** 검증된 subgraph를 먼저 확정하고 그 범위 안에서만 보고서 문장을 생성한다. (→ [`07`](./07-llm-and-agents.md))
6. **Idempotency.** 모든 작업은 idempotency key를 가지며 retry해도 동일 graph mutation을 중복 생성하지 않는다. (→ [`04`](./04-ingestion-and-parsing.md), [`11`](./11-observability-and-governance.md))
7. **Human review as data.** 사람의 교정은 원 모델 출력·수정 결과·이유를 함께 저장하는 학습/평가 데이터다. (→ [`05`](./05-resolution-and-extraction.md), [`10`](./10-evaluation-and-testing.md))

## 4. 초기 도메인 스코프

첫 버전 도메인은 **AI 반도체·데이터센터 공급망**이다 (blueprint §4). 온톨로지·골든 데이터셋·소스 커넥터는 이 도메인을 기준으로 구체화한다. 도메인 확장은 온톨로지 버전 migration으로 처리한다.

**초기 Scout 5종** (Phase 0 확정) — SEC EDGAR · arXiv · CHIPS/NIST · NVIDIA Newsroom · SemiEngineering. 구체 스키마·라이선스·접근·수집 제약은 [`04`](./04-ingestion-and-parsing.md) §1.4가 정본이다.

## 5. 용어집 (세계관 ↔ 기술)

| 세계관 | 기술 개념 | 정본 문서 |
| --- | --- | --- |
| Citadel | 전체 플랫폼 | [`01`](./01-architecture.md) |
| Scouts | Source connectors / collectors | [`04`](./04-ingestion-and-parsing.md) |
| Scout Reports | Raw documents | [`03`](./03-storage-and-data-model.md) |
| Watchtower | Ingestion monitor | [`04`](./04-ingestion-and-parsing.md), [`11`](./11-observability-and-governance.md) |
| Grand Archive | Data lakehouse | [`03`](./03-storage-and-data-model.md) |
| Hall of Witnesses | Evidence & provenance store | [`03`](./03-storage-and-data-model.md) |
| War Table | Temporal Evidence Knowledge Graph | [`06`](./06-graph-service.md) |
| Chronicle | Bitemporal event history | [`03`](./03-storage-and-data-model.md) |
| Lorekeepers | Resolution pipeline | [`05`](./05-resolution-and-extraction.md) |
| Seers | LLM reasoning agents | [`07`](./07-llm-and-agents.md) |
| Warchief's Council | Multi-agent investigation | [`07`](./07-llm-and-agents.md) |
| Signal Spire | Change alerts | [`11`](./11-observability-and-governance.md) |
| Campaign | Investigation | [`09`](./09-api.md) |
| Archivists | Parser | [`04`](./04-ingestion-and-parsing.md) |
| Citadel Gate | API Gateway | [`09`](./09-api.md) |
| Council Chamber | Investigation UI | [`07`](./07-llm-and-agents.md) / [`09`](./09-api.md) |
| Trail | Provenance chain | [`03`](./03-storage-and-data-model.md) |

## 6. 의사결정 로그 (인덱스 레벨)

| ID | 결정 | 근거 | 상태 |
| --- | --- | --- | --- |
| ADR-000 | 설계 SSOT를 `docs/design/`에 12개 문서로 분할, 백본(01–03)이 하위 스펙의 기준 | blueprint 전 영역을 구현 계약으로 분해하되 참조 일관성 확보 | Accepted |
| ADR-001 | ID는 `<prefix>-<ULID>`, Document만 내용 기반 sha256 | 시간 정렬 + document idempotency (§16 Phase 0 완료 조건) | Accepted |
| ADR-002 | 버전 5축(ontology/schema/prompt/model/extraction_code_version) 필수 부착 | 재현성·회귀 테스트 (blueprint §9.5) | Accepted |
