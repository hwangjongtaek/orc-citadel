# 06 · 그래프 서비스 (War Table)

> **상태:** Review · **Spec:** 0.1.0 · **Blueprint 매핑:** §8.9, §17
> 상위 규약: [README](./README.md) · 관련: [02-ontology](./02-ontology.md), [03-storage](./03-storage-and-data-model.md), [05-resolution](./05-resolution-and-extraction.md)

War Table은 조사자가 시간·근거·관계를 탐색하는 **serving 그래프**다. 본 문서는 [`02-ontology`](./02-ontology.md)의 시맨틱 레이어를 물리 그래프 DB로 매핑하고, [`03-storage`](./03-storage-and-data-model.md)의 `graph_mutations` 이벤트를 소비해 materialized graph를 구성·재구축하는 계약을 확정한다.

## 1. 위치와 역할

- **그래프는 SoT가 아니다** (불변식 [`README`](./README.md) §3-1). SoT는 immutable raw document + curated lakehouse table + append-only `graph_mutations` log이며, War Table 그래프는 이 log에서 **언제든 재구축 가능한 파생 serving representation**이다.
- 그래프 서비스가 소유하는 것: (1) 물리 그래프 스키마(라벨·관계·인덱스), (2) mutation 이벤트를 그래프에 적용하는 **Applier**, (3) authoritative/quarantine 분리, (4) rebuild/replay, (5) 조회 API.
- 그래프 서비스가 소유하지 **않는** 것: 온톨로지 정의([`02-ontology`](./02-ontology.md)), 저장 스키마·이벤트 스키마·bitemporal 원장([`03-storage`](./03-storage-and-data-model.md)), 해소·추출 판정([`05-resolution`](./05-resolution-and-extraction.md)).
- **저장소 선택.** 초기 **Neo4j Community Edition**(단일 인스턴스, [`01-architecture`](./01-architecture.md) 스택). Community는 다중 DB·클러스터링이 제약되므로 authoritative/quarantine는 **라벨 분리**로 구현한다(§4). 확장 시 **Memgraph** 등 대안으로 교체하되, 물리 스키마 매핑(§2)과 Applier 계약(§3)은 저장소 독립적으로 유지해 교체 비용을 격리한다.

## 2. 물리 그래프 매핑

[`02-ontology`](./02-ontology.md) §2–3의 노드/엣지 타입을 Neo4j 라벨·관계타입·속성으로 매핑한다.

### 2.1 노드 라벨

| 온톨로지 노드 | Neo4j 라벨 | 상태 라벨(추가) |
| --- | --- | --- |
| Person/Organization/Product/Technology/Location | `:Entity:Person` 등 (공통 `:Entity` + 세부) | `:Authoritative` \| `:Quarantine` |
| Event | `:Event` | 동일 |
| Document / Source | `:Document` / `:Source` | 동일 |
| Claim / CanonicalClaim | `:Claim` / `:CanonicalClaim` | 동일 |
| Evidence / Assertion | `:Evidence` / `:Assertion` | 동일 |
| Investigation | `:Investigation` | — |

- 모든 노드는 공통 속성 `id`, `type`, `created_tx`, `ontology_version`을 가진다([`02-ontology`](./02-ontology.md) §2.1). `provenance_ref`는 Claim/Evidence/Assertion 필수.
- 상태 라벨(`:Authoritative`/`:Quarantine`)은 §4의 게이트 결과를 표현한다.

### 2.2 관계 타입과 reification

[`02-ontology`](./02-ontology.md)는 관계를 `Claim` 노드로 **reify**한다. 따라서 `subject`/`object`/`speaker`는 Claim의 속성이 아니라 **그래프 관계**로 저장한다(그래프 탐색·경로 질의 대상이 되도록).

```cypher
// Claim reification: subject/object/speaker를 관계로
(:Entity {id:'org-A'})-[:SUBJECT]->(:Claim {id:'clm-1'})
(:Claim {id:'clm-1'})-[:OBJECT]->(:Entity {id:'org-B'})
(:Entity {id:'org-A'})-[:MADE_CLAIM {via_document_id:'doc-…'}]->(:Claim {id:'clm-1'})  // speaker
(:Claim {id:'clm-1'})-[:MEMBER_OF]->(:CanonicalClaim {id:'ccl-1'})
(:Evidence {id:'evd-1'})-[:SUPPORTS {strength:0.8, rationale:'…', judged_by:'llm:claude-sonnet-5'}]->(:Claim {id:'clm-1'})
```

- [`02-ontology`](./02-ontology.md) §3 엣지 표를 관계타입에 1:1 매핑: `MENTIONS`, `PUBLISHED_BY`, `MADE_CLAIM`, `SUBJECT`, `OBJECT`, `ABOUT`, `MEMBER_OF`, `SUPPORTS`, `CONTRADICTS`, `QUALIFIES`, `SUPERSEDES`, `DERIVED_FROM`, `CITES`, `PARTICIPATED_IN`, `PRECEDES`, `SAME_AS`, `POSSIBLY_SAME_AS`. (valid time은 `VALID_DURING` 엣지 없이 노드 inline 속성 `valid_from`/`valid_to`/`time_precision`으로 표현 — [`02`](./02-ontology.md) ADR-206)
- `SUPPORTS`는 `strength`/`rationale`/`judged_by`를 관계 속성으로 필수 저장한다. `CONTRADICTS`는 여기에 더해 `conflict_type`을 필수로 가진다(`conflict_type`은 `CONTRADICTS` 전용, [`02-ontology`](./02-ontology.md) §3.1).
- 관계 속성은 UI 토큰 매핑([`02-ontology`](./02-ontology.md) §3.2)에 그대로 노출된다(색만으로 전달 금지).

### 2.3 필수 인덱스·제약

```cypher
// 전역 id 유일성 — Neo4j 제약은 라벨 단위이므로 전 라벨에 각각 선언
CREATE CONSTRAINT entity_id_unique          IF NOT EXISTS FOR (n:Entity)         REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT claim_id_unique           IF NOT EXISTS FOR (n:Claim)          REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT canonicalclaim_id_unique  IF NOT EXISTS FOR (n:CanonicalClaim) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT evidence_id_unique        IF NOT EXISTS FOR (n:Evidence)       REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT assertion_id_unique       IF NOT EXISTS FOR (n:Assertion)      REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT document_id_unique        IF NOT EXISTS FOR (n:Document)       REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT source_id_unique          IF NOT EXISTS FOR (n:Source)         REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT event_id_unique           IF NOT EXISTS FOR (n:Event)          REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT investigation_id_unique   IF NOT EXISTS FOR (n:Investigation)  REQUIRE n.id IS UNIQUE;

// predicate 조회 (Claim 필터·집계 hot path)
CREATE INDEX claim_predicate IF NOT EXISTS FOR (c:Claim) ON (c.predicate);

// entity identifier 조회 (Entity Resolution 강한 신호, 05) — canonical_name/legal_name + 별칭·법적명 fulltext
CREATE INDEX entity_canonical_name IF NOT EXISTS FOR (e:Entity) ON (e.canonical_name);
CREATE INDEX entity_legal_name     IF NOT EXISTS FOR (e:Entity) ON (e.legal_name);
CREATE FULLTEXT INDEX entity_identifiers IF NOT EXISTS FOR (e:Entity) ON EACH [e.aliases, e.legal_name];

// bitemporal 시간질의 (AS-OF, §8) — 버전 축은 Assertion에 부착(03 §6.2, 아래 §6·§8.2)
CREATE INDEX assertion_valid IF NOT EXISTS FOR (a:Assertion) ON (a.valid_from, a.valid_to);
CREATE INDEX assertion_tx    IF NOT EXISTS FOR (a:Assertion) ON (a.tx_from, a.tx_to);
```

- `id IS UNIQUE`는 idempotency의 그래프측 최종 방어선이다(중복 `create_node` 차단).
- 외부 권위 식별자(`identifiers{}`: QID/LEI/ticker/GeoNames)는 조회·해소 신호이므로 별도 property + fulltext 인덱스로 노출한다([`02-ontology`](./02-ontology.md) §2.2, [`05-resolution`](./05-resolution-and-extraction.md)).

## 3. Mutation 적용기 (Applier)

Applier는 [`03-storage`](./03-storage-and-data-model.md) §7의 `graph_mutations` 이벤트를 **순서대로(ULID `mutation_id` 오름차순)** 소비해 materialized graph에 적용하는 소비자다. 그래프에 대한 **유일한 쓰기 경로**다(직접 write 금지 → 불변식 §3-3).

### 3.1 공통 규칙

- **Idempotency.** 각 이벤트의 `idempotency_key`(= stage input 해시)를 그래프측 `:AppliedMutation {key}` 노드/집합에 기록한다. 이미 적용된 key 재수신 시 **no-op**([`03-storage`](./03-storage-and-data-model.md) §7.2, 불변식 §3-6).
- **버전 부착.** 이벤트 `version_tuple`(5축: `ontology_version`/`schema_version`/`prompt_template_hash`/`model_id`/`extraction_code_version`)을 생성 element에 전파한다([`README`](./README.md) §2.3).
- **게이트 우선.** 노드/엣지 생성은 §4 schema validation + provenance 게이트를 통과해야 `:Authoritative`, 아니면 `:Quarantine`.

### 3.2 op별 적용 규칙

| op | 적용 규칙 |
| --- | --- |
| `create_node` | `MERGE (n {id})` 후 속성 set. 게이트 결과로 `:Authoritative`/`:Quarantine` 라벨 부여. |
| `create_edge` | 양끝 노드 존재 확인(reference 무결성, [`02-ontology`](./02-ontology.md) §4-3) → 관계 생성. 미존재 시 quarantine 사유 기록. |
| `merge_entity` | SAME_AS 동치류에 canonical 대표 지정, claim 재지정(§5.1–§5.2). |
| `unmerge` | `merge_entity` 역연산: 대상 `SAME_AS` 제거 + member `canonical_id` 원복 + canonical rewrite 무효화(§5.3). `resolution_ref`로 역연산 대상 병합을 특정한다. |
| `supersede` | `SUPERSEDES` 관계 생성 + 이전 Assertion 버전 tx_to close 반영(§6). |
| `delete` | soft delete: `:Deleted` 라벨 + `deleted_tx` set(원장은 append-only이므로 물리 삭제 아님, §8.4 삭제 전파). |
| `quarantine` | authoritative에서 `:Quarantine`로 라벨 전환 + 사유 기록(§4). |

### 3.3 적용 pseudo-code

```python
def apply(evt):  # evt: graph_mutations row
    if graph.seen(evt.idempotency_key):
        return NOOP                                   # 3.1 idempotency
    with graph.tx() as tx:
        if evt.op == "create_node":
            n = tx.merge_node(evt.payload["id"], evt.payload["props"])
            label = "Authoritative" if gate_passes(evt.payload) else "Quarantine"
            tx.set_label(n, label, reason=gate_reason(evt.payload))
        elif evt.op == "create_edge":
            if not tx.both_endpoints_exist(evt.payload):
                tx.quarantine_edge(evt.payload, reason="dangling_ref")   # 02 §4-3
            else:
                tx.create_rel(evt.payload)
        elif evt.op == "merge_entity":
            apply_merge(tx, evt.payload)               # §5.1
        elif evt.op == "unmerge":
            apply_unmerge(tx, evt.payload)             # §5.3 merge_entity 역연산:
                                                       #   resolution_ref로 대상 SAME_AS 특정 →
                                                       #   SAME_AS 제거 + canonical_id 원복 + :Merged 해제
        elif evt.op == "supersede":
            tx.create_rel_supersedes(evt.payload)
            tx.close_tx_to(evt.payload["superseded_id"], evt.payload["superseded_at"])  # §6
        elif evt.op == "delete":
            tx.soft_delete(evt.payload["id"], evt.tx_time)
        elif evt.op == "quarantine":
            tx.relabel(evt.payload["id"], "Quarantine", reason=evt.payload["reason"])
        tx.mark_applied(evt.idempotency_key, evt.mutation_id)
```

- `gate_passes`는 §4의 schema validation + provenance 검사다. 판정 자체는 [`05-resolution`](./05-resolution-and-extraction.md)/[`02-ontology`](./02-ontology.md) 제약에 위임하며, Applier는 결과 라벨링만 담당한다.

### 3.4 op별 payload 스키마

[`03-storage`](./03-storage-and-data-model.md) §7.1의 `payload`는 opaque `jsonb`이나, Applier가 op별로 요구하는 **필수 키·타입**은 아래로 확정한다(누락 시 quarantine + 사유 기록). `resolution_ref`는 이벤트 최상위 컬럼([`03`](./03-storage-and-data-model.md) §7.1)이며 merge/unmerge가 이를 키로 사용한다.

| op | 필수 payload 키 (타입) |
| --- | --- |
| `create_node` | `id`(string), `props`(map), `labels`(string[], optional 세부 라벨) |
| `create_edge` | `type`(string, 관계타입), `from`(id), `to`(id), `props`(map) |
| `merge_entity` | `member`(id), `canonical`(id) + 이벤트 `resolution_ref`(string), `actor` |
| `unmerge` | `member`(id), `canonical`(id) + 이벤트 `resolution_ref`(string, 역연산 대상 병합 특정) |
| `supersede` | `new_id`(id), `superseded_id`(id), `superseded_at`(timestamp), `reason`(string) |
| `delete` | `id`(string) |
| `quarantine` | `id`(string), `reason`(string) |

## 4. Authoritative vs Quarantine 그래프

blueprint §8.9: 추출 결과를 바로 authoritative graph에 넣지 않는다. schema validation과 provenance 검사를 통과한 변경만 authoritative, 나머지는 quarantine에 적재한다.

### 4.1 분리 방식

- **초기(Neo4j Community):** 물리 분리 대신 **`:Authoritative` / `:Quarantine` 상태 라벨**로 하나의 그래프 안에서 논리 분리한다. 모든 조회 API는 기본으로 `:Authoritative`만 반환하고 `:Deleted`(soft-delete, §3.2)는 기본 제외한다(quarantine·deleted는 명시적 opt-in).
- **확장:** Memgraph 등에서는 별도 DB/그래프로 물리 분리 가능(ADR-603 참조).

### 4.2 게이트 조건

authoritative 진입 = 아래 **모두** 통과([`02-ontology`](./02-ontology.md) §4, [`03-storage`](./03-storage-and-data-model.md) §8.3):

1. **Provenance 게이트.** Claim/Evidence/Assertion은 `provenance_ref` ≥ 1(= 존재하는 `ext-…` 추출 기록). 무출처 → quarantine.
2. **Predicate 폐쇄성.** `predicate` ∈ controlled vocabulary([`02-ontology`](./02-ontology.md) §5). 미등록 → quarantine + 온톨로지 proposal 트리거([`02-ontology`](./02-ontology.md) §6.2).
3. **Reference 무결성.** `subject_id`/`object_id`/`speaker_id`가 존재 엔터티(또는 `object_literal`).
4. **시간·confidence 정합성.** `valid_from ≤ valid_to`, `confidence`/`certainty` ∈ [0,1]. 낮은 confidence는 정책 임계 미만 시 quarantine(blueprint §8.9).

### 4.3 승격 경로 (Quarantine → Authoritative)

- quarantine element는 사유(`quarantine_reason`)와 함께 보존된다. 결함이 해소되면 **새 mutation 이벤트**로 승격한다(원 이벤트 수정 아님, append-only).
  - provenance 보강: 추출 재실행으로 `ext-…` 생성 → `create_node`/`create_edge` 재발행.
  - predicate 등록: 온톨로지 minor bump + backfill replay(§7, [`02-ontology`](./02-ontology.md) §6.2).
- 승격은 Applier가 `:Quarantine` → `:Authoritative` 라벨 전환으로 반영하며, 모든 전환은 감사 로그에 남는다([`11`](./11-observability-and-governance.md)).

## 5. Entity Merge / Unmerge

### 5.1 Merge

- `SAME_AS`([`02-ontology`](./02-ontology.md) §3, §4-5)는 대칭·전이 **동치류(equivalence class)**를 형성하고, 각 동치류는 **canonical 대표 1개**를 가진다.
- 병합은 `merge_entity` 이벤트로 표현하며 원 엔터티 ID는 **재작성하지 않는다**([`README`](./README.md) §2.2). 대신 canonical 매핑으로 표현한다.

```cypher
// merge_entity 적용: canonical 대표 지정 + SAME_AS 동치류
MATCH (a:Entity {id:$member}), (c:Entity {id:$canonical})
MERGE (a)-[r:SAME_AS {resolution_ref:$res_id, decided_by:$actor}]->(c)
SET a.canonical_id = c.id, a:Merged;
```

### 5.2 Claim 재지정 영향

- 병합 시 member 엔터티를 `subject`/`object`/`speaker`로 가진 Claim은 **canonical 대표를 향하도록 재해석**된다. 물리적으로 관계를 재작성하지 않고, 조회 계층이 `canonical_id`를 따라 rewrite하는 **view 접근**을 우선한다(unmerge 가역성 보존).
- 이 재지정은 독립 증거 수·모순 판정에 영향을 주므로 [`05-resolution`](./05-resolution-and-extraction.md) contradiction/independence 재평가를 트리거한다.

### 5.3 Unmerge (오병합 복구)

- **모든 `merge_entity`는 대응 `unmerge` 이벤트로 reversible**해야 한다(blueprint §8.5 precision-first, 불변식 §3-3, [`03-storage`](./03-storage-and-data-model.md) §7.2).
- `unmerge` 적용: `SAME_AS` 제거 + `canonical_id` 원복 + 영향 Claim의 canonical rewrite 무효화. 원 병합 이벤트의 `resolution_ref`로 역연산 대상을 특정한다.

```cypher
// unmerge 적용 (merge_entity 역연산): resolution_ref로 대상 SAME_AS 특정 → 제거·원복
MATCH (a:Entity)-[r:SAME_AS {resolution_ref:$res_id}]->(c:Entity)
DELETE r
REMOVE a:Merged
SET a.canonical_id = null;    // canonical_id 원복 → 조회 계층 rewrite(§5.2) 무효화
```

- precision-first 원칙상 불확실한 병합은 `POSSIBLY_SAME_AS` 후보로만 유지하고 authoritative merge를 미룬다([`02-ontology`](./02-ontology.md) §3, [`05-resolution`](./05-resolution-and-extraction.md)).

## 6. Supersession

- **bitemporal 버전 단위는 `Assertion`이다**([`03-storage`](./03-storage-and-data-model.md) §6.2). Claim은 reified statement, Assertion은 그 Claim의 valid/tx 버전을 담는 노드다. supersession·`tx_to` close·AS-OF는 모두 Assertion에 적용한다(§2.3 인덱스·§8.2 질의 일관).
- 정정·갱신 사실은 이전 Assertion 버전을 **삭제하지 않고** `SUPERSEDES` 관계로 잇고, 이전 버전의 bitemporal `tx_to`를 close한다([`03-storage`](./03-storage-and-data-model.md) §6.1–§6.2).

```cypher
// supersede 적용: 신 Assertion 버전 → 구 버전 SUPERSEDES + 구 버전 tx_to close
MATCH (old:Assertion {id:$superseded_id})
CREATE (new:Assertion {id:$new_id})-[:SUPERSEDES {reason:$reason, superseded_at:$t}]->(old)
SET old.tx_to = $t;          // 이전 버전은 그래프에 남되 "현재 아님"으로 표시
```

- `tx_to = null`인 버전만 "현재 시스템이 믿는" 상태다. 이전 버전은 time-travel(§8)과 감사를 위해 보존된다.
- 시간 슬라이더 UI는 superseded 노드를 삭제하지 않고 `edge-superseded` 토큰(흐린 점선 + 시간화살표, [`02-ontology`](./02-ontology.md) §3.2)으로 구분 표시한다.

## 7. Rebuild / Replay

불변식 §3-1·§3-3: materialized graph는 `graph_mutations` log replay로 **전량 재구축 가능**하다(재현성, blueprint §8.9, §17, [`03-storage`](./03-storage-and-data-model.md) §7.2).

### 7.1 Full rebuild

- 그래프를 비우고 `graph_mutations`를 `mutation_id`(ULID) 오름차순으로 전량 replay. Applier는 idempotent하므로 부분 실패 후 재개해도 동일 결과에 수렴한다.
- 용도: 저장소 교체(Neo4j→Memgraph), 물리 스키마 변경, 손상 복구, 재현성 검증([`10`](./10-evaluation-and-testing.md) 대상).

### 7.2 Incremental rebuild

- 신규 문서·정정이 영향을 준 **subgraph만** 재적용한다. 영향 범위 = 신규/변경 `mutation_id` 이후 이벤트 + 그들이 참조하는 엔터티/claim의 인접 subgraph(merge·supersede 파급 포함).
- hairball 방지·비용 절감을 위해 정상 운영은 incremental, 정합성 보증이 필요할 때 full rebuild를 사용한다.

### 7.3 Ontology migration backfill

- 온톨로지 major/minor 변경은 [`02-ontology`](./02-ontology.md) §6.2 절차(proposal→review→promotion→backfill)를 따른다.
- backfill은 in-place 마이그레이션 대신 **event replay 재구축을 우선**한다([`02-ontology`](./02-ontology.md) §6.2 말미). 필요 시 기존 element를 새 `ontology_version` target으로 재해석하는 변환 이벤트를 발행한 뒤 replay한다.

### 7.4 Rollback (역이벤트)

- **로그 truncation 금지.** `graph_mutations`는 append-only이므로(불변식 §3-3, [`03-storage`](./03-storage-and-data-model.md) §7.2) 잘못된 변경을 되돌릴 때 원 이벤트를 삭제·수정하지 않는다. 대신 **역이벤트(reverse event)를 새로 발행**해 상태를 revert한다.
- op별 역이벤트:
  - `create_node`/`create_edge` → `delete`(soft-delete `:Deleted`, §3.2).
  - `merge_entity` → `unmerge`(§5.3, 원 병합의 `resolution_ref` 참조).
  - `supersede` → 재정정 `supersede`(이전 Assertion 버전을 다시 현재로 여는 신 버전 발행) 또는 `delete`.
  - `quarantine` → 승격 경로(§4.3)로 `:Authoritative` 복원.
- **감사·재현성 보존.** 원 변경과 역이벤트가 모두 로그에 남으므로 "무엇을, 왜 되돌렸는가"가 추적 가능하고, full/incremental rebuild(§7.1–§7.2) 결과도 결정적으로 유지된다.
- **증분 rebuild와의 관계.** 역이벤트는 일반 mutation과 동일하게 `mutation_id` 순서로 소비되므로 rollback 후에는 영향 subgraph만 incremental 재적용하면 되고(§7.2), 정합성 보증이 필요하면 full rebuild로 검증한다.

## 8. Query API 개요

조사(Investigation) 중심의 그래프 조회 계약. 상세 REST 계약은 [`09`](./09-api.md), 성능 목표는 [`11`](./11-observability-and-governance.md)에 위임한다.

- **canonical view-rewrite는 필수 wrapper다.** 병합은 관계를 물리 재작성하지 않으므로(§5.2) 모든 serving 질의는 `SAME_AS*0..` 해소 단계를 거쳐 동치류를 canonical 대표로 접어야 한다. 이를 생략하면 merged-away member가 별도 엔터티로 노출된다.
- **기본 필터.** 모든 serving 질의는 기본으로 `:Authoritative`만 반환하고 `:Deleted`를 제외한다(§4.1).

### 8.1 Investigation subgraph 조회

- 진입점: `Investigation` → 관련 Claim/Entity/Evidence subgraph. 기본은 `:Authoritative`만.

```cypher
// investigation 범위의 claim + 근거 subgraph (progressive: 1-hop)
// canonical view-rewrite: scope의 canonical 대표 → SAME_AS 동치류 전체의 claim을 접어 조회(§5.2)
MATCH (inv:Investigation {id:$inv})
UNWIND inv.scope_entities AS seed
MATCH (canon:Entity {id: seed})                 // scope는 canonical id 기준
MATCH (member:Entity)-[:SAME_AS*0..]->(canon)   // 동치류 전체(자기 포함)
MATCH (c:Claim:Authoritative)-[:ABOUT]->(member)
WHERE NOT c:Deleted
OPTIONAL MATCH (ev:Evidence)-[r:SUPPORTS|CONTRADICTS]->(c)
RETURN canon AS entity, c, r, ev LIMIT $page;
```

### 8.2 Time-travel (AS-OF)

- **버전 축은 Assertion에 부착**된다(§6, [`03-storage`](./03-storage-and-data-model.md) §6.2). AS-OF 질의는 `Assertion`의 valid/tx를 필터하고 대응 `Claim`을 `claim_id`로 잇는다.
- **AS-OF valid time `T_v`:** `valid_from ≤ T_v < valid_to`. `valid_from IS NULL`이면 open lower bound(하한 무제한)로 항상 하한을 충족하며, 경계 해석은 `time_precision`을 따른다.
- **AS-OF transaction time `T_t`:** `tx_from ≤ T_t < (tx_to ?? ∞)`.
- 두 축 동시 지정으로 "특정 관찰 시점 기준, 특정 유효 시점 상태"를 재현한다([`03-storage`](./03-storage-and-data-model.md) §6.3). superseded 버전을 삭제하지 않으므로 과거 상태가 그대로 조회된다.

```cypher
// AS-OF: T_t 시점에 시스템이 믿던, T_v 시점에 유효한 assertion 버전 → 대응 claim
MATCH (a:Assertion:Authoritative)
WHERE (a.valid_from IS NULL OR a.valid_from <= $Tv)   // open lower bound 처리
  AND ($Tv < a.valid_to OR a.valid_to IS NULL)
  AND a.tx_from <= $Tt AND ($Tt < a.tx_to OR a.tx_to IS NULL)
MATCH (c:Claim {id: a.claim_id})
RETURN a, c;
```

### 8.3 Progressive disclosure (hairball 금지)

- 전체 그래프를 한 번에 반환하지 않는다. 진입점 → 요약(집계 노드/대표 claim) → on-demand expand로 단계 공개한다.
- 기본 페이지네이션·hop 제한·relationship 타입 필터를 강제하고, 노드 수/hop이 임계 초과 시 요약 노드로 축약한다(War Table UI 계약, DESIGN.md).
- p50/p95/p99 지연 목표와 SLO는 [`11`](./11-observability-and-governance.md)에 위임한다.

## 9. 의사결정 로그

| ID | 결정 | 근거 | 상태 |
| --- | --- | --- | --- |
| ADR-601 | 초기 그래프 DB로 Neo4j Community 채택, 스키마 매핑·Applier 계약을 저장소 독립으로 유지 | 성숙한 Cypher·생태계, 교체 비용 격리([`01`](./01-architecture.md)) | Accepted · **구현(P1 ③+트랙 b)**: `Neo4jGraphStore`가 재생 그래프를 Neo4j Community(bolt 7687)에 MERGE 적래+explorer 조회(`Entity` 노드·`id` 유일 제약), **read path 배선** — `node_detail(node_id)`(노드 상세)·`reconstruct_graph()`(Neo4j 상태에서 `GraphService` 재구축, ADR-604 replay 대체 read 백업) (`prototype/orc_citadel/neo4j_graph_store.py`, 2026-08-11) |
| ADR-602 | 그래프에 대한 유일한 쓰기 경로는 `graph_mutations` 소비 Applier(직접 write 금지) | 불변식 §3-3 event-driven, replay·audit 보장 | Accepted |
| ADR-603 | authoritative/quarantine를 초기엔 상태 라벨로 논리 분리, 확장 시 물리 분리 | Community 다중 DB 제약, blueprint §8.9 | Accepted |
| ADR-604 | graph 재구축은 event log replay 기반(full/incremental), migration backfill도 replay 우선 | SoT는 log·graph는 파생([`03`](./03-storage-and-data-model.md) §7, §17) | Accepted |
| ADR-605 | entity merge는 canonical 매핑 + view rewrite, ID 재작성 금지, unmerge로 가역 | 오병합 복구·precision-first(blueprint §8.5, 불변식 §3-4) | Accepted |
| ADR-606 | bitemporal 버전 단위는 `Assertion`(valid/tx·supersede·AS-OF·인덱스 모두 Assertion에 부착), Claim은 reified statement | 03 §6.2와 정합, Claim/Assertion 축 분열 제거 | Accepted |
| ADR-607 | rollback은 log truncation이 아니라 역이벤트(`delete`/`unmerge`/`supersede`) 발행으로 표현, 이후 incremental rebuild | append-only 불변식 §3-3, 감사·재현성 보존([`03`](./03-storage-and-data-model.md) §7.2) | Accepted |

> **Q4 한계 측정 게이트 (2026-08-03 확정):** Neo4j Community 한계 도달은 **Phase 1(10만 문서 기준선) 부하 테스트에서 측정**한다. 교체·물리 분리 판정을 트리거하는 임계(설계 게이트, 측정은 Phase 1):
> - **노드 수** ≥ `1e6` (Community 단일 인스턴스 실용 한계) 또는
> - **그래프 조회 p95 latency** ≥ `500 ms` (SLO 게이트, 09 §2.2 조회 계약) 또는
> - **재구축(이벤트 replay) 벽시계** > 증분 재구축의 `10×` (백필 비용 분기).
>
> 이 임계 하나라도 초과하면 06 ADR-601/603의 저장소 추상·라벨 분리 계약 위에서 **Memgraph 등 물리 분리/교체**로 전환한다 (교체 비용은 이미 격리됨). prototype(in-memory)은 이 측정의 대상이 아니며, Phase 0 완료 조건에는 영향 없다.
