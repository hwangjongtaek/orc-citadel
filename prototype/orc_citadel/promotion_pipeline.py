"""S39/S40 종단 간 승격 파이프라인 (설계 10 §3.1).

S36 EvalSuite 평가 → S38 PromotionGate 승격/차단을 자동 결합. 골든 영속(S34) →
P/R/F1(S33) → 회귀(S35) → durable 승격/차단(S38).

S40 추가 — 5축 version-aware 승격 (03 §7.1, 10 §3.1):
- version 인자에 5축 dict(`version_tuple`) 허용 → fingerprint(`vt-`) baseline.
- 온톨로지 major bump(02 §6.3) 시 `ontology_major_bump=True` + `revalidate_required`
  (전량 재평가 신호). minor는 정상 판정.
- 뒤쪽 호환: 기존 문자열 version 그대로 동작.

- run(version|version_tuple): 평가+판정+align(승격 시 active baseline 영속).
- dry_run: 평가+판정만, align 없음 (read-only, 불변식 §3-3).
- action: PROMOTED / BLOCKED / INITIALIZED.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from orc_citadel.eval_suite import EvalSuite
from orc_citadel.regression import EvalSnapshot
from orc_citadel.pipeline_gate import PromotionGate
from orc_citadel.versioning import fingerprint, ontology_major_bump


@dataclass(frozen=True)
class PromotionResult:
    version: str
    action: str            # PROMOTED | BLOCKED | INITIALIZED.
    passed: bool
    gates: dict
    metrics: dict
    regressions: list
    realized: bool         # baseline 반영 여부.
    ontology_major_bump: bool = False
    revalidate_required: bool = False


class PromotionPipeline:
    """EvalSuite 평가 → PromotionGate 승격/차단 종단 간 결합 (design 10 §3.1)."""

    def __init__(self, zone, permitted: dict | None = None) -> None:
        self._zone = zone
        self._permitted = permitted

    def _resolve(self, version=None, version_tuple=None) -> tuple[str, str | None]:
        """version(문자열) 또는 version_tuple(5축 dict) → (fingerprint, ontology)."""
        if version_tuple is not None:
            return fingerprint(version_tuple), version_tuple.get("ontology_version")
        return (version or "default"), None

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

    def _ontology_decision(self, version_tuple, active) -> tuple[bool, bool]:
        """온톨로지 major bump 판정 — baseline active와 현재 tuple 비교 (02 §6.3).

        현재(version_tuple)가 5축이 아니거나 baseline에 ontology 기록이 없으면
        major False (추론 불가 시 보수적으로 재평가 신호 없음).
        """
        if version_tuple is None:
            return False, False
        cur_onto = version_tuple.get("ontology_version")
        prev_onto = active.get("ontology") if active else None
        if cur_onto is None or prev_onto is None:
            return False, False
        major = ontology_major_bump(prev_onto, cur_onto)
        return major, major  # major이면 재평가 필요.

    def _decide(self, suite_res, gate_verdict, version: str,
                ontology_major: bool = False) -> PromotionResult:
        action = {"init": "INITIALIZED", "promote": "PROMOTED",
                  "keep": "BLOCKED"}[gate_verdict["action"]]
        blocked = gate_verdict["blocked"]
        return PromotionResult(
            version=version, action=(action if not ont_major_for(action, ontology_major)
                                     else "BLOCKED"),
            passed=(not blocked and not ontology_major),
            gates=suite_res.gates, metrics=suite_res.metrics,
            regressions=gate_verdict["regressions"], realized=False,
            ontology_major_bump=ontology_major,
            revalidate_required=ontology_major,
        )

    def run(self, version=None, *, version_tuple=None) -> PromotionResult:
        fp, ontology = self._resolve(version, version_tuple)
        suite_res, snapshot, gate, verdict = self._evaluate(fp)
        active = self._zone.active_baseline()
        ont_major, _ = self._ontology_decision(version_tuple, active)
        res = self._decide(suite_res, verdict, fp, ont_major)
        # block 또는 major 재평가가 아니면 align (INITIALIZED/PROMOTED → active 반영).
        if not verdict["blocked"] and not ont_major:
            gate.align(snapshot, ontology=ontology)
            res = PromotionResult(
                version=fp, action=res.action, passed=res.passed,
                gates=res.gates, metrics=res.metrics,
                regressions=res.regressions, realized=True,
                ontology_major_bump=False, revalidate_required=False,
            )
        return res

    def dry_run(self, version=None, *, version_tuple=None) -> PromotionResult:
        """평가·판정만 — align 없음 (read-only, 불변식 §3-3)."""
        fp, _ = self._resolve(version, version_tuple)
        suite_res, _, _, verdict = self._evaluate(fp)
        active = self._zone.active_baseline()
        ont_major, _ = self._ontology_decision(version_tuple, active)
        return self._decide(suite_res, verdict, fp, ont_major)


def ont_major_for(action: str, ontology_major: bool) -> bool:
    """major 재평가 시 promote/init 조차 block 우선 (전량 재검토, 02 §6.3)."""
    return ontology_major
