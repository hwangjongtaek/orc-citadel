"""S36 평가 스위트 러너 (설계 10 §6 CI 게이트).

S33(하네스)→S34(골든 영속)→S35(회귀)를 하나의 결정적 러너로 묶는다. 골든 자동 로드 →
P/R/F1 평가 → baseline 대비 회귀 → 통과/차단 최종 판정 + 인간 읽기 리포트.

- baseline 미주입: 게이트·지표만 (첫 실행).
- baseline 주입: 회귀·gate 종합 판정 (design 10 §6.2 promotion-block).
- passed: 골든 게이트 전부 통과 && 회귀 없음.
- **read-only** (불변식 §3-3) — zone 읽기만, 영속·mutation 미노출.
  prototype은 phase 0 소량이라 판정 트래킹 (CI 하드차단은 후속).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from orc_citadel.eval_harness import EvalHarness
from orc_citadel.regression import EvalSnapshot, RegressionRunner


@dataclass(frozen=True)
class SuiteResult:
    metrics: dict
    gates: dict
    regressions: list
    passed: bool
    report: str


class EvalSuite:
    """골든→하네스→회귀를 묶는 read-only 평가 스위트 (design 10 §6)."""

    def __init__(self, zone, baseline: EvalSnapshot | None = None) -> None:
        self._zone = zone
        self._baseline = baseline

    def run(self) -> SuiteResult:
        h = EvalHarness(zone=self._zone)
        rep = h.report()
        cc = rep["canonicalization"]
        cd = rep["contradiction"]
        # 게이트 pass는 하네스의 promotion_blocked(골든 vacuous 처리 포함, S34)에 위임.
        # per-metric `pass_p/pass`는 표시용 — gate 종합 판정은 promotion_blocked 사용.
        gates = {
            "canonicalization": {"pass": cc["gate"]["pass"],
                                 "f1": cc["metrics"]["f1"]},
            "contradiction": {"pass": cd["gate"]["pass_p"],
                              "precision": cd["metrics"]["precision"],
                              "recall": cd["metrics"]["recall"]},
        }
        metrics = {
            "canonicalization_f1": rep["canonicalization"]["metrics"]["f1"],
            "canonicalization_precision": cc["metrics"]["precision"],
            "contradiction_precision": cd["metrics"]["precision"],
            "contradiction_recall": cd["metrics"]["recall"],
        }

        # 회귀 — baseline 주입 시.
        regressions = []
        if self._baseline is not None:
            rr = RegressionRunner().run(self._baseline, h)
            regressions = rr.regressions

        # gate 종합 — promotion_blocked(골든 vacuous 처리)가 진실 소스.
        gate_pass = not rep["promotion_blocked"]
        passed = gate_pass and not regressions
        report = self._format_report(metrics, gates, regressions, passed)
        return SuiteResult(metrics=metrics, gates=gates,
                           regressions=regressions, passed=passed, report=report)

    def _format_report(self, metrics, gates, regressions, passed) -> str:
        lines = []
        lines.append("=== 평가 스위트 (design 10 §6) ===")
        lines.append(f"  canonicalization: F1={metrics['canonicalization_f1']:.2f} "
                     f"P={metrics['canonicalization_precision']:.2f} "
                     f"gate={'PASS' if gates['canonicalization']['pass'] else 'FAIL'}")
        lines.append(f"  contradiction: P={metrics['contradiction_precision']:.2f} "
                     f"R={metrics['contradiction_recall']:.2f} "
                     f"gate={'PASS' if gates['contradiction']['pass'] else 'FAIL'}")
        if regressions:
            lines.append("  회귀: " + ", ".join(sorted(regressions)))
        lines.append("  결론: " + ("PASS" if passed else "FAIL (승격 차단)"))
        return "\n".join(lines)

    def print_report(self) -> str:
        res = self.run()
        print(res.report)
        return res.report
