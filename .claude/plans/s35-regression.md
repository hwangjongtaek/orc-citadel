# S35 · 평가 회귀 실행기 (design 10 §3)

## 목표

S34로 골든셋이 영속되고 `EvalHarness.report()`가 지표·gate를 낸다. 이제 design 10 §3 **회귀(regression)** — 모델/프롬프트/골든 버전이 바뀔 때 **직전 승격(last-promoted) 기준선 대비 per-metric delta**로 회귀를 감지하고, ADR-1008 상대 허용치(§3.2)를 초과하면 승격을 block한다.

**scan**: EvalHarness 지표(캐노니컬 F1·모순 P/R)를 스냅샷으로 캡처(baseline), 이후 상태(현재)와 비교해 delta·회귀 여부를 리포트.

## 회귀 계약 (design 10 §3.1·§3.2)

- **기준선(last-promoted baseline)**: 스냅샷(S35가 캡처한 `EvalSnapshot`) — 승격 지표 보존.
- **회귀 판정 (§3.2 placeholder, ADR-1008)**:
  - entity resolution `P`·오병합률: 하락 불허(0p, hard) — 우리 스코프는 캐노니컬/모순이므로 캐노니컬 F1은 **≤1%p** 입니다 (예비 규칙, dev 실측 후 조정).
  - contradiction `P`: **≤1%p**.
  - canonicalization F1, 기타 gate: **≤2%p**.
- delta: `current − baseline`. **허용치 초과 하락** (delta < −permitted) 시 회귀.
- 승격 게이트 (§3.1): 골든 gate 미달(Harness.promotion_blocked) **또는** 상대 회귀 발생 → block.

## 모듈·API

`prototype/orc_citadel/regression.py`:

```python
@dataclass(frozen=True)
class EvalSnapshot:
    version: str            # gold_version / pipeline version
    metrics: dict           # {metric_name: value} — EvalHarness.report()에서 추출
    @staticmethod capture(harness, version) -> EvalSnapshot

@dataclass(frozen=True)
class RegressionResult:
    deltas: dict            # metric -> delta
    regressions: list       # 허용치 초과 하락 metric 목록
    blocked: bool           # 회귀 or gate 미달로 block
    report: dict            # 대조 리포트

class RegressionRunner:
    """EvalHarness 지표와 last-promoted baseline을 대조하는 read-only 회귀."""
    def __init__(self, permitted: dict | None = None):  # metric -> 허용치(pp)
    def run(self, baseline: EvalSnapshot, current: EvalSnapshot | harness) -> RegressionResult
```

`permitted` 기본 (ADR-1008 placeholder):
```python
DEFAULT_PERMITTED = {"canonicalization_f1": 2.0, "canonicalization_precision": 0.0,
                     "contradiction_precision": 1.0, "contradiction_recall": 2.0}
```

**read-only** (불변식 §3-3): 스냅샷·대조만, 영속·mutation 미노출.

## TDD (Red→Green→Refactor)

`test_regression.py`:
1. **Red**:
   - `EvalSnapshot.capture(harness)` — EvalHarness.report()에서 메트릭 dict 추출.
   - `RegressionRunner.run` — baseline과 동일하면 delta 0, blocked=False.
   - 상승 — current metric > baseline → delta 양수, 회귀 없음.
   - 허용치 초과 하락 — current F1 < baseline − 2%p → regressions에 포함, blocked=True.
   - 허용치 내 하락 — 하락 ≤ 허용치 → 회귀 없음, blocked=False.
   - precision 0p 허용 — 캐노니컬 P 미세 하락 → 회귀.
   - gate 미달과 조합 — 골든 gate 미달이면 blocked (회귀와 무관).
   - read-only — `apply`/`persist` 미노출; 입력 snapshot 불변.
2. **Green** — 최소 구현.
3. **Refactor** — 중복 없음.

## 실데이터 스모크

S34 골든(copy)로 capture → 동일하게 재실행 → delta 0·blocked=False; 조작된 현재 지표로 회귀 감지 시연.

## 커밋

**code-only (behavioral)**: `feat(S35): eval regression runner — baseline delta vs ADR-1008 thresholds (design 10 §3)`.

## 완료 기준

- [ ] Red→Green→Refactor, 전체 테스트 통과 (기존 293 + 신규).
- [ ] 결정성 — 동일 baseline+current → 동일 delta.
- [ ] read-only — 쓰기 미노출.
- [ ] 실데이터 스모크 — delta·회귀·block pad.
