"""S33 평가 하네스 (설계 10 §1.2·§2) — 소량 골든셋 P/R.

프로젝트 핵심 가치(design 10 §8 "KG가 얼마나 정확한가")에 수치로 답하는 경량.
**claim pair 골든셋**으로 파이프라인 산출(캐노니컬·모순)을 대조해 P/R/F1 계산.

- Canonicalization P/R (design 10 §1.2, gate ≥ 0.85): 골든 equivalent 쌍이 실제
  같은 CanonicalClaim으로 병합되는지 — TP/FP/FN.
- Contradiction P/R (design 10 §1.2, gate P ≥ 0.90, target R ≥ 0.75): 골든 contradicts
  쌍이 실제 conflict_candidates에 존재하는지.
- split ∈ {dev, test} (ADR-1007 튜닝/게이트 분리).
- 골든셋은 **human review as data** (design 10 §2.2, 불변식 §3-7) — 원 출력·정답·이유.
- **read-only** (불변식 §3-3) — 대조만, 쓰기·영속·mutation 미노출.
"""
from __future__ import annotations

from dataclasses import dataclass, field

CANONICAL_GATE = 0.85
CONTRADICTION_GATE_P = 0.90
CONTRADICTION_TARGET_R = 0.75


@dataclass(frozen=True)
class GoldenPair:
    claim_a: str
    claim_b: str
    label: str              # equivalent | contradicts | unrelated
    split: str = "dev"      # dev | test (ADR-1007)
    rationale: str = ""


@dataclass(frozen=True)
class Metric:
    tp: int
    fp: int
    fn: int

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


class EvalHarness:
    """골든셋(claim pair) 대비 파이프라인 산출 대조 — read-only 평가."""

    def __init__(self, zone=None, canonical_claims=None, member_of=None,
                 conflicts=None, golden=None) -> None:
        """상태는 zone에서 읽거나 직접 주입 (결정적·독립 테스트용).

        주입 우선: canonical_claims/member_of/conflicts/golden 이 명시되면 사용.
        zone 주입 시 zone의 캐노니컬·모순·골든(read-only 조회) 사용.
        """
        if canonical_claims is not None:
            self._canonical_claims = list(canonical_claims)
            self._member_of = list(member_of or [])
        elif zone is not None:
            self._canonical_claims = zone.canonical_claims()
            self._member_of = zone.member_of()
        else:
            self._canonical_claims, self._member_of = [], []

        self._conflicts = list(conflicts) if conflicts is not None \
            else (zone.conflict_candidates() if zone is not None else [])
        # 골든 — 주입 우선, zone이면 golden_pairs 자동 로드 (10 §2.3).
        if golden is not None:
            self._golden = list(golden)
        elif zone is not None:
            self._golden = [GoldenPair(
                claim_a=g["claim_a"], claim_b=g["claim_b"], label=g["label"],
                split=g["split"], rationale=g.get("rationale") or "",
            ) for g in zone.golden_pairs()]
        else:
            self._golden = []

        # claim → canonical_id 맵.
        self._claim_canonical = {r["claim_id"]: r["canonical_claim_id"]
                                 for r in self._member_of}

    # --- helpers ---------------------------------------------------------

    def _pairs(self, split: str | None, *labels: str) -> list[GoldenPair]:
        out = [g for g in self._golden
               if g.label in labels and (split is None or g.split == split)]
        return out

    def _same_canonical(self, a: str, b: str) -> bool:
        ca, cb = self._claim_canonical.get(a), self._claim_canonical.get(b)
        return ca is not None and ca == cb

    def _in_conflict(self, a: str, b: str) -> bool:
        for cf in self._conflicts:
            pair = {cf["claim_id_a"], cf["claim_id_b"]}
            if {a, b} == pair:
                return True
        return False

    # --- canonicalization -------------------------------------------------

    def canonicalization_metrics(self, split: str | None = None) -> Metric:
        tp = fp = fn = 0
        for g in self._pairs(split, "equivalent", "unrelated"):
            merged = self._same_canonical(g.claim_a, g.claim_b)
            if g.label == "unrelated":
                if merged:  # 오병합.
                    fp += 1
            else:  # equivalent.
                if merged:
                    tp += 1
                else:
                    fn += 1
        return Metric(tp=tp, fp=fp, fn=fn)

    # --- contradiction ----------------------------------------------------

    def contradiction_metrics(self, split: str | None = None) -> Metric:
        tp = fp = fn = 0
        for g in self._pairs(split, "contradicts", "unrelated"):
            found = self._in_conflict(g.claim_a, g.claim_b)
            if g.label == "unrelated":
                if found:
                    fp += 1  # 오판.
            else:  # contradicts.
                if found:
                    tp += 1
                else:
                    fn += 1
        return Metric(tp=tp, fp=fp, fn=fn)

    # --- report -----------------------------------------------------------

    def report(self, split: str | None = None) -> dict:
        cc = self.canonicalization_metrics(split)
        cd = self.contradiction_metrics(split)
        cc_golden = [g for g in self._golden
                     if g.label in ("equivalent", "unrelated")]
        cd_golden = [g for g in self._golden if g.label in ("contradicts", "unrelated")]
        # 골든셋이 비어 있으면 vacuous pass (gate 강제를 위한 골든이 없으므로 block 안 함).
        cc_pass = (len(cc_golden) == 0) or (cc.f1 >= CANONICAL_GATE)
        cd_pass = (len(cd_golden) == 0) or (
            cd.precision >= CONTRADICTION_GATE_P
            and cd.recall >= CONTRADICTION_TARGET_R)
        return {
            "canonicalization": {
                "metrics": {"tp": cc.tp, "fp": cc.fp, "fn": cc.fn,
                            "precision": cc.precision, "recall": cc.recall,
                            "f1": cc.f1},
                "gate": {"threshold": CANONICAL_GATE, "pass": cc_pass},
            },
            "contradiction": {
                "metrics": {"tp": cd.tp, "fp": cd.fp, "fn": cd.fn,
                            "precision": cd.precision, "recall": cd.recall,
                            "f1": cd.f1},
                "gate": {"threshold_p": CONTRADICTION_GATE_P,
                         "target_r": CONTRADICTION_TARGET_R,
                         "pass_p": cd.precision >= CONTRADICTION_GATE_P,
                         "pass_r": cd.recall >= CONTRADICTION_TARGET_R,
                         "pass": cd_pass},
            },
            "promotion_blocked": not (cc_pass and cd_pass),
            "golden_count": len(self._golden),
        }
