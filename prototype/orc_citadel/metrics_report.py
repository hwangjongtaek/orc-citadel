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

from orc_citadel.eval_harness import (
    EvalHarness, CANONICAL_GATE,
    ENTITY_RESOLUTION_GATE_P, ENTITY_RESOLUTION_GATE_WRONG_MERGE,
)

CONTRADICTION_GATE_P = 0.90
CONTRADICTION_TARGET_R = 0.75
# 출처 계보(dup) 게이트 (design 10 §1.1 — Dup precision ≥ 0.98, target recall ≥ 0.90).
LINEAGE_GATE_P = 0.98
LINEAGE_TARGET_R = 0.90


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
                if "wrong_merge_rate" in m:
                    lines.append(f"  {key}: 오병합률={m['wrong_merge_rate']:.4f} "
                                 f"P={m['precision']:.2f} R={m['recall']:.2f} "
                                 f"(tp={m['tp']} fp={m['fp']} fn={m['fn']}) "
                                 f"[gate {'PASS' if s.gate['pass'] else 'FAIL'}]")
                else:
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
    """entity pair 골든세트(10 §2.1) 존재 시 ER P/R·오병합률 측정, 아니면 미측정.

    골든 same/not_same 쌍이 있으면 EvalHarness.entity_resolution_metrics (ADR-1007
    precision-first: P ≥ 0.97, 오병합률 ≤ 0.02). uncertain 쌍은 병합 가정 판정을
    안 하므로(POSSIBLY_SAME_AS 유지, ADR-507) 게이트에서 제외 — vacuous pass 금지
    (§6.2): same/not_same 골든 부재 시 measured=False.
    """
    h = EvalHarness(zone=zone)
    golden = [g for g in h._golden_entities if g.label in ("same", "not_same")]
    if not golden:
        return MetricsSlice(
            key="entity_resolution", measured=False, metrics=None, gate=None,
            note="entity pair 골든세트(same/not_same) 미확보 — ER P/R·오병합률은 "
                 "Phase 2 골든 확장(10 §2.1) 후 측정 (uncertain만으로는 vacuous pass 금지).",
        )
    m = h.entity_resolution_metrics()
    metrics = {"tp": m.tp, "fp": m.fp, "fn": m.fn,
               "precision": m.precision, "recall": m.recall, "f1": m.f1}
    wrong_merge = m.fp / (m.tp + m.fp) if (m.tp + m.fp) else 0.0
    metrics["wrong_merge_rate"] = wrong_merge
    gate = {"threshold_p": ENTITY_RESOLUTION_GATE_P,
            "threshold_wrong_merge": ENTITY_RESOLUTION_GATE_WRONG_MERGE,
            "pass": m.precision >= ENTITY_RESOLUTION_GATE_P
                    and wrong_merge <= ENTITY_RESOLUTION_GATE_WRONG_MERGE}
    return MetricsSlice(key="entity_resolution", measured=True,
                        metrics=metrics, gate=gate)


def _lineage(zone) -> MetricsSlice:
    """계보 골든셋(10 §2.1, dup/independent) 존재 시 dup P/R 측정, 아니면 미측정.

    골든 dup/independent 쌍이 있으면 EvalHarness.lineage_metrics — 같은 dup_clusters
    클러스터로 축소됐는지 대조 (design 10 §1.1: Dup precision ≥ 0.98, target R ≥ 0.90).
    independent 오축소=fp(복제 K건을 독립 K으로 세는 과대평가 방지, design 04 §4).
    골든 부재 시 vacuous pass 없이 measured=False (honest gap §6.2).
    """
    h = EvalHarness(zone=zone)
    golden = [g for g in h._golden_lineage if g.label in ("dup", "independent")]
    if not golden:
        return MetricsSlice(
            key="lineage", measured=False, metrics=None, gate=None,
            note="골든 계보 쌍(dup/independent) 미확보 — dup P/R은 Phase 2 골든 "
                 "확장(10 §2.1) 후 측정.",
        )
    m = h.lineage_metrics()
    metrics = {"tp": m.tp, "fp": m.fp, "fn": m.fn,
               "precision": m.precision, "recall": m.recall, "f1": m.f1}
    gate = {"threshold_p": LINEAGE_GATE_P, "target_r": LINEAGE_TARGET_R,
            "pass": m.precision >= LINEAGE_GATE_P
                    and m.recall >= LINEAGE_TARGET_R}
    return MetricsSlice(key="lineage", measured=True,
                        metrics=metrics, gate=gate)


def generate_metrics_report(zone) -> MetricsReport:
    slices = {
        "claim_extraction": _claim_extraction(zone),
        "contradiction": _contradiction(zone),
        "entity_resolution": _entity_resolution(zone),
        "lineage": _lineage(zone),
    }
    ce = slices["claim_extraction"]
    er = slices["entity_resolution"]
    lg = slices["lineage"]
    if ce.measured and er.measured:
        m = ce.metrics
        er_m = er.metrics
        summary = (f"Claim extraction(canonicalization) F1={m['f1']:.2f} "
                   f"(P={m['precision']:.2f}, R={m['recall']:.2f}, tp={m['tp']}) · "
                   f"ER P={er_m['precision']:.2f} 오병합률={er_m['wrong_merge_rate']:.4f} "
                   f"(tp={er_m['tp']} fp={er_m['fp']} fn={er_m['fn']}) 공개; "
                   f"contradiction은 골든 미확보로 미측정(honest gap).")
        if lg.measured:
            lg_m = lg.metrics
            summary += (f" · Lineage(dup) P={lg_m['precision']:.2f} "
                        f"R={lg_m['recall']:.2f} (tp={lg_m['tp']} fp={lg_m['fp']}"
                        f" fn={lg_m['fn']}) 공개.")
    elif ce.measured:
        m = ce.metrics
        summary = (f"Claim extraction(canonicalization) F1={m['f1']:.2f} "
                   f"(P={m['precision']:.2f}, R={m['recall']:.2f}, tp={m['tp']}) 공개; "
                   f"contradiction·ER은 골든 미확보로 미측정(honest gap).")
    else:
        summary = "골든셋 부족 — 공개 가능한 측정 지표 없음."
    return MetricsReport(slices=slices, summary=summary)
