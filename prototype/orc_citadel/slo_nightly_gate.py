"""SLO nightly 게이트 — 운용 루프 통합 오케스트레이션 (10 §1.4·11 §2.3).

Phase 6 DoD ② — "지속 수집이 자동 신호·SLO 에 반영되는 운용 루프 가동". 각 SLO
하니스의 **측정 → 판정 → Watchtower 운영 경보 라우팅** 을 하나의 기계적 nightly
게이트로 연결한다.

```
하니스 측정(slo_metrics_harness / reflection_slo_harness)
  → 이 게이트 classify_slo (evaluate_slo0* 판정)
  → Watchtower 운영 경보 라우팅 (watchtower_slo_alert)
  → error budget 집계 (위반/측정, not-measured 는 분모 제외 — honest-gap §6.2)
```

- **CI 비차단** (10 §1.4): slo-gate 는 차단 없이 nightly 경보. 이 게이트는 분류·
  알림을 **산출물로만** 만들며, 저장·발송·스케줄은 호출자(운영 드라이버) 몫.
- **측정은 주입**(mock/실측 격리): nightly 드라이버가 하니스에서 실측값을 얻어
  `measurements: {slo_id: 실측값|None}` 형태로 넘긴다. 게이트는 계산만 책임.
- **fire-once** (ADR-1104): 재사용하는 `WatchtowerSloAlert` 가 `slo:{slo_id}`
  로 과잉 알림을 막는다. 호출자가 라우터 인스턴스를 매 nightly 재사용/교체 결정.
- **read-only(불변식 §3-3)·결정적.**
"""
from __future__ import annotations

from .reflection_slo_harness import evaluate_slo01
from .slo_metrics_harness import (
    evaluate_slo05, evaluate_slo06, evaluate_slo07,
    reprocess_benchmark,
)
from .watchtower_slo_alert import WatchtowerSloAlert

# nightly 루프 대상 — Phase 6 deferred SLO(11 §2.3). SLO-08 은 "벤치 공개" 계약.
NIGHTLY_SLOS = ("SLO-01", "SLO-05", "SLO-06", "SLO-07", "SLO-08")

# SLO id → 판정 함수 (+ 측정값 해석 계약).
_EVALUATORS = {
    "SLO-01": evaluate_slo01,   # 측정값: p95_ms (반영 지연)
    "SLO-05": evaluate_slo05,   # 측정값: success_rate
    "SLO-06": evaluate_slo06,   # 측정값: pass_rate
    "SLO-07": evaluate_slo07,   # 측정값: median_days 입력은 중앙값 일 → None 가능
    "SLO-08": reprocess_benchmark,  # 측정값: bench dict (벤치 공개, 게이트 없음)
}


def classify_slo(slo_id: str, measurement) -> dict:
    """단일 SLO 측정값 → 판정 결과 (evaluate_slo0* 재사용).

    `measurement` 는 해당 SLO 하니스가 산출한 실측값(또는 미측정 None — §6.2).
    SLO-08 은 임계 게이트 없는 공개 계약이라 `reprocess_benchmark` 로 분류한다.
    미지정 SLO id 는 조용히 ok 로 퉁치지 않고 ValueError (명시적 실패).
    """
    if slo_id not in _EVALUATORS:
        raise ValueError(f"unknown SLO id for nightly gate: {slo_id!r}")
    evaluator = _EVALUATORS[slo_id]
    eval_result = evaluator(measurement)
    return {
        "slo_id": slo_id,
        "classified": eval_result.get("classified", "unclassified"),
        "evaluation": eval_result,
    }


def run_nightly_gate(measurements: dict | None,
                     router: WatchtowerSloAlert | None = None) -> dict:
    """운용 루프 통합 게이트 — 측정 → 판정 → 경보 라우팅 → error budget.

    `measurements` = {slo_id: 실측값|None}. None(미측정) 은 honest-gap(§6.2) —
    위반으로도, error budget 분모로도 세지 않고 `not_measured` 로 노출한다.

    반환: {per_slo, violations, not_measured, ok, error_budget, router}.
    `router` 를 넘기면 그 상태(fire-once)를 유지 — 밖에서 nightly 주기별로
    재사용/교체할 수 있다. read-only·결정적.
    """
    measurements = dict(measurements or {})
    router = router if router is not None else WatchtowerSloAlert()

    per_slo = {}
    for slo_id in NIGHTLY_SLOS:
        if slo_id in measurements:
            per_slo[slo_id] = classify_slo(slo_id, measurements[slo_id])

    routed = router.route(per_slo)

    # error budget — 위반 / 측정된 SLO (SLO-08 게이트 제외, not-measured 분모 제외).
    measured_count = sum(
        1 for r in per_slo.values()
        if r["classified"] in ("ok", "slo-gate")
    )
    violation_count = len(routed["violations"])
    ratio = (round(violation_count / measured_count, 4)
             if measured_count else None)
    error_budget = {
        "violations": violation_count,
        "measured_count": measured_count,
        "violation_ratio": ratio,
    }

    return {
        "per_slo": per_slo,
        "violations": routed["violations"],
        "not_measured": routed["not_measured"],
        "ok": routed["ok"],
        "error_budget": error_budget,
        "router": router,
    }
