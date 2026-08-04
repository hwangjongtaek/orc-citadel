# S7 Claim 추출 — 결정적 규칙 기반 최소 (설계 05 §3, 02 §2.4·§5.1)

> 권장안 선정. 해소된 entity·mention 위에서 **결정적 규칙으로 predicate 후보**를 추출하고
> `claim_candidates`(03 §4.2)에 영속한다. LLM 의존 canonicalization/canonicalization/
> contradiction은 스텁/후속 — 정규·중요 predicate만 규칙 엔진이 잡는다 (precision 우선).
> 대상 문서: [05-resolution-and-extraction.md](../../docs/design/05-resolution-and-extraction.md) §3,
> [02-ontology.md](../../docs/design/02-ontology.md) §2.4·§5.1, 03 §4.2.

## 배경·범위

| 결정 | 근거 |
| --- | --- |
| **결정적 predicate 패턴(규칙)으로만 추출** | 설계 05 §5 "deterministic-first": 규칙·사전으로 판정 가능한 것만 LLM에 보내지 않는다. L1 mention 추출처럼 순수 Python |
| **claim_candidates(`status=candidate`) 영속** | 03 §4.2: 별도 `claims` 테이블 없이 claim_candidates가 claim-of-record(후속 promote 시). prototype은 `candidate`로 저장 |
| **source_span은 clean text 축** `(doc, seg, char_start/end)` | provenance 필수 (03 §8.2, ADR-302). 문자열 (segment_id, char_start, char_end)로 보존 |
| **subject/object는 해소된 entity_id** | 02 §4-3 Reference 무결성: 미해소는 promote 차단. 규칙이 subject로 쓸 entity는 이미 해소된 mention의 `resolved_entity_id` |
| **modality/polarity/confidence 기본값 부여** | 02 §2.4: `modality=asserted` 등. prototype은 규칙에선 고정 기본값 + certainty null |
| **canonicalization(§4)·contradiction(§5)·LLM 추출 제외** | LLM·embedding 의존, 후속 |

## 구현 계획

- **`extract_claims.py`** (신규): 결정적 predicate 규칙이 각 segment(문장)에서
  `(predicate, subject_entity, object, object_literal, event_type_hint)` 후보를 낸다.
  입력은 (doc_id, segments, resolved mention index). `ClaimCandidate` dataclass 산출.
- **predicate 규칙 테이블** (`PREDICATE_RULES`): regex → (predicate, modality 등).
  - `host a conference call|will host|announces|holds` → `announces` + event earnings
  - `powers|enables|supplies fuels|depends on` → `announces`/`manufactures` 샘플
  - (prototype: 소수 규칙, 확장은 규칙 추가로 — 05 §5 결정적)
- **`curated_zone.py`** (수정): `claim_candidates` 테이블(03 §4.2) + persist/query + parquet.
  컬럼: claim_candidate_id(`clm-`), doc_id, source_span(segment_id, char_start, char_end),
  predicate, subject_id/object_id/object_literal, modality, polarity, confidence,
  status=candidate, observed_at, ontology_version, extraction_model.
- **`claim_smoke.py`** (신규): 실수집 6건 → 해소 → 규칙 claim 추출 → 영속·조회.
- **TDD 테스트**.

## DoD

- NVIDIA 공시 doc: `announces`(conference call → earnings type) 1+건 추출, source_span으로
  segment.text slice 재현 (provenance 왕복)
- Jetson doc: 규칙-잡히는 claim(있으면) 추출; SemiEngineering(본문 크롬만)은 0건 (precision)
- subject는 해소된 entity id (NVIDIA)로 바인딩
- claim_candidates 영속·조회·parquet export, 전체 테스트 통과, code-only 커밋

## 한계 (문서화)

- LLM 추출·canonicalization·contradiction·POSSIBLY/quarantine 게이트·human review는 후속
- object_id vs object_literal XOR 중 object_literal 우선 최소 — entity object는 규칙이 명시적으로
  해소 mention에서만 바인딩
- source_span은 clean text 축 (raw HTML 축 역매핑은 후속, 04 §3.4)
