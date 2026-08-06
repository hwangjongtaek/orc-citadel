"""S38 Durable 승격 게이트 (설계 10 §3.1, ADR-1003).

S35 회귀의 last-promoted baseline을 **curated zone에 영속**해 실행 간 유지되는
승격 게이트로 완결한다 — design 10 §3.1: 게이트 통과 && 회귀 없음 → 승격.

- promotion_baselines: version 기반 결정적 PK, active/superseded (승격 이력 보존).
- PromotionGate.evaluate(snapshot): active baseline 대비 deltas·regressions·blocked,
  action(promote/keep/init).
- 회귀 없음+게이트 통과 → action=promote; align 가 active 갱신(superseded).
- 회귀 있음 → blocked, keep.
- **read-mostly** (불변식 §3-3): evaluate 는 조회만(상태 불변), align 만 영속.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from orc_citadel.regression import RegressionRunner, EvalSnapshot


class PromotionGate:
    """zone 영속 baseline으로 승격/차단을 판정하는 게이트 (design 10 §3.1)."""

    def __init__(self, zone, permitted: dict | None = None) -> None:
        self._zone = zone
        self._runner = RegressionRunner(permitted=permitted)

    def evaluate(self, snapshot: EvalSnapshot) -> dict:
        """current snapshot(후보)을 active baseline과 대조.

        반환: {passed, blocked, action, deltas, regressions, baseline_version, reason}.
        action: promote(통과) / keep(회귀·게이트 미달 차단) / init(baseline 없음).
        상태 불변 — 영속 없음.
        """
        active = self._zone.active_baseline()
        if active is None:
            return {"passed": False, "blocked": False, "action": "init",
                    "deltas": {}, "regressions": [], "baseline_version": None,
                    "reason": "first run — no baseline"}
        baseline = EvalSnapshot(version=active["version"],
                                metrics=active["metrics"])
        res = self._runner.run(baseline, snapshot)
        passed = res.blocked is False
        return {
            "passed": passed,
            "blocked": res.blocked,
            "action": "promote" if passed else "keep",
            "deltas": res.deltas,
            "regressions": res.regressions,
            "baseline_version": baseline.version,
            "reason": "" if passed else (
                "회귀: " + ", ".join(res.regressions) if res.regressions
                else "gate 미달"),
        }

    def align(self, snapshot: EvalSnapshot) -> bool:
        """승격 진행 — passed 시 현재 active를 superseded로, 신규 baseline 영속.

        blocked이면 영속하지 않고 False 반환 (baseline 유지).
        """
        res = self.evaluate(snapshot)
        if res["blocked"]:
            return False
        current = self._zone.active_baseline()
        if current is not None:
            self._zone.mark_baseline_superseded(current["version"])
        self._zone.persist_promotion_baseline(version=snapshot.version,
                                              metrics=snapshot.metrics)
        return True
