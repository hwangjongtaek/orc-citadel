"""S12 Edge 후보 — POSSIBLY_SAME_AS (설계 02 §3, 05 §2).

해소 §2.4의 `POSSIBLY_SAME_AS` 후보 엣지. SAME_AS(자동 병합·merge_entity)와 달리
**후보/승격만** — 확정은 결정적 외부식별자 exact match 또는 인간 확인 (ADR-507).
prototype은 해소 stage-1의 후보를 minimal edge 후보로 승격한다.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PossiblySameAsEdge:
    edge_id: str
    entity_a_id: str
    entity_b_id: str
    score: float  # ∈ [0,1] (02 §3.1 weight 범위, 불변식4-7)
    blocking_key: str  # norm_name/identifier (02 §3)
    resolution_ref: str  # → resolution decision (05 §2.5)
    judged_by: str = "pipeline"

    def to_row(self) -> dict:
        return {
            "edge_id": self.edge_id,
            "entity_a_id": self.entity_a_id,
            "entity_b_id": self.entity_b_id,
            "relation": "POSSIBLY_SAME_AS",
            "score": self.score,
            "blocking_key": self.blocking_key,
            "resolution_ref": self.resolution_ref,
            "judged_by": self.judged_by,
        }
