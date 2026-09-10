# 03 · 저장 계층·데이터 모델 (Grand Archive · Chronicle · Hall of Witnesses)

> **상태:** ✅ Stable · **Spec:** 1.2.0 · **Blueprint 매핑:** §6.4, §6.5, §7.1, §17
> 상위 규약: [`README.md`](./README.md) · 관련: [`02-ontology`](./02-ontology.md), [`06-graph`](./06-graph-service.md)

Lakehouse 저장 계층(raw/normalized/curated), 테이블 스키마, ID 체계 적용, **append-only mutation log**, **bitemporal 모델**, **provenance chain**을 확정한다. 본 계층이 시스템의 **Source of Truth**이며 그래프·검색 인덱스는 여기서 재구축된다 (불변식 §3-1).

## 1. 저장 계층 개요 (3-zone Lakehouse)

blueprint §7.1의 3 zone을 테이블 계약으로 확정한다.

```text
raw zone        immutable object store (수정 금지, 모든 버전 보존)
   │  parse/normalize
normalized zone 구조화된 문서 (문단·문장·offset·언어)
   │  extract/resolve
curated zone    entity mention · claim/evidence · canonical mapping · dedup cluster
   │  materialize
[serving]       War Table (graph) · Search/Vector index  ← 재구축 가능한 파생물
```

| Zone | 포맷 | 저장소(초기) | 변경성 | 소유 stage |
| --- | --- | --- | --- | --- |
| raw | 원본 bytes + JSON metadata | MinIO(object) | **immutable, append-only** | S2 |
| normalized | Parquet | MinIO + 카탈로그 | 재생성 가능(parser_version) | S3 |
| curated | Parquet(→Iceberg) | MinIO + 카탈로그 | 재생성 가능 | S5–S6 |
| mutation log | Postgres(→Iceberg) | PostgreSQL | **append-only** | S7 |

- **초기 로컬 분석**은 MinIO 위 Parquet를 **DuckDB**로 직접 질의한다(별도 엔진 불필요, blueprint §7.1). Scale 단계에서 Iceberg 카탈로그로 승격한다(§9).

### 1.1 파티셔닝·클러스터링 스킴

Parquet(→Iceberg) 파티션 키는 재처리·시간 질의·삭제 전파를 고려해 다음으로 확정한다.

| 테이블 | 파티션 키 | 클러스터링/정렬 |
| --- | --- | --- |
| `documents` / `segments` | `source_id`, `publication_time`(월 버킷) | `doc_id` |
| `mentions` / `claim_candidates` / `evidence_candidates` | `dedup_version`, `status` | `doc_id` |
| `assertions` | `tx_from`(월 버킷) | `subject_id`, `predicate` |
| `graph_mutations` | `tx_time`(일 버킷) | `mutation_id` |

- 파티션 키는 재생성 버전 축(`parser_version`/`dedup_version`)과 정렬해 **전체 재처리 시 파티션 단위 교체**가 가능하도록 한다.
- 삭제 전파(§8.4)는 `source_id`/`doc_id` 프루닝으로 대상 파티션을 좁힌다.

## 2. Raw Zone

### 2.1 객체 레이아웃

```text
raw/
  source_id=<src-…>/
    doc_id=<doc-…>/           # doc_id = sha256(raw_bytes)[:24]
      content.bin             # 원본 bytes (수정 금지)
      fetch.json              # 수집 메타데이터
```

### 2.2 `fetch.json` 스키마

```json
{
  "doc_id": "doc-9f2a...c1",
  "source_id": "src-01J9...",
  "url": "https://...",
  "content_hash": "sha256:...",
  "fetched_at": "2025-02-15T09:00:00Z",
  "http_status": 200,
  "response_headers": { "content-type": "text/html", "last-modified": "..." },
  "license": "cc-by / proprietary / gov-public",
  "robots_allowed": true,
  "fetch_correlation_id": "..."
}
```

- **불변식:** 동일 `url`의 변경된 버전은 **새 `doc_id`로 모두 보존**한다 (덮어쓰기 금지, blueprint §7.1, §8.1).
- `doc_id`가 내용 기반이므로 동일 bytes 재수집은 동일 객체 → idempotent (S2, 불변식 §3-6).
- 라이선스·robots는 [`11`](./11-observability-and-governance.md) governance가 강제한다.

## 3. Normalized Zone

### 3.1 `documents` 테이블

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `doc_id` | string(PK) | 내용 기반 ID |
| `source_id` | string | → Source |
| `url` | string | |
| `title` | string | |
| `authors` | string[] | |
| `language` | string | 감지 언어 |
| `publication_time` | timestamp | 공개 시각 |
| `revision_time` | timestamp | 수정 시각 |
| `parser_version` | string | 재현성 |
| `char_len` | int | |

### 3.2 `segments` 테이블 (문단·문장)

안정적 문단·문장 ID와 원문 offset 매핑을 보존한다 (blueprint §8.2, provenance 근간).

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `segment_id` | string(PK) | `<doc_id>#p<par>.s<sent>` — **결정적** |
| `doc_id` | string | |
| `kind` | enum | `paragraph`/`sentence`/`table_cell`/`footnote`/`list_item` |
| `text` | string | 정규화 텍스트 |
| `char_start` | int | **원문(raw)** 기준 offset |
| `char_end` | int | |
| `norm_char_start` | int | 정규화 텍스트 기준 시작 offset |
| `norm_char_end` | int | 정규화 텍스트 기준 끝 offset (원문↔정규화 양방향 매핑용, ADR-302) |
| `order` | int | 문서 내 순서 |

- `segment_id`는 결정적이라 재파싱 시 안정적으로 유지된다 (offset mapping unit test 대상, → [`10`](./10-evaluation-and-testing.md)).
- **원문 offset ↔ 정규화 offset 매핑**을 함께 저장해 provenance 왕복을 보장한다 (blueprint §8.2).

## 4. Curated Zone

추출·해소 산출물. 각 row는 version tuple을 부착한다.

### 4.1 `mentions`

| 컬럼 | 설명 |
| --- | --- |
| `mention_id` | `men-<ULID>` ([`README`](./README.md) §2.2) |
| `doc_id` / `segment_id` | 출처 위치 |
| `surface_text` | 표면형 |
| `mention_type` | Person/Org/Product/... |
| `char_start`/`char_end` | span — **원문(raw)** 기준 offset (§3.2와 동일 축) |
| `resolved_entity_id` | 해소 결과(nullable, → [`05`](./05-resolution-and-extraction.md)) |
| `extraction_version` | 버전 tuple |

### 4.2 `claim_candidates` / `evidence_candidates`

[`02`](./02-ontology.md) §2.4의 Claim/Evidence 속성을 그대로 저장하되 `status`(`candidate`/`promoted`/`quarantined`)를 추가한다. graph 반영 전 curated에 머문다.

- **Claim-of-record.** 별도 `claims` 테이블을 두지 않고 `claim_candidates`에서 `status=promoted`인 row가 **claim-of-record**(정본 Claim)이다. §6.2 `assertions.claim_id` FK는 이 promoted row(`claim_id = claim_candidate_id`)를 참조한다 (ADR-306). `candidate`/`quarantined` row는 authoritative graph의 참조 대상이 될 수 없다.
- **Claim→Assertion emission 계약.** Claim이 `promoted`로 전이될 때 정규 삼항(subject/predicate/object)과 valid time을 갖는 `Assertion`을 1건 이상 materialize한다. emission은 §7 `graph_mutations` 이벤트(`op=create_node`/`supersede`)를 통해서만 발생하며, 동일 `idempotency_key` 재실행 시 중복 발행하지 않는다 ([`02`](./02-ontology.md) §2.4 Claim→Assertion materialization 규칙과 정합).

### 4.3 `dup_clusters` (출처 계보)

blueprint §8.3. 복제 기사를 하나의 근원으로 축소한다.

| 컬럼 | 설명 |
| --- | --- |
| `cluster_id` | `clus-<ULID>` |
| `root_doc_id` | 근원 문서 |
| `member_doc_ids[]` | 파생 문서 |
| `independent_addition_doc_ids[]` | 독립적 추가 정보 보유 문서 |
| `dedup_method` | `content_hash`/`minhash`/`embedding`/`llm` |

- **독립 증거 수 계산의 근거.** 500개 복제 기사는 1개 근원 + N개 독립 추가로 카운트한다 (blueprint §8.3, §11).

### 4.4 Durable investigation 운영 메타데이터

기존 curated evidence를 대상으로 한 비동기 조사는 PostgreSQL의 `investigations`·`jobs`·`steps`에만 기록한다. `investigations`는 question, subject_id, scope, mode, owner, version tuple, correlation_id, status, coverage, termination, report JSONB, audit_trace JSONB와 UTC timestamps를 가진다. `jobs`는 단일 investigation에 1:1로 연결되고 `queued|running|succeeded|failed|cancelled`, `cancel_requested`, worker lease/claim token, error JSONB를 가진다. `steps`는 `(investigation_id, step_id)` unique의 append-only `PLAN|RUN|SYNTHESIZE|AUDIT` 기록이다.

- 동일 `Idempotency-Key`는 최초 `inv-`/`job-`을 반환하고 행을 늘리지 않는다.
- claim은 `FOR UPDATE SKIP LOCKED`와 lease token으로 원자화한다. 만료된 `running`만 재claim하며 이전 claim token의 완료는 거부한다.
- report·audit_trace는 완료와 함께 영속해 재시작 뒤에도 동일하게 조회한다.
- 이 운영 write는 graph mutation·curated write가 아니며, 조사 전후 두 zone의 상태는 불변이다.

## 5. ID·Idempotency 요약

[`README`](./README.md) §2.2를 저장 계층에 적용한 규칙.

| 대상 | 결정성 | idempotency 근거 |
| --- | --- | --- |
| `doc_id` | 내용 기반 sha256 | 동일 bytes → 동일 ID |
| `segment_id` | 위치 기반 | 재파싱 안정성 |
| 추출/해소 ID | ULID | idempotency key는 별도 (stage input hash) |
| `mut-` 이벤트 | ULID + idempotency_key 컬럼 | 재실행 시 중복 mutation 차단 (§7) |

## 6. Bitemporal 모델 (Chronicle)

blueprint §6.4를 스키마로 확정한다. 두 시간 축을 모든 `Assertion`/`Claim`에 보존한다.

### 6.1 두 시간 축

| 축 | 의미 | 컬럼 |
| --- | --- | --- |
| **valid time** | 현실에서 사실·주장이 유효한 기간 | `valid_from`, `valid_to`, `time_precision` |
| **transaction time** | 시스템이 관찰·저장/무효화한 기간 | `tx_from`, `tx_to` |

- `tx_to = null` → 현재도 시스템이 믿는 버전. 새 버전 추가 시 이전 버전의 `tx_to`를 close (덮어쓰기 금지).
- 이로써 다음 질문에 답한다 (blueprint §6.4): "2025-03 실제 CEO?"(valid time) vs "2025-03에 시스템이 안 CEO?"(transaction time) vs "정정 자료가 과거 결론을 어떻게 바꿨나?"(supersession).

### 6.2 `assertions` 테이블 (bitemporal, system-versioned projection)

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `assertion_id` | string(PK) | `asr-<ULID>` |
| `claim_id` | string | → Claim (§4.2 promoted claim-of-record) |
| `subject_id`/`predicate`/`object_id` | string | 정규 삼항 |
| `valid_from`/`valid_to` | timestamp(nullable) | valid time (열린 하한/상한 = `null`) |
| `time_precision` | enum | `year`/`quarter`/`month`/`day`/`unknown` ([`README`](./README.md) §2.4) |
| `tx_from`/`tx_to` | timestamp | transaction time (`tx_to` nullable) |
| `supersedes_id` | string(nullable) | 대체 대상 assertion |
| `superseded_reason` | string | 변경 원인 |
| `mutation_id` | string | 생성 이벤트(→§7 `graph_mutations.mutation_id`) |
| `provenance_ref` | string[] | → §8 |
| `ontology_version` | semver | 저장 element 필수 (02 §2). 추출 단계 `ClaimCandidate.ontology_version`이 materialize 시 승격되어 authoritative claim 의 version 을 보존 (MVP #3). 5축 `version_tuple`(§7.1, mutation 축)과 별개 — assertion 축의 온톨로지 버전 단축 표기. |

- **Append-only SoT는 `assertions`가 아니라 `graph_mutations`이다** (§7, 불변식 §3-3). `assertions`는 mutation log에서 재구축 가능한 **system-versioned projection**이며, 유일하게 허용되는 in-place write는 supersession 시 **직전 버전의 `tx_to`를 close**하는 것뿐이다(그 외 컬럼 수정·row 물리 삭제 금지). 이 close 역시 `supersede` mutation 이벤트 적용의 결과로만 발생한다 (ADR-303, ADR-307).

### 6.3 시간 질의 계약

- **AS-OF valid time `T_v`:** `valid_from ≤ T_v < valid_to`.
- **AS-OF transaction time `T_t`:** `tx_from ≤ T_t < (tx_to ?? ∞)`.
- 두 축 동시 질의로 "특정 관찰 시점 기준, 특정 유효 시점의 상태"를 재현한다.
- 시간 슬라이더 UI는 노드를 삭제하지 않고 valid/transaction 상태 변화를 구분 표시한다 (DESIGN.md, blueprint §6.4).
- **구현(P1 time-travel)**: assertion 축은 `CuratedZone.assertions_as_of`(§6.2 AS-OF 양축 필터, S25)·catalog 의 `as_of_tx/valid`(09 §2.2). **그래프(노드/엣지) 축은 `replay_graph_at_tx`(graph_replay, ADR-604)** — `graph_mutations` 로그를 관측 시점 `tx_time ≤ T_t` 까지 잘라 재생해 "그 시점 시스템이 믿던 그래프"를 재구축(§7.2 — superseded/delete 도 로그에 남으므로 과거 상태 그대로 조회). 두 축 병행 시 "특정 관측 시점×특정 유효 시점" 재현 계약 완결.

## 7. Mutation Log (Append-only Event Store)

불변식 §3-3. 그래프 변경은 event로만 발생하며 event log에서 materialized graph를 재구축할 수 있다 (blueprint §8.9, §17).

### 7.1 `graph_mutations` 테이블

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `mutation_id` | string(PK) | `mut-<ULID>` |
| `idempotency_key` | string(unique) | stage input 해시 — 중복 방지 |
| `op` | enum | `create_node`/`create_edge`/`merge_entity`/`unmerge`/`supersede`/`delete`/`quarantine` |
| `payload` | jsonb | 대상 element·속성 |
| `resolution_ref` | string(nullable) | → resolution decision([`05`](./05-resolution-and-extraction.md)) |
| `actor` | enum | `pipeline`/`llm:<model>`/`human:<user>` |
| `version_tuple` | jsonb | 5축: `ontology_version`/`schema_version`/`prompt_template_hash`/`model_id`/`extraction_code_version` ([`README`](./README.md) §2.3) |
| `correlation_id` | string | end-to-end 추적 |
| `tx_time` | timestamp | 기록 시각 |

### 7.2 이벤트 계약

- **Append-only.** 이벤트는 수정·삭제하지 않는다. 되돌리기는 역이벤트(`delete`, `supersede`, `unmerge`)로 표현한다.
- **Replay 가능.** `graph_mutations`를 순서대로 적용하면 동일 materialized graph가 나온다 (재현성, blueprint §21-2).
- **Merge 되돌리기.** `merge_entity`는 대응 `unmerge` 이벤트로 rollback 가능해야 한다 (blueprint §8.5, precision-first).
- **Idempotency.** 동일 `idempotency_key` 재수신 시 no-op (불변식 §3-6).

## 8. Provenance Chain (Hall of Witnesses)

blueprint §6.5. 모든 그래프 요소는 원문까지 왕복 추적 가능해야 한다 (불변식 §3-2).

### 8.1 Provenance 경로

```text
Graph element (Claim/Evidence/Assertion)
  → extraction_record (ext-…)          # 추출 1회의 기록
  → normalized document version (doc_id, parser_version)
  → source span (segment_id, char_start/end)
  → immutable raw document (raw/…/content.bin, content_hash)
  → source URL + retrieval metadata (fetch.json)
```

### 8.2 `extraction_records` 테이블

blueprint §6.5 최소 provenance 필드를 확정한다.

| 컬럼 | 설명 |
| --- | --- |
| `extraction_id` | `ext-<ULID>` |
| `element_id` | 생성된 claim/evidence/mention |
| `doc_id` / `segment_id` | 원문 문서·구절 |
| `char_start`/`char_end` | 문자 offset — **원문(raw)** 기준 (§3.2 dual offset 축과 동일) |
| `content_hash` | 원문 해시 |
| `fetched_at` / `published_at` | 수집·공개 시각 |
| `model_id` / `prompt_template_hash` / `schema_version` | 추출 모델·프롬프트·스키마 버전 |
| `preprocess_code_version` | 전처리 코드 버전 |
| `review_history[]` | 승인/교정 이력 (→ [`05`](./05-resolution-and-extraction.md) human review) |

### 8.3 Provenance 게이트

- `provenance_ref`(= `extraction_id[]`) 없는 Claim/Evidence/Assertion은 **authoritative graph 진입 금지** → quarantine (불변식 §3-2, [`02`](./02-ontology.md) §4-1).
- 모델이 생성한 신규 사실은 source span 없이 저장하지 않는다 (blueprint §13).

### 8.4 삭제 전파

삭제 요청·원천 문서 제거는 파생 데이터까지 전파해야 한다 (blueprint §13). raw→normalized→curated→graph 역방향으로 `delete`/`quarantine` 이벤트를 발행한다. 상세 절차는 [`11`](./11-observability-and-governance.md) §retention.

## 9. 데이터 규모 계획

blueprint §7.3.

| 단계 | 문서 수 | 저장 목표 |
| --- | --- | --- |
| Prototype | 1만 | 단일 MinIO, 온톨로지·provenance 검증 |
| MVP | 10만 | 3-zone + graph, 전체 재처리 |
| Scale | 100만 | Iceberg 승격 검토, 증분 처리 |
| Challenge | 1,000만 | 텍스트 ~50GB, 총 수백 GB (HTML+버전+임베딩+인덱스+그래프) |

## 10. 의사결정 로그

| ID | 결정 | 근거 | 상태 |
| --- | --- | --- | --- |
| ADR-301 | raw zone 완전 immutable, URL 변경분은 새 doc_id로 보존 | 재현성·버전 추적(blueprint §7.1) | Accepted · **구현(P1 ②)**: `MinioRawStore`로 MinIO raw 객체 스토어 영속 — content-hash doc_id·ADR-301 보존(`prototype/orc_citadel/minio_raw_store.py`, 2026-08-11) |
| ADR-302 | `segments`에 원문·정규화 offset **양방향** 저장 | provenance 왕복 보장(§8.2) | Accepted |
| ADR-303 | bitemporal 2축을 assertions에 필수 저장 | 변화 이력 재현(blueprint §6.4) | Accepted |
| ADR-304 | 그래프 변경은 `graph_mutations` 이벤트로만, replay로 재구축 | SoT는 log, graph는 파생(§17) | Accepted · **구현(P1 ①)**: `PostgresMutationLog` SoT 영속 + 순서 보존 replay 검증(`postgres_mutation_log.py`) · **구현(P1 ⑤)**: `graph_replay.replay_graph`가 postgres 로그→`GraphService` 재생으로 materialized graph 재구축 (`graph_replay.py`, 2026-08-11) |
| ADR-305 | provenance_ref 없는 element는 quarantine | 무출처 사실 차단(blueprint §13) | Accepted · **구현(P1 ③)**: curated zone에 `extraction_records` 테이블 신설 + gate가 `provenance_ref` 없으면 quarantine(`missing_provenance_record`) — 파이프라인이 추출 시 record 영속·ref 부여 (`prototype/orc_citadel/curated_zone.py`·`gate.py`·`pipeline_runner.py`, 2026-08-11) |
| ADR-306 | 별도 `claims` 테이블 없이 `claim_candidates(status=promoted)`를 claim-of-record로 선언, promote 시 §7 이벤트로 Assertion emission | 후보/정본 이중 테이블 제거, `assertions.claim_id` FK 대상 확정(§4.2) | Accepted |
| ADR-307 | `assertions`는 append-only SoT가 아니라 `graph_mutations`의 system-versioned projection — 허용 in-place write는 supersession 시 `tx_to` close뿐 | append-only 오표기 정정, SoT 단일화(§6.2, §7) | Accepted |
