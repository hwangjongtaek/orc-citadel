# S38 · Durable 승격 게이트 (design 10 §3.1, ADR-1003)

## 목표

S35 `RegressionRunner`의 baseline이 **메모리 주입**이라 실행 간 유지되지 않는다. design 10 §3.1 승격 게이트("모델/프롬프트/골든 변경 → 직전 승격(last-promoted) 기준선 대비 회귀 → 게이트 통과 && 회귀 없음 → 승격")를 **영속 baseline**으로 완결한다.

## 승격 게이트 계약 (design 10 §3.1, ADR-1003)

- **`promotion_baselines` 테이블** (curated zone 영속) — last-promoted 지표 스냅샷:
  | 컬럼 | 설명 |
  |---|---|
  | `baseline_id` | 결정적 PK (version 기반) |
  | `version` | 골든/pipeline 버전 |
  | `metrics` | EvalSnapshot.metrics (JSON) |
  | `promoted_at` | 승격 시각 |
  | `promoted_by` | `pipeline` (자동 승격) |
  | `status` | `active`(현재 last-promoted) / `superseded` |
- **평가 스위트 결합**: EvalSuite가 zone의 active baseline을 읽어 `RegressionRunner`와 대조(promote/block).
- **승격 흐름**: 게이트 통과 && 회귀 없음 → **baseline 갱신**(신규 active, 기존 superseded). block이면 현재 유지.
- **승격 이력**: superseded baseline이 남아 감사·되돌림 가능 (bitemporal/이벤트 계약).

## module·API

**`curated_zone.py`** — `promotion_baselines` + `persist_promotion_baseline` + `promotion_baselines()` + `active_baseline()` + parquet export.

**`pipeline_gate.py`** (신규) — durable 승격 게이트:
```python
class PromotionGate:
    """zone 영속 baseline으로 승격/차단을 판정하는 read-mostly 게이트 (design 10 §3.1)."""
    def __init__(self, zone, permitted=None): ...
    def evaluate(self, snapshot: EvalSnapshot) -> dict
        # {passed, blocked, reason, deltas, regressions, baseline_version, action: promote|keep}
    def align(self, snapshot):  # passed → 영속 baseline 갱신 (승격)
```

## TDD (Red→Green→Refactor)

`test_promotion_gate.py` / `test_promotion_persist.py`:

1. **Red**:
   - 영속 — persist/promotion_baselines()/active_baseline() idempotent·결정적 ID.
   - `evaluate` — active baseline 있으면 그 대비 deltas·regressions·blocked.
   - 회귀 없음+게이트 통과 → passed=True, action=promote, `align`가 active baseline 갱신(기존 superseded).
   - 회귀 있음 → blocked=True, action=keep (baseline 유지).
   - active baseline 없음(first) → baseline 미설정 상태로 게이트만 (생성 전).
   - read-only — evaluate는 영속 미노출; align만 영속.
2. **Green** — 최소 구현.
3. **Refactor** — 중복 없음.

## 실데이터 스모크

임시 복사 DB — 골든 영속 → active baseline 생성 → evaluate → align 승격 → 재실행 회귀 판정.

## 커밋

**code-only (behavioral)**: `feat(S38): durable promotion gate — last-promoted baseline via zone (design 10 §3.1, ADR-1003)`.

## 완료 기준

- [ ] Red→Green→Refactor, 전체 테스트 통과 (기존 318 + 신규).
- [ ] 결정성 — 동일 상태 → 동일 판정.
- [ ] read-mostly — evaluate는 조회, align만 영속.
- [ ] 실데이터 스모크 — 승격·차단 pad.
