# S27 통합 검증 — fixture golden + 계약 불변식 (03 §5, 05 §6, ADR-507)

> 권장안: 결정적+LLM 하이브리드 파이프라인(S24)을 **fixture golden 테스트**로 회귀
> 고정하고, 계약 불변식(결정성·멱등성·provenance·노-자동-병합)을 종합 점검한다.

## 배경·범위

S24 단일 진입점이 만든 결과를 회귀 고정하고, 하이브리드 판정의 계약 위반을 잡는다.

| 결정 | 근거 |
| --- | --- |
| fixture-golden 결정성·멱등성·재생성 테스트 | 03 §5, 불변식 §3-3/§3-6 |
| provenance 체인 무결성(claim→doc/segment→raw) | 불변식 §3-2, ADR-302 |
| 어세션=promoted claim, 근거(mutation) 연결 | 05 §6 · 03 §6.2 |
| **ADR-507 노-자동-병합**: LLM `equivalent`라도 결정적-우선만 병합 | G4, 05 §5 |
| **판정 영속 안전**: judge flavor 무관 LLM verdict 영속 | S23 — 통합 버그 발견·수정 |

## 구현 계획

- **test_integration_invariants.py**: golden 결정성(존 간)·멱등 upsert·provenance·
  assertion 근거·ADR-507(공격적 LLM도 자동 병합 금지)·미결 쌍 LLM 병합·영속 검증.
- **버그 수정**: `run_pipeline`이 `canonicalize_claims(..., llm_records=[...])`로 성공 판정을
  누적 → S23 version-tuple 영속. 기존 `_persist_llm_verdicts`는 확장형(BoundedJudge)
  `verdicts`만 봐서 **plain judge의 판정이 유실**되던 통합 버그를 해결.
- **Smoke**: 395문서 결정적 재실행 결정성 + 어세션 일치 확인.

## DoD

- golden 결정성·멱등·provenance·ADR-507 불변식이 테스트로 고정
- plain judge 판정도 S23에 영속 (버그 수정)
- 공격적 LLM이 진짜 미결 쌍은 병합하되 LLM-only 자동 병합 없음
- 전체 테스트 통과, code-only 커밋

## 한계 (문서화)

- 검증은 prototype 데이터(fixture·395문서) — 운영 스케일 회귀는 CI/평가 단계(10)
- 대표 docs 기반 — 금융 리포트 광범위 Entity는 후속
