# S9 Claim Canonicalization (설계 05 §4, 02 §2.4·§3.1) — 결정적 최소

> 권장안 선정. 표현이 다르지만 의미가 같은 claim을 하나의 CanonicalClaim으로 묶는다.
> LLM 관계 판정(§4.2)은 후속 스텁 — prototype은 **결정적 규칙으로 `equivalent`만** 판정.
> 대상 문서: [05-resolution-and-extraction.md](../../docs/design/05-resolution-and-extraction.md) §4,
> [02-ontology.md](../../docs/design/02-ontology.md) §2.4(CanonicalClaim)·§3.1(MEMBER_OF), 03 §4.2.

## 배경·범위

| 결정 | 근거 |
| --- | --- |
| **후보 축소(§4.1) 결정적** — same subject ∧ same predicate | O(n²) 방지 blocking, 결정적. (시간 window는 prototype claim이 valid null이라 생략 — 후속) |
| **`equivalent`만 결정적 판정**: 같은 blocking 그룹 ∧ 겹치는 source_span(같은 문장 표면형) | 실수집에서 반복 매칭(power·powered·conference call)이 전형. LLM 없이 결정적으로 "같은 표현" 판정 |
| **나머지 6라벨(more_specific/general/supports/contradicts/unrelated/superseded)은 스텁** | 의미 관계는 비결정적 → LLM 의존 (05 §4.2, ADR-503) |
| **CanonicalClaim(`ccl-`) + `MEMBER_OF` 엣지(정본)** | 02 §2.4 정의 + §3.1: 소속의 정본은 MEMBER_OF 엣지, member_claim_ids/canonical_claim_id는 파생 |
| **Claim.canonical_claim_id 채움** (03 §4.2 claim_candidates) | 파생 표현, canonical_claim_id 컬럼에 반영 |

## 구현 계획

- **`canonicalize.py`** (신규): `canonicalize_claims(claims) → list[CanonicalClaim]`
  - blocking: (subject_id, predicate) 그룹
  - `equivalent`: 그룹 내 claim들이 서로 source_span 겹침(같은 문장 표현) → 하나의 CanonicalClaim
  - CanonicalClaim: `ccl-` 결정적 ID + canonical_text(대표: 가장 긴/uniq surface) + member_claim_ids + 정규 삼항(subject/predicate)
- **`curated_zone.py`** (수정): `canonical_claims` 테이블(02 §2.4) + `member_of` 엣지(03 §3.1) + claim.canonical_claim_id 반영 + parquet
- **`canonicalize_smoke.py`** (신규): 실수집 → claim → gate → canonicalize → 영속
- **TDD 테스트**

## DoD

- NVIDIA·announces 6건 중 겹치는 span claim들이 1 CanonicalClaim으로, GeForce NOW·announces 2건도 1개로
- CanonicalClaim에 member_claim_ids·canonical_text·정규 삼항, MEMBER_OF 엣지 영속
- claim_candidates.canonical_claim_id 채워짐
- 결정성·idempotency (같은 입력 → 같은 ccl), 전체 테스트 통과, code-only 커밋

## 한계 (문서화)

- 시간 window 기반 blocking(§4.1)·LLM 관계 판정(§4.2 전 라벨)·low-conf quarantine(게이트 후속 연동)은 후속
- canonical_text는 결정적 대표(가장 긴 surface) — 자연어 정규화는 LLM 후속
- prototype CanonicalClaim은 (subject, predicate, uniq surface) 동치류 — object까지 완전한 의미 정규화는 후속
