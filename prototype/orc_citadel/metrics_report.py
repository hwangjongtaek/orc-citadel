"""MVP #4 평가 수치 공개 (설계 10 §1.2·§2.1) — ER·Claim Extraction 실측 리포트.

실데이터 골든셋(`golden_pairs`) 대비 KG 품질 지표(설계 10 §1.2)를 검증 가능하게 공개.
- **claim_extraction (canonicalization)**: 골든 equivalent/unrelated 쌍 대비 병합 여부로
  TP/FP/FN → P/R/F1 계산 (§1.2 canonicalization gate ≥ 0.85). 골든이 있으면 measured.
- **contradiction**: 골든 contradicts 쌍이 있으면 P/R 측정. 골든에 contradicts가 없으면
  vacuous pass가 아니라 **measured=False 미측정**으로 명시 (§1.2 · §6.2 — pass는 골든 존재 시에만).
- **entity_resolution (ER)**: entity pair 골든세트(§2.1 1,000건) 미구축 → **measured=False**,
  Phase 2 골든 확장 후 측정 경로로 명시. (현재 오병합 게이트 검증 불가)

**read-only** (불변식 §3-3): 조회만 — 골든·baseline 영속 없음, 결정적.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from orc_citadel.eval_harness import EvalHarness, CANONICAL_GATE

CONTRADICTION_GATE_P = 0.90
CONTRADICTION_TARGET_R = 0.75


@dataclass(frozen=True)
class MetricsSlice:
    """개별 지표 축의 측정 결과.

    measured=True  : 골든 존재 → metrics/gate 채움.
    measured=False : 골든 미확보(또는 골든세트 미구축) → metrics=None, note에 이유.
    """
    key: str
    measured: bool
    metrics: dict | None
    gate: dict | None
    note: str = ""


@dataclass(frozen=True)
class MetricsReport:
    slices: dict            # key -> MetricsSlice — claim_extraction / contradiction / entity_resolution.
    summary: str

    def format(self) -> str:
        lines = ["=== 평가 수치 공개 (설계 10 §1.2, MVP #4) ==="]
        for key, s in self.slices.items():
            if s.measured:
                m = s.metrics
                lines.append(f"  {key}: F1={m['f1']:.2f} P={m['precision']:.2f} "
                             f"R={m['recall']:.2f} (tp={m['tp']} fp={m['fp']} fn={m['fn']}) "
                             f"[gate {'PASS' if s.gate['pass'] else 'FAIL'}]")
            else:
                lines.append(f"  {key}: 미측정 (measured=False) — {s.note}")
        lines.append(f"  요약: {self.summary}")
        return "\n".join(lines)


def _claim_extraction(zone) -> MetricsSlice:
    h = EvalHarness(zone=zone)
    golden = [g for g in zone.golden_pairs()
              if g["label"] in ("equivalent", "unrelated")]
    if not golden:
        return MetricsSlice(
            key="claim_extraction", measured=False, metrics=None, gate=None,
            note="골든 equivalent/unrelated 쌍 미확보 — 측정 불가.",
        )
    cc = h.canonicalization_metrics()
    p, r, f1 = cc.precision, cc.recall, cc.f1
    metrics = {"tp": cc.tp, "fp": cc.fp, "fn": cc.fn,
               "precision": p, "recall": r, "f1": f1}
    gate = {"threshold": CANONICAL_GATE, "pass": f1 >= CANONICAL_GATE}
    return MetricsSlice(key="claim_extraction", measured=True,
                        metrics=metrics, gate=gate)


def _contradiction(zone) -> MetricsSlice:
    golden = [g for g in zone.golden_pairs() if g["label"] == "contradicts"]
    if not golden:
        return MetricsSlice(
            key="contradiction", measured=False, metrics=None, gate=None,
            note="골든 contradicts 쌍 미확보 — vacuous pass 없이 미측정 (gate는 골든 존재 시에만 판정, 10 §6.2).",
        )
    h = EvalHarness(zone=zone)
    cd = h.contradiction_metrics()
    p, r = cd.precision, cd.recall
    metrics = {"tp": cd.tp, "fp": cd.fp, "fn": cd.fn,
               "precision": p, "recall": r, "f1": cd.f1}
    gate = {"threshold_p": CONTRADICTION_GATE_P, "target_r": CONTRADICTION_TARGET_R,
            "pass": p >= CONTRADICTION_GATE_P and r >= CONTRADICTION_TARGET_R}
    return MetricsSlice(key="contradiction", measured=True,
                        metrics=metrics, gate=gate)


def _entity_resolution(zone) -> MetricsSlice:
    # entity pair 골든세트(설계 10 §2.1, 1,000건)·오병합 평가용 골든 없음 → 미측정.
    return MetricsSlice(
        key="entity_resolution", measured=False, metrics=None, gate=None,
        note="entity pair 골든세트 미구축 — ER P/R·오병합률은 Phase 2 골든 확장(10 §2.1) 후 측정.",
    )


def generate_metrics_report(zone) -> MetricsReport:
    slices = {
        "claim_extraction": _claim_extraction(zone),
        "contradiction": _contradiction(zone),
        "entity_resolution": _entity_resolution(zone),
    }
    ce = slices["claim_extraction"]
    if ce.measured:
        m = ce.metrics
        summary = (f"Claim extraction(canonicalization) F1={m['f1']:.2f} "
                   f"(P={m['precision']:.2f}, R={m['recall']:.2f}, tp={m['tp']}) 공개; "
                   f"contradiction·ER은 골든 미확보로 미측정(honest gap).")
    else:
        summary = "골든셋 부족 — 공개 가능한 측정 지표 없음."
    return MetricsReport(slices=slices, summary=summary)
