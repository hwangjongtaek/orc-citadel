# Apache Iceberg · Redpanda cutover — 완료 기록

> **완료:** 2026-09-22 · Design Spec `1.7.0`
> 본 문서는 착수 계획이 아니라 Q6(Iceberg)·Q7(event stream)의 결정·완료 범위·검증 근거와 남은 운영 위험을 보존하는 handoff record다.

## 1. 최종 결정

| 결정 | 확정 내용 | 근거·경계 |
| --- | --- | --- |
| **D1 — disk** | 증설 없이 계속하되 G2 이후 범위를 확대하지 않음 | **근거 정정 (2026-09-22 검증):** 최초 기록의 free 509 GiB 는 개발 Mac 실측이었다. D1 은 1,000만 corpus 가 쌓이는 **원격 호스트**(`10.0.0.11`) 결정이며, 그 실측은 **502G 중 183G 여유(62% used)** 로 cutover 전후 변동 없다. 03 §9 목표 "총 수백 GB" 와 같은 자릿수라는 위험은 **해소되지 않았다**. 결정(증설 없이 계속·범위 확대 없음)은 유지하되 근거는 이 수치다. |
| **D2 — catalog** | **Lakekeeper REST catalog** | 단일 호스트 운영 단순성과 PyIceberg REST 연동을 기준으로 채택했다. normalized·curated의 catalog이며 raw를 소유하지 않는다. |
| **D3 — broker** | **Redpanda Community Edition** | 단일 호스트에서 Kafka API를 유지하면서 JVM/ZooKeeper 운영 부담을 피한다. S1–S7 event stream의 현행 broker다. |

도입 순서는 Iceberg 선행, Redpanda 후행이었다. 다중 writer가 consume하기 전에
normalized/curated가 Iceberg의 atomic snapshot commit을 사용해야 했기 때문이다.

## 2. Phase 완료 범위

| Gate | 완료 결과 |
| --- | --- |
| **G1 — catalog/runtime** | Lakekeeper와 PyIceberg write path를 기동하고 local persistent catalog/file warehouse와 prod REST catalog 경계를 확정했다. |
| **G2 — normalized** | `documents`·`segments`를 legacy DuckDB에서 Iceberg로 migration했다. `(doc_id, parser_version)` idempotency, source/month partition, snapshot 기반 version evolution을 보존했다. |
| **G3 — curated** | 구현된 curated **18개 table**을 shared Iceberg warehouse로 전환하고 source/visible count equality를 확인했다. |
| **Raw backend closure** | raw는 Iceberg로 올리지 않고 immutable source-sharded zstd Parquet로 유지했다. 현행 prod는 shared `proddata` filesystem을 사용한다. MinIO 대체 backend도 같은 `raw/<source>/shard-*.parquet` layout·metadata schema를 구현했으며, 배치된 MinIO는 Iceberg warehouse를 담당한다. |
| **K1–K3 — broker/topics/producer** | Redpanda CE, S1–S7 각 primary/retry/DLQ/quarantine topic, acked reference-only envelope, durable raw 뒤 S1/S2 producer를 구현했다. `ResultCapReached`는 terminal S1 event다. |
| **K4 — promotion consumer** | stable group `orc-citadel-s2-promotion-v1`이 S2 primary+retry를 bounded batch(max 1,000)로 소비해 reference가 가리키는 doc만 Iceberg로 승격한다. |
| **K5 — scheduler boundary** | scheduler는 collection dispatch+metrics만 담당한다. direct promotion, zone rebuild, snapshot 호출은 제거했고 always-on `promotion-consumer`가 승격을 소유한다. |

현행 prod overlay는 13개 Compose service를 선언한다. `redpanda-init`은 28개 topic을
멱등 생성하고 종료하는 one-shot이며, `promotion-consumer`는 MinIO·Lakekeeper health와
topic bootstrap을 기다린 뒤 상시 실행한다. 착수 계획에 적었던 service-count
추정치는 폐기하고 이 선언 목록을 정본으로 삼는다.

## 3. 최종 저장 계약

```text
raw/<source_id>/shard-*.parquet      immutable, zstd, prod shared filesystem
              │
              ├─ normalized.documents   Apache Iceberg
              ├─ normalized.segments    Apache Iceberg
              └─ curated.* (18 tables)  Apache Iceberg
                         catalog: Lakekeeper REST

PostgreSQL: graph mutation log + investigation metadata/job queue (변경 없음)
```

현행 curated table은 `mentions`, `dup_signatures`, `dup_bands`, `dup_clusters`,
`entities`, `claim_candidates`, `canonical_claims`, `member_of`,
`conflict_candidates`, `assertions`, `authoritative_edges`, `canonical_llm_records`,
`conflict_verdicts`, `golden_pairs`, `golden_entity_pairs`, `golden_lineage_pairs`,
`promotion_baselines`, `extraction_records`다.

**`evidence_candidates` runtime table은 구현되어 있지 않다.** ontology의 Evidence
개념만으로 table 존재를 주장하지 않는다. mutation log의 Iceberg 전환도 수행하지
않았으며 PostgreSQL append-only SoT를 유지한다.

## 4. 최종 event-stream 계약

- topic 이름은 `orc.events.s{1..7}.<stage-slug>.v1`이며 각 S1–S7 stage에
  primary, `.retry`, `.dlq`, `.quarantine` route가 있다(총 28개).
- envelope는 versioned JSON reference만 운반한다. raw bytes나 Iceberg row를 broker에
  복제하지 않는다. producer는 `acks=all`과 idempotence를 사용하고 broker callback이
  성공해야 반환한다.
- 모든 collection path는 raw shard가 durable해진 뒤 local SQLite outbox가 raw row를
  reconcile하고 `S1/document_fetched`와 `S2/raw_stored`를 발행한다. 각 stage는 broker
  acknowledgement 뒤에만 ack 처리되며 raw commit 뒤 publish 실패는 다음 dispatch가
  URL skip보다 먼저 복구한다. `ResultCapReached`는 `S1/result_cap_reached`,
  `status=terminal`로 발행해 조용한 누락을 금지한다.
- promotion consumer는 `enable.auto.commit=false`, `enable.auto.offset.store=false`다.
  path-safe slug와 `raw://<source_id>/doc-<24hex>`가 가리키는 정확한 raw row를 검증한다.
  동일 content의 여러 source reference가 있으면 normalized의 단일 `source_id/url`은
  `(source_id, url)` 사전순 최소 provenance로 고정해 delivery order에 따른 flip을
  차단한다. duplicate reference는 결정적 ID로 idempotent replay하여
  normalized→curated 사이 부분 실패를 복구한다. 이미 완료된 논리 결과는 zero
  summary를 반환하며 row 수를 늘리지 않는다. S3 `normalization_completed`는 durable
  Iceberg write 뒤에 acked publish하고, 모든 필수 outbound acknowledgement 전에는
  input offset을 commit하지 않는다.
- invalid envelope/reference와 재시도로 해소할 수 없는 data defect는 S2 quarantine이다.
  inbound/outbound envelope는 1 MiB·JSON depth 32·scalar 8,192자 상한을 적용하고,
  invalid Kafka key는 고정 길이 hash로 바꾼다. unexpected/transient failure는
  `attempt_count`를 먼저 증가시키고 증가값이 `< max_retries`면 retry,
  `>= max_retries`면 DLQ로 보낸다. quarantine은 DLQ가 아니다.
- PostgreSQL `FOR UPDATE SKIP LOCKED` queue는 **investigation job 전용**으로 그대로다.
  수집·승격에는 Redpanda 전 PostgreSQL queue가 없었으므로 이번 변경은 queue 승격이
  아니라 신규 event-stream 도입이다(ADR-102 정정).

host external advertised listener는 **`127.0.0.1:19092`**다. macOS에서 `localhost`가
IPv6 `::1`로 resolve되어 IPv4 listener 연결이 실패하는 문제를 이 명시 주소로 닫았다.

## 5. G2 측정 결과 — normalized Iceberg

| 축 | 실측 결과 | 판정 |
| --- | --- | --- |
| Legacy normalized | **255,500 KiB** DuckDB | migration 기준선 |
| Iceberg normalized | **145,228 KiB** | legacy 대비 **43.2% 작음** |
| Row 수 | **105,252 documents**, **823,629 segments** | exact migration count |
| Partition | documents/segments 각각 **233** | source/month partition 확인 |
| Snapshot | documents/segments **11/83** | migration snapshot 기록 |
| Migration wall time | **11.47s** | measured |
| Disk free — 개발 Mac | **509 GiB** | G2 실행 환경. **D1 근거 아님** |
| Disk free — 원격 prod `10.0.0.11` | **183 GiB** (502G 중, 62% used) | **D1 의 실제 근거.** cutover 전후 변동 없음 |

### Parser-version evolution

p1→p2 smoke는 **documents 2행 / segments 2행**을 보존했고 두 table 모두 snapshot
**1→2**, warehouse **+29,815 bytes**였다. version bump가 기존 version row를 덮어쓰지
않고 새 snapshot으로 남는 계약을 확인했다.

### Incremental temporary smoke

| 경로 | Iceberg | Legacy baseline | 해석 |
| --- | ---: | ---: | --- |
| warm 신규 1건 | **0.1082s** | **0.147–0.158s** | 개선 |
| no-change | **0.0348s** | **0.01s** | **3.48× 회귀**, 절대 **+24.8ms** |
| cold-create | **0.3075s** | 없음 | baseline과 직접 비교 불가 |

no-change 상대 회귀를 개선으로 포장하지 않는다. 동시에 절대 증가량이 24.8ms임을
기록해 운영 중요도를 왜곡하지 않는다.

## 6. G3 측정 결과 — curated Iceberg

| 축 | 실측 결과 | 판정 |
| --- | --- | --- |
| Legacy curated | **6,156 KiB** DuckDB | migration 기준선 |
| Shared Iceberg warehouse | **145,228 → 145,908 KiB** | curated 전환 증가 **+680 KiB** |
| Count equality | 구현된 **18 tables** 전부 source = visible | migration equality 확인 |
| Legacy lazy tables | `dup_signatures`/`dup_bands` 부재 | source count를 정확히 **0**으로 취급 |
| Synthetic selective lookup | **10,000 signatures / 80,000 band rows**, matching candidate 1건 | **p50 22.804ms, max 79.258ms** |

selective lookup latency는 과거 **12.4ms/doc full dedup coefficient와 직접 비교할 수
없다**. 실제 corpus에는 persisted signature population이 0이었으므로 real-corpus
end-to-end dedup 비교는 **미측정**이다. correctness/LSH tests가 green인 것과 실제
corpus 성능이 측정되지 않은 것은 서로 다른 사실이다.

## 7. 검증 증거와 완료 판정

- G2 exact row counts, partition/snapshot counts, migration wall time와 disk size를 기록했다.
- parser p1→p2가 row 보존·snapshot 증가로 나타나는 것을 별도 smoke로 확인했다.
- incremental warm/no-change/cold-create를 분리했고 비교 불가능한 cold 수치를
  baseline 개선으로 사용하지 않았다.
- G3는 18개 table 모두 source/visible equality로 확인했고 legacy에 없던 lazy table을
  0으로 처리했다.
- synthetic band lookup은 candidate 선택 결과와 p50/max를 함께 기록했다.
- event path는 acked S1/S2 reference, terminal cap event, manual offset-after-durability,
  retry/DLQ/quarantine 분리, scheduler dispatch-only boundary로 봉인됐다.
- 실제 Redpanda smoke는 S2 원본 1건과 동일 duplicate 1건을 소비한 뒤
  **`mentions=1`, `dup_signatures=1`, `counts_stable=true`**를 확인했다.
- 최종 회귀는 **1,603 passed, 8 skipped**였고 cutover 집중 회귀는
  **136 passed**였다. `uv lock --check`, prod profile Compose config와 선언 service
  **13개**도 확인했다.
- 실제 Redpanda final smoke는 durable outbox row 1건에서 S1/S2를 acked publish하고
  **`inserted=1`, `delivered=1`, `redrain=0`, `pending=0`,
  `stages=[S1,S2]`**를 확인했다. 9,000자 URL은 `url-sha256:` bounded reference로
  운반되어 후속 row를 막지 않았다.
- 실제 MinIO smoke는 동일 bytes를 서로 다른 source 2곳에 저장해 **rows=2**,
  `content_hash`·전체 response headers metadata parity와 source별 URL 보존을 확인했다.
- 최종 독립 code/security/SSOT 재검토에서 blocker/high 문서 불일치는 남지 않았다.
  Compose 내부 `allowall`/plaintext 신뢰는 아래 운영 위험으로 명시적으로 남긴다.

Q6과 Q7은 이 범위에서 **완료**다. 이 판정은 1,000만 corpus 전체 수집·운영 완료나
아래 위험의 해소를 의미하지 않는다.

## 8. 남은 정직한 운영 위험

1. **Small files / compaction — 측정됐고, 나쁘다 (2026-09-23 prod).** 더 이상
   미측정 항목이 아니다. 문서 238건을 event 경로로 승격한 뒤 전 테이블 스냅샷
   합계가 **13 → 1,254**로 늘었다. 최악은 `curated.mentions` — **행 589개에
   스냅샷 476개**, 즉 행 하나 남짓마다 커밋 한 번이다. `claim_candidates` 247,
   `dup_bands` 241 도 같은 양상이고, 반대로 `normalized.documents` 는 8,
   `segments` 34 로 배치 쓰기가 제대로 되고 있다. 차이는 승격 파이프라인의
   curated 쓰기가 행 단위 `persist_*` 호출이라는 점이다. compaction·snapshot
   expiry 이전에 **쓰기 경로의 커밋 배치화**가 선행 과제다.
2. **실제 signature population — 이제 존재한다.** 이 항목의 전제였던
   "persisted signatures 0" 은 해소됐다: prod `dup_signatures` **238**,
   `dup_bands` **1,144**. 다만 238문서 코퍼스라 file pruning 효율은 여전히
   의미 있는 규모에서 미측정이고, synthetic 10k/80k lookup 을 실측으로
   오표기하지 않는다는 원칙은 유지한다.
3. **DuckDB UI parquet 스냅샷의 자동 갱신 부재.** K5 가 scheduler 를 collection
   dispatch+metrics 전용으로 좁히면서 기존 `_snapshot_parquet` 훅이 제거됐다.
   `parquet_snapshot` 모듈 자체는 Iceberg 읽기로 갱신돼 동작하지만 **프로덕션
   호출자가 0개**이고(테스트만 참조), `docker-compose.yml` 의 duckdb-ui 는 여전히
   `./prototype/data/parquet:ro` 를 마운트한다 → **UI 가 마지막 수동 export 시점에
   고정된다.** 훅을 되살리면 ADR-107 의 scheduler 경계를 다시 여는 셈이므로,
   갱신 주체를 promotion consumer 로 둘지 별도 one-shot 으로 둘지는 결정 대상이다.
   그 전까지 신선도는 수동 `python -m orc_citadel.parquet_snapshot` 에만 의존한다.
4. **단일 호스트 trust boundary.** local Lakekeeper·MinIO·Redpanda host ports는
   loopback에만 bind하고 prod overlay는 publish하지 않지만, Compose 내부는 현재
   Lakekeeper `allowall`과 plaintext Kafka를 신뢰한다. untrusted/multi-tenant network로
   확장하기 전 OIDC+OpenFGA와 SASL/TLS+topic ACL을 별도 보안 ADR로 도입해야 한다.
5. **단일 broker/catalog host.** Redpanda CE·Lakekeeper는 현재 단일 호스트다. HA나
   Kubernetes 승격은 availability/throughput SLO가 정당화할 때 별도 ADR 대상이다.
6. **문서당 승격 비용이 폴 경계와 충돌한다 (2026-09-23 prod 실측).** 미승격 25건
   승격에 **150.3s = 6.01s/doc** (183문서 코퍼스). 배치 시간은 문서 내용에 따라
   크게 흔들린다 — 수정 후 10배치 관측에서 **최단 ~60s, 최장 ~800s** (동일한
   25건 배치). `POLL_BATCH_SIZE=25` / `max.poll.interval.ms=900_000` 은 이
   실측 위에 잡은 값이고 최장 배치는 이미 선언 간격의 **약 89%** 를 쓴다.
   코퍼스가 자라면 dedup·블록 재조정이 코퍼스를 되읽으므로 이 여유는 줄어든다
   — 상수 조정이 아니라 승격 비용 자체를 손봐야 하는 시점이 온다. 1,000만
   스케일에서 6s/doc 는 성립하지 않는다(단순 투영 약 694일). **Q6/Q7 이후
   재개하기로 한 1,000만 측정의 첫 실측 벽이다.**

## 9. 유지된 범위 밖 항목

- 라이선스가 확인된 신규 source 등록과 1,000만 수집 재개. D1은 G2 이후 scope 확대를
  승인하지 않았다.
- `_arxiv_date_windows`의 10k 초과 월 누락 및 `start="202608112359"` hard-coded 상한.
  `ResultCapReached` event 계약은 조용한 누락을 드러내지만 이 별도 결함 자체를
  수정했다는 뜻은 아니다.
- PostgreSQL `graph_mutations`를 Iceberg로 전환하는 작업. replay 정확성 때문에 별도다.
- investigation job의 PostgreSQL SKIP LOCKED queue. 감사·claim/lease 계약을 그대로
  유지한다.
- ClickHouse·Kubernetes 승격. 각각 자체 측정 trigger와 ADR이 필요하다.
