# S11 Assertion Materialization (설계 03 §6.2·§7, ADR-306)

> 권장안 1 선택. 게이트로 promoted된 claim의 **정규 삼항 Assertion**을 bitemporal
> (valid + transaction 두 시간 축)로 materialize한다. Claim→Assertion emission 계약
> (ADR-306) 충족. 대상: [03-storage-and-data-model](../../docs/design/03-storage-and-data-model.md) §6.2·§7,
> 02 §2.4·§3(SUBJECT/OBJECT edge).

## 배경·범위

| 결정 | 근거 |
| --- | --- |
| **promoted claim → Assertion 1:1 materialize** | 03 §6.2: Assertion은 system-versioned projection (재구축 가능) |
| **정규 삼항** `(subject_id, predicate, object_id|object_literal)` | 02 §2.4 Claim→Assertion materialization 규칙 (object_id/object_literal XOR) |
| **bitemporal 두 축** | §6.1: valid time(현실 유효) + transaction time(시스템 관찰). `tx_to=null` → 현재 버전 |
| **`supersedes_id`/`superseded_reason`** | bitemporal supersession (ADR-303/307). prototype은 null + "supersedes" 체인 예비 |
| **`mutation_id` 부여 — append-only event로만** | §7.1: 생성은 `create_node` mutation 이벤트. 재생(replay)으로 assertions projection 재구축 |
| **`provenance_ref`** | §8: claim의 source_span(extraction_record) 참조 |
| **추출·해소·게이트·canonicalize·contradiction은 기존 재사용** | S1→S10 기반 위. 이 단계 산출은 assertions |

## 구현 계획

- **`assertions.py`** (신규): `materialize(claim, observed_at, mutation) → Assertion`
  - assertion_id = `asr-` + 결정적 hash (claim_id 기반, §5 idempotency)
  - valid time은 claim.valid_from/to·time_precision (null + unknown 허용)
  - tx_from = observed_at, tx_to = null (현재 버전)
  - provenance_ref = extraction_record 참조 (prototype: claim span string)
- **`gate.py`** (수정): promoted claim에 `create_node` emission → materialize 연동
  (이미 create_node 이벤트 발행 — Assertion은 여기서 소비)
- **`curated_zone.py`** (수정): `assertions` 테이블 + persist/query/parquet + supersede close
- **`assertions_smoke.py`** (신규): 실수집 → promote → Assertion materialize → 영속
- **TDD 테스트**

## DoD

- promoted claim → Assertion(정규 삼항·bitemporal) materialize, asr- id 결정적
- tx_to null(현재 버전), valid time 반영, provenance_ref 연결
- append-only create_node 이벤트(게이트) ↔ Assertion projection 재구축 가능
- assertions 영속·조회·parquet, 전체 테스트 통과, code-only 커밋

## 한계 (문서화)

- supersession(슈퍼슬라이드 close)·버전 체인·`supersede` mutation은 후속 (prototype은 첫 버전)
- Assertion을 그래프 엣지(SUBJECT/OBJECT)로 materialize는 06 그래프 서비스 후속
- LLM canonicalization 전 단계의 Assertion은 규칙 기반 (후속 LLM 재추출 시 재materialize)
