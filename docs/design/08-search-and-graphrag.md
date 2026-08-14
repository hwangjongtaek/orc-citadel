# 08 · 검색·GraphRAG

> **상태:** Review · **Spec:** 0.1.0 · **Blueprint 매핑:** §10
> 상위 규약: [README](./README.md) · 관련: [03-storage](./03-storage-and-data-model.md), [06-graph](./06-graph-service.md), [07-llm](./07-llm-and-agents.md)

Citadel의 검색은 단일 벡터 RAG가 아니라 **BM25 · Vector search · Graph traversal 세 경로**를 조합하는 GraphRAG다. 본 문서는 Search Service([`01`](./01-architecture.md) §3 컴포넌트, S8 Index stage)의 인덱스 설계, Agent의 질의 분해 계약, hybrid ranking, 최종 context 구성 계약을 확정한다.

핵심 불변식(→ [`README`](./README.md) §3):

- **검색 인덱스는 SoT가 아니다.** OpenSearch 인덱스는 curated zone([`03`](./03-storage-and-data-model.md))과 War Table([`06`](./06-graph-service.md))에서 **전량 재구축 가능한 파생물**이다 (§3-1).
- **질문을 무조건 벡터 검색으로 보내지 않는다.** Agent가 질문을 구조화 분해한 뒤 경로를 선택한다 (blueprint §10).
- **최종 context는 전체 문서가 아니라** 필요한 source span + claim + provenance + 주변 그래프다 (blueprint §10, Evidence-first §3-5).

---

## 1. 3경로 검색 (Three-Path Retrieval)

blueprint §10의 세 경로를 인덱스 대상·용도로 확정한다. 세 경로는 배타적이지 않으며 하나의 하위 질문에 대해 병렬 실행 후 통합된다(§4 hybrid ranking).

| 경로 | 강점 용도 | 인덱스/대상 | 반환 단위 | 소유 저장소 |
| --- | --- | --- | --- | --- |
| ① **BM25** | 정확한 명칭·희귀 표현·식별자·수치·따옴표 인용 | `documents`·`segments` 텍스트 | `segment_id` | OpenSearch (`os-segment`) |
| ② **Vector search** | 의미적으로 유사한 문장·주장(표현이 다른 동의 명제) | `segment` / `claim.canonical_text` 임베딩 | `segment_id` / `clm-id` | OpenSearch (`os-vector-*`) |
| ③ **Graph traversal** | 엔터티·사건·시간·증거 관계(경로 질의) | War Table(materialized graph) | `clm`/`evd`/`asr`/entity id | Neo4j([`06`](./06-graph-service.md)) |

### 1.1 각 경로 상세

- **① BM25** — lexical 정확성이 필요한 경우에 우선한다. 회사 legal name, ticker/LEI, 제품 버전 문자열, 규제 조항 번호, 드문 기술 용어, 원문 그대로의 인용구 검색에 강하다. Vector가 놓치는 "정확히 이 표기"를 잡는다. 대상은 `segments.text`(문장·문단·표 셀)와 `documents`의 title/authors.
- **② Vector search** — "표현은 달라도 의미가 같은" 문장·주장을 찾는다. 두 벡터 인덱스로 분리한다: (a) **segment 임베딩** — 원문 문장 근접 검색(신규 evidence 후보 발굴), (b) **claim canonical_text 임베딩** — 이미 그래프에 있는 정규 명제와의 의미 유사 claim 검색(claim similarity, §3). object/predicate가 달라도 의미가 겹치는 claim을 후보로 만든다.
- **③ Graph traversal** — "누가·언제·무엇에 대해·어떤 증거로"를 구조로 질의한다. entity lookup → relation traversal, 시간 조건(inline `valid_from`/`valid_to`, bitemporal AS-OF → [`03`](./03-storage-and-data-model.md) §6.3), 증거 관계(`SUPPORTS`/`CONTRADICTS`), 출처 독립성(`DERIVED_FROM`/`dup_clusters`)을 따라간다. **predicate traversal은 논리적 질의다**: 관계는 reification되어 있으므로(`Org -SUBJECT→ Claim{predicate} -OBJECT→ Org`, → [`02`](./02-ontology.md) §2.4, [`06`](./06-graph-service.md) §2.2) `predicate`로 훑는 것은 물리 엣지가 아니라 Claim 노드를 경유해 확장된다. Graph는 텍스트 랭킹이 아니라 **관계·경로·시간 제약**의 정답을 제공한다.

> 경로 선택 원칙: 명칭·식별자가 명확하면 ①·③을 먼저, 의미 탐색·공백 발굴이면 ②를 우선한다. Agent가 §3 분해 결과로 경로별 subquery를 배분한다.

---

## 2. 인덱싱 (S8) — OpenSearch 인덱스 설계

[`01`](./01-architecture.md) §4 stage **S8 Index**를 인덱스 계약으로 확정한다. idempotency key = `element_id + index_version`(→ [`01`](./01-architecture.md) §4 idempotency 규약 정합; `element_id`는 `doc_id` scope를 포함하는 복합 ID), 재실행 단위 = element.

### 2.1 인덱스 구성

초기 구성은 단일 OpenSearch 인스턴스(→ [`01`](./01-architecture.md) §5; 본 문서 §8 ADR-801). 세 개의 논리 인덱스를 둔다.

| 인덱스 | 대상 | 유형 | 임베딩 |
| --- | --- | --- | --- |
| `os-segment` | normalized `segments` | BM25 (문서/segment 전문) | — |
| `os-vector-segment` | `segments` 문장 | k-NN 벡터 | segment `text` 임베딩 |
| `os-vector-claim` | authoritative `Claim` | k-NN 벡터 | `claim.canonical_text` 임베딩 |

- **무엇을 임베딩하나:** 원문 텍스트 전체가 아니라 **segment 문장**과 **claim의 `canonical_text`**만 임베딩한다(→ [`02`](./02-ontology.md) §2.4, ADR-802). Evidence는 별도 임베딩하지 않고 소속 `segment`/`claim` 벡터로 검색 후 provenance로 연결한다.
- `index_version`은 모든 문서에 부착된다. 임베딩 모델·차원·분석기 변경은 `index_version` bump → **전량 reindex** 트리거이며, 인덱스가 파생물이므로 curated/graph에서 재구축한다(불변식 §3-1).

### 2.2 BM25 인덱스 매핑 예시 (`os-segment`)

```json
{
  "settings": {
    "index": { "number_of_shards": 1, "number_of_replicas": 0 },
    "analysis": {
      "analyzer": {
        "citadel_text": { "type": "standard" },
        "citadel_ko":   { "type": "nori" }
      }
    }
  },
  "mappings": {
    "properties": {
      "segment_id":       { "type": "keyword" },
      "doc_id":           { "type": "keyword" },
      "source_id":        { "type": "keyword" },
      "source_type":      { "type": "keyword" },
      "kind":             { "type": "keyword" },
      "language":         { "type": "keyword" },
      "text":             { "type": "text", "analyzer": "citadel_text",
                            "fields": { "ko": { "type": "text", "analyzer": "citadel_ko" } } },
      "entity_ids":       { "type": "keyword" },
      "publication_time": { "type": "date" },
      "valid_from":       { "type": "date" },
      "valid_to":         { "type": "date" },
      "dup_cluster_id":   { "type": "keyword" },
      "is_root_doc":      { "type": "boolean" },
      "mention_surfaces": { "type": "text", "analyzer": "citadel_text",
                            "fields": { "ko":  { "type": "text", "analyzer": "citadel_ko" },
                                        "raw": { "type": "keyword" } } },
      "status":           { "type": "keyword" },
      "index_version":    { "type": "keyword" }
    }
  }
}
```

- filter 필드(`source_type`, `language`, `entity_ids`, `publication_time`, `valid_*`, `dup_cluster_id`, `status`)로 §3의 temporal constraint·source-type filter·독립성 축소를 인덱스 레벨에서 지원한다.
- **`status`(`authoritative`|`quarantine`|`superseded`) 기본 필터.** 모든 기본 검색 질의는 `status = authoritative` 절을 암묵 포함한다(quarantine·superseded 누출 방지, 불변식 §3-2·§2.4). Audit/Counter-Evidence 등 명시적 opt-in 질의만 다른 status를 조회한다.
- **`mention_surfaces`** — 아직 entity로 해소되지 않은 surface 문자열(별칭·표기 변형)을 색인해, `entity_lookup` 미해소 시 BM25 mention 후보 검색(§1.1·§3.1)의 대상 필드로 쓴다.

### 2.3 벡터 인덱스 매핑 예시 (`os-vector-claim`)

```json
{
  "settings": { "index": { "knn": true } },
  "mappings": {
    "properties": {
      "clm_id":            { "type": "keyword" },
      "canonical_claim_id":{ "type": "keyword" },
      "subject_id":        { "type": "keyword" },
      "predicate":         { "type": "keyword" },
      "object_id":         { "type": "keyword" },
      "modality":          { "type": "keyword" },
      "valid_from":        { "type": "date" },
      "valid_to":          { "type": "date" },
      "provenance_ref":    { "type": "keyword" },
      "status":            { "type": "keyword" },
      "embedding": {
        "type": "knn_vector",
        "dimension": 1024,
        "method": { "name": "hnsw", "space_type": "cosinesimil", "engine": "lucene" }
      },
      "embedding_model":   { "type": "keyword" },
      "index_version":     { "type": "keyword" }
    }
  }
}
```

- `os-vector-segment`는 위와 동일 구조에서 `clm_id` 대신 `segment_id`/`doc_id`를 키로 가지며 `status`도 동일하게 부착한다.
- 벡터 인덱스도 `subject_id`/`predicate`/`valid_*`/`status`를 저장해 **k-NN + pre-filter**(구조·시간·상태 축소 후 유사도 검색)를 수행한다. k-NN pre-filter에도 §2.2와 동일한 `status = authoritative` 기본 절이 적용된다.
- **임베딩·reranker 모델 핀(→ §8 ADR-809):** dense embedding = `BAAI/bge-m3`(multilingual, **1024-dim**, cosine), reranker = `BAAI/bge-reranker-v2-m3`(cross-encoder). `embedding_model` 필드에 모델 ID+개정을 기록하고, 모델·차원 변경은 `index_version` bump → 전량 reindex(§2.4) 트리거다. 이 핀은 08 소유이며 [`07`](./07-llm-and-agents.md)는 이를 참조만 한다(07↔08 순환 소유 해소).

### 2.4 갱신 — 증분 인덱싱 (신규 element만)

- S8은 curated/graph 변경을 구독해 **신규/변경 element만 증분 색인**한다. 재실행 단위가 element이므로 전체 corpus reindex를 피한다([`01`](./01-architecture.md) S8).
- idempotency: `element_id + index_version` upsert. 동일 element·동일 index_version 재수신은 no-op(불변식 §3-6).
- **동기화 원천(sync source) = graph mutation event.** S8은 War Table의 mutation event 스트림(`create_node`/`create_edge`/`merge_entity`/`unmerge`/`supersede`/`delete`/`quarantine`, → [`03`](./03-storage-and-data-model.md) §7.1, [`06`](./06-graph-service.md) §3.2)을 구독해 대응 문서의 `status`를 갱신한다: `quarantine`→`status=quarantine`, `supersede`→(이전 버전)`status=superseded`, `delete`→문서 제거, 그 외→`status=authoritative`. **quarantine·superseded 문서는 기본 검색에서 제외**(§2.2 기본 필터)하되 인덱스에서 즉시 삭제하지 않고 `status` 플래그로 관리한다(재현·감사·복구 가능).
- **`os-vector-segment` delta.** segment 벡터는 normalized `segments`의 신규/변경(재정규화·재분절)분에만 재임베딩·upsert하며, 텍스트 무변경 segment는 no-op이다(`embedding_model`·`index_version` 무변경 시).
- `index_version` 변경 시에만 전량 reindex. 그 외에는 증분만 수행한다. 전량 reindex는 **무중단 alias swap**으로 반영한다: 새 `index_version` 물리 인덱스를 뒤에서 빌드한 뒤 read alias(`os-vector-claim` 등 논리명)를 원자적으로 교체하고 구 인덱스를 회수한다.

---

## 3. 질의 분해 (Query Decomposition)

blueprint §10: **질문을 무조건 벡터로 보내지 않는다.** Retrieval Agent([`07`](./07-llm-and-agents.md))가 하위 질문을 아래 구조로 분해하고, 각 요소를 적절한 경로(§1)에 배분한다.

```text
Entity lookup
+ temporal constraint
+ relation traversal
+ claim similarity search
+ source-type filter
```

### 3.1 분해 계약 (구조화 스키마)

Agent는 자유 텍스트가 아니라 다음 구조화 객체를 산출한다(structured output, version-pinned).

```json
{
  "subquestion_id": "sq-01J9...",
  "text": "2024년 이후 A사의 AI 가속기 공급망 다변화가 실제로 진행되었는가",
  "entity_lookup": [
    { "surface": "A사", "resolved_entity_id": "org-01J9...", "role": "subject" },
    { "surface": "AI 가속기", "resolved_entity_id": "prd-01J9...", "role": "about" }
  ],
  "temporal_constraint": {
    "valid_from": "2024-01-01", "valid_to": null,
    "as_of_transaction_time": null, "time_precision": "month"
  },
  "relation_traversal": [
    { "from": "org-01J9...", "predicate": "supplies", "direction": "in", "max_hops": 2 },
    { "from": "org-01J9...", "predicate": "depends_on", "direction": "out", "max_hops": 1 }
  ],
  "claim_similarity": {
    "enabled": true,
    "seed_text": "A사가 공급처를 다변화했다",
    "predicate_hint": ["supplies", "depends_on", "partners_with"],
    "top_k": 50
  },
  "source_type_filter": ["official", "exchange", "gov"],
  "independence_required": true,
  "path_plan": ["graph", "bm25", "vector"]
}
```

| 필드 | 경로 매핑 | 설명 |
| --- | --- | --- |
| `entity_lookup` | ③ Graph / ① BM25 | surface를 resolved entity로. 미해소면 BM25 mention 검색으로 후보화 |
| `temporal_constraint` | ③ Graph / filter | valid time + transaction time AS-OF([`03`](./03-storage-and-data-model.md) §6.3), 인덱스 date filter |
| `relation_traversal` | ③ Graph | predicate·방향·hop 수로 subgraph 경로 질의 |
| `claim_similarity` | ② Vector(`os-vector-claim`) | 의미 유사 claim 후보. `predicate_hint`로 pre-filter |
| `source_type_filter` | filter(전 경로) | official/press/gov/research/exchange([`02`](./02-ontology.md) §2.3) |
| `independence_required` | ③ Graph / filter | `dup_clusters`로 독립 근거만(§1.1, blueprint §11) |
| `path_plan` | 실행 순서 | 우선순위 경로 배열 |

- **경로 배분 규칙:** `entity_lookup`이 해소되고 `relation_traversal`이 있으면 **Graph 우선**, `claim_similarity.enabled`면 벡터를 병행, 정확 명칭·식별자·인용은 BM25로 보낸다. 순수 의미 탐색이 아니면 벡터 단독으로 보내지 않는다.
- 분해 결과는 `subquestion_id` 단위로 저장되어 조사 루프([`07`](./07-llm-and-agents.md))의 evidence coverage 계산·재현에 쓰인다.

---

## 4. Hybrid Ranking

세 경로의 후보를 하나의 랭킹으로 통합한다. 원칙: **넓게 뽑고(recall) → 구조·시간으로 축소 → reranker로 정밀 정렬(precision)**.

### 4.1 후보 축소 파이프라인

```text
[분해] subquery per path (§3)
  → ① BM25 top_k_bm25 (segment)          ┐
  → ② Vector top_k_vec (segment/claim)    ├─ 병렬 후보 생성
  → ③ Graph traversal 경로 결과            ┘
  → 구조·시간·출처 pre-filter (predicate / valid time / source_type / independence)
  → dedup + 출처 계보 축소 (dup_cluster_id → root 1 + independent additions)
  → hybrid fusion (BM25 score ⊕ embedding score)
  → reranker (cross-encoder, top_n)        ← 모델 tier는 07 참조
  → context builder 입력 (top_m)
```

- **Canonical candidate unit = `claim`.** 이종 경로의 후보를 단일 단위인 **claim(`canonical_claim_id` 기준)**으로 정규화한 뒤 fusion한다. 경로별 원 후보와 claim의 매핑(segment→claim linkage):
  - ② `os-vector-claim`·③ Graph 결과는 이미 claim 단위다.
  - ① BM25(`os-segment`)·② `os-vector-segment`의 `segment_id` 후보는 해당 segment가 **근거로 참여한 claim**(`Claim -PROVENANCE→ segment`, → [`02`](./02-ontology.md) §2.4, [`03`](./03-storage-and-data-model.md) §8.3)으로 승격해 매핑한다. 아직 claim에 연결되지 않은 신규 segment span은 **후보 발굴용 unlinked 항목**으로 유지되어 Retrieval Agent(§7) 경로로만 넘어가고, claim proxy가 없으므로 fusion 랭킹과는 별도 트랙으로 둔다.
- **Fusion 방법 = RRF(Reciprocal Rank Fusion) 단일 채택.** claim c의 최종 점수 `score(c) = Σ_path w_path · 1/(k + rank_path(c))`, 기본 `k = 60`, 경로 가중 `w_bm25 = w_vector = 1.0`(초기값, 실측 조정 — → §8 ADR-808). 이종 점수 스케일(BM25 raw vs cosine)을 직접 가중합하지 않고 **rank 기반**으로 합쳐 스케일 정규화 문제를 회피한다.
- **Graph exact-match 주입 = 보장 포함셋(guaranteed inclusion).** ③ Graph traversal이 관계·시간 제약을 정확히 만족시킨 claim(경로 정답)은 RRF 점수와 무관하게 reranker 입력 top_n에 **무조건 포함**되며, RRF 합산 시 `rank_graph = 0`에 준하는 최상위 rank 기여(prior)를 받는다. exact 관계 정답이 유사도 랭킹에 밀려 탈락하지 않도록 보장한다.
- **출처 계보 축소:** 같은 `dup_cluster_id`의 복제 문서는 root 1개 + independent additions로 접어 독립 근거 수를 과대평가하지 않는다(blueprint §8.3, §11).
- **Reranker:** 후보 축소 후 소수(top_n)에만 cross-encoder reranker를 적용한다. **embedding·reranker의 모델·차원 핀은 본 문서(08)가 소유**하고(→ §8 ADR-809), 조사 예산에 따른 **모델 tier/호출 정책은 [`07`](./07-llm-and-agents.md)가 소유**한다(blueprint §9.2). 본 문서는 순서(fusion→rerank)와 모델 핀을 확정한다(ADR-803·808·809).
- 각 단계 `top_k`/`top_n`/`top_m`는 investigation budget([`07`](./07-llm-and-agents.md))에 종속된 튜너블 파라미터다.

> **구현 메모 (Phase 4 — 대량 embedding·LLM batch inference, 2026-08-12):** `batch_inference.py` — 08 hypothesis embedding 핀(§2.3)·ADR-802·809를 **인덱스 작성 측이 아니라 임베딩 호출 측**에서 봉인 (mock/실측 격리, Phase 4 DoD ①). **embedding 핀 = `BAAI/bge-m3`(1024-dim, `cosinesimil`)** — `EMBEDDING_MODEL`/`EMBEDDING_DIM`/`EMBEDDING_SPACE`, **08 소유**이며 07 은 참조만(07↔08 순환 소유 해소). `embeddable_kind` — **단지 segment/claim 만 임베딩**(ADR-802, 문서·evidence 비임베딩 — evidence 는 provenance 로 연결, §1.1②). `embedding_index_version` = model:dim 축약 — 모델·차원 변경 시 `index_version` 변화로 **전량 reindex 트리거**(§2.1, 불변식 §3-1 파생물). `embed_texts` — 대량 텍스트 일괄 임베딩, executor 주입 지점(실측 백엔드 격리), 각 항목에 `embedding_model`·`index_version` 부착(§2.1 정합). read-only(불변식 §3-3)·결정적. Spec 그대로(0.1.9). [10 §4.5](./10-evaluation-and-testing.md)의 batch inference 메모와 연결.

---

## 5. Context 구성 계약 (Context Assembly)

blueprint §10: 최종 context에는 **전체 문서가 아니라 필요한 source span + claim + provenance + 주변 그래프**만 넣는다. Evidence-first(§3-5)의 검색 측 구현이다.

### 5.1 Context 패킷 스키마

```json
{
  "subquestion_id": "sq-01J9...",
  "items": [
    {
      "claim_id": "clm-01J9...",
      "canonical_text": "A사는 B사 의존도를 2024년 축소했다.",
      "modality": "asserted",
      "source_span": {
        "doc_id": "doc-9f2a...c1",
        "segment_id": "doc-9f2a...c1#p12.s3",
        "char_start": 480, "char_end": 612,
        "quote": "…B사 비중을 30%로 낮췄다…"
      },
      "provenance_ref": ["ext-01J9..."],
      "evidence": [
        { "evd_id": "evd-01J9...", "relation": "supports", "evidence_type": "primary",
          "source_span": { "doc_id": "doc-3b7e...a2", "segment_id": "doc-3b7e...a2#p4.s1",
                           "char_start": 88, "char_end": 210, "quote": "…독립 출처의 확인 문장…" } }
      ],
      "neighbors": [
        { "edge": "CONTRADICTS", "claim_id": "clm-01JA...", "note": "동일 기간 반대 공시" }
      ],
      "source": { "source_id": "src-01J9...", "source_type": "exchange", "independent": true },
      "valid_from": "2024-01-01", "valid_to": null,
      "retrieval_paths": ["graph", "vector"],
      "score": 0.81
    }
  ],
  "token_budget": { "limit": 8000, "used": 5200, "policy": "span_over_document" }
}
```

### 5.2 구성 규칙

- **문서 전체 금지.** claim/evidence의 `source_span`(문장 단위 quote)만 포함하고, 필요 시 인접 segment 1개까지만 확장한다.
- **주변 그래프 포함.** 대상 claim의 `SUPPORTS`/`CONTRADICTS`/`QUALIFIES`/`SUPERSEDES` 이웃과 출처 독립성 신호를 함께 넣어 모순·시간 변화·독립 근거를 판단 가능하게 한다([`02`](./02-ontology.md) §3).
- **Provenance 필수.** 모든 항목은 `provenance_ref`와 `source_span`을 가진다. 없으면 context에 넣지 않는다(불변식 §3-2, [`03`](./03-storage-and-data-model.md) §8.3). **유일한 예외는 §6의 `source: "model_prior"` 항목**으로, 이는 provenance 없이 `included_in_conclusion: false`·`flag` 하에서만 gap 표시용으로 존재하며 결론·감사 대상에서 제외된다. 이로써 최종 보고서 문장을 원문까지 감사 가능하게 한다(blueprint §21-8).
- **토큰 예산.** `token_budget`을 초과하면 score 하위·중복 출처(dup_cluster)부터 제거하고, root 문서와 독립 additions를 우선 보존한다. 예산은 investigation budget([`07`](./07-llm-and-agents.md))에서 배정된다.

---

## 6. 모델 사전지식(Parametric Knowledge) 처리

blueprint §10 마지막 문단을 계약으로 강제한다.

- 그래프·검색으로 근거를 찾지 못한 정보를 모델 사전지식으로 보충하는 경우, 해당 진술은 **반드시 별도 표시**한다(`source: "model_prior"`).
- 사전지식 진술은 `provenance_ref`가 없으므로 **authoritative graph에 저장하지 않고**(불변식 §3-2, [`03`](./03-storage-and-data-model.md) §8.3), **기본적으로 최종 결론에서 제외**한다.
- context 항목에는 다음 플래그로만 존재할 수 있으며, 조사 gap을 드러내는 용도(어디에 근거가 없는지)로 쓴다.

```json
{
  "content": "일반적으로 첨단 로직 파운드리는 소수 공급자에 집중된다.",
  "source": "model_prior",
  "provenance_ref": [],
  "included_in_conclusion": false,
  "flag": "unverified_background"
}
```

- Synthesis/Audit Agent([`07`](./07-llm-and-agents.md))는 `source: "model_prior"` 문장을 검증 가능 문장으로 승격하지 않는다. 사용자에게는 "미검증 배경 지식"으로만 노출하거나 제거한다(blueprint §13, §21-8).

---

## 7. Retrieval Agent 연동 (→ [`07`](./07-llm-and-agents.md))

Retrieval Agent(blueprint §9.3)는 Search Service의 read API를 사용하며(그래프 직접 mutate 금지, [`01`](./01-architecture.md) §3 경계 규칙), **그래프 공백을 채울 문서 탐색**을 담당한다.

- **입력:** Graph Explorer가 식별한 공백/미해결 하위 claim([`07`](./07-llm-and-agents.md) 조사 루프의 `identify missing evidence`).
- **동작:** §3 분해 계약으로 subquery를 만들고, ① BM25(정확 명칭)·② Vector(의미 유사·`os-vector-segment`로 신규 문장 발굴)를 결합해 그래프에 아직 없는 문서/segment를 찾는다. Counter-Evidence Agent를 위해 부정 표현·반대 출처 유형·다른 시간 범위로도 탐색한다(blueprint §9.3).
- **출력:** 신규 evidence 후보(segment span)를 **Extractor → Lorekeepers → Graph Service** 경로로 넘긴다(직접 그래프 반영 금지, 불변식 §3-3). 반영 결과는 S8 증분 인덱싱(§2.4)으로 검색에 반영된다.
- **종료 기여:** 신규 독립 증거 발견률 감소가 조사 루프 종료 조건의 한 신호다(blueprint §9.4).

```text
Graph gap (07 Graph Explorer)
  → Retrieval Agent: decompose (§3) → BM25 + Vector (§1)
  → candidate segment spans (with provenance)
  → Extractor → Lorekeepers → Graph Service (mutation event, 06)
  → S8 incremental index (§2.4)
  → 다음 조사 iteration에서 검색 가능
```

---

## 8. 의사결정 로그 (ADR-8xx)

| ID | 결정 | 근거 | 상태 |
| --- | --- | --- | --- |
| ADR-801 | 검색은 **OpenSearch 단일 인스턴스**로 초기 구성, BM25·벡터를 한 엔진에서 운용 | 컴포넌트 최소화·단계적 도입([`01`](./01-architecture.md) §5, blueprint §7.2·§18). 인덱스 크기·QPS 증가 시 cluster 승격 | Accepted |
| ADR-802 | 임베딩 대상은 **segment 문장 + claim `canonical_text`만**, 문서 전체·evidence는 비임베딩 | 의미 검색은 문장/명제 단위가 최적, 비용·인덱스 크기 통제(blueprint §9.2·§18). evidence는 provenance로 연결 | Accepted |
| ADR-803 | 랭킹 순서는 **hybrid fusion(BM25⊕embedding) → reranker**, reranker는 축소된 top_n에만 | 후보 축소로 비용 통제 후 정밀 정렬. 모델 tier는 [`07`](./07-llm-and-agents.md)가 소유(blueprint §9.2) | Accepted |
| ADR-804 | 질문을 벡터 단독으로 보내지 않고 **구조화 분해(§3.1) 후 경로 배분** | GraphRAG 정체성, 관계·시간 정답은 그래프가 제공(blueprint §10) | Accepted |
| ADR-805 | context는 **span+claim+provenance+주변 그래프**만, 전체 문서 금지 + 토큰 예산 | Evidence-first(§3-5), 감사 가능성(blueprint §21-8) | Accepted |
| ADR-806 | 모델 사전지식은 `source:"model_prior"`로 표시, **기본 결론 제외·graph 미저장** | blueprint §10 마지막·§13, provenance 불변식 §3-2 | Accepted |
| ADR-807 | 검색 인덱스는 파생물, `index_version` 변경 시에만 전량 reindex·그 외 증분 | SoT는 lakehouse+graph(불변식 §3-1), 재구축 가능성 | Accepted |
| ADR-808 | hybrid fusion은 **RRF(`k=60`) 단일 방식**, candidate unit = **claim**(segment→claim linkage로 승격), graph exact-match는 **보장 포함셋** | 이종 점수 스케일 가중합 회피(rank 기반), 관계 정답 보존, 단일 정규화 단위로 dedup·독립성 축소 일관(§4.1). `k`·경로 가중은 실측 조정 | Accepted |
| ADR-809 | **embedding = `BAAI/bge-m3`(1024-dim, cosine), reranker = `BAAI/bge-reranker-v2-m3` 핀은 08 소유**, tier/호출 정책만 [`07`](./07-llm-and-agents.md) | 모델·차원 단일 소유로 07↔08 순환참조 해소, 인덱스 차원 정합. 모델 개정은 `index_version` bump + 무중단 alias swap, 성능은 [`10`](./10-evaluation-and-testing.md) 회귀로 검증 | Accepted |
