# S46 · Investigation Runner (설계 07 §4 조사 루프)

## 목표
S43 coverage→S44 Graph Explorer→S45 counter-evidence를 하나의 **조사 루프**로 묶어 종료까지 진행 (07 §4 state machine, tier L3~L5).

## 루프 계약 (07 §4)
```
PLAN(subclaim 트리) → 각 subclaim:
  RETRIEVE_SUBGRAPH (S44) → IDENTIFY_GAPS (S43 coverage)
  gap 있으면 COUNTER_EVIDENCE (S45) 반증 탐색
종료(terminate) 기준: coverage ≥ 0.80 (10 §1.3) || gap에서 새로운 evidence 없음 || token budget(최대 반복)
→ SYNTHESIZE (S47 예고) report 기반
```

## 모듈·API
`prototype/orc_citadel/investigation_runner.py`:
```python
@dataclass(frozen=True)
class InvestigationResult:
    subject_id: str
    coverage: float
    subclaims: list
    gaps: list            # 미충족 subclaim (SYNTHESIZE open_questions 입력)
    counter_evidence: list
    iterations: int
    terminated_by: str    # coverage | no_new_evidence | budget
    token_usage: dict     # S42 (LLM 미실행 prototype → 0)
class InvestigationRunner:
    """조사 루프 (07 §4) — read-only 종료까지 진행."""
    def __init__(self, zone, graph, coverage_threshold=0.8, max_iters=3): ...
    def run(self, subclaims) -> InvestigationResult
```
read-only — graph mutation 없음, 반복 시 그래프/존 수정 없음(같은 state 평가).

## TDD (Red→Green→Refactor)
`test_investigation_runner.py`:
- coverage ≥ 0.80 → terminated_by=coverage.
- gap 있지만 반복에 따라 변화 없음(no_new_evidence) → terminate.
- 반복 예산(max_iters) 초과 → budget.
- subclaim별 counter_evidence 포함.
- read-only — mutation 미노출.
- 결정성.

## 커밋 code-only behavioral, main 직접 머지.
