# Orc Citadel — 로드맵 & 진행 관리

> 이 문서는 프로젝트 **진행 내역을 추적**한다. 스펙 정의는 [`docs/design/`](./design/README.md)(SSOT)에 있고, 여기서는 "무엇을 언제 어디까지 했는가"만 관리한다.
> 규칙: 설계·구현 변경은 (1) 해당 design 문서 수정 (2) `design/README.md` Spec version 반영 (3) 본 문서 §5 Changelog 기록의 3단계를 거친다.

- **최종 갱신:** 2026-08-11
- **현재 단계:** Phase 0 (설계·데이터 검증) — *설계 문서 Review 승격 완료, Stable 확정 대기*
- **Spec version:** 0.1.0 · **Ontology version:** 1.0.0

## 1. 상태 요약 (한눈에)

| 트랙 | 상태 | 비고 |
| --- | --- | --- |
| 상세 설계 (Design SSOT) | 🟡 Review | 12개 문서 Review 승격. 리뷰 패스 완료(BLOCKER 3 + MAJOR 36 해소, 상호 일관성 재검증 전항목 PASS). Stable 확정 대기 |
| 도메인·소스 선정 | ✅ 완료 | AI 반도체·데이터센터 공급망 확정, 초기 Scout 5종 선정(04 §1.4) |
| 1만 문서 샘플 | ✅ 완료 | 2026-08-11 arXiv metadata 1만 + RSS/SEC — 총 raw 11,361건 |
| Prototype 구현 | 🟡 진행 중 (S1–S47 + Q2/Q3/Q5) | 결정적+LLM 하이브리드 파이프라인 · bitemporal · 소비 계층(S28–31) · 평가/승격 트랙(S33–41) · **조사 에이전트 트랙(S43–47)** 구현 · Q2·Q3 해소 ([§5 Changelog](#5-changelog)) |

범례: ✅ 완료 · 🟡 진행 중 · ⬜ 예정 · ⛔ 블록됨

## 2. 설계 문서 진행 (Design SSOT)

[`docs/design/`](./design/README.md) 12개 문서의 작성 상태. 상태는 각 문서 헤더의 레전드(Draft/Review/Stable)와 동기화한다.

| # | 문서 | 작성 | 리뷰 | 확정 |
| --- | --- | :---: | :---: | :---: |
| — | README (인덱스·규약) | ✅ | ✅ | ✅ |
| 01 | architecture | ✅ | ✅ | ⬜ |
| 02 | ontology | ✅ | ✅ | ⬜ |
| 03 | storage-and-data-model | ✅ | ✅ | ⬜ |
| 04 | ingestion-and-parsing | ✅ | ✅ | ⬜ |
| 05 | resolution-and-extraction | ✅ | ✅ | ⬜ |
| 06 | graph-service | ✅ | ✅ | ⬜ |
| 07 | llm-and-agents | ✅ | ✅ | ⬜ |
| 08 | search-and-graphrag | ✅ | ✅ | ⬜ |
| 09 | api | ✅ | ✅ | ⬜ |
| 10 | evaluation-and-testing | ✅ | ✅ | ⬜ |
| 11 | observability-and-governance | ✅ | ✅ | ⬜ |

**설계 단계 종료 조건:** 12개 문서 전부 Review 통과 + 상호 참조 일관성 검증 + Phase 0 완료 조건(§3)에 매핑되는 스펙 확정.

## 3. 단계별 로드맵 (Blueprint §16 → 실행 계획)

각 Phase의 완료 조건(DoD)은 blueprint에서 가져와 검증 가능한 체크리스트로 만든다. 담당 스펙 문서를 함께 표기한다.

### Phase 0 — 설계·데이터 검증 (1~2주) · *현재*

| 작업 | 담당 스펙 | 상태 |
| --- | --- | :---: |
| 초기 도메인·source 3~5개 선정 | [04](./design/04-ingestion-and-parsing.md) | ✅(5종 확정) |
| 최소 ontology 정의 | [02](./design/02-ontology.md) | ✅(v1.0.0 초안) |
| 데이터 이용 조건(라이선스) 검토 | [11](./design/11-observability-and-governance.md) | ✅(04 §1.4 반영) |
| 1만 문서 샘플 확보 | [04](./design/04-ingestion-and-parsing.md) | ✅ arXiv metadata 경로(04 §1.4 CC0)로 1만 수집 완료 — saved 9,979 / skipped 21 / errors 0, 총 raw 11,361건 (2026-08-11) |
| provenance·bitemporal 모델 prototype | [03](./design/03-storage-and-data-model.md) | ✅ |
| 결정적+LLM 하이브리드 파이프라인 prototype | [05](./design/05-resolution-and-extraction.md) | ✅ S1–S42 (수집→어세션→캐노니컬→모순→승격) |
| 소비·조사 에이전트·평가 트랙 | [07](./design/07-llm-and-agents.md), [10](./design/10-evaluation-and-testing.md) | ✅ S28–S47 (read-only 소비·조사 루프·평가/승격·성능) |

**DoD:** ① 원문↔graph element 왕복 추적 가능 ② 동일 문서 재처리 시 중복 mutation 없음.

> **Phase 0 → Phase 1 진입 게이트 (2026-08-03):** ① 1만 문서 샘플 확보(사용자 arXiv 실행) ② Q4/Q6 측정 게이트는 Phase 1 부하에서 첫 판정 ③ 골든·승격 기준선(22건, S41/B2) 재검증. DoD ①②는 prototype에서 이미 충족(S27/S37 E2E 검증).
> **게이트 판정 (2026-08-11):** ① ✅ 총 raw 11,361건 확보 ③ ✅ 골든 22건 로드·평가 스위트 무회귀(canonicalization F1=1.0 유지, suite PASS)·promotion dry_run INITIALIZED/passed — 호스트·컨테이너 양쪽 동일 결과. ②는 예정대로 Phase 1 부하에서 첫 판정.

### Phase 1 — 10만 문서 MVP (3~5주)

| 작업 | 담당 스펙 |
| --- | --- |
| raw/normalized/curated 저장 계층 | [03](./design/03-storage-and-data-model.md) |
| parsing·dedup | [04](./design/04-ingestion-and-parsing.md) |
| entity·claim extraction | [05](./design/05-resolution-and-extraction.md) |
| Neo4j graph 적재 | [06](./design/06-graph-service.md) |
| 기본 graph explorer | [09](./design/09-api.md), DESIGN.md |
| 5개 조사 질문 end-to-end | [07](./design/07-llm-and-agents.md), [09](./design/09-api.md) |

**DoD:** ① 10만 문서 전체 재처리 가능 ② 최종 보고서 검증 가능 문장에 source span 연결.

### Phase 2 — Entity·Claim 품질 (6~8주)

| 작업 | 담당 스펙 |
| --- | --- |
| 후보 blocking + Entity Resolution | [05](./design/05-resolution-and-extraction.md) |
| Claim Canonicalization | [05](./design/05-resolution-and-extraction.md) |
| 출처 계보 모델 | [04](./design/04-ingestion-and-parsing.md), [11](./design/11-observability-and-governance.md) |
| contradiction candidate 생성 | [05](./design/05-resolution-and-extraction.md) |
| quarantine·review workflow | [05](./design/05-resolution-and-extraction.md), [06](./design/06-graph-service.md) |
| 골든 데이터셋 구축 | [10](./design/10-evaluation-and-testing.md) |

**DoD:** ① 핵심 품질 지표 자동 계산 ② entity merge 감사·rollback 가능.

### Phase 3 — Research Agent (9~10주)

| 작업 | 담당 스펙 |
| --- | --- |
| Planner·Graph Explorer·Retrieval Agent | [07](./design/07-llm-and-agents.md), [08](./design/08-search-and-graphrag.md) |
| Counter-Evidence Agent | [07](./design/07-llm-and-agents.md) |
| Synthesis·Audit Agent | [07](./design/07-llm-and-agents.md) |
| 조사 budget·종료 조건 | [07](./design/07-llm-and-agents.md) |
| 비용·evidence coverage 대시보드 | [11](./design/11-observability-and-governance.md) |

**DoD:** ① Agent가 그래프 공백 탐색·신규 evidence 추가 ② 반증 탐색 제거 버전 대비 평가 점수 향상.

### Phase 4 — 100만 문서 확장 (11~12주)

| 작업 | 담당 스펙 |
| --- | --- |
| 분산 batch 처리 | [01](./design/01-architecture.md) |
| 증분 graph update | [06](./design/06-graph-service.md) |
| 대량 embedding·LLM batch inference | [07](./design/07-llm-and-agents.md), [08](./design/08-search-and-graphrag.md) |
| ClickHouse 분석 | [11](./design/11-observability-and-governance.md) |
| full rebuild vs partial recomputation benchmark | [10](./design/10-evaluation-and-testing.md) |

**DoD:** ① 100만 문서 처리 시간·비용 공개 ② 신규 문서 SLO 내 graph 반영.

### Phase 5 — 1,000만 문서 Challenge

다국어 ER · hot/cold graph 분리 · impact graph 부분 재계산 · source adaptive scheduling · ontology migration 자동화 · 지속적 Campaign·Signal Spire. (상세 계획은 Phase 4 종료 시 확정.)

## 4. MVP 최종 성공 기준 (Blueprint §21 추적)

| # | 기준 | 검증 스펙 | 상태 |
| --- | --- | --- | :---: |
| 1 | 10만+ 실제 공개 문서 처리 | [04](./design/04-ingestion-and-parsing.md) | ⬜ |
| 2 | 전체 데이터셋 처음부터 재처리 | [01](./design/01-architecture.md), [06](./design/06-graph-service.md) | ⬜ |
| 3 | 모든 authoritative claim에 source span·버전 | [02](./design/02-ontology.md), [03](./design/03-storage-and-data-model.md) | ⬜ |
| 4 | ER·Claim Extraction 평가 수치 공개 | [10](./design/10-evaluation-and-testing.md) | ⬜ |
| 5 | 동일 근원 파생 출처 독립 중복 계산 방지 | [04](./design/04-ingestion-and-parsing.md), [11](./design/11-observability-and-governance.md) | ⬜ |
| 6 | valid/transaction time으로 변화 이력 재현 | [03](./design/03-storage-and-data-model.md) | ⬜ |
| 7 | Research Agent 공백·반대 증거 탐색 | [07](./design/07-llm-and-agents.md) | ⬜ |
| 8 | 보고서 검증 가능 문장 그래프·원문 감사 | [07](./design/07-llm-and-agents.md), [03](./design/03-storage-and-data-model.md) | ⬜ |
| 9 | 문서당 비용·전체 처리 시간 측정 | [10](./design/10-evaluation-and-testing.md), [11](./design/11-observability-and-governance.md) | ⬜ |
| 10 | 모델·프롬프트·ontology 버전 회귀 테스트 | [10](./design/10-evaluation-and-testing.md) | ⬜ |

## 5. Changelog

가장 최신이 위로. 스펙·설계 변경을 기록한다 (구현 세부 커밋은 git 이력).

### 2026-08-11
- **트랙 a — viewer 조사 그래프(War Table) 렌더링 (design 09 §2.2 War Table).** 조사 결과에 그래프가 없던 것을, `_api_investigate` 응답에 **조사 subgraph**(entities·relationships·relation_paths·independence_summary) 추가 + `loadInvestigation` JS 가 **War Table**(노드·관계·경로·독립출처) 렌더링. subgraph 는 기존 `ApiFacade.get_investigation_graph`(트랙 B) 재사용 — 파사드 단위검증과 정합. 전 과정 TDD — 신규 `test_viewer_graph.py` 1개 — 스위트 462→**463개 통과**. 후속: Neo4j read path(트랙 b)·time-travel.
- **트랙 C — 5개 조사 질문 end-to-end + DoD ② source-span provenance (design 07 §3-5·09 §2.3, ADR-703).** 조사 모듈(S43–S47)의 단위테스트만 있던 것에 **pipeline→조사 루프→보고서 end-to-end 드라이버**를 추가 — `run_pipeline` 결과의 assertions 로 ABOUT 그래프(별도 재구축) 구성, 5개 조사 질문(Subclaim) 정의, `InvestigationRunner`→`Synthesizer` 실행, audit passed·evidence-first(asserted 문장 claim_ref 필수) 검증. **DoD ② 충족 핵심**: `ApiFacade.get_evidence_provenance` trail이 기존 claim→doc 에만 끝나던 것을 **`extraction_records` 의 segment_id·char_start/char_end span step 을 연결**(파이프라인이 이미 영속한 char offset을 왕복·노출, 03 §8 ADR-305). 전 과정 TDD — 신규 `test_investigation_e2e.py`·`test_provenance_span.py` 2개 — 스위트 460→**462개 통과**. 후속: viewer 그래프 렌더링·Neo4j read path·time-travel·10만 실제 대량 실행.
- **트랙 B — 기본 graph explorer: investigation-subgraph 엔드포인트 배선 (design 09 §2.2, ADR-906).** 기존 `get_graph_node`/`get_graph_expand`(노드·인접)만 있고 조사 subgraph 엔드포인트(`GET /v1/investigations/{id}/graph`)가 미배선이던 것을, `ApiFacade`에 `GraphExplorer` 배선 + `get_investigation_graph(subject_id, hops)` 메서드 추가 — investigation subgraph(subject entity·claims·evidence·relationships)+relation_paths+independence_summary 반환(progressive disclosure 시드, 06 §8.1·§8.3). read-only(불변식 §3-3). 전 과정 TDD — `test_api_facade.py`에 신규 1개 — 스위트 459→**460개 통과**. 라이브 데모: org-a 서브그래프·claims·relation_paths 반환. 후속: viewer 그래프 렌더링·Neo4j read path·time-travel.
- **트랙 A — parsing·dedup 실배선 (design 04 §4, ADR-403).** `Deduplicator`(S4)가 실제 파이프라인(run_pipeline)에 배선되지 않고 `dup_clusters`가 안 채워지던 것을, `_run_chain`이 각 doc 의 clean text·publication_time·source_type 을 수집한 뒤 `Deduplicator().dedup(...)` 실행 + `persist_cluster` 로 영속하도록 배선. `PipelineResult.clusters` 필드 추가. **결정적 cluster_id** — 기존 `new_ulid("clus")`(비결정적)를 `sorted(members)+DEDUP_VERSION` 해시로 교체(04 §4.2 재생성 계약, extract_smoke 의 순번 치환 우회 제거). 전 과정 TDD — 신규 `test_pipeline_dedup_wiring.py` 3개 — 스위트 456→**459개 통과**. 라이브 데모: 중복 2건→단일 클러스터(root 이른 것·member 파생). 후속: 트랙 B(explorer)·C(조사 질문+DoD②).
- **후속 ③ — Neo4j 그래프 적래 + explorer (design 06, ADR-601/602/603).** 재생 그래프(`replay_graph`)의 authoritative 노드·엣지를 가동 중인 **Neo4j Community**(bolt 7687)에 적래(MERGE)하고 조회 — `Neo4jGraphStore`(`neo4j_graph_store.py`) 신설. 노드=`:Entity`(공통 `id`+props, design 06 §2.1 단순화), 엣지=`(:Entity)-[:ETYPE]->(:Entity)`. §2.3 `entity_id_unique` 제약이 MERGE idempotency 방어선 — 중복 적래 노드 없음(불변식 §3-6). explorer `query_neighbors`(인접 조회). 드라이버 `neo4j` 추가. 전 과정 TDD — 신규 `test_neo4j_graph_store.py` 3개 — 스위트 453→**456개 통과**. 라이브 데모: 재생 그래프(2노드·1엣지)→Neo4j 적래 node_count 2→neighbors 양방향. Q4 부하 스트레스·Memgraph 전환·세부 라벨/Provenance 는 후속.
- **후속 ② — 파이프라인 → postgres SoT 배선 (design 03 §7, ADR-602·304).** `run_pipeline` 이 승격 claim 의 그래프 mutation 을 in-memory `Gate` 에만 두고 postgres 로그에 안 쓰던 것을, 선택 `mutation_log`(① `PostgresMutationLog`) 제공 시 **승격 claim 을 `create_node {id}` + version_tuple 로 `graph_mutations` SoT 에 기록**(ADR-602 — 그래프 변경은 로그로만)하고 그래프 재구축을 **`replay_graph`(⑤)로 수행**(ADR-304 실경로). 미제공 시 기존 in-memory `_build_graph(gate)` 유지(파괴 없음). 전 과정 TDD — 신규 `test_pipeline_postgres_wiring.py` 3개(NVIDIA 대표 HTML) — 스위트 450→**453개 통과**. 라이브 데모: 파이프라인 승격 2건 → postgres create_node 로그 → fresh replay nodes 2 동일. 후속: Neo4j 적래(후속 ③).
- **후속 ① — MinIO ↔ 파이프라인 실배선 + fetch.json 완비 (design 03 §2, ADR-301).** 수집(`collect_large._save_zone`)과 파이프라인 입력(`load_raw_zone`)이 로컬 fs 를 쓰는 한편 ②의 MinIO 저장소가 미배선이던 것을 연결 — `_save_zone`에 `minio_store` 백엔드 옵션(로컬 fs default 유지, content-hash doc_id 로 재개 스킵), 신규 `load_raw_zone_minio`가 MinIO `raw/<source>/<doc>/{content.bin,fetch.json}` 로부터 파이프라인 meta list(`[{source_id,url,doc_id,content}]`) 재구성(동일 계약). fetch.json 에 governance(11) 필드 **license/robots_allowed** 완비. 전 과정 TDD — 신규 `test_minio_pipeline_wiring.py` 4개 — 스위트 446→**450개 통과**. 라이브 데모: 수집→MinIO 객체→재수집 idempotent→파이프라인 입력 재구성. 후속: 파이프라인 postgres 배선(후속 ②)·Neo4j(후속 ③).
- **저장 계층 키스톤 ⑤ — postgres SoT 로그 재생 → 그래프 재구축 (design 03 §7, ADR-304).** ①의 postgres `graph_mutations` SoT(영속만 되고 미소비)를 `GraphService`(Applier/replay, design 06 §3)로 **순서대로 재생**해 materialized graph 를 재구축 — `graph_replay.py`(`events_from_mutations`·`replay_graph`). payload/jsonb 원형 보존 전달, 동일 `idempotency_key` 중복 no-op(불변식 §3-6). ADR-304 DoD("로그→동일 그래프 재구축, blueprint §21-2") 실증. 전 과정 TDD — 신규 `test_graph_replay.py` 4개 — 스위트 442→**446개 통과**. 라이브 데모: SoT 로그 create_node·edge → replay → nodes 2·edge 1 재구축. 후속: 파이프라인 postgres 배선·Neo4j 적재.
- **저장 계층 키스톤 ③ — `extraction_records` 테이블 + provenance 게이트 (design 03 §8, ADR-305).** 추출 기록이 in-memory(↓ `RawStore` dict)로만 존재하던 것을 **curated zone에 `extraction_records` 테이블(§8.2 스키마)**로 영속화 — `persist_extraction_record`(element_id → **결정적** `ext-` id, 동일 element 재영속 no-op)·`extraction_records()`·`has_extraction_record` 추가. **ADR-305 게이트 강제**: `gate.py` provenance 검증에 `missing_provenance_record` reason 추가 — `provenance_ref`(=extraction_id[]) 없는 claim은 authoritative 진입 금지→quarantine. 파이프라인 `_run_chain`이 추출 시 record 영속·`ClaimCandidate.provenance_ref` 부여(frozen dataclass `object.__setattr__`)해 실제 흐름에서 게이트 충족. 전 과정 TDD — `test_gate` 헬퍼 갱신 + 신규 `test_extraction_records.py` 6개 — 스위트 436→**442개 통과**. 후속: MinIO raw 참조 연결·fetch.json 완비.
- **저장 계층 키스톤 ② — MinIO raw 객체 스토어 (design 03 §2, ADR-301).** raw zone(§2.1)이 로컬 fs+in-memory `RawStore`뿐이던 것을 가동 중인 **minio:RELEASE 컨테이너**에 영속화 — `MinioRawStore`(`minio_raw_store.py`) 신설. §2 객체 레이아웃(`raw/<source_id>/<doc_id>/{content.bin, fetch.json}`)대로 객체 키를 두고, **content-hash idempotency**(동일 bytes=동일 doc_id, no-op)와 **ADR-301**(동일 url 변경분=새 doc_id 보존, 덮어쓰기 금지)을 보장한다. fetch.json은 §2.2 핵심 필드(doc_id/source_id/url/content_hash/fetched_at) 기록 — license/robots 등 governance(11) 필드는 후속. 전용 버킷 격리 테스트로 **round-trip·idempotency·ADR-301·객체 레이아웃** 검증. 전 과정 TDD — 스위트 430→**436개 통과**. 드라이버 `minio` 추가(오프라인 시 importorskip skip). scope ② — provenance 게이트(§8)는 후속 증분 ③.
- **저장 계층 키스톤 ① — PostgreSQL `graph_mutations` SoT + replay (design 03 §7, ADR-304/307).** append-only mutation log가 in-memory `list`뿐이던 것을 가동 중인 **postgres:16 컨테이너**에 영속화 — `PostgresMutationLog`(`postgres_mutation_log.py`) 신설. §7.1 스키마(`mutation_id PK, idempotency_key UNIQUE, op, payload, resolution_ref, actor, version_tuple, correlation_id, tx_time`)대로 `graph_mutations` 테이블을 생성하고, 기존 `MutationLog`의 append-only/idempotency 계약(불변식 §3-3/§3-6)을 유지한다. 전용 테이블명 격리 테스트로 **append-only·순서 보존 replay(ADR-304)·동일 `idempotency_key` no-op**을 검증. 전 과정 TDD — 스위트 424→**430개 통과**. 드라이버 `psycopg[binary]` 추가(오프라인 시 테스트 skip, 연결 없이 424 유지). scope ① — MinIO raw(§2)·extraction_records 게이트(§8)는 후속 증분.
- **골든·승격 기준선 재검증 (Phase 0→1 게이트 ③).** curated zone의 골든 22건 + 저장 기준선(vt-adf4482…, superseded)으로 평가 스위트(S36)·promotion dry_run(S38–40) 재실행: canonicalization F1=1.0/P=1.0 유지, **회귀 0건, suite PASS**, dry_run INITIALIZED/passed (S41 리포트와 동일 상태 재현). 호스트 venv와 prototype 컨테이너 양쪽에서 동일 결과 — 게이트 ①·③ 충족, ②(Q4/Q6)는 Phase 1 부하 측정 예약.
- **1만 문서 샘플 확보 (Phase 0 완료 조건 ①).** 컨테이너 기반 `collect_large --limit 10000 --sec 5` 실행으로 arXiv 1만 처리(saved 9,979 / skipped 21 / errors 0) + RSS 30 + SEC 5 — 총 raw 11,361건. 과정에서 abs 페이지 스크레이핑이 anti-bot 429를 반복 유발(크래시 4회)해 **04 §1.4 정본 경로(API metadata CC0)로 수집 전환**: `ArxivConnector.discover_entries`(entry 원문 XML을 raw 문서로, 문서당 GET 0회, 페이지 1000건×10회), `_with_retry`(429/5xx·URLError/Timeout 지수 backoff·Retry-After 준수), 파서 Atom entry 지원(`extract_html` 분기). 전 과정 TDD — 스위트 407→424개 통과. 신규 XML 문서 파싱 E2E 검증(title/published/segments) 완료.
- **infra: docker-compose 스택 착수 (design 01 §6.1 부분 구현).** postgres/minio/neo4j/opensearch 4종을 버전 고정·healthcheck·named volume으로 구성, prototype viewer는 `--profile prototype` 컨테이너(python:3.12-slim, `data/` 볼륨 마운트, `VIEWER_HOST` 바인딩 주입)로 선택 실행. api/worker는 FastAPI 코드 확보 후, grafana는 메트릭 소스 확보 후 추가. 크리덴셜은 `.env` 주입(`.env.example` 갱신).

### 2026-08-03
- **D 항목 확정 — 잔여 Open Question·Phase 게이트 (Q4/Q6/Q3·Phase 1).** 남은 할일(D)의 측정 가능 기준을 설계 정본에 게이트로 명시 (Phase 1에서 측정·판정):
  - **Q4 (06 §9)** — Neo4j 한계 측정 게이트: 노드 ≥1e6, 그래프 조회 p95 ≥500ms, 재구축 > 증분 10× → Memgraph 물리 분리/교체 (ADR-601/603 저장소 추상 유지).
  - **Q6 (03 §9)** — Iceberg 승격은 Scale(100만)·증분 처리 단계에서 기준 수립 (Phase 1 관측 대기).
  - **Q3 (10 §7)** — ER은 결정적 exact match 채택으로 회피 해소; embedding/LLM ER 도입 시에만 dev 실측 + test 게이트(P≥0.97) 재적용 (데이터 다변화 후).
  - **Phase 0→1 진입 게이트** — 1만 문서 확보(사용자 arXiv 실행)·Q4/Q6 첫 측정·골든/승격 기준선 재검증. DoD ①②는 prototype에서 충족(S27/S37).
- **Q5 기준선 실측 (B1).** dev proxy(bunker-flash)로 실제 LLM 판정 3쌍(canonicalization)을 실행해 S42 usage 집계로 **토큰·비용 기준선 확보**: input 628 / output 160 tokens, **호출당 ≈0.0014 USD**(placeholder 환산). 문서당·조사당 비용 목표는 Phase 1 하이브리드 대량 실행에서 확정 (design 10 §1.4). 전체 arXiv 1만 수집(`--limit 10000 --sec 5`)은 사용자 실행 대기.

### 2026-08-03 (이전 — 새 기능 트랙)
- **새 기능 트랙 완성 — LLM 저장-기반 조사 에이전트 (S43–S47, 07 조사 루프).** 소비·평가 계층(S28–S41)을 **read-only·evidence-first**로 재사용해 조사 사이클을 prototype 완결:
  - **S43 evidence coverage** (07 §4·10 §1.3) — subclaim별 근거 coverage·gap·expected_info_gain.
  - **S44 Graph Explorer** (07 §3.3) — subgraph + relation_paths + independence_summary (S26/S29 재사용).
  - **S45 Counter-Evidence** (07 §3.6) — hypotheses + negative_queries + 모순 후보(근거·판정 이유 포함, binary 금지).
  - **S46 Investigation Runner** (07 §4) — coverage→explorer→counter-evidence 루프, 종료(coverage≥0.80 / no_new_evidence / budget).
  - **S47 Synthesis/Audit** (07 §9.3·README §3-5) — 결론 봉투(09 §4) + evidence-first report(asserted/fact는 claim_ref 필수) + Audit 위반 차단.
  - **공통 불변식**: Agent는 graph mutate 금지(§3-3), 무출처 문장은 prediction만(§3-5), 결정적·TDD, main 직접 머지.
- **평가·승격 트랙 완성 (S38–S41).** design 10 3/6 승격 게이트 종단 구현 + Q2/Q3/Q5 진행:
  - **S38 durable promotion gate** — last-promoted baseline을 zone 영속(10 §3.1, ADR-1003), active/superseded 승격 이력.
  - **S39 end-to-end promotion pipeline** — EvalSuite→PromotionGate 자동 승격/차단 (PROMOTED/BLOCKED/INITIALIZED).
  - **S40 5-axis version-aware** — 5축 tuple(03 §7.1) fingerprint baseline, 온톨로지 major bump 시 전량 재평가(revalidate_required).
  - **S41 phase0 report** — 실데이터 승격 적용 + Q3/Q5 최소 실측 (29 claim confidence 균일 0.8, 결정적-only → LLM 비용 미측정 표기).

### 2026-08-03 (이전 — Q3–Q6)
- **Q3–Q6 결정 및 Q5 진행(S42).** Open Question 상세 리스트업 후 권장안으로 확정:
  - **Q3 해소(회피)** — ER은 결정적 외부식별자 exact match만 자동 병합(05 ADR-507)이라 임계값 튜닝 대상 아님. 점수·LLM 고신뢰는 POSSIBLY 후보만 유지(precision-first).
  - **Q4·Q6 Phase 1 예약** — 그래프 DB 한계·Iceberg 트리거는 규모 부족(prototype in-memory·DuckDB/parquet)으로 관측 대기, 10만 문서 진입 시 06/03 정본에서 측정·확정.
  - **Q5 진행(S42)** — `ClaudeJudge`에 토큰·비용 누적 추가(`usage()`/`cost_usd()`, design 10 §1.4): LLM 판정 호출 input/output tokens 집계, token→USD 환산 placeholder. 기준선은 Phase 1 실제 LLM 하이브리드 실행에서 확정.

### 2026-08-03 (이전 — Q2, prototype)
- **Q2 해소 — near-dup MinHash 임계값 실측.** 초기 수집 395문서 MinHash Jaccard 분포를 측정: intra/inter 모두 0.5~0.7 겹침(진짜 복제만 0.9+), 단일 임계 신뢰 판정 불가 확인 → 설계 04 ADR-403의 3-tier(MinHash→embedding→LLM ③) 전략 재확인. prototype `JACCARD_THRESHOLD`를 (구)0.6 → **0.90**으로 상향해 확실한 복제만 병합, 애매(0.80~0.90)는 수준 ③ 위임. (구)0.6 오결합 후보 5152쌍 실증 제거, 신규 임계에서 진짜 복제 6쌍만 잡음. [04 ADR-403](./design/04-ingestion-and-parsing.md)에 실측 근거 기록.

### 2026-08-03 (이전 — Phase 0 prototype 구현)
- **Phase 0 prototype 전방위 구현 (S1–S37).** Review 확정 스펙(0.1.0)의 **결정적+LLM 하이브리드 파이프라인**을 TDD(Red→Green)로 구현·검증. git 이력(`protoal/plain commit`, `feat(S#)`), 단계 계획(`.claude/plans/s#-*.md`)이 기록 지점.
  - **결정적 체인** — 수집(S1–S3 SEC/arXiv) → 중복(S4) → 파싱(S5) → ER/해소(S6) → claim 추출(S7) → 게이트(S8, S13) → 캐노니컬(S9) → 모순(S10) → assertion(S11) → 그래프 mutation(S15–S18). **bitemporal AS-OF**(S25, ADR-606).
  - **LLM 계층** — ClaudeJudge(S21)·결정적-우선 하이브리드(S22)·판정 영속(S23), ADR-507 노-자동-병합 준수.
  - **통합** — `pipeline_runner` 단일 진입점(S24)·Investigation subgraph(S26)·통합 불변식(S27, 실버그 발견·수정).
  - **소비 계층 (read-only)** — Catalog cursor 페이징(S28)·어세션 근거·다차원 신뢰도(S29, 09 §4)·subject 결론(S30, 09 §3)·랭킹(S31)·API 파사드(S32, 09 §2/§3). browser viewer 실행(S32 후속, 로컬 확인).
  - **평가 계층 (read-only)** — P/R/F1 하네스(S33)·골든셋 영속(S34, 10 §2.3)·회귀 실행기(S35, 10 §3/ADR-1008)·평가 스위트 러너(S36, 10 §6). **전 계층 E2E 불변식**(S37) 추가.
  - **실데이터 검증** — 395문서 수집(소량, 수동 coronary), 29 assertion 전 계층 E2E 일관성. 전체 테스트 318 passed.
  - **Open Question 진행** — Q2 dup(MinHash), Q3 ER/컨피던스 임계값, Q5 LLM 비용 — 하네스·회귀 토대 완성, **dev 파티션 실측 튜닝은 후속** (10 §2.4/§3.2, ADR-1008 placeholder).

### 2026-08-03 (기존 — 설계 리뷰·스펙 확정)
- **초기 Scout 5종 선정 (Q1 해소).** 미국 중심 AI 반도체·데이터센터 공급망 도메인의 초기 소스를 웹 리서치(실제 API/RSS 검증)로 선정: **SEC EDGAR**(gov)·**arXiv**(research)·**CHIPS/NIST**(gov)·**NVIDIA Newsroom**(official)·**SemiEngineering**(press). 전 source 공식 API/RSS로 수집 가능(Easy), 재배포 전면 제한(`allow_redistribute=false`, 11 §5.4 정합). 상업 테크 프레스(EE Times·The Register·TechCrunch)는 robots.txt가 AI 크롤러(`anthropic-ai`/`ClaudeBot`)를 차단해 초기 세트 제외, TSMC는 Cloudflare 403 제외. 구체 스키마·라이선스·수집 제약은 [04 §1.4](./design/04-ingestion-and-parsing.md) 정본. Open Question Q1 해소.
- **설계 문서 Review 승격 (리뷰 패스 완료).** 12개 문서를 blueprint 충실도·7 불변식·상호참조·구현가능성 기준으로 병렬 심층 리뷰(문서별 11 + 상호 일관성 스윕 1). BLOCKER 3 + MAJOR 36 + MINOR 다수를 문서에 직접 반영 후 독립 재검증(전항목 PASS). 상태 `Draft`→`Review`. Spec은 0.1.0 유지(Stable 변경 아님).
  - **BLOCKER 해소:** (1) 06 Applier에 `unmerge` op 분기 추가(merge 가역성·불변식 3·4) (2) 02 미정의 `TimeInterval` 노드/`VALID_DURING` 엣지 폐기, valid time을 inline 속성 단일 표현(ADR-206) (3) 02 `Assertion` 속성표 신설 + Claim→Assertion materialization 계약(ADR-207).
  - **교차 결정(사용자 확정):** 독립 증거 수 = **출처(source) 단위**(11 §1.4 정본, 04 위임, 09 `independent_source_count`); ER LLM '동일' 판정 → **`POSSIBLY_SAME_AS` 후보만, 확정 병합은 인간확인/결정적 식별자로만**(precision-first, 05 ADR-507).
  - **정합 반영:** 버전축 4→**5축**(`extraction_code_version` 포함); 보고서 문장 `kind`→정본 `modality{fact,asserted,opinion,prediction}`(07↔09); mention ID `men-` 접두사 등록; quarantine 논리 분리(라벨)→확장 시 물리(06 ADR-603); `allow_redistribute` 재배포 게이트(04↔11); alert `campaign_id`→`investigation_id`; retention_class 정책(11); 03 promoted-claim 저장·assertions=projection 재정의; 08 hybrid fusion(RRF k=60)·embedding/reranker 핀(bge-m3); 09 authz·테넌시; 10 slo-gate 분리·held-out partition·회귀 tolerance.
- **설계 SSOT 착수.** `docs/design/` 신설. 백본 문서 작성: README(규약·ID 체계·불변식), 01-architecture, 02-ontology(v1.0.0), 03-storage-and-data-model.
- 하위 스펙 04–11 초안 작성 (수집·해소·그래프·LLM/에이전트·검색·API·평가·관측/거버넌스).
- **상호 참조 일관성 검수 완료.** 불변식 위반 없음. 수정 반영: (a) `graph_mutations.op` enum에 `unmerge` 추가(03/08/09) (b) Signal Spire 트리거 enum 09↔11 통일(정본 11 §4.1) (c) S7 idempotency key를 `mutation_id`→`idempotency_key`(stage input 해시)로 정정(01/11) (d) `MEMBER_OF` 엣지 02 §3 등재 (e) `segments.norm_char_end` 추가(양방향 offset 매핑) (f) `clus-` 접두사·운영 ID·버전 필드명 별칭 정합.
- **UI 목업 세분화.** 설계(blueprint §1.4 공간계층)에 따라 War Table 단일 목업을 8개 Citadel 공간 화면으로 세분화(`docs/mockups/`): index + Citadel Gate·Watchtower·Grand Archive·Hall of Witnesses·War Table·Council Chamber·Chronicle Vault·Signal Spire. 공유 셸 재사용, 렌더링 검증 완료. 일러스트 생성 프롬프트(`docs/mockups/illustration-prompts.md`) 추가.
- **목업 시각화 완료(마무리).** 자산 22종 연결·검증 완료:
  - 브랜드 문장 `crest-hero`(index·Gate), 화면 히어로/masthead 8종(pixel-art, `orc-citadel-hero.png` 스타일).
  - 캐릭터 초상 5종(orc-camp 복사): Council 8-Agent roster 아바타 + Gate 온보딩 + Hall 안내.
  - 빈 상태 6종 → `empty-states.html` 갤러리(no-data 조건부라 갤러리로 통합).
  - 처리 상태 2종: orc-camp 애니메이션 재사용(CSS `steps()`, `prefers-reduced-motion` 정지) — Watchtower 수집·Council 추론.
  - 일러스트 프롬프트 전량 픽셀아트·복붙용(preamble 인라인)으로 통일. 전 목업 asset 참조·링크·파싱 최종 검증 통과.
- 본 로드맵 신설.

## 6. 열린 질문 (Open Questions)

설계 확정 전 해소가 필요한 항목. 해소 시 해당 design 문서 ADR로 이전한다. (Q1은 2026-08-03 해소 → [04](./design/04-ingestion-and-parsing.md) §1.4, Q2는 2026-08-03 해소 → [04](./design/04-ingestion-and-parsing.md) ADR-403, Q3은 2026-08-03 결정 → [05](./design/05-resolution-and-extraction.md) ADR-507.)

| # | 질문 | 관련 스펙 | 상태 |
| --- | --- | --- | --- |
| Q3 | Entity Resolution accept/reject 임계값 | 05, 10 | ✅ **결정적 ER 채택으로 회피 해소** — 자동 병합 경로는 결정적 외부식별자 exact match뿐(ADR-507), 점수·LLM은 POSSIBLY 후보만 유지 → 임계값 튜닝 대상 아님 |
| Q4 | 그래프 DB: Neo4j Community 한계 | 06, 01 | ⬜ **Phase 1 부하 후 판정 예약** — in-memory prototype 규모로 측정 불가, 10만 문서 진입 시 06 정본·교체 비용 격리(저장소 추상) 유지 |
| Q5 | LLM 비용 목표 실측 | 07, 10 | 🟡 **집계 인프라(S42) + 기준선 실측(B1)** — dev proxy(bunker-flash) 실제 LLM 판정 3쌍: input 628/output 160 tokens, **호출당 ≈0.0014 USD** (placeholder 환산) |
| Q6 | Iceberg 승격 트리거 정량화 | 03, 01 | ⬜ **Phase 1 범위로 설계 확정** — DuckDB/parquet 단계에선 관측 미대상, 확장 시 트리거 기준 정량화 |
