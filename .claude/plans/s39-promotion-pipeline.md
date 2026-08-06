# S39 · 종단 간 승격 파이프라인 (EvalSuite → PromotionGate)

## 목표

S36(`EvalSuite`)의 평가 결과를 S38(`PromotionGate`)의 durable baseline 판정과 **자동 결합**한다. 골든 영속(S34) → P/R/F1(S33) → 회귀(S35) → durable 승격/차단(S38)의 종단 간 흐름을 하나의 `PromotionPipeline`으로 묶어, 모델/골든 버전 변경 시 **결정적·durable로 승격/차단**한다 (design 10 §3.1).

## 흐름

```text
PromotionPipeline.run(zone, version)
  → EvalSuite(zone) 평가 (S36): metrics·gates·regressions
  → PromotionGate(zone) 기준: active baseline 대비 승격/차단 (S38)
  → 결정:
      passed && gate 통과 && 회귀 없음 → align(영속 active 갱신) -> PROMOTED
      회귀 or gate 미달                     → keep (baseline 유지)      -> BLOCKED
      baseline 없음(first)                  → align 생성                -> INITIALIZED
  → 결과: {version, action, passed, gates, metrics, regressions, realized(baseline 반영 여부)}
```

- `version`은 골든/pipeline 버전 — Batch snapshot 캡처.
- **read-mostly**: 평가·판정은 조회, `align`(승격)만 영속.

## module·API

`prototype/orc_citadel/promotion_pipeline.py`:

```python
@dataclass(frozen=True)
class PromotionResult:
    version: str
    action: str          # PROMOTED | BLOCKED | INITIALIZED
    passed: bool
    gates: dict
    metrics: dict
    regressions: list
    realized: bool       # baseline 반영되었는지 (align 성공)

class PromotionPipeline:
    """EvalSuite 평가 → PromotionGate 승격/차단 종단 간 결합 (design 10 §3.1)."""
    def __init__(self, zone, permitted=None): ...
    def run(self, version: str) -> PromotionResult
    def dry_run(self, version: str) -> PromotionResult   # 상동, align 없음(read-only)
```

- `run` — 평가+판정+align(영속).
- `dry_run` — 평가+판정만, align 없음 (read-only, 불변식 §3-3).

## TDD (Red→Green→Refactor)

`test_promotion_pipeline.py` — zone + 골든 + baseline 배치.

1. **Red**:
   - `run` — 골든 로드 → metrics·gates, baseline 없음 → INITIALIZED + realized(align).
   - baseline 동일 → PROMOTED (회귀 없음, align로 active 갱신).
   - baseline 대비 회귀 → BLOCKED, baseline 유지.
   - gate 미달 → BLOCKED.
   - `dry_run` — 평가·판정만, 영속 없음 (baseline 수 불변).
2. **Green** — 최소 구현.
3. **Refactor** — 중복 없음.

## 실데이터 스모크

임시 복사 DB — 골든 영속 → run(INITIALIZED→PROMOTED) → 회귀 시 BLOCKED · dry_run read-only.

## 커밋

**code-only (behavioral)**: `feat(S39): end-to-end promotion pipeline — EvalSuite→PromotionGate (design 10 §3.1)`.

## 완료 기준

- [ ] Red→Green→Refactor, 전체 테스트 통과 (기존 327 + 신규).
- [ ] 결정성 — 동일 상태 → 동일 판정·realized.
- [ ] read-mostly — dry_run 영속 없음.
- [ ] 실데이터 스모크 — INITIALIZED/PROMOTED/BLOCKED pad.
