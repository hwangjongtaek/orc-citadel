# S10 Contradiction — 결정적 충돌 후보 규칙 (설계 05 §5.1, 02 §3.1·ADR-504)

> 권장안 선정. claim 쌍의 충돌 후보를 **결정적 그래프 규칙**(05 §5.1)으로 생성하고
> `conflict_candidates`에 저장한다. LLM 판정(§5.2 verdict/conflict_type)은 스텁 —
> prototype은 규칙 판정(actor=pipeline)으로 상충 사실 여부만 후보화 (precision-first).
> 대상 문서: [05-resolution-and-extraction.md](../../docs/design/05-resolution-and-extraction.md) §5,
> [02-ontology.md](../../docs/design/02-ontology.md) §3.1, 03 §4.

## 배경·범위

| 결정 | 근거 |
| --- | --- |
| **충돌 후보 규칙(§5.1) 결정적 구현** — same subject ∧ same-or-incompatible predicate ∧ mutually exclusive object/양극 | 05 §5.1: 후보 생성은 deterministic. LLM은 "실제 모순 여부"만 판정(§5.2) — prototype은 규칙 선까지 |
| **conflict_type 저장** (value_conflict/temporal/scope) | 02 §3.1·ADR-504: 반박은 binary 아님, 타입·rationale 필수 |
| **LLM 판정(§5.2)·evidence_spans·SUPPORTS/CONTRADICTS edge 생성은 스텁** | LLM 의존 — 결정적 규칙 범위 밖 |
| **rationale·judged_by(actor) 저장 계약 유지** (§5.3) | §5.3: edge에 rationale·judged_by 필수. prototype은 규칙 판정 `actor=pipeline` |
| **실수집은 모순 후보 없음 — 합성으로 규칙 검증** | 실측: 전 claim `announces`·`positive`라 상충 쌍 없음. 규칙 정당성은 TDD 합성 케이스로 증명 (설계 원칙: 실제 데이터가 없는 경로도 규칙은 정당해야) |

## 핵심 계약

- `conflict_candidates`: 같은 blocking 그룹(same subject, same-or-incompatible predicate)
  내에서 **상충 신호**(candidate A vs B) → `(claim_id_a, claim_id_b, conflict_type, rationale, judged_by, created_at)`
- **결정 규칙** (05 §5.1 mutually exclusive):
  - `polarity` positive vs negative → `value_conflict` 후보
  - object_literal 서로 다른 값 (동일 predicate에서) → `value_conflict`
  - predicate incompatible (depends_on-supplies 반대 방향 등 최소) → 후보
  - verdict는 `conflict` 후보화로만 (실제 모순 확인은 후속 LLM)
- **결정성·idempotency** (03 §5): 같은 claim 쌍 → 같은 conflict 후보.

## 구현 계획

- **`contradiction.py`** (신규): `find_conflict_candidates(claims) → list[ConflictCandidate]`
  - blocking: (subject, predicate-호환) 그룹 → 상충 쌍
  - `ConflictCandidate`: claim_id_a/b, conflict_type, rationale, judged_by
- **`curated_zone.py`** (수정): `conflict_candidates` 테이블 + persist/query/parquet
- **`contradiction_smoke.py`** (신규): 실수집(모순 없음 → 후보 0건 검증) + (선택) 합성 주입으로 후보 생성 시연
- **TDD 테스트**

## DoD

- 합성: same subject·same predicate·positive vs negative → `value_conflict` 후보 + rationale
- 합성: object_literal 상충 값 → 후보; identical claim은 후보 아님
- conflict 대한 결정성·judged_by=pipeline 저장
- 실수집 모순 후보 0건 (정직) — 규칙은 TDD로 검증
- 전체 테스트 통과, code-only 커밋

## 한계 (문서화)

- LLM 판정(§5.2)·SUPPORTS/CONTRADICTS edge·evidence_spans·verdict 분류(temporal/scope)
  재분류는 후속
- overlapping valid time(허위 모순 방지)은 claim valid null이라 prototype에선 생략 — 후속
- 실수집 모순 부재는 데이터 특성(90% 이상 동일 이벤트 계열) — 1만 문서에서 상충 풍부화 예상
