# 03 · 저장 계층·데이터 모델 (Grand Archive · Chronicle · Hall of Witnesses)

> **상태:** ✅ Stable · **Spec:** 1.7.0 · **Blueprint 매핑:** §6.4, §6.5, §7.1, §17
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

| Zone | 포맷 | 현행 저장소 | 변경성 | 소유 stage |
| --- | --- | --- | --- | --- |
| raw | source-sharded zstd Parquet | **prod shared filesystem**; MinIO는 동일 레이아웃의 대체 backend | **immutable, append-only** | S2 |
| normalized | Apache Iceberg | Lakekeeper REST catalog + warehouse | 재생성 가능(`parser_version`) | S3 |
| curated | Apache Iceberg | Lakekeeper REST catalog + shared warehouse | 재생성 가능 | S5–S6 |
| mutation log | PostgreSQL | PostgreSQL | **append-only** | S7 |

DuckDB zone file은 2026-09-22 migration의 **legacy 입력/비교 기준선**일 뿐 현행
normalized/curated 저장소가 아니다. DuckDB는 local ad-hoc 분석 도구로만 남는다.
PostgreSQL mutation log와 §4.4 investigation 운영 메타데이터/queue는 이번 cutover
범위 밖이며 변경하지 않았다.

### 1.1 파티셔닝·클러스터링 스킴

Iceberg 파티션 키는 재처리·시간 질의·삭제 전파를 고려해 다음으로 확정한다.

| 테이블 | 파티션 키 | 클러스터링/정렬 |
| --- | --- | --- |
| `documents` / `segments` | `source_id`, `publication_time`(월 버킷) | `doc_id` |
| `mentions` | `dedup_version` | `doc_id` |
| `claim_candidates` | `status` | `doc_id` |
| `dup_signatures` / `dup_bands` | `dedup_version` | `doc_id`, `dedup_version`[, `band_idx`] |
| `assertions` | `tx_from`(월 버킷) | `subject_id`, `predicate` |

- normalized는 source/month로 prune하고 `(doc_id, parser_version)`·`(segment_id, parser_version)` identifier로 version을 보존한다. curated는 table별 재생성/status/시간 축에 맞춰 partition한다.
- 삭제 전파(§8.4)는 `source_id`/`doc_id` pruning으로 대상 file을 좁힌다.

### 1.2 Iceberg cutover 실측 (G2/G3, 2026-09-22)

**G2 normalized.** legacy normalized DuckDB는 **255,500 KiB**, migration 뒤 Iceberg는
**145,228 KiB**로 **43.2% 작았다**. 정확히 **105,252 documents**와
**823,629 segments**를 이관했고 두 table 모두 **233 partitions**, snapshot 수는
`documents/segments` 순서로 **11/83**이었다. migration 벽시계는 **11.47s**였다.
D1 재판정 시 디스크 여유는 **509 GiB**였으며, 이 결과로 D1은 **증설 없이 계속하되
범위를 확대하지 않음**으로 확정했다.

`parser_version` p1→p2 schema/version evolution smoke는 documents 2행·segments 2행을
그대로 보존했고, 각 table snapshot은 **1→2**, warehouse 증가는 **29,815 bytes**였다.
incremental 임시 smoke에서 warm 신규 1건은 **0.1082s**로 legacy 기준선
**0.147–0.158s**보다 개선됐다. 반면 no-change는 **0.0348s**로 기준선 **0.01s** 대비
**3.48× 회귀**했지만 절대 증가는 **+24.8ms**다. cold-create **0.3075s**는 legacy
기준선과 직접 비교할 수 없는 별도 측정이다.

**G3 curated.** legacy curated DuckDB는 **6,156 KiB**였다. 같은 shared Iceberg
warehouse는 G2의 **145,228 KiB → 145,908 KiB**, 즉 **+680 KiB** 증가했고, 현행
**18개 curated table** 모두 source row count와 visible row count가 같았다. legacy
corpus에는 lazy `dup_signatures`/`dup_bands` table이 없었으므로 두 source count를
정확히 0으로 취급했다.

synthetic selective lookup은 **10,000 signatures / 80,000 band rows**에서 matching
candidate 1건을 반환했고 **p50 22.804ms, max 79.258ms**였다. 이는 과거
**12.4ms/doc full dedup 계수와 직접 비교할 수 없다**. 실제 corpus의 persisted
signature population이 0이어서 real-corpus end-to-end dedup 비교는 **미측정**이며,
correctness/LSH tests가 green이라는 사실만 별도로 유지한다.

## 2. Raw Zone

### 2.1 객체 레이아웃

raw zone은 Iceberg table로 승격하지 않는다. 원문은 **immutable source-sharded zstd
Parquet**가 정본이다. 현행 prod는 scheduler와 promotion-consumer가 공유하는
`proddata:/app/data/raw` filesystem volume에 배치한다. MinIO raw 구현은 아래와 같은
상대 레이아웃·metadata schema를 보존하는 대체 backend이며, 배치된 prod raw 경로로
오표기하지 않는다(ADR-309).

```text
raw/
  <source_id>/
    shard-<ts>-<rand>.parquet   # zstd, 기본 shard_size=10,000
```

샤드 스키마는 `doc_id, source_id, url, fetched_at, http_status, robots_allowed,
license, meta_json, content(BLOB)`다. `content`는 원본 bytes 그대로이고
`doc_id = "doc-" + sha256(content)[:24]`는 압축 전 bytes 기준이다. 기록된 shard는
수정하지 않으며 추가분은 항상 새 shard다. filesystem backend는 위 경로를 파일로,
MinIO 대체 backend는 같은 상대 경로를 object key로 사용한다. 과거 MinIO의
`raw/source_id=<...>/doc_id=<...>/{content.bin,fetch.json}` 배치는 폐기되어 backend
schema divergence가 닫혔다.

raw를 Iceberg로 올리지 않는 이유는 원문이 update/schema-evolution 대상이 아니고,
content-hash idempotency와 append-only shard가 필요한 불변식을 더 직접적으로
보장하기 때문이다. Lakekeeper/Iceberg는 normalized/curated의 row-level
evolution·snapshot·multi-writer commit에만 사용한다.

**근거 (ADR-308, 2026-09-20 동일 corpus 104,471건 실측).** doc당 디렉터리+2파일은
1,000만 건에서 inode 30M(원격 여유 25.34M)을 요구해 성립하지 않는다. 같은
corpus에서 shard는 디스크 888MB→67.3MB(content 실제 298MB — 나머지는 block
padding 낭비), skip index 18.9s→0.02s, 재처리 입력은 전량 RAM 상주(RSS ≈ raw
bytes)에서 streaming peak 0.54GB로 바뀌었다. 압축비는 source별 zstd
4.44×(arXiv metadata)~43.05×(HTML boilerplate)였다.

### 2.2 수집 metadata 논리 스키마

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

- **불변식:** 동일 `url`의 변경된 버전은 **새 `doc_id`로 모두 보존**한다(덮어쓰기 금지, blueprint §7.1, §8.1).
- §2.1의 논리 metadata 필드는 별도 `fetch.json` object가 아니라 **shard column**으로 저장되고, 스키마 외 필드는 `meta_json`에 보존한다.
- `doc_id`가 내용 기반이므로 동일 bytes 재수집은 동일 객체 → idempotent (S2, 불변식 §3-6).
- 라이선스·robots는 [`11`](./11-observability-and-governance.md) governance가 강제한다.

## 3. Normalized Zone

### 3.1 `documents` 테이블

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `doc_id` | string(identifier) | 내용 기반 ID; `parser_version`과 composite identifier |
| `source_id` | string | → Source |
| `url` | string | |
| `title` | string | |
| `language` | string | 감지 언어 |
| `publication_time` | timestamp | 공개 시각 |
| `revision_time` | timestamp | 수정 시각 |
| `parser_version` | string(identifier) | 동일 `doc_id`의 parser version별 row 보존 |
| `char_len` | int | |

### 3.2 `segments` 테이블 (문단·문장)

안정적 문단·문장 ID와 원문 offset 매핑을 보존한다 (blueprint §8.2, provenance 근간).

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `segment_id` | string(identifier) | `<doc_id>#p<par>.s<sent>` — `parser_version`과 composite identifier |
| `doc_id` | string | → `documents.doc_id` |
| `kind` | enum | `paragraph`/`sentence`/`table_cell`/`footnote`/`list_item` |
| `text` | string | 정규화 텍스트 |
| `char_start` | int | **원문(raw)** 기준 offset |
| `char_end` | int | |
| `norm_char_start` | int | 정규화 텍스트 기준 시작 offset |
| `norm_char_end` | int | 정규화 텍스트 기준 끝 offset (원문↔정규화 양방향 매핑용, ADR-302) |
| `ord` | int | 문서 내 순서 |
| `parser_version` | string(identifier) | 재파싱 version별 segment row 보존 |
| `source_id` / `publication_time` | string / timestamp | physical partition source; public segment API에서는 숨김 |

- `segment_id`는 결정적이라 재파싱 시 안정적으로 유지된다 (offset mapping unit test 대상, → [`10`](./10-evaluation-and-testing.md)).
- **원문 offset ↔ 정규화 offset 매핑**을 함께 저장해 provenance 왕복을 보장한다 (blueprint §8.2).

## 4. Curated Zone

추출·해소 산출물. 각 row는 version tuple을 부착한다. 현행 구현의 table은 정확히
18개다: `mentions`, `dup_signatures`, `dup_bands`, `dup_clusters`, `entities`,
`claim_candidates`, `canonical_claims`, `member_of`, `conflict_candidates`,
`assertions`, `authoritative_edges`, `canonical_llm_records`, `conflict_verdicts`,
`golden_pairs`, `golden_entity_pairs`, `golden_lineage_pairs`,
`promotion_baselines`, `extraction_records`.

**`evidence_candidates` runtime table은 없다.** Evidence ontology object를 이유로
구현되지 않은 table을 있다고 기록하지 않는다. 현행 evidence/provenance material은
promoted claim, assertion, authoritative edge, extraction record와 source span
경로로 조회한다.

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

### 4.2 `claim_candidates`

[`02`](./02-ontology.md) §2.4의 Claim 속성을 저장하고
`status`(`candidate`/`promoted`/`quarantined`)를 붙여 graph 반영 전 상태를 구분한다.

- **Claim-of-record.** 별도 `claims` table을 두지 않고 `claim_candidates`에서 `status=promoted`인 row가 **claim-of-record**다. §6.2 `assertions.claim_id` FK는 이 promoted row(`claim_id = claim_candidate_id`)를 참조한다(ADR-306). `candidate`/`quarantined` row는 authoritative graph의 참조 대상이 될 수 없다.
- **Claim→Assertion emission 계약.** Claim이 `promoted`로 전이될 때 정규 삼항(subject/predicate/object)과 valid time을 갖는 `Assertion`을 1건 이상 materialize한다. emission은 §7 `graph_mutations` event(`op=create_node`/`supersede`)를 통해서만 발생하며, 동일 `idempotency_key` 재실행 시 중복 발행하지 않는다([`02`](./02-ontology.md) §2.4 Claim→Assertion materialization 규칙과 정합).

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

기존 curated evidence를 대상으로 한 비동기 조사는 PostgreSQL의 `investigations`·`jobs`·`steps`·`report_artifacts`에만 기록한다. `investigations`는 question, subject_id, scope, mode, owner, version tuple, correlation_id, status, coverage, termination, report JSONB, audit_trace JSONB, 불변 `report_profile`과 UTC timestamps를 가진다. `jobs`는 단일 investigation에 1:1로 연결되고 `queued|running|succeeded|failed|cancelled`, `cancel_requested`, worker lease/claim token, error JSONB를 가진다. `steps`는 `(investigation_id, step_id)` unique의 append-only `PLAN|RUN|SYNTHESIZE|AUDIT|REPORT` 기록이다. `report_artifacts`는 investigation당 하나의 exact HTML bytes와 content/source/draft hash, 생성 mode, template/schema/model/prompt/usage/Audit metadata를 분리 저장한다.

- 동일 `Idempotency-Key`는 최초 `inv-`/`job-`을 반환하고 행을 늘리지 않는다.
- claim은 `FOR UPDATE SKIP LOCKED`와 lease token으로 원자화한다. 만료된 `running`만 재claim하며 이전 claim token의 완료는 거부한다.
- `complete_with_report_artifact`는 artifact insert·`REPORT` step·JSON report/audit·investigation/job 완료를 한 transaction에서 확정한다. 저장 경계에서 HTML/draft/source hash와 investigation의 template/schema/prompt pin을 다시 검증한다.
- cutover 이전 `completed` row의 `report_profile=NULL`은 `legacy_json_only`로 남긴다. 배포 시점의 queued/running row만 현재 profile로 멱등 backfill해 새 worker가 HTML 없이 실패하지 않게 한다.
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
  → immutable raw shard row (raw/<source_id>/shard-*.parquet, content_hash)
  → source URL + retrieval metadata (shard columns/meta_json)
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
| Prototype | 1만 | proddata raw filesystem + MinIO Iceberg warehouse, 온톨로지·provenance 검증 |
| MVP | 10만 | 3-zone + graph, 전체 재처리 |
| Scale | 100만 | **Iceberg 운영 중**, 증분 처리·snapshot/compaction tuning |
| Challenge | 1,000만 | 텍스트 ~50GB, 총 수백 GB (HTML+버전+임베딩+인덱스+그래프) |

## 10. 의사결정 로그

| ID | 결정 | 근거 | 상태 |
| --- | --- | --- | --- |
| ADR-301 | raw zone 완전 immutable, URL 변경분은 새 doc_id로 보존 | 재현성·버전 추적(blueprint §7.1) | Accepted · prod filesystem과 MinIO 대체 backend 모두 source-sharded zstd Parquet layout으로 구현 |
| ADR-302 | `segments`에 원문·정규화 offset **양방향** 저장 | provenance 왕복 보장(§8.2) | Accepted |
| ADR-303 | bitemporal 2축을 assertions에 필수 저장 | 변화 이력 재현(blueprint §6.4) | Accepted |
| ADR-304 | 그래프 변경은 `graph_mutations` 이벤트로만, replay로 재구축 | SoT는 log, graph는 파생(§17) | Accepted · **구현(P1 ①)**: `PostgresMutationLog` SoT 영속 + 순서 보존 replay 검증(`postgres_mutation_log.py`) · **구현(P1 ⑤)**: `graph_replay.replay_graph`가 postgres 로그→`GraphService` 재생으로 materialized graph 재구축 (`graph_replay.py`, 2026-08-11) |
| ADR-305 | provenance_ref 없는 element는 quarantine | 무출처 사실 차단(blueprint §13) | Accepted · **구현(P1 ③)**: curated zone에 `extraction_records` 테이블 신설 + gate가 `provenance_ref` 없으면 quarantine(`missing_provenance_record`) — 파이프라인이 추출 시 record 영속·ref 부여 (`prototype/orc_citadel/curated_zone.py`·`gate.py`·`pipeline_runner.py`, 2026-08-11) |
| ADR-306 | 별도 `claims` 테이블 없이 `claim_candidates(status=promoted)`를 claim-of-record로 선언, promote 시 §7 이벤트로 Assertion emission | 후보/정본 이중 테이블 제거, `assertions.claim_id` FK 대상 확정(§4.2) | Accepted |
| ADR-307 | `assertions`는 append-only SoT가 아니라 `graph_mutations`의 system-versioned projection — 허용 in-place write는 supersession 시 `tx_to` close뿐 | append-only 오표기 정정, SoT 단일화(§6.2, §7) | Accepted |
| ADR-308 | raw를 doc당 디렉터리+2파일에서 **source별 Parquet shard(zstd)**로 전환. 불변식·doc_id 규칙은 불변 | 1,000만 건 inode 30M 요구·skip 전수 scan 18.9s/103k·재처리 전량 RAM 상주가 동시에 무너짐 — 같은 corpus 실측으로 디스크 13.2×·skip 945×·streaming 전환(2026-09-20) | Accepted · **구현**: prod filesystem과 MinIO 대체 backend가 동일 `raw/<source>/shard-*.parquet` layout·metadata schema를 사용. 현행 prod raw는 shared `proddata` filesystem이며 MinIO는 Iceberg warehouse를 담당(2026-09-22) |
| ADR-404 | S4 near-dup 후보를 LSH 밴딩으로 좁히고 MinHash 서명을 `dup_signatures`/`dup_bands` 에 영속 | 전수 비교가 실측 O(N²)(1,000만 투영 4.1년)이고, 서명 재계산만도 12.4ms/doc × 1,000만 = 36h — nightly 주기에 들어가지 않음 (2026-09-20) | Accepted · **구현**: `dedup.band_keys` + `CuratedZone.persist_signature`/`band_candidates` · 증분 승격이 후보만 SQL 로 조회 (전체 서명 적재 ≈5GB 회피). 판정 임계(0.90·ADR-403) 불변, 재현율 실측 1.0000(703건·790쌍) |
| ADR-405 | 커넥터 kind 3종 신설(`paged_api`·`bulk_archive`·`index_stream`)과 단일 디스패치(`COLLECTORS`) | 2026-09-20 도메인 조사에서 AI·경제·과학 3분야가 독립적으로 같은 3종을 지목 — 확보 가능 11.66M 중 대부분이 이 경로 | Accepted · **구현**: `collect_large.collect_paged_api`/`collect_bulk_archive`/`collect_index_stream` + 러너·nightly·viewer 러너 디스패치 통합. 아카이브 엔트리 식별자는 `{archive_url}#{entry_path}`, 결과 상한은 `ResultCapReached` 로 전파(조용한 누락 금지). 소스 등록은 미포함 |
| ADR-309 | normalized·curated는 **Lakekeeper REST catalog + Apache Iceberg**로 전환하고, raw는 Iceberg로 올리지 않은 채 immutable source-sharded zstd Parquet로 유지한다 | G2: 255,500→145,228 KiB(-43.2%), 105,252 docs/823,629 segments, migration 11.47s, parser-version snapshot evolution 확인. G3: 18 table count equality, shared warehouse +680 KiB. raw는 update/evolution 대상이 아니며 shard 불변식이 더 직접적 | Accepted · Implemented 2026-09-22 (D1 계속/무확장, D2 Lakekeeper) |
