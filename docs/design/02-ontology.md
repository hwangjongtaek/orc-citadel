# 02 · 온톨로지 (Ontology)

> **상태:** Review · **Spec:** 0.1.0 · **Ontology version:** `1.0.0` · **Blueprint 매핑:** §6
> 상위 규약: [`README.md`](./README.md) · 관련: [`03-storage`](./03-storage-and-data-model.md), [`06-graph`](./06-graph-service.md), [`05-resolution`](./05-resolution-and-extraction.md)

War Table의 시맨틱 레이어를 정의하는 **핵심 SSOT**다. 노드 타입, 엣지 타입, 속성, 제약, 버저닝·거버넌스를 확정한다. 물리 저장 스키마는 [`03`](./03-storage-and-data-model.md), 그래프 라벨·인덱스는 [`06`](./06-graph-service.md)가 소유한다.

## 1. 온톨로지 설계 원칙

1. **관계의 Reification.** `A -[DEPENDS_ON]-> B` 같은 직접 관계 대신 `Claim` 노드로 reify한다. 누가·언제·어떤 근거로 주장했는지를 1급 시민으로 표현하기 위함이다 (blueprint §6.3).
2. **사실과 주장의 분리.** 그래프는 "진실"을 저장하지 않는다. **"누가 무엇을 주장했고 어떤 증거가 그것을 지지/반박하는가"**를 저장한다. `supports`를 진실로, `contradicts`를 거짓으로 승격하지 않는다.
3. **Provenance 필수.** 모든 `Claim`/`Evidence`/`Assertion`은 원문 span까지 추적 가능해야 authoritative graph에 진입한다 (불변식 §3-2).
4. **버전 관리 가능.** 온톨로지는 semver로 관리하고 proposal→review→promotion 절차로만 변경한다 (blueprint §18 ontology 폭발 대응).

## 2. 노드 타입 (Node Types)

blueprint §6.1을 확정·확장한다. 공통 속성은 모든 노드가 가진다.

### 2.1 공통 속성 (모든 노드)

| 속성 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `id` | string | ✓ | `<prefix>-<ULID>` (Document은 content hash), [`README`](./README.md) §2.2 |
| `type` | enum | ✓ | 노드 타입 |
| `created_tx` | timestamp | ✓ | transaction time 생성 시각 |
| `ontology_version` | semver | ✓ | 생성 당시 온톨로지 버전 |
| `provenance_ref` | ext-id[] | 조건부 | Entity 외 Claim/Evidence/Assertion 필수 (→ [`03`](./03-storage-and-data-model.md)) |

### 2.2 엔터티 노드

| 노드 | prefix | 고유 속성 | 식별/해소 키 |
| --- | --- | --- | --- |
| `Person` | `per` | `canonical_name`, `aliases[]`, `identifiers{}`(예: 위키데이터 QID), `roles[]` | name + identifier |
| `Organization` | `org` | `legal_name`, `aliases[]`, `jurisdiction`, `identifiers{}`(LEI, ticker), `org_type` | legal_name + identifier |
| `Product` | `prd` | `name`, `version`, `manufacturer_id`(→org), `category` | name + manufacturer |
| `Technology` | `tec` | `name`, `category`, `aliases[]` | name |
| `Location` | `loc` | `name`, `coordinates`, `admin_hierarchy[]`, `identifiers{}`(GeoNames) | name + hierarchy |

- `identifiers{}`는 외부 권위 식별자 맵. Entity Resolution의 강한 신호 (→ [`05`](./05-resolution-and-extraction.md)).
- 엔터티는 **provenance_ref 없이도** 생성 가능하나 최소 1개 이상의 mention으로 뒷받침되어야 한다.

### 2.3 사건·문서 노드

| 노드 | prefix | 고유 속성 |
| --- | --- | --- |
| `Event` | `evt` | `event_type`(계약/발표/사고/규제/투자/M&A/제품출시…), `valid_time`, `status`(planned/confirmed/cancelled), `participants[]`(→엔터티) |
| `Document` | `doc` | `url`, `content_hash`, `publication_time`, `revision_time`, `language`, `source_id`(→src) |
| `Source` | `src` | `publisher`, `source_type`(official/press/gov/research/exchange), `ownership`, `dimensions{}`(→[`11`](./11-observability-and-governance.md) 신뢰도 차원) |

`Event.event_type`은 온톨로지 controlled vocabulary이며 §5 참조. 초기 도메인(AI 반도체 공급망) 특화 타입을 우선 정의한다.

- **Event provenance.** `Event`는 그 사건을 보고한 `Claim`(예: `announces` predicate)을 통해 provenance를 얻는다. 즉 `Event`는 `provenance_ref`를 직접 요구하지 않으나, authoritative graph 진입은 이를 뒷받침하는 provenance 있는 `Claim` ≥ 1을 전제로 한다 (불변식 §4-1은 Claim/Evidence/Assertion에 적용).

### 2.4 주장·증거 노드 (핵심)

#### `Claim` (`clm`)

출처가 제시한 명제. 관계 reification의 중심.

```json
{
  "id": "clm-01J9...",
  "type": "Claim",
  "subject_id": "org-01J9...",
  "predicate": "depends_on",
  "object_id": "org-01J9...",
  "object_literal": null,
  "canonical_text": "A사는 AI 가속기 부품을 B사에 주로 의존한다.",
  "modality": "asserted",
  "polarity": "positive",
  "certainty": 0.9,
  "qualifier": { "scope": "AI accelerator components", "quantity": null },
  "valid_from": "2025-01-01",
  "valid_to": null,
  "time_precision": "month",
  "speaker_id": "org-01J9...",
  "observed_at": "2025-02-15T09:00:00Z",
  "confidence": 0.83,
  "canonical_claim_id": "ccl-01J9...",
  "provenance_ref": ["ext-01J9..."],
  "ontology_version": "1.0.0",
  "extraction_model": "claude-sonnet-5"
}
```

| 속성 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `subject_id` | entity-id | ✓ | 주장 주체 |
| `object_id` | entity-id | 조건부 | 주장 대상. `object_literal`과 **XOR**(정확히 하나만 존재) |
| `object_literal` | any | 조건부 | object가 값일 때 (예: 금액, 비율). `object_id`와 **XOR** |
| `predicate` | enum | ✓ | controlled vocabulary (§5) |
| `canonical_text` | string | ✓ | 주장의 대표 자연어 표현 |
| `modality` | enum | ✓ | `fact` / `asserted` / `opinion` / `prediction` (사실·주장·의견·예측 구분, blueprint §8.6) |
| `polarity` | enum | ✓ | `positive` / `negative` |
| `certainty` | float | nullable | 화자의 확실성 (모델 confidence와 구분), ∈ [0,1] |
| `qualifier` | object | nullable | 적용 범위·수량 한정자 (`scope`, `quantity`) |
| `valid_from` | date | nullable | valid time 시작 (미상은 `null` + `time_precision`) |
| `valid_to` | date | nullable | valid time 종료 (open이면 `null`) |
| `time_precision` | enum | 조건부 | `valid_*` 정밀도 ([`README`](./README.md) §2.4). `valid_from` 존재 시 필수 |
| `speaker_id` | entity-id | nullable | 주장한 주체 (문서 저자/인용 화자) |
| `observed_at` | timestamp | ✓ | 시스템이 관찰한 시각 |
| `confidence` | float | ✓ | **추출 모델의** 신뢰도, ∈ [0,1] |
| `canonical_claim_id` | ccl-id | nullable | 소속 canonical claim (§2.4 CanonicalClaim) |
| `extraction_model` | string | ✓ | 추출 모델 ID (버전 축, → [`03`](./03-storage-and-data-model.md) §7.1) |

> **속성↔엣지 이중 표현.** `subject_id`/`object_id`/`speaker_id`는 조회 편의를 위한 property이며, 그래프 상의 정본 관계는 각각 `SUBJECT`/`OBJECT`/`MADE_CLAIM` 엣지(§3)다. 두 표현은 항상 일치해야 하며 불일치 시 엣지를 정본으로 본다.

> **주의:** `confidence`(모델 신뢰도)와 `certainty`(화자 확실성)는 별개다. 최종 결론 confidence는 claim별 증거 구조로 계산하며 단일 값이 아니다 (→ [`11`](./11-observability-and-governance.md) 신뢰도, blueprint §11).

#### `CanonicalClaim` (`ccl`)

의미가 같은 여러 `Claim`을 묶는 정규 명제. Claim Canonicalization 산출물 (→ [`05`](./05-resolution-and-extraction.md)).

| 속성 | 설명 |
| --- | --- |
| `canonical_text` | 대표 표현 |
| `member_claim_ids[]` | 소속 claim |
| `subject_id`/`predicate`/`object_id` | 정규 삼항 |

> **정본 소속 인코딩은 `MEMBER_OF` 엣지 1개다.** 소속은 `MEMBER_OF`(Claim→CanonicalClaim), `CanonicalClaim.member_claim_ids[]`, `Claim.canonical_claim_id` 세 곳에 나타나지만 **정본은 `MEMBER_OF` 엣지**이며 나머지 둘은 조회 편의용 파생(derived) 표현이다. 세 표현은 항상 일치해야 하고 재구축 시 `MEMBER_OF`에서 파생분을 재생성한다.

#### `Evidence` (`evd`)

주장을 평가하는 원문 구절·데이터.

| 속성 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `source_span` | span | ✓ | 문서 offset (→ [`03`](./03-storage-and-data-model.md) provenance) |
| `document_id` | doc-id | ✓ | 소속 문서 버전 |
| `extraction_version` | version tuple | ✓ | 추출 버전 (5축, → [`03`](./03-storage-and-data-model.md) §7.1) |
| `evidence_type` | enum | ✓ | `primary`(1차 자료) / `secondary`(해석) |

#### `Assertion` (`asr`)

시간·provenance를 가진 관계 주장의 저장 단위. Claim이 그래프 관계로 materialize된 형태이며 bitemporal 이력의 최소 단위다 (→ [`03`](./03-storage-and-data-model.md) §6). 이 표가 **semantics를 소유**하고, 물리 컬럼은 [`03`](./03-storage-and-data-model.md) §6.2 `assertions` 테이블과 1:1 대응한다 (필드명 동일).

| 속성 | 타입 | 필수 | 설명 (semantics) |
| --- | --- | --- | --- |
| `assertion_id` | `asr-<ULID>` | ✓ | 저장 단위 식별자 |
| `claim_id` | clm-id | ✓ | materialize된 원본 Claim |
| `subject_id` | entity-id | ✓ | 정규 삼항 주체 |
| `predicate` | enum | ✓ | 정규 삼항 술어 (§5) |
| `object_id` | entity-id | 조건부 | 정규 삼항 대상. `object_literal`과 **XOR** |
| `object_literal` | any | 조건부 | object가 값일 때. `object_id`와 **XOR** |
| `valid_from` | date | nullable | valid time 시작 (현실 유효 구간) |
| `valid_to` | date | nullable | valid time 종료 (open이면 `null`) |
| `time_precision` | enum | 조건부 | `valid_*` 정밀도. `valid_from` 존재 시 필수 |
| `tx_from` | timestamp | ✓ | transaction time 시작 (시스템 관찰·저장 시각) |
| `tx_to` | timestamp | nullable | transaction time 종료. `null`=현재도 유효한 버전 |
| `supersedes_id` | asr-id | nullable | 대체 대상 assertion (supersession 체인) |
| `superseded_reason` | string | nullable | 변경 원인 |
| `mutation_id` | mut-id | ✓ | 생성 이벤트 (→ [`03`](./03-storage-and-data-model.md) §7) |
| `provenance_ref` | ext-id[] | ✓ | 원문 span 추적 (불변식 §4-1) |

> **Claim → Assertion materialization.** 게이트(§4)를 통과한 `Claim`은 정규 삼항(`subject_id`/`predicate`/`object_id`\|`object_literal`)과 valid time을 복사해 `Assertion`으로 materialize된다. `Claim`은 출처가 제시한 명제 단위(화자·`certainty`·`modality` 보존)이고, `Assertion`은 그 명제가 그래프 관계로 승격된 bitemporal 저장 단위다 — 이는 조회·시간질의 성능을 위한 의도된 비정규화(denormalization)이며 정본 관계 삼항은 두 곳에서 동일해야 한다. 하나의 `Claim`은 tx 축을 따라 여러 `Assertion` 버전을 가질 수 있다. 정정·supersession 시 이전 버전 `tx_to`를 close(덮어쓰기 금지)하고 새 버전이 `supersedes_id`로 이전 버전을 가리킨다 (→ [`03`](./03-storage-and-data-model.md) §6, ADR-207).

### 2.5 조사 노드

| 노드 | prefix | 속성 |
| --- | --- | --- |
| `Investigation` | `inv` | `question`, `scope`(time/region/source_type), `status`(planned/running/paused/done), `budget`, `owner` |

## 3. 엣지 타입 (Relationship Types)

blueprint §6.2를 확정한다. 각 엣지는 방향·정의역·공역을 가진다.

| 관계 | from → to | 의미 | 속성 |
| --- | --- | --- | --- |
| `MENTIONS` | Document → Entity | 문서가 엔터티 언급 | `span`, `mention_text` |
| `PUBLISHED_BY` | Document → Source | 문서 발행 주체 | — |
| `MADE_CLAIM` | Entity → Claim | 인물·기관이 주장 제시 | `via_document_id` |
| `SUBJECT` | Claim → Entity | 주장 주체 | — |
| `OBJECT` | Claim → Entity | 주장 대상 | — |
| `ABOUT` | Claim\|Event → Entity | 주장/사건이 대상을 가리킴 | — |
| `SUPPORTS` | Evidence\|Claim → Claim | 지지 | `strength`, `rationale`, `judged_by` |
| `CONTRADICTS` | Evidence\|Claim → Claim | 반박 | `strength`, `rationale`, `conflict_type`, `judged_by` |
| `QUALIFIES` | Claim → Claim | 적용 범위 한정 | `scope` |
| `SUPERSEDES` | Claim\|Assertion → Claim\|Assertion | 이전 버전 대체 | `reason`, `superseded_at` |
| `DERIVED_FROM` | Document\|Claim → Document\|Source | 파생 | `derivation_type` |
| `CITES` | Document → Document | 명시적 인용 | — |
| `PARTICIPATED_IN` | Entity → Event | 사건 참여 | `role` |
| `PRECEDES` | Event → Event | 시간 선후 | — |
| `SAME_AS` | Entity → Entity | 동일성 확정 | `resolution_ref`, `decided_by` |
| `POSSIBLY_SAME_AS` | Entity → Entity | 동일 후보(미확정) | `score`, `blocking_key` |
| `MEMBER_OF` | Claim → CanonicalClaim | claim이 정규 명제에 소속 (canonicalization 산출, → [`05`](./05-resolution-and-extraction.md)) | `relation`=`equivalent`만 |

### 3.1 관계 유형별 판정 근거 필수

`SUPPORTS`/`CONTRADICTS`는 binary가 아니다. `rationale`(판정 이유)와 `judged_by`(모델/사람)를 반드시 저장한다 (blueprint §8.8). `conflict_type`은 `value_conflict`/`temporal`/`scope` 등으로 구분한다 (→ [`05`](./05-resolution-and-extraction.md) contradiction).

- **`MEMBER_OF.relation`은 `equivalent`로 제한한다.** canonicalization 라벨셋은 7종이지만 (05 [ADR-503](./05-resolution-and-extraction.md)), `CanonicalClaim` 병합(=`MEMBER_OF`)을 만드는 것은 `equivalent` 판정뿐이다. `more_specific`/`more_general`은 `QUALIFIES`, `supports`/`contradicts`는 `SUPPORTS`/`CONTRADICTS`, `temporally_superseded`는 `SUPERSEDES`로 별도 엣지가 되며 `MEMBER_OF`를 만들지 않는다 (→ [`05`](./05-resolution-and-extraction.md) §4.2).
- **유효 구간은 inline 단일 표현이다.** `valid_from`/`valid_to`/`time_precision`을 `Claim`·`Assertion`·`Event`의 속성으로 직접 표현하며 별도 `TimeInterval` 노드나 `VALID_DURING` 엣지를 두지 않는다 (중복 제거, ADR-206). valid time 질의는 이 속성에 직접 건다 (→ [`06`](./06-graph-service.md) 인덱스, [`03`](./03-storage-and-data-model.md) §6.3).

### 3.2 UI 표현 매핑

관계 유형은 색만으로 전달하지 않는다. DESIGN.md의 edge 토큰과 1:1 매핑된다.

| 관계 | 상태 색 | 선 형태 | DESIGN 토큰 |
| --- | --- | --- | --- |
| `SUPPORTS` | war-green | 실선 | `edge-supports` |
| `CONTRADICTS` | contradiction red | 이중선 | `edge-contradicts` |
| `QUALIFIES` | signal-amber | 점선 | `edge-qualifies` |
| `POSSIBLY_SAME_AS`/uncertain | uncertain violet | 점선+? | `edge-uncertain` |
| `SUPERSEDES` | iron gray | 흐린 점선+시간화살표 | `edge-superseded` |

## 4. 무결성 제약 (Constraints)

그래프 반영 전 schema validation에서 강제한다 (→ [`06`](./06-graph-service.md)).

1. **Provenance 게이트:** `Claim`/`Evidence`/`Assertion`은 `provenance_ref` ≥ 1 이어야 authoritative graph 진입. 미충족 시 quarantine (→ [`05`](./05-resolution-and-extraction.md)).
2. **Predicate 폐쇄성:** `predicate`는 §5 controlled vocabulary에 존재해야 한다. 미등록 predicate는 quarantine + 온톨로지 proposal 대상.
3. **Reference 무결성:** `subject_id`/`object_id`/`speaker_id`는 존재하는 엔터티를 가리켜야 한다 (또는 `object_literal` 사용).
4. **시간 정합성:** `valid_to`가 있으면 `valid_from ≤ valid_to`. 미상은 `null` + `time_precision`. valid time은 노드 속성으로만 표현하며 별도 `TimeInterval` 노드/`VALID_DURING` 엣지를 두지 않는다 (ADR-206).
5. **SAME_AS 무순환·전이:** `SAME_AS`는 대칭·전이적 동치류를 형성하며 canonical 대표를 1개 가진다. 순환 merge는 이벤트로 되돌릴 수 있어야 한다 (불변식 §3-3,4).
6. **Confidence 범위:** `confidence`/`certainty` ∈ [0,1].
7. **Edge weight 범위:** 엣지 가중치는 `[0,1]`로 정규화한다 — `SUPPORTS`/`CONTRADICTS.strength`, `POSSIBLY_SAME_AS.score`. 범위를 벗어난 값은 schema validation에서 거부한다.
8. **`object` XOR:** `Claim`/`Assertion`은 `object_id`와 `object_literal` 중 정확히 하나만 가진다.

## 5. Controlled Vocabulary (초기 도메인)

AI 반도체·데이터센터 공급망 도메인의 초기 어휘. 온톨로지 버전에 종속된다.

### 5.1 Predicate (Claim)

| predicate | subject→object | 예시 |
| --- | --- | --- |
| `depends_on` | Org → Org/Product | 공급 의존 |
| `supplies` | Org → Org | 공급 관계 |
| `invests_in` | Org → Org/Event | 투자 |
| `acquires` | Org → Org | 인수 |
| `partners_with` | Org → Org | 제휴 |
| `manufactures` | Org → Product | 제조 |
| `regulates` | Org(gov) → Org/Product/Tech | 규제 |
| `announces` | Org/Person → Event | 발표 |
| `located_in` | Org/Event → Location | 위치 |
| `has_capacity` | Org/Product → literal | 생산능력(수치) |
| `has_market_share` | Org → literal | 점유율 |

### 5.2 event_type

`contract` / `announcement` / `investment` / `acquisition` / `product_launch` / `regulation_change` / `supply_disruption` / `earnings` / `partnership`.

### 5.3 modality

`fact`(검증 가능한 사실 진술) / `asserted`(당사자 주장) / `opinion`(의견·해석) / `prediction`(미래 예측).

## 6. 온톨로지 버저닝·거버넌스

blueprint §18(ontology 폭발), §17 versioning을 절차로 확정한다.

### 6.1 버전 규칙 (semver)

| 변경 | 버전 | 예 |
| --- | --- | --- |
| 노드/엣지/predicate **추가**(하위호환) | minor | `1.0.0`→`1.1.0` |
| 속성 의미·필수성 **변경**, 타입 **제거** | major | `1.0.0`→`2.0.0` |
| 문구·설명 수정 | patch | `1.0.0`→`1.0.1` |

### 6.2 변경 절차 (proposal → review → promotion)

```text
1. Proposal   : 새 predicate/노드 필요 감지 (quarantine 누적 or 사람 제안)
2. Review     : 골든 데이터셋 영향·중복 여부 검토, ADR 작성
3. Promotion  : ontology_version bump → migration 스크립트 → 회귀 테스트
4. Backfill   : 필요 시 기존 element 재해석 (event replay, → 06)
```

- 미등록 predicate/노드로 들어온 추출 결과는 **자동 승격하지 않고** quarantine에 쌓여 proposal 트리거가 된다.
- 온톨로지 migration은 event log replay로 materialized graph를 재구축하는 방식을 우선한다 (→ [`06`](./06-graph-service.md)).

### 6.3 버전 호환성 계약

- 저장된 모든 element는 `ontology_version`을 가진다. 조회 시 현재 버전과의 호환성을 판단한다 (contract test, → [`10`](./10-evaluation-and-testing.md)).
- 모델·프롬프트가 특정 ontology_version을 target한다. 불일치 시 재추출 대상.

## 7. 객체 그래프 (요약)

```text
(Source)◄─PUBLISHED_BY─(Document)─MENTIONS─►(Entity)
                           │
                     DERIVED_FROM/CITES
                           │
(Entity)─MADE_CLAIM─►(Claim)─SUBJECT/OBJECT─►(Entity)
                       │  ▲
                       │  │ MEMBER_OF
                       │  (CanonicalClaim)
             (Evidence)─SUPPORTS/CONTRADICTS─►(Claim)
                       │
                  source_span → (Document offset)  ← provenance trail (03)

(Claim)─SUPERSEDES─►(Claim)      (Entity)─SAME_AS─►(Entity)
(Entity)─PARTICIPATED_IN─►(Event)─PRECEDES─►(Event)
```

## 8. 의사결정 로그

| ID | 결정 | 근거 | 상태 |
| --- | --- | --- | --- |
| ADR-201 | 관계를 Claim 노드로 reification | 화자·시간·근거 표현 필요 (blueprint §6.3) | Accepted |
| ADR-202 | `confidence`(모델)와 `certainty`(화자) 속성 분리 | 신뢰도 과대평가 방지, blueprint §11 | Accepted |
| ADR-203 | predicate/event_type controlled vocabulary + quarantine 트리거 | ontology 폭발 통제 (§18) | Accepted |
| ADR-204 | 초기 vocabulary를 AI 반도체 공급망 도메인에 한정 | 범위 명확화(§4), 확장은 migration | Accepted |
| ADR-205 | `CanonicalClaim`을 별도 노드로 (Claim에 flag 대신) | canonicalization 이력·다대일 표현 | Accepted |
| ADR-206 | `TimeInterval` 노드/`VALID_DURING` 엣지 폐기 → valid time을 `valid_from`/`valid_to`/`time_precision` inline 속성으로 단일 표현 | 정의되지 않은 노드(prefix/props 없음)·inline과의 중복 제거, 03/06에 backing 없음 | Accepted |
| ADR-207 | `Assertion`을 `Claim` 삼항의 bitemporal materialization(비정규화)으로 정의, semantics는 02·물리 컬럼은 03 §6.2 소유 | 조회·시간질의 성능 위한 의도적 denormalization, tx-versioned 이력 단위 필요 | Accepted |
| ADR-208 | `MEMBER_OF.relation`을 `equivalent`로 제한 | 05 canonicalization(ADR-503, 7-label)과 정합 — `equivalent`만 CanonicalClaim 병합, 나머지는 별도 엣지 | Accepted |
