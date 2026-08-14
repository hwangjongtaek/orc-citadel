# 05 · 해소·추출 (Lorekeepers)

> **상태:** Review · **Spec:** 0.1.0 · **Blueprint 매핑:** §8.4–§8.9
> 상위 규약: [README](./README.md) · 관련: [02-ontology](./02-ontology.md), [03-storage](./03-storage-and-data-model.md), [06-graph](./06-graph-service.md), [10-eval](./10-evaluation-and-testing.md)

Lorekeepers는 normalized zone의 문서를 받아 **entity mention → 해소된 entity**, **claim candidate → canonical claim → assertion**으로 정제하는 파이프라인이다. 이 문서는 blueprint §8.4–§8.9를 구현 계약으로 확정한다. 산출물은 모두 curated zone([`03`](./03-storage-and-data-model.md) §4)에 머물다가 §7 그래프 반영 게이트를 통과해야 authoritative graph([`06`](./06-graph-service.md))에 진입한다.

**설계 원칙 (이 문서 전반에 적용):**

- **Precision > recall** (불변식 [`README`](./README.md) §3-4). 불확실한 병합·연결은 하지 않고 후보/quarantine으로 유지한다.
- **Provenance 필수** (불변식 §3-2). source span 없는 모델 산출물은 authoritative graph에 넣지 않는다 ([`02`](./02-ontology.md) §4-1, [`03`](./03-storage-and-data-model.md) §8.3).
- **Event-driven & reversible** (불변식 §3-3). merge·supersession·quarantine은 `graph_mutations` event로 기록하고 되돌릴 수 있다 ([`03`](./03-storage-and-data-model.md) §7, [`06`](./06-graph-service.md)).
- **Human review as data** (불변식 §3-7). 사람의 교정은 원 모델 출력·수정 결과·이유를 함께 저장하는 골든셋 소스다 (§8, [`10`](./10-evaluation-and-testing.md)).
- **Deterministic-first.** 규칙·사전으로 판정 가능한 것은 LLM에 보내지 않는다. LLM은 모호·복합 사례에만 투입한다 (비용 통제, blueprint §9.2).

파이프라인 stage 개요 (blueprint §8.4–§8.9):

```text
normalized documents
  → (§1) Entity 후보 추출        → mentions
  → (§2) Entity Resolution       → resolved entity + SAME_AS / POSSIBLY_SAME_AS
  → (§3) Claim 추출              → claim_candidates (structured output)
  → (§4) Claim Canonicalization  → CanonicalClaim
  → (§5) Contradiction Detection → SUPPORTS / CONTRADICTS (+ conflict_type)
  → (§6) 그래프 반영 게이트       → authoritative graph | quarantine graph
  → (§8) Quarantine & Review     → golden set (→ 10)
```

---

## 1. Entity 후보 추출 (§8.4)

목표는 문서에서 **entity mention**을 빠짐없이(recall 우선) 뽑아 `mentions` 테이블([`03`](./03-storage-and-data-model.md) §4.1)에 적재하는 것이다. 이 단계는 해소를 하지 않는다. 표면형과 문맥만 확정한다.

### 1.1 추출 전략 (deterministic 우선, LLM 보완)

| 층위 | 수단 | 담당 | 산출 |
| --- | --- | --- | --- |
| L1 | deterministic parser (사전·gazetteer·정규식: ticker, LEI, QID, URL) | 규칙 | 강한 식별자 mention |
| L2 | NER (domain fine-tuned) | 모델 | Person/Org/Product/Technology/Location mention |
| L3 | LLM 보완 | LLM | 복합 엔터티, 암시적 참조(대명사·생략), coref, 역할(role) |

- L1·L2를 먼저 돌리고, **L3는 L1/L2가 놓친 span과 coreference에만** 투입한다 (전체 재추출 아님).
- L3 LLM은 반드시 `char_start`/`char_end` span을 반환해야 하며, span 없는 mention은 폐기한다 (provenance 원칙).

### 1.2 mention 레코드 (→ [`03`](./03-storage-and-data-model.md) §4.1 `mentions`)

`mentions` 테이블 컬럼에 더해, 해소 입력으로 쓰는 문맥·source 필드를 함께 저장한다.

```json
{
  "mention_id": "men-01J9...",
  "doc_id": "doc-9f2a...c1",
  "segment_id": "doc-9f2a...c1#p3.s2",
  "surface_text": "TSMC",
  "mention_type": "Organization",
  "char_start": 412,
  "char_end": 416,
  "aliases": ["Taiwan Semiconductor", "台積電"],
  "identifiers": { "ticker": "TSM", "lei": null },
  "context_window": "…said TSMC will expand its Arizona fab…",
  "source_id": "src-01J9...",
  "role_hint": "supplier",
  "resolved_entity_id": null,
  "extraction_version": { "model_id": "ner-domain-1", "schema_version": "0.1.0", "extraction_code_version": "git:abcdef1" }
}
```

- `identifiers`/`aliases`/`context_window`는 §2 Entity Resolution의 강한 신호다 ([`02`](./02-ontology.md) §2.2 `identifiers{}`).
- `resolved_entity_id`는 이 단계에서 `null`이며 §2에서 채워진다.

---

## 2. Entity Resolution (§8.5)

전체 엔터티 쌍을 비교하지 않는다. **precision-first** 캐스케이드로, 각 단계는 앞 단계가 확정하지 못한 것만 다음으로 넘긴다.

```text
candidate blocking
  → lexical & identifier matching   (deterministic accept)
  → embedding reranking             (후보 축소)
  → rule-based accept / reject
  → ambiguous  → LLM judge
  → uncertain  → quarantine (POSSIBLY_SAME_AS 유지)
```

### 2.1 Candidate blocking

O(n²) 비교를 피하기 위해 **blocking key**로 같은 버킷의 후보만 비교한다.

| blocking key | 정의 | 대상 타입 |
| --- | --- | --- |
| `identifier` | 정규화 식별자 값 (ticker/LEI/QID/GeoNames) | 전체 |
| `norm_name` | 소문자·공백·법인 접미사(Inc/Ltd/Corp) 제거한 이름 | Person/Org |
| `name_ngram` | 이름 char 3-gram MinHash band | 전체 |
| `phonetic` | Double Metaphone(사람·기관명) | Person/Org |

- 한 mention은 여러 key로 여러 버킷에 들어갈 수 있다 (recall 확보). 비교는 버킷 내부에서만 수행한다.
- blocking key는 `POSSIBLY_SAME_AS.blocking_key` 속성에 기록된다 ([`02`](./02-ontology.md) §3).

### 2.2 단계별 판정 (임계값은 pseudo, [`10`](./10-evaluation-and-testing.md)에서 튜닝)

```text
resolve(mention m, candidate c) -> ACCEPT | POSSIBLY | LLM | REJECT | QUARANTINE
# ACCEPT   = 결정적 외부식별자 exact match → SAME_AS 자동 병합 허용 (G4 유일 자동 경로)
# POSSIBLY = 비결정적 고신뢰 후보 → POSSIBLY_SAME_AS, 확정은 human/rule (자동 병합 금지)

# 1) identifier matching — 가장 강한 신호 (결정적 외부식별자 exact match)
if shared_identifier(m, c):            return ACCEPT      # 결정적, LLM 불필요 → SAME_AS

# 2) lexical matching
lex = jaro_winkler(norm_name(m), norm_name(c))
if lex >= 0.97 and type(m) == type(c): return POSSIBLY    # 강한 이름 일치이나 비결정적 → 후보 유지
if lex <  0.60:                        return REJECT

# 3) embedding reranking — name+context 임베딩
emb = cosine(embed(m.context), embed(c.context))
score = 0.5*lex + 0.5*emb

# 4) rule-based (precision 우선: 문턱을 높게)
if score >= 0.92 and not type_conflict and not hard_negative(m, c): return POSSIBLY  # 고신뢰 후보, 자동 병합 금지
if score <  0.55 or  type_conflict:                                 return REJECT

# 5) 중간 신뢰 [0.75, 0.92) → LLM judge (모호 사례만 LLM 투입)
if 0.75 <= score < 0.92:               return LLM

# 6) 저신뢰 [0.55, 0.75) 및 그 외 → quarantine (POSSIBLY_SAME_AS 유지)
return QUARANTINE
```

- `hard_negative`: 상충하는 식별자(다른 ticker/LEI), 양립 불가한 jurisdiction 등 → 즉시 REJECT.
- **precision > recall 원칙**: 자동 `SAME_AS` 병합은 **결정적 외부식별자 exact match(1단계)로만** 한다. 점수 기반 고신뢰(≥0.92)·강한 이름 일치(lex≥0.97)는 `ACCEPT`가 아니라 `POSSIBLY_SAME_AS` 후보로만 남기고, 확정은 인간 확인 또는 식별자 매칭을 요구한다 (G4, ADR-507). 애매하면 병합하지 **않고** 후보로 남긴다 (불변식 §3-4, blueprint §8.5·§17).

**Arbitration (다중 후보 조정).** `resolve(m, c)`는 pair 단위 판정이라, 한 mention이 여러 candidate에 대해 상충하는 결과를 낼 수 있다. 병합 전 mention별로 결과를 집계한다 (전이 병합으로 인한 불변식4 위반 방지):

- 결정적 `ACCEPT`가 **정확히 하나**면 그 entity로 `SAME_AS` 병합한다.
- 결정적 `ACCEPT`가 **둘 이상**이고 대상 entity들이 서로 `SAME_AS`로 이미 연결돼 있지 **않으면** → **병합 금지**. 전원 `POSSIBLY_SAME_AS`로 강등하고 quarantine(`ambiguous_merge`, §7)로 보낸다.
- `ACCEPT`가 없고 `POSSIBLY`/`LLM` 후보만 있으면, 자동 병합하지 않고 후보들을 `POSSIBLY_SAME_AS`로 유지한다(최고점 후보를 대표 후보로 표시하되 확정하지 않음).

### 2.3 LLM judge I/O (structured output)

모호 사례만 LLM에 보낸다. 입력·출력 모두 JSON schema로 계약한다.

```json
// input
{
  "task": "entity_resolution_judge",
  "mention": { "surface_text": "…", "context_window": "…", "identifiers": {}, "type": "Organization" },
  "candidate": { "entity_id": "org-01J9...", "canonical_name": "…", "aliases": [], "identifiers": {} },
  "blocking_key": "norm_name",
  "score": 0.81
}
// output (structured)
{
  "decision": "same" | "different" | "uncertain",
  "confidence": 0.0,
  "rationale": "두 문맥 모두 Arizona fab 확장을 다루며 식별자 TSM 일치",
  "evidence_spans": [{ "doc_id": "doc-…", "char_start": 412, "char_end": 416 }]
}
```

- `decision=same` ∧ `confidence ≥ 임계` → **`POSSIBLY_SAME_AS` 후보 생성(`create_edge`)**. LLM 판정만으로 `SAME_AS` 자동 병합하지 않는다 — 확정은 인간 확인 또는 결정적 외부식별자 exact match로만 (G4, ADR-507).
- `decision=different` → REJECT. `uncertain` 또는 저신뢰 → QUARANTINE (`POSSIBLY_SAME_AS` 유지).
- LLM 출력에도 `evidence_spans`를 요구해 provenance를 유지한다.

### 2.4 Merge를 event로 저장·reversible

해소 결과는 두 종류의 event로 기록된다 (불변식 §3-3, [`03`](./03-storage-and-data-model.md) §7, [`06`](./06-graph-service.md)).

| 판정 경로 | 그래프 표현 | mutation `op` | 되돌리기 |
| --- | --- | --- | --- |
| ACCEPT — 결정적 외부식별자 exact match **또는** 인간 확인(§8) | `SAME_AS` edge + canonical 대표 지정 | `merge_entity` | `unmerge` 역이벤트 |
| POSSIBLY — 점수 고신뢰(≥0.92)·lexical(≥0.97) 후보 | `POSSIBLY_SAME_AS` edge (`score`, `blocking_key`) | `create_edge` | `delete` |
| LLM `same` / QUARANTINE (미확정) | `POSSIBLY_SAME_AS` edge (`score`, `blocking_key`, `judged_by`) | `create_edge` | `delete` |
| REJECT / `different` | (no edge) | — | — |

- **`SAME_AS`(+`merge_entity`)는 두 경로로만 확정된다** (G4, ADR-507): (a) 결정적 외부식별자 exact match, (b) 인간 확인(§8 review의 `approve`/`correct`). LLM·점수·이름 기반 고신뢰는 모두 `POSSIBLY_SAME_AS` 후보에 머문다.
- **`SAME_AS` 확정 전에는 `POSSIBLY_SAME_AS`를 사용한다** (blueprint §8.5, [`02`](./02-ontology.md) §3). 후보 관계는 War Table에서 `edge-uncertain`(점선+?)으로 표시된다 ([`02`](./02-ontology.md) §3.2).
- 모든 판정은 `resolution_decisions`(`res-<ULID>`)에 근거를 남기고, `graph_mutations.resolution_ref`가 이를 가리킨다 ([`03`](./03-storage-and-data-model.md) §7.1).
- ID는 재작성하지 않는다. 병합은 `SAME_AS`/canonical 매핑으로만 표현한다 ([`README`](./README.md) §2.2, [`02`](./02-ontology.md) §4-5).

### 2.5 `resolution_decisions` 레코드

| 컬럼 | 설명 |
| --- | --- |
| `resolution_id` | `res-<ULID>` |
| `mention_id` / `candidate_entity_id` | 대상 |
| `decision` | `accept`/`reject`/`possibly`/`quarantine` |
| `stage` | `identifier`/`lexical`/`embedding`/`rule`/`llm` |
| `score` / `blocking_key` | 판정 근거 신호 |
| `actor` | `pipeline`/`llm:<model>`/`human:<user>` |
| `rationale` | 판정 이유 (LLM/사람) |
| `review_history[]` | 사람 교정 이력 (→ §8) |
| `version_tuple` | ontology/schema/prompt/model/extraction_code_version (README §2.3 5축) |

---

## 3. Claim 추출 (§8.6)

LLM은 문서를 자유 형식으로 요약하지 않는다. **source span에 근거한 구조화 출력**만 생성한다. 산출물은 `claim_candidates`([`03`](./03-storage-and-data-model.md) §4.2, `status=candidate`)에 적재되며 스키마는 [`02`](./02-ontology.md) §2.4 `Claim`과 정합해야 한다.

### 3.1 추출 스키마 (JSON schema 계약)

```json
{
  "$schema": "claim_extraction/0.1.0",
  "type": "object",
  "required": ["subject", "predicate", "object", "modality", "polarity",
               "certainty", "source_span", "confidence"],
  "properties": {
    "subject":     { "type": "string", "description": "resolved entity mention 참조" },
    "predicate":   { "enum": ["depends_on","supplies","invests_in","acquires",
                              "partners_with","manufactures","regulates","announces",
                              "located_in","has_capacity","has_market_share"] },
    "object":      { "type": ["string","null"] },
    "object_literal": {},                          // object가 값일 때 (금액·비율)
    "qualifier":   { "type": "object",
                     "properties": { "scope": {"type":"string"},
                                     "quantity": {} } },
    "modality":    { "enum": ["fact","asserted","opinion","prediction"] },
    "polarity":    { "enum": ["positive","negative"] },
    "certainty":   { "type": "number", "minimum": 0, "maximum": 1 },   // 화자 확실성
    "valid_from":  { "type": ["string","null"], "format": "date" },
    "valid_to":    { "type": ["string","null"], "format": "date" },
    "time_precision": { "enum": ["year","quarter","month","day","unknown"] },
    "source_span": { "type": "object",
                     "required": ["doc_id","segment_id","char_start","char_end"] },
    "speaker":     { "type": ["string","null"], "description": "주장한 주체(저자/인용 화자)" },
    "confidence":  { "type": "number", "minimum": 0, "maximum": 1 }    // 추출 모델 신뢰도
  }
}
```

### 3.2 [`02`](./02-ontology.md) Claim과의 매핑

| 추출 스키마 필드 | Claim 속성 ([`02`](./02-ontology.md) §2.4) | 비고 |
| --- | --- | --- |
| `subject` / `object` | `subject_id` / `object_id` | §2 해소된 entity ID로 치환 |
| `object_literal` | `object_literal` | 수량·비율·금액 |
| `predicate` | `predicate` | controlled vocabulary ([`02`](./02-ontology.md) §5.1). 미등록 → §6 quarantine |
| `modality` | `modality` | fact/asserted/opinion/prediction |
| `polarity` / `certainty` | `polarity` / `certainty` | `certainty`=화자 확실성 |
| `valid_from/to` / `time_precision` | 동일 | 미상은 `null`+`time_precision` ([`README`](./README.md) §2.4) |
| `source_span` | `provenance_ref` → `extraction_records`([`03`](./03-storage-and-data-model.md) §8.2) | span 없으면 폐기 |
| `speaker` | `speaker_id` | 해소된 entity ID |
| `confidence` | `confidence` | **모델** 신뢰도. `certainty`와 구분 ([`02`](./02-ontology.md) ADR-202) |

- **`confidence`(모델)와 `certainty`(화자)는 별개다** ([`02`](./02-ontology.md) §2.4 주의). 스키마에서 분리 강제.
- `subject`/`object`/`speaker`는 §2 해소를 거쳐 entity ID로 치환된 뒤에만 promotion 대상이 된다 (Reference 무결성, [`02`](./02-ontology.md) §4-3).
- **Evidence(`evd-`)는 별도 추출 stage가 아니라 source span 그 자체다**: claim의 `source_span`이 `extraction_records`([`03`](./03-storage-and-data-model.md) §8.2)로 물질화되며, 이것이 evidence 참조의 정본이다. 별도 evd- 생성 파이프라인은 두지 않는다.

---

## 4. Claim Canonicalization (§8.7)

표현이 다르지만 의미가 같은 `Claim`을 하나의 `CanonicalClaim`([`02`](./02-ontology.md) §2.4)으로 묶는다. **후보 축소 → LLM 관계 판정** 순서로 비용을 통제한다.

### 4.1 후보 축소 (blocking)

모든 claim 쌍을 비교하지 않는다. 다음이 겹치는 claim만 후보로 만든다:

```text
same (or SAME_AS-linked) subject
  ∧ same-or-related predicate
  ∧ overlapping time window (valid_from/valid_to)
→ canonicalization candidate pair
```

### 4.2 관계 판정 라벨 (LLM structured output)

축소된 후보쌍에 대해 LLM이 7개 라벨 중 하나를 판정한다.

| 라벨 | 의미 | 그래프 반영 |
| --- | --- | --- |
| `equivalent` | 의미 동일 | 같은 `CanonicalClaim.member_claim_ids[]`에 병합 |
| `more_specific` | A가 B보다 구체적 | `QUALIFIES` (A→B) |
| `more_general` | A가 B보다 일반적 | `QUALIFIES` (B→A) |
| `supports` | A가 B를 지지 | `SUPPORTS` (§5로 이관 가능) |
| `contradicts` | A가 B를 반박 | `CONTRADICTS` (→ §5 판정) |
| `unrelated` | 무관 | (no edge) |
| `temporally_superseded` | 시간상 이전 버전 대체 | `SUPERSEDES` (bitemporal, [`03`](./03-storage-and-data-model.md) §6) |

```json
// LLM output
{
  "task": "claim_canonicalization",
  "pair": ["clm-01J9A...", "clm-01J9B..."],
  "relation": "equivalent",
  "canonical_text": "TSMC는 Arizona fab 생산능력을 2025년 확장한다.",
  "confidence": 0.88,
  "rationale": "동일 subject/predicate, 동일 valid window, 표현만 상이"
}
```

- `equivalent` 판정이 확정되면 `CanonicalClaim`(`ccl-<ULID>`)을 생성/연결하고 `Claim.canonical_claim_id`를 채운다.
- `temporally_superseded`는 `SUPERSEDES` event로 기록되어 bitemporal supersession을 만든다 ([`03`](./03-storage-and-data-model.md) §6.2, [`02`](./02-ontology.md) §3).
- 저신뢰 판정은 §6 게이트에서 quarantine된다.

---

## 5. Contradiction Detection (§8.8)

모든 claim 쌍을 직접 비교하지 않는다. **그래프 규칙으로 충돌 후보**를 만들고 **LLM이 실제 모순 여부**를 판정한다. 반박은 binary가 아니다 ([`02`](./02-ontology.md) §3.1).

### 5.1 충돌 후보 규칙 (deterministic)

```text
same subject
  ∧ same-or-incompatible predicate
  ∧ mutually exclusive object / value
  ∧ overlapping valid time
→ contradiction candidate
```

- mutually exclusive 예: `has_market_share`가 동일 subject·기간에 서로 다른 값, 또는 `depends_on`의 `polarity`가 positive vs negative.
- overlapping valid time은 `time_precision`을 반영해 판정한다 (허위 모순 방지, [`README`](./README.md) §2.4).

### 5.2 LLM 판정: 실제 모순 vs 시간차 vs 범위차

```json
// LLM output
{
  "task": "contradiction_detection",
  "pair": ["clm-01J9A...", "clm-01J9B..."],
  "verdict": "real_conflict" | "temporal" | "scope" | "not_conflict",
  "conflict_type": "value_conflict" | "temporal" | "scope",
  "rationale": "두 값은 서로 다른 세그먼트(HBM vs 로직)를 지칭 → scope 차이",
  "confidence": 0.8,
  "evidence_spans": [ { "doc_id": "doc-…", "char_start": 0, "char_end": 0 } ]
}
```

### 5.3 저장 계약

- `CONTRADICTS`/`SUPPORTS` edge에 **`rationale`(판정 이유)와 `judged_by`(모델/사람)를 반드시 저장**한다 ([`02`](./02-ontology.md) §3.1, blueprint §8.8).
- `conflict_type`은 `value_conflict`/`temporal`/`scope`로 구분한다. `temporal`은 모순이 아니라 supersession 후보로 재분류될 수 있다 (→ §4 `temporally_superseded`).
- `verdict=not_conflict`는 edge를 만들지 않는다. UI는 `CONTRADICTS`를 `edge-contradicts`(이중선)로 표시한다 ([`02`](./02-ontology.md) §3.2).

---

## 6. 그래프 반영 게이트 (§8.9)

추출·해소 산출물은 curated zone에 머물다가 이 게이트를 통과해야 authoritative graph에 진입한다. 게이트는 두 검증을 강제한다 ([`02`](./02-ontology.md) §4, [`06`](./06-graph-service.md)).

```text
candidate (claim_candidates / mentions / edges)
  → (1) schema validation      : 타입·필수속성·confidence 범위 [0,1]
  → (2) provenance validation  : provenance_ref ≥ 1 (source span 존재)
  → (3) predicate 폐쇄성        : predicate ∈ controlled vocabulary
  → (4) confidence 게이트       : confidence ≥ promotion 임계
       ┌── 모두 통과 ─────────► authoritative graph  (append-only event)
       └── 실패 ──────────────► quarantine graph      (§8 review)
```

| 검증 실패 조건 | 처리 |
| --- | --- |
| `provenance_ref` 없음 (source span 부재) | quarantine (불변식 §3-2, [`03`](./03-storage-and-data-model.md) §8.3) |
| 미등록 `predicate`/노드 타입 | quarantine + 온톨로지 proposal 트리거 ([`02`](./02-ontology.md) §4-2·§6.2) |
| `confidence` < promotion 임계 | quarantine (저신뢰) |
| Reference 무결성 위반 (미해소 subject/object) | quarantine, §2 재해소 대기 |
| schema/time 정합성 위반 | reject 또는 quarantine |

- **promotion 임계값(게이트 (4))은 element 종류(claim/edge/mention)별로 다르며, 구체 값과 튜닝은 [`10`](./10-evaluation-and-testing.md)이 소유한다** (이 문서는 게이트 규칙만 정의하고 값은 위임).
- **승인된 변경은 append-only event로만 기록**한다: `create_node`/`create_edge`/`merge_entity`/`supersede` ([`03`](./03-storage-and-data-model.md) §7). materialized graph는 event log replay로 재구축 가능해야 한다 (불변식 §3-1·§3-3).
- 게이트 통과·실패 모두 `correlation_id`로 end-to-end 추적된다 ([`03`](./03-storage-and-data-model.md) §7.1, [`11`](./11-observability-and-governance.md)).

---

## 7. Quarantine Graph

quarantine은 "버리는 곳"이 아니라 **격리·검토·학습 소스**다. 지금은 authoritative graph와 **논리적으로 분리**(상태 라벨 `:Quarantine` vs `:Authoritative`)하며, 확장 시 물리적으로 분리된 별도 그래프(Memgraph)로 이전한다 ([`06`](./06-graph-service.md) §4.1 ADR-603).

### 7.1 진입 조건 (요약)

| 출처 stage | 조건 |
| --- | --- |
| Entity Resolution (§2) | `uncertain`/`quarantine` 판정, `POSSIBLY_SAME_AS` 후보 |
| Claim 추출 (§3) | source span 부재, 미해소 subject/object |
| Canonicalization (§4) | 저신뢰 관계 판정 |
| Contradiction (§5) | 저신뢰 `verdict` |
| 게이트 (§6) | provenance/predicate/confidence 검증 실패 |

### 7.2 quarantine 레코드 상태

| 필드 | 설명 |
| --- | --- |
| `quarantine_id` | ULID |
| `element_ref` | 대상 candidate/edge |
| `reason` | `no_provenance`/`unknown_predicate`/`low_confidence`/`ambiguous_merge`/`ref_integrity` |
| `entered_at` / `dwell_time` | 진입 시각·체류 시간 (blueprint §11 관측) |
| `review_status` | §8 상태 |

---

## 8. Review Workflow & Human Review as Data

quarantine과 저신뢰 결정은 사람 검토로 흐른다. 검토는 단순 수정 UI가 아니라 **골든셋 생성 과정**이다 (불변식 §3-7, blueprint §17).

### 8.1 review 상태 전이

```text
pending ──assign──► in_review ──┬─ approve ──► promoted     (→ authoritative graph, event 발행)
                                ├─ correct ──► corrected    (수정본 promotion)
                                ├─ reject  ──► rejected     (근거 남기고 폐기)
                                └─ escalate ► proposal      (온톨로지 proposal, → 02 §6.2)
```

- `approve`/`correct`는 게이트(§6)를 다시 통과해 append-only event로 그래프에 반영된다.
- 미등록 predicate 누적은 `escalate → proposal`로 온톨로지 변경 절차를 트리거한다 ([`02`](./02-ontology.md) §6.2).

### 8.2 Human review as data (골든셋)

모든 검토 결정에 다음 3요소를 함께 저장한다 (불변식 §3-7, [`03`](./03-storage-and-data-model.md) §8.2 `review_history[]`).

```json
{
  "review_id": "…",
  "element_ref": "clm-01J9... | res-01J9... | edge",
  "original_model_output": { "...": "모델이 낸 원 판정 (해소/추출/canonicalization/contradiction)" },
  "human_decision": { "verdict": "corrected", "corrected_value": { } },
  "reason": "predicate는 supplies가 아니라 depends_on — 문맥상 의존 관계",
  "reviewer": "human:jane",
  "reviewed_at": "2026-08-03T09:00:00Z",
  "version_tuple": { "ontology_version": "1.0.0", "model_id": "claude-sonnet-5" }
}
```

- 이 레코드가 **골든 데이터셋**의 원천이 된다 ([`10`](./10-evaluation-and-testing.md)). Entity Resolution·Claim Extraction·Canonicalization·Contradiction 각 stage별 라벨로 회귀 평가에 쓰인다 (blueprint §12·§15·§17).
- 원 모델 출력을 보존하므로 모델·프롬프트 교체 시 동일 케이스 재평가가 가능하다 ([`README`](./README.md) §2.3, [`02`](./02-ontology.md) §6.3).

**구현 (Phase 2 — review→골든 파생 경로, 2026-08-12):** `review.py`에 `derive_golden(rq, zone, gold_version, labeled_by, split)` 추가 — human review 결정(ADR-506)을 zone 의 골든 claim pair(`persist_golden_pair`)·entity pair(`persist_golden_entity_pair`)로 파생. corrected/approved 결정만 파생하고(pending/in_review 는 골든 원천 아님), 인간 교정본(`corrected_value`)의 `verdict`를 골든 라벨로, `claim_b`(claim 골든: equivalent/contradicts/unrelated) 또는 `entity_a`/`entity_b`(entity 골든: same/not_same)로 쌍을 추출 — 불변식 §3-7(원출력+수정+이유 보존). human review 가 metrics_report/DoD ① 의 골든셋으로 이어지는 경로 완결. 결정적 멱등(persist_golden_* 의 ON CONFLICT no-op, 03 §5) · ADR-1007 split. TDD — `test_review_golden` 신규 5개(claim 파생·entity 파생·미결정 skip·멱등·결정적) — 스위트 526→**531개 통과**(회귀 0).

---

## 9. 의사결정 로그 (ADR-5xx)

| ID | 결정 | 근거 | 상태 |
| --- | --- | --- | --- |
| ADR-501 | Entity Resolution positive-link 후보 임계(≈0.92)를 reject 임계보다 높게 두는 **precision-first threshold** | 오병합은 연결된 전 claim을 오염시킴; 불확실은 병합 대신 후보 유지 (불변식 §3-4, blueprint §8.5·§17) | Accepted |
| ADR-502 | 확정(`SAME_AS`) 전 **`POSSIBLY_SAME_AS`** 후보 관계 사용, merge는 `merge_entity` event로 reversible | reversible merge·audit (불변식 §3-3, [`03`](./03-storage-and-data-model.md) §7.2, [`02`](./02-ontology.md) §3) | Accepted |
| ADR-503 | Canonicalization 라벨셋을 7종(equivalent/more_specific/more_general/supports/contradicts/unrelated/temporally_superseded)으로 고정 | blueprint §8.7 명세와 정합, temporal supersession을 모순과 분리 | Accepted |
| ADR-504 | Contradiction은 binary 아님 — `conflict_type`(value_conflict/temporal/scope) + `rationale` 필수 저장 | 시간차·범위차를 모순으로 오판 방지 ([`02`](./02-ontology.md) §3.1, blueprint §8.8) | Accepted |
| ADR-505 | 추출 스키마에서 `confidence`(모델)와 `certainty`(화자)를 분리 강제, 미해소 subject/object는 promotion 차단 | 신뢰도 과대평가·reference 무결성 위반 방지 ([`02`](./02-ontology.md) ADR-202·§4-3) | Accepted |
| ADR-506 | quarantine 진입 원소와 사람 검토 결정을 **원 모델출력+수정결과+이유**로 저장해 골든셋화 | human review as data (불변식 §3-7, [`10`](./10-evaluation-and-testing.md)) | Accepted |
| ADR-507 | ER 확정 병합(`SAME_AS`+`merge_entity`)은 **결정적 외부식별자 exact match 또는 인간 확인으로만**. LLM `same`·점수/이름 기반 고신뢰는 `POSSIBLY_SAME_AS` 후보에 머물고 자동 병합하지 않는다. 다중 후보는 arbitration으로 조정(충돌 시 병합 금지→quarantine) | 오병합은 전이적으로 연결된 claim을 오염(불변식4); LLM·유사도는 비결정적 → 후보 유지가 precision-first에 부합 (G4, 불변식 §3-4, blueprint §8.5) | Accepted |
