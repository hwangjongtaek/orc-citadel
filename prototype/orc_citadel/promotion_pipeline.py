"""S39 종단 간 승격 파이프라인 (설계 10 §3.1).

S36 EvalSuite 평가 → S38 PromotionGate 승격/차단을 자동 결합. 골든 영속(S34) →
P/R/F1(S33) → 회귀(S35) → durable 승격/차단(S38)의 종단 간 흐름을 `run` 하나로.

- run(version): 평가+판정+align(승격 시 active baseline 영속).
- dry_run(version): 평가+판정만, align 없음 (read-only, 불변식 §3-3).
- action: PROMOTED(통과) / BLOCKED(회귀·gate 미달) / INITIALIZED(first, 생성).
- realized: baseline 반영(promotion/초기화) 여부.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from orc_citadel.eval_suite import EvalSuite
from orc_citadel.regression import EvalSnapshot
from orc_citadel.pipeline_gate import PromotionGate


@dataclass(frozen=True)
class PromotionResult:
    version: str
    action: str          # PROMOTED | BLOCKED | INITIALIZED.
    passed: bool
    gates: dict
    metrics: dict
    regressions: list
    realized: bool       # baseline 반영 여부.


class PromotionPipeline:
    """EvalSuite 평가 → PromotionGate 승격/차단 종단 간 결합 (design 10 §3.1)."""

    def __init__(self, zone, permitted: dict | None = None) -> None:
        self._zone = zone
        self._permitted = permitted

    def _evaluate(self, version: str) -> tuple:
        suite = EvalSuite(zone=self._zone)
        res = suite.run()
        snapshot = EvalSnapshot(
            version=version,
            metrics={"canonicalization_f1": res.metrics["canonicalization_f1"],
                     "canonicalization_precision": res.metrics["canonicalization_precision"],
                     "contradiction_precision": res.metrics["contradiction_precision"],
                     "contradiction_recall": res.metrics["contradiction_recall"]})
        gate = PromotionGate(zone=self._zone, permitted=self._permitted)
        verdict = gate.evaluate(snapshot)
        return res, snapshot, gate, verdict

    def _decide(self, suite_res, gate_verdict, version: str) -> PromotionResult:
        action = {"init": "INITIALIZED", "promote": "PROMOTED",
                  "keep": "BLOCKED"}[gate_verdict["action"]]
        return PromotionResult(
            version=version, action=action,
            passed=(gate_verdict["action"] != "keep" and suite_res.passed),
            gates=suite_res.gates, metrics=suite_res.metrics,
            regressions=gate_verdict["regressions"], realized=False,
        )

    def run(self, version: str) -> PromotionResult:
        suite_res, snapshot, gate, verdict = self._evaluate(version)
        res = self._decide(suite_res, verdict, version)
        # block이 아니면 align (INITIALIZED/PROMOTED → active 반영).
        if not verdict["blocked"]:
            gate.align(snapshot)
            res = PromotionResult(
                version=version, action=res.action,
                passed=res.passed, gates=res.gates, metrics=res.metrics,
                regressions=res.regressions, realized=True,
            )
        return res

    def dry_run(self, version: str) -> PromotionResult:
        """평가·판정만 — align 없음 (read-only, 불변식 §3-3)."""
        suite_res, _, _, verdict = self._evaluate(version)
        return self._decide(suite_res, verdict, version)
