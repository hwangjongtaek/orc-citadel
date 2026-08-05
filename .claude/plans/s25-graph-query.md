# S25 그래프·어세션 질의 — bitemporal AS-OF (06 §8.2, ADR-606)

> 권장안: `run_pipeline`(S24)이 만든 curated assertions 위에서 **bitemporal AS-OF
> 질의**를 구현·검증한다 (설계 06 §8.2, ADR-606 — 버전 축은 Assertion에 부착).

## 배경·범위

설계 06 §8.2: AS-OF는 Assertion의 valid/tx 두 축을 필터해 시간 여행을 재현한다.
기존 GraphService.as_of는 claim-level·tx_only 한계 — Assertion-level 양축 AS-OF가 부재.

| 결정 | 근거 |
| --- | --- |
| `CuratedZone.assertions_as_of(valid_at, tx_at)` 구현 | 06 §8.2·ADR-606: valid/tx 양축 |
| valid: `valid_from ≤ T_v < valid_to` (open bound) | 06 §8.2 · time_precision 경계 |
| tx:   `tx_from ≤ T_t < (tx_to ?? ∞)` | 03 §6.3, tx_to null = 현재 |
| **datetime 파라미터를 문자열이 아닌 TIMESTAMP로 일관 바인딩** | aware-datetime 저장 offset 문제(경계 비교 어긋남) — 버그 수정 |
| superseded 버전 삭제하지 않음 → 과거 상태 그대로 조회 | 03 §6.3, append-only |

## 구현 계획

- **curated_zone.py**: `assertions_as_of(valid_at=None, tx_at=None)` — DB 필터로 양축
  bitemporal 질의. 인자 없으면 현재(tx_to null).
- **TDD**: Red→Green — 현재/과거 T_t, valid 경계(open lower/upper ex), tx 경계, supersede
  제외 검증.
- **Smoke**: 395문서 결정적 체인 어세션 29건 위에서 현재·과거 AS-OF 질의 — 시간 여행
  재현 확인 (미관측 tx_from 제외 등).

## DoD

- valid/tx 양축 AS-OF가 06 §8.2 경계 규칙대로 동작
- 과거 T_t에서 supersede 이전 버전/아직 미관측 assertion 올바르게 구분
- 아직 미관측(future tx_from) 어세션 제외 — 시간 여행 정확
- 전체 테스트 통과, code-only 커밋

## 한계 (문서화)

- investigation subgraph·progressive disclosure(§8.1/§8.3)는 후속 — 여기선 bitemporal
  AS-OF(§8.2)가 핵심
- time_precision 세밀 경계 해석(일/월)은 평가 단계(10)에서 튜닝
