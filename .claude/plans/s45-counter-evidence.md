# S45 · Counter-Evidence Agent (설계 07 §3.6)

## 목표

조사 루프의 Counter-Evidence Agent — 현재 결론 정의(conclusion: subject·predicate·object)에 대한 **반증 탐색**을 read-only로 산출 (07 §3.6, tier L5).

## 출력 계약 (07 §3.6)

```json
{
  "conclusion": "...",          # 검증 대상 현재 결론
  "hypotheses": [...],          # 반대 가설 (subject에 대한 부정적 주장)
  "negative_queries": [...],    # 부정 검색용 쿼리 (결론을 반박할 수 있는 용어)
  "contradiction_candidates": [ # S10 기존 모순(같은 subject 다른 주장)
    {claim_a, claim_b, conflict_type, rationale}
  ]
}
```

**불변식 (07 §3.6):** 반박 여부를 binary로만 남기지 않고 **근거·판정 이유** 포함. 모순 vs 시간차 vs 범위차 구분 라벨(05) — S10 conflict_candidates가 이미 conflict_type 구분.

## module·API

`prototype/orc_citadel/counter_evidence.py`:
```python
class CounterEvidenceAgent:
    """현재 결론에 대한 반증 탐색 (07 §3.6, read-only)."""
    def __init__(self, zone): ...
    def explore(self, subject_id, predicate, object_literal=None) -> dict
    def hypotheses(self, subject_id, predicate, object_literal=None) -> list[str]
    def negative_queries(self, subject_id, predicate) -> list[str]
    def contradiction_candidates(self, subject_id) -> list[dict]
```
read-only — graph mutation 미노출. hypotheses/negative_queries는 결정적 규칙 생성(부정·반대·무효화 단어 조합).

## TDD (Red→Green→Refactor)
`test_counter_evidence.py`: hypotheses 생성(부정 가설), negative_queries, contradiction_candidates(존재 모순), 불변식(이유 포함), read-only, 결정성.

## 커밋 code-only behavioral, main 직접 머지.
