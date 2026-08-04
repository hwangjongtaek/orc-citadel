# S8 그래프 반영 게이트 (설계 05 §6, 03 §7)

> 권장안 선정. curated claim 후보가 authoritative graph로 승격되기 전 거치는
> **그래프 반영 게이트**를 결정적으로 구현한다. 게이트 규칙(1 schema · 2 provenance ·
> 3 predicate 폐쇄성 · 4 confidence 임계)은 설계 05 §6이 정의하고, 임계값은 설계 10이
> 소유(prototype은 기본 placeholder 상수 — ADR·dev/tuning 후속).
> 대상 문서: [05-resolution-and-extraction.md](../../docs/design/05-resolution-and-extraction.md) §6,
> [03-storage-and-data-model.md](../../docs/design/03-storage-and-data-model.md) §7, 02 §5.1.

## 배경·범위

| 결정 | 근거 |
| --- | --- |
| **claim_candidates → gate → promoted|quarantined** | 게이트 통과 시 authoritative 진입(append-only event), 실패 시 quarantine (05 §6) |
| **기존 `MutationLog` 재사용** — append-only event store (op=create_node) | 03 §7: 승인 변경은 append-only event로만 기록. 기존 append-only 이벤트 로그를 그대로 사용(재구축 가능) |
| **게이트 규칙 4종 결정적 구현** | (1) schema (2) provenance ≥ 1 (3) predicate ∈ 어휘 (4) confidence ≥ 임계 |
| **promotion 임계/임계값은 placeholder 상수** | 05 §6 (4)는 [10]이 소유 — prototype은 05 기본값 + ADR placeholder (실제 값은 dev/test 후속) |
| **predicate 어휘는 02 §5.1에서** | controlled vocabulary (announces/depends_on/supplies/...) |
| **mention/edge 게이트는 스텁** | 이번 scope는 claim 중심 (05 §6은 claim/edge/mention 모두, prototype는 claim부터) |

## 구현 계획

- **`gate.py`** (신규): `promotion_gate(claim_candidate) → ControlResult(promote/quarantine, [reasons])`
  - (1) schema: 필수 필드·confidence∈[0,1]·엔티티 subject/object 참조
  - (2) provenance: source_span (seg_order, char_start/end) 존재·valid
  - (3) predicate 폐쇄성: `predicate ∈ CONTROLLED_PREDICATES` (02 §5.1)
  - (4) confidence ≥ PROMOTION_CONFIDENCE (placeholder)
- **`mutation_log.py`** (수정): 게이트 통과 claim을 append-only event(op=create_node)로 기록하고 **상태 promoted** 부여. quarantine은 quarantine reason만 기록(직접 mutation 아님 — 03 §7에서 quarantine은 op).
- **`curated_zone.py`** (수정): claim_candidates.status 업데이트(promoted/quarantined) + quarantine reason, promoted/수만 조회·parquet.
- **`gate_smoke.py`** (신규): 실수집 → claim → gate → 영속·상태 전이 검증.
- **TDD 테스트** (gate).

## DoD

- NVIDIA 공시 announces(earnings) claim: schema/provenance/predicate 통과 → **promoted** + create_node 이벤트
- subject 미해소/빈 span/predicate 미등록/저신뢰 → **quarantined** + reason
- claim_candidates.status 전이 저장·조회, append-only 이벤트 로그 재생으로 재구축 가능
- 전체 테스트 통과, code-only 커밋

## 한계 (문서화)

- 임계값·promotion 임계는 05 §6이 10에 위임 — prototype은 placeholder 상수 (실제 값은 dev/test 튜닝, ADR-1007/1008)
- mention/edge 게이트·human review(05 §8)·quarantine 워크플로(review 상태 전이)는 후속
- authoritative "graph"는 이 prototype에서 materialized projection(조건 만족 시 상태 promoted)으로 표현
