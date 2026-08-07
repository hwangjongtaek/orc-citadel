"""S44 Graph Explorer (설계 07 §3.3) — read-only 조사 그래프 탐색.

조사 루프의 Graph Explorer — subclaim → 관련 subgraph + relation_paths +
independence_summary (07 §3.3, tier L3·graph:read).

- subgraph          : S26 investigation_subgraph (canonical view-rewrite fold).
- relation_paths    : entity → ABOUT claim → SUPPORTS|CONTRADICTS evidence 경로.
- independence_summary: S29 근거·dup 보정 독립 출처 (evidence_count/independent,
                        dedup_ratio).
- **read-only** (불변식 §3-3): 조회만, graph mutation·영속 미노출.
"""
from __future__ import annotations

from orc_citadel.catalog import CatalogGraph
from orc_citadel.assertion_evidence import AssertionEvidenceProjector


class GraphExplorer:
    """조사 루프의 read-only 그래프 탐색 (07 §3.3)."""

    def __init__(self, zone, graph) -> None:
        self._graph = CatalogGraph(graph)
        self._evidence = AssertionEvidenceProjector(zone)

    def _relation_paths(self, subgraph: dict) -> list[str]:
        paths = []
        entity = subgraph.get("entity")
        if entity:
            for rel in subgraph.get("relationships", []):
                rel_type = rel.get("type")
                if rel_type == "ABOUT":
                    paths.append(f"{entity}/ABOUT/{rel.get('to')}")
                elif rel_type in ("SUPPORTS", "CONTRADICTS"):
                    paths.append(f"{rel.get('from')}/{rel_type}/{rel.get('to')}")
        return paths

    def _compute_independence(self, subject_id: str) -> dict:
        evs = self._evidence.for_subject(subject_id)
        count = sum(e.evidence_count for e in evs)
        indep = sum(e.independent_source_count for e in evs)
        ratio = round(1.0 - (indep / count), 4) if count else 0.0
        return {
            "evidence_count": count,
            "independent_source_count": indep,
            "dedup_ratio": ratio,
            "note": f"독립 출처 {indep}건 / 근거 {count}건 (dup cluster 보정)",
        }

    def _independence_summary(self, subject_id: str) -> dict:
        return self._compute_independence(subject_id)

    def explore(self, subclaim_id: str, subject_id: str, hops: int = 1) -> dict:
        sub = self._graph.investigation_subgraph(subject_id, hops=hops)
        return {
            "subclaim": subclaim_id,
            "subject_id": subject_id,
            "subgraph": sub,
            "relation_paths": self._relation_paths(sub),
            "independence_summary": self._independence_summary(subject_id),
        }

    def independence_summary(self, subject_id: str) -> dict:
        return self._independence_summary(subject_id)
