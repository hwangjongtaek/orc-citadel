# S22 LLM 판정 하이브리드 통합 + 실데이터 E2E 스모크

> 권장안: S21의 `ClaudeJudge`를 캐노니컬·모순 흐름에 **결정적-우선** 원칙(05 §5/§6,
> blueprint §9.2)대로 연결한다. 결정적 규칙이 미결로 남긴 쌍에만 LLM 판정을 주입하고,
> 395문서 실데이터로 하이브리드 전 체인 E2E 스모크를 돌려 확정한다.
> 대상: [05](../../docs/design/05-resolution-and-extraction.md) §4.2(7라벨)·§5.2(verdict)
> — LLM relationship/conflict 판정.

## 배경·범위

현재 `canonicalize_claims`(S9)와 `find_conflict_candidates`(S10)는 **순수 결정적** —
LLM 훅이 없다. 설계 05는 "결정적-우선, 모호한 쌍만 LLM(비용 통제)"을 명문화한다(§5 라인83).

| 결정 | 근거 |
| --- | --- |
| `canonicalize_claims(..., judge=None)` — 미결 쌍만 LLM | 05 §4.2: 축소 후보쌍 → LLM 7라벨. 결정적 `equivalent`는 그대로 |
| `find_conflict_candidates(..., judge=None)` — 미결 쌍만 LLM | 05 §5.2: 후보 → LLM real_conflict|temporal|scope|not_conflict |
| `judged_by`로 결정적/LLM 판정 구분 | 저장 계약(02 §3.1) — rationales + `judged_by` |
| **결정성 불변식 유지**: judge 미주입 시 S9/S10과 동일 출력 | 03 §5 재생성 — 기존 테스트 전부 통과 필수 |

## 구현 계획

- **`canonicalize.py`**: `canonicalize_claims(claims, judge=None)` — 그룹 내 겹치지 않는
  쌍(결정적 `_claims_equivalent` False)에만 `judge.judge_canonicalization((a,b))` 호출,
  `relation == "equivalent"`이면 union (LLM 판정 근거 저장). judge 없으면 기존 동작.
- **`contradiction.py`**: `find_conflict_candidates(claims, judge=None)` — 결정적 후보 생성
  후, judge로 실제 모순 여부 판정 (`real_conflict`만 유지, `not_conflict`/`temporal`/`scope`
  제거) 또는 보강. judge 없으면 기존 후보 그대로.
- **TDD**: Red→Green — mock `LlmJudge`로 미결 쌍만 LLM 호출·판정 반영 검증. 기존 S9/S10
  테스트가 judge 없이 그대로 통과(결정성) 함을 확인.
- **ClaudeJudge 연결 smoke**: `ClaudeJudge`(bunker-flash, proxy)를 실제 주입해 대표 미결
  쌍에 판정 → version tuple·judged_by=llm 확인.
- **실데이터 E2E 스모크**: 395문서 하이브리드 전 체인 (mentions→resolve→gate→claims→
  canonicalize(judge)→contradiction(judge)→assertion), aggregate + 결정성 불변식.

## DoD

- judge 미주입: 결정적 결과 그대로 (기존 테스트 전부 green — 재생성 안전)
- judge 주입: 미결 쌍만 LLM 판정 반영, `judged_by="llm"` 구분
- 실데이터 395문서 E2E 스모크 통과 (하이브리드 전 체인, 결정성 유지)
- ClaudeJudge 실주입 smoke: `judged_by=llm` + version tuple
- 전체 테스트 통과, code-only 커밋 (behavioral)

## 한계 (문서화)

- 실 LLM 판정은 비용·네트워크 의존 — 스모크는 소량, 회귀는 사용자가 실행
- LLM 판정은 `POSSIBLY` 신호로만 — SAME_AS 자동 병합(ADR-507) 등 확정 경로는 기존대로
- mock은 계약-유효, 실프록시 모델 선택은 배포 시 주입 (S21과 동일)
