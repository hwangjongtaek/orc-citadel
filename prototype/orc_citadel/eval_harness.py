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

import json
from dataclasses import dataclass, field

CANONICAL_GATE = 0.85
CONTRADICTION_GATE_P = 0.90
CONTRADICTION_TARGET_R = 0.75
# ER/오병합률 게이트 (design 10 §1.2·ADR-1001, precision-first).
ENTITY_RESOLUTION_GATE_P = 0.97
ENTITY_RESOLUTION_GATE_WRONG_MERGE = 0.02


@dataclass(frozen=True)
class GoldenPair:
    claim_a: str
    claim_b: str
    label: str              # equivalent | contradicts | unrelated
    split: str = "dev"      # dev | test (ADR-1007)
    rationale: str = ""


@dataclass(frozen=True)
class GoldenEntityPair:
    entity_key_a: str
    entity_key_b: str
    label: str              # same | not_same | uncertain
    split: str = "dev"      # dev | test (ADR-1007)
    rationale: str = ""


@dataclass(frozen=True)
class GoldenLineagePair:
    doc_a: str
    doc_b: str
    label: str              # dup | independent
    split: str = "dev"      # dev | test (ADR-1007)
    rationale: str = ""


def entity_key_for(mention_type: str, canonical_name: str,
                   identifiers: dict | None = None) -> str:
    """골든 entity key — ADR-507 결정적 규칙과 동일한 식별 기준.

    결정적 외부식별자가 있으면 `id:<sorted identifiers>`, 없으면
    `surface:<type>:<canonical_name>`. 골든세트와 zone 해소 결과 양쪽이 같은
    형식을 써야 same/not_same 판정이 정합된다 (불변식 §3-7).
    """
    if identifiers:
        return "id:" + json.dumps(sorted(identifiers.items()),
                                   ensure_ascii=False, sort_keys=True)
    return f"surface:{mention_type}:{canonical_name}"


def build_entity_merge(entities_rows: list[dict]) -> dict:
    """zone의 해소된 entity row들 → {entity_key: entity_id} 맵 (read-only).

    결정적 식별자를 가진 entity는 `id:<sorted ids>` 키, 식별자 없는 canonical은
    각 surface_forms를 `surface:<type>:<surface>` 키로 확장한다. 멀티 surface(동치류)
    해소가 같은 entity_id로 매핑되는 지점이 골든 same 쌍의 정답 트리거다.
    """
    mapping: dict[str, str] = {}
    for e in entities_rows:
        ids = e.get("identifiers") or {}
        mention_type = e.get("mention_type") or ""
        if ids:
            mapping[entity_key_for(mention_type, "", ids)] = e["entity_id"]
        for s in e.get("surface_forms") or []:
            mapping[entity_key_for(mention_type, s)] = e["entity_id"]
    return mapping


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
                 conflicts=None, golden=None, entities=None,
                 golden_entities=None, golden_lineage=None, clusters=None) -> None:
        """상태는 zone에서 읽거나 직접 주입 (결정적·독립 테스트용).

        주입 우선: canonical_claims/member_of/conflicts/golden/entities/golden_entities/
        golden_lineage/clusters 가 명시되면 사용. zone 주입 시 zone의
        캐노니컬·모순·골든·entity·계보(read-only 조회) 사용.
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

        # 골든 entity pair (Phase 2 §2.1) — 주입 우선, zone이면 자동 로드.
        if golden_entities is not None:
            self._golden_entities = list(golden_entities)
        elif zone is not None:
            self._golden_entities = [GoldenEntityPair(
                entity_key_a=g["entity_key_a"], entity_key_b=g["entity_key_b"],
                label=g["label"], split=g["split"],
                rationale=g.get("rationale") or "",
            ) for g in zone.golden_entity_pairs()]
        else:
            self._golden_entities = []

        # zone의 해소된 entity rows → entity_key → entity_id 맵.
        if entities is not None:
            self._entity_merge = build_entity_merge(entities)
        elif zone is not None:
            self._entity_merge = build_entity_merge(zone.entities())
        else:
            self._entity_merge = {}

        # 골든 계보 쌍 (Phase 2 §2.1 — dup/independent) — 주입 우선, zone이면 자동 로드.
        if golden_lineage is not None:
            self._golden_lineage = list(golden_lineage)
        elif zone is not None:
            self._golden_lineage = [GoldenLineagePair(
                doc_a=g["doc_a"], doc_b=g["doc_b"], label=g["label"],
                split=g["split"], rationale=g.get("rationale") or "",
            ) for g in zone.golden_lineage_pairs()]
        else:
            self._golden_lineage = []

        # zone의 계보 클러스터 (dup_clusters) → {doc_id: cluster_set} 멤버십 맵.
        if clusters is not None:
            self._cluster_membership = self._build_cluster_membership(clusters)
        elif zone is not None:
            self._cluster_membership = self._build_cluster_membership(zone.clusters())
        else:
            self._cluster_membership = {}

        # claim → canonical_id 맵.
        self._claim_canonical = {r["claim_id"]: r["canonical_claim_id"]
                                 for r in self._member_of}

    @staticmethod
    def _build_cluster_membership(clusters: list[dict]) -> dict[str, str]:
        """계보 클러스터 rows → {doc_id: cluster_id} 멤버십 맵 (read-only)."""
        m: dict[str, str] = {}
        for c in clusters:
            cid = c.get("cluster_id")
            for did in (c.get("member_doc_ids") or []):
                m[did] = cid
        return m

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

    # --- entity resolution -------------------------------------------------

    def entity_resolution_metrics(self, split: str | None = None) -> Metric:
        """ER P/R·오병합률 — 골든 entity pair 대비 해소 대조 (design 10 §1.2, ADR-1001).

        시스템 판정 = 골든 두 entity_key가 같은 canonical entity로 병합됐는지
        (ADR-507: 결정적 외부식별자 exact match만 병합 — `_entity_merge` 맵 재현).
        - same  쌍이 병합되면 tp, 병합 실패면 fn (오분리 under-merge).
        - not_same 쌍이 같은 entity_id로 병합되면 fp — **오병합** (그래프 전역 오염,
          precision-first: 게이트 P ≥ 0.97, 오병합률 ≤ 0.02).
        - uncertain 은 병합 가정 판정을 안 함 (POSSIBLY_SAME_AS 유지, ADR-507) → 게이트 제외.
        """
        tp = fp = fn = 0
        for g in self._golden_entities:
            if g.label not in ("same", "not_same"):
                continue  # uncertain — 병합 가정 판정 불가(ADR-507), 게이트 제외.
            if split is not None and g.split != split:
                continue
            merged = (self._entity_merge.get(g.entity_key_a)
                      == self._entity_merge.get(g.entity_key_b)) \
                and g.entity_key_a in self._entity_merge \
                and g.entity_key_b in self._entity_merge
            if g.label == "same":
                if merged:
                    tp += 1
                else:
                    fn += 1  # 오분리 (under-merge, recall 하락).
            else:  # not_same
                if merged:
                    fp += 1  # 오병합 (그래프 전역 오염).
        return Metric(tp=tp, fp=fp, fn=fn)

    # --- lineage (출처 계보) ----------------------------------------------

    def lineage_metrics(self, split: str | None = None) -> Metric:
        """출처 계보(dup) P/R — 골든 계보 쌍 대비 클러스터 축소 대조 (design 10 §1.2·§2.1).

        시스템 판정 = 골든 두 doc 이 같은 `dup_clusters` 클러스터 멤버인지 (design 04 §4,
        root/derived/independent — `_cluster_membership` 맵 재현).
        - dup 쌍이 같은 클러스터로 축소되면 tp, 분리(오분리)면 fn (복제 과대집계).
        - independent 쌍이 같은 클러스터로 오축소되면 fp — 복제 K건을 독립 K으로 세는
          과대평가 방지 (design 04 §4).
        """
        tp = fp = fn = 0
        for g in self._golden_lineage:
            if split is not None and g.split != split:
                continue
            same = (g.doc_a in self._cluster_membership
                    and self._cluster_membership.get(g.doc_a)
                    == self._cluster_membership.get(g.doc_b))
            if g.label == "dup":
                if same:
                    tp += 1
                else:
                    fn += 1
            else:  # independent
                if same:
                    fp += 1
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
