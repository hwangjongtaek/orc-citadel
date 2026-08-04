# S12 mention/edge 게이트 확장 (설계 05 §6 전체) — authoritative graph 완성

> 권장안 2 선택. claim 중심이던 그래프 반영 게이트(05 §6)를 **mention·edge 후보까지**
> 확장해 authoritative graph를 완성한다. 게이트 4검증(provenance/사전/confidence/
> schema)을 element 종류별로 적용 (05 §6은 claim_candidates/mentions/edges 모두 명시).
> 대상: [05-resolution-and-extraction.md](../../docs/design/05-resolution-and-extraction.md) §6,
> 02 §2.2(mention)·§3(POSSIBLY_SAME_AS), 03 §4.

## 배경·범위

| 결정 | 근거 |
| --- | --- |
| **gate를 Mention·Edge 후보로 확장** | 05 §6: "candidate (claim_candidates / mentions / edges)" — 현재 gate는 claim만 |
| **mention 게이트**: provenance(span) ≥ 1 + 해소 entity 참조 + type 유효 | mention은 해소 후 authoritative 진입 (02 §2.2). span 없는 mention 폐기 원칙(05 §1.1) |
| **edge 게이트**: POSSIBLY_SAME_AS 등 — resolution_ref + score ∈ [0,1] | 02 §3.1·§3(edge): POSSIBLY_SAME_AS는 score/blocking_key, SAME_AS는 resolution_ref |
| **통과 → append-only create_node/create_edge 이벤트** | 03 §7: 승인 변경 이벤트만. mention=create_node, edge=create_edge |
| **게이트 임계값은 05 §6이 [10] 위임 — placeholder 유지** | 기존와 동일 정책 |

## 핵심 계약

- `Gate.evaluate_mention(m) → PromotedResult` : span 유효 + resolved entity 참조 +
  mention_type ∈ 유효(Person/Org/...) → promote(create_node)
- `Gate.evaluate_edge(edge) → PromotedResult` : resolution_ref/score 쌍 후보,
  score ∈ [0,1] → promote(create_edge). POSSIBLY_SAME_AS는 자동 병합 아님 —
  게이트는 승격만 (SAME_AS 자동 병합은 여전히 결정적 식별자만, ADR-507)
- mention/edge도 `entities`·`mentions`에 resolved/edge 반영 (기존 영속 재사용)
- **POSSIBLY_SAME_AS 후보(해소 §2)**: 게이트로 authoritative에 **edge 후보**로 승격되며,
  자동 SAME_AS 병합 없음 — precision-first (ADR-507)

## 구현 계획

- **`gate.py`** (수정): `evaluate_mention(m)`, `evaluate_edge(edge)` 추가 + 이벤트
  (create_node/create_edge). claim `evaluate`는 그대로 (S8).
- **`mentions.py`** or 기존: POSSIBLY_SAME_AS edge 후보 생성 (Stage-2 해소 후보 —
  새 모듈 `edges.py` 최소: 후보 edge 생성). score/blocking_key.
- **`curated_zone.py`** (수정): `authoritative_edges` 테이블(02 §3) + mention.authoritative
  반영 + parquet.
- **`edge_gate_smoke.py`** (신규): 실수집 → mention/edge 게이트 → authoritative 영속.
- **TDD 테스트**

## DoD

- 해소된 mention(span 유효·entity 참조) → promote(create_node), span 없는/미해소 → quarantine
- POSSIBLY_SAME_AS edge(score∈[0,1]·resolution_ref) → promote(create_edge), score∉[0,1] → quarantine
- 자동 SAME_AS 병합은 결정적 식별자만 (ADR-507 유지) — edge는 후보/승격만
- authoritative 영속·조회·parquet, 전체 테스트 통과, code-only 커밋

## 한계 (문서화)

- mention·edge의 authoritative "그래프"는 prototype에서 상태(mention.authoritative·edges
  테이블)로 표현 (물리 그래프는 06 후속)
- embedding/LLM 기반 후보(Stage-2 이상)·quarantine 워크플로(review)는 후속
- edge 후보의 `blocking_key`·score는 결정적 규칙(해소 stage-1)에서 — LLM score 후속
