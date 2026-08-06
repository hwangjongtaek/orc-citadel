"""S35 평가 회귀 실행기 (설계 10 §3).

EvalHarness 지표를 **last-promoted baseline** 스냅샷과 대조해 per-metric delta·
회귀·block 여부를 판정한다 (design 10 §3.1 승격 게이트, §3.2 상대 허용치 ADR-1008).

- EvalSnapshot : 승격 지표 스냅샷 (version + metrics). capture(harness)로 report에서 추출.
- RegressionRunner.run(baseline, current) -> RegressionResult:
  - deltas      : metric → delta(current − baseline).
  - regressions : 허용치(pp) 초과 하락 metric 목록.
  - gate_missed : 현재 EvalHarness 골든 gate 미달 (design 10 §3.1).
  - blocked     : regressions 발생 또는 gate 미달 → 승격 차단.
- permitted 기본 (ADR-1008 placeholder): canonicalization_precision 0p(hard),
  canonicalization_f1 ≤2%p, contradiction_precision ≤1%p, contradiction_recall ≤2%p.
  (placeholder — design 10 §3.2: dev 파티션 실측 후 조정.)
- **read-only** (불변식 §3-3) — 스냅샷·대조만, 영속·mutation 미노출.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from orc_citadel.eval_harness import EvalHarness

# ADR-1008 placeholder — 단위: %p (0.01 = 1%p).
DEFAULT_PERMITTED = {
    "canonicalization_precision": 0.0,   # 하락 불허 (hard, 오병합 무관용).
    "canonicalization_f1": 2.0,
    "contradiction_precision": 1.0,
    "contradiction_recall": 2.0,
}


@dataclass(frozen=True)
class EvalSnapshot:
    version: str
    metrics: dict

    @staticmethod
    def capture(harness, version: str) -> "EvalSnapshot":
        rep = harness.report()
        cc = rep["canonicalization"]["metrics"]
        cd = rep["contradiction"]["metrics"]
        return EvalSnapshot(
            version=version,
            metrics={
                "canonicalization_f1": cc["f1"],
                "canonicalization_precision": cc["precision"],
                "contradiction_precision": cd["precision"],
                "contradiction_recall": cd["recall"],
            },
        )


@dataclass(frozen=True)
class RegressionResult:
    baseline_version: str
    current_version: str
    deltas: dict
    regressions: list
    blocked: bool
    gate_missed: bool = False


class RegressionRunner:
    """EvalHarness 지표와 last-promoted baseline을 대조하는 read-only 회귀."""

    def __init__(self, permitted: dict | None = None) -> None:
        self._permitted = dict(DEFAULT_PERMITTED if permitted is None else permitted)

    def run(self, baseline: EvalSnapshot, current) -> RegressionResult:
        """current: EvalSnapshot 또는 EvalHarness (gate 미달 감지용).

        current가 harness면 그 지표로 스냅샷·gate를 함께 캡처.
        """
        gate_missed = False
        if isinstance(current, EvalHarness):
            gate_missed = current.report().get("promotion_blocked", False)
            current = EvalSnapshot.capture(current, version=baseline.version)
        elif not hasattr(current, "metrics"):
            current = current

        keys = set(baseline.metrics) | set(current.metrics)
        deltas = {k: current.metrics.get(k, 0.0) - baseline.metrics.get(k, 0.0)
                  for k in keys}
        # 허용치(pp) 기준 — delta가 −permitted 미만(초과 하락)이면 회귀.
        regressions = []
        for k, delta in deltas.items():
            # permitted에서 "%p → 0.01 단위" 변환 (미지 metric은 허용치 2%p 기본).
            tol_pp = self._permitted.get(k, 2.0)
            tol = tol_pp / 100.0
            if delta < -tol:
                regressions.append(k)

        return RegressionResult(
            baseline_version=baseline.version,
            current_version=current.version,
            deltas=deltas,
            regressions=sorted(regressions),
            gate_missed=gate_missed,
            blocked=bool(regressions) or gate_missed,
        )
