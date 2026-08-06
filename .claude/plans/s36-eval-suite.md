# S36 · 평가 스위트 러너 (design 10 §6 CI 게이트)

## 목표

S33(하네스)→S34(골든 영속)→S35(회귀)의 3단을 **하나의 결정적 러너**로 묶는다. design 10 §6 CI 게이트 — 골든셋 로드 → P/R/F1 평가 → baseline 대비 회귀 판정 → **통과/차단 최종 판정 + 인간 읽기 리포트**를 한 번에 출력한다.

design 10 §6.1 merge-block(unit/integration), §6.2 promotion-block(골든 회귀 + hard-gate). prototype은 phase 0 소량이므로 **판정만 트래킹, CI 하드차단은 후속** (기존 방침 유지).

## 흐름

```text
eval_suite.run(zone, baseline=None)
  → golden 자동 로드 (S34 zone.golden_pairs)
  → EvalHarness(zone) 평가 (S33) — canonicalization/contradiction P/R/F1
  → baseline 주입 시 RegressionRunner 대조 (S35) — delta·회귀·gate
  → SuiteResult:
      metrics       : {metric: {value, threshold}}
      gates         : {gate_name: {pass, detail}}
      regressions   : [metric...]
      passed        : bool (게이트 전부 통과 && 회귀 없음)
      report        : 인간 읽기 요약 (한국어 라인)
```

- baseline 미주입 → 게이트(promotion_blocked)·지표만, 회귀는 판정 안 함(첫 실행 baseline).
- baseline 주입 → 회귀·gate 종합 판정.
- **read-only** (불변식 §3-3): zone 읽기만, 영속·mutation 미노출. baseline은 스냅샷(report 생성)으로 명시.

## module·API

`prototype/orc_citadel/eval_suite.py`:

```python
@dataclass(frozen=True)
class SuiteResult:
    metrics: dict
    gates: dict
    regressions: list
    passed: bool
    report: str     # 줄바꿈 결합 한국어 요약

class EvalSuite:
    """골든→하네스→회귀를 묶는 read-only 평가 스위트 (design 10 §6)."""
    def __init__(self, zone, baseline: EvalSnapshot | None = None): ...
    def run(self) -> SuiteResult
    def print_report(self) -> None   # CI-friendly 표준 출력
```

## TDD (Red→Green→Refactor)

`test_eval_suite.py` — zone + golden 배치.

1. **Red**:
   - `run()` — 골든 자동 로드, P/R/F1·gate 계산 (S33·S34 재사용).
   - baseline 미주입 — 게이트·지표만, passed는 게이트 통과 여부.
   - baseline 주입 동일 — 회귀 없음, passed=True.
   - baseline 주입 회귀 — regressions 포함, passed=False.
   - gate 미달 — passed=False (promotion_blocked).
   - `report` — 한국어 요약 라인 (게이트·지표·회귀 포함).
   - `print_report` — pass/fail 축약 라인.
   - read-only — `apply`/`persist` 미노출.
2. **Green** — 최소 구현.
3. **Refactor** — 중복 없음.

## 실데이터 스모크

임시 복사 DB — 골든 영속(S34 스모크 동일) → EvalSuite.run → 리포트, baseline 전후.

## 커밋

**code-only (behavioral)**: `feat(S36): eval suite runner — golden→harness→regression CI gate (design 10 §6)`.

## 완료 기준

- [ ] Red→Green→Refactor, 전체 테스트 통과 (기존 302 + 신규).
- [ ] 결정성 — 동일 zone·baseline → 동일 결과.
- [ ] read-only — 쓰기 미노출.
- [ ] 실데이터 스모크 — 게이트·회귀·리포트 pad.
