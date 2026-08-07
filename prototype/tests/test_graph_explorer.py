"""S44 Graph Explorer (설계 07 §3.3) TDD.

조사 루프의 read-only 그래프 탐색 — subclaim → 관련 subgraph + relation_paths +
independence_summary. S26 investigation_subgraph(정규 뷰 재작성)·S29 독립성 보정 재사용.

- subgraph: entity→ABOUT claim→SUPPORTS/CONTRADICTS evidence (hopped).
- relation_paths: entity→claim→evidence 경로 목록.
- independence_summary: evidence_count·independent_source_count(dup 보정)·dedup_ratio.
- **read-only** (불변식 §3-3) — graph mutation 미노출.

Atomic TDD: Red → Green.
"""
from __future__ import annotations

import pytest

from orc_citadel.graph_explorer import GraphExplorer
from orc_citadel.curated_zone import CuratedZone


def _graph():
    from orc_citadel.graph_service import GraphService as GS
    g = GS()
    g.apply([
        {"mutation_id": "m1", "idempotency_key": "k1", "op": "create_node",
         "payload": {"id": "org-a", "props": {}, "labels": []}},
        {"mutation_id": "m2", "idempotency_key": "k2", "op": "create_node",
         "payload": {"id": "clm-1", "props": {}, "labels": []}},
        {"mutation_id": "m3", "idempotency_key": "k3", "op": "create_node",
         "payload": {"id": "evd-1", "props": {}, "labels": []}},
        {"mutation_id": "m4", "idempotency_key": "k4", "op": "create_edge",
         "payload": {"type": "ABOUT", "from": "org-a", "to": "clm-1", "props": {}}},
        {"mutation_id": "m5", "idempotency_key": "k5", "op": "create_edge",
         "payload": {"type": "SUPPORTS", "from": "evd-1", "to": "clm-1", "props": {}}},
    ])
    return g


def _zone() -> CuratedZone:
    z = CuratedZone(":memory:")
    z.initialize()
    # subject org-a assert → 근거.
    from orc_citadel.assertions import materialize
    from orc_citadel.extract import Mention
    from orc_citadel.extract_claims import ClaimCandidate
    from datetime import datetime, timezone

    cc = ClaimCandidate(
        claim_candidate_id="clm-1", doc_id="doc-a", predicate="announces",
        subject_id="org-a", object_id="org-b", object_literal=None,
        modality="asserted", polarity="positive", confidence=0.8, seg_order=0,
        char_start=0, char_end=4, surface_fragment="x", event_type_hint=None,
        status="promoted")
    z.persist_claim(cc)
    z.persist_mention(Mention(mention_id="men-1", doc_id="doc-a",
                              segment_id="doc-a#s0", surface_text="org-a",
                              mention_type="ORG", char_start=0, char_end=4,
                              context_window=None))
    z.persist_assertion(materialize(cc, observed_at=datetime(2026, 1, 1,
                                                             tzinfo=timezone.utc),
                                    mutation="mut-1"))
    return z


def test_explore_structure():
    """explore — subgraph·relation_paths·independence_summary 포함."""
    e = GraphExplorer(_zone(), _graph())
    res = e.explore(subclaim_id="s1", subject_id="org-a")
    assert "subgraph" in res and "relation_paths" in res
    assert "independence_summary" in res
    assert res["subgraph"]["entity"] == "org-a"
    assert any(cls["id"] == "clm-1" for cls in res["subgraph"]["claims"])


def test_relation_paths():
    """relation_paths — entity→claim→evidence 경로."""
    e = GraphExplorer(_zone(), _graph())
    res = e.explore("s1", "org-a")
    paths = res["relation_paths"]
    assert any("/ABOUT/" in p for p in paths)
    assert any("/SUPPORTS/" in p for p in paths)


def test_independence_summary_dedup():
    """independence_summary — dup 보정된 독립 출처."""
    z = _zone()
    # 2 doc, dup 클러스터로 묶어 독립 1로.
    z.persist_cluster("clu-1", root_doc_id="doc-a", member_doc_ids=["doc-a"],
                      independent_addition_doc_ids=[], dedup_method="exact")
    e = GraphExplorer(z, _graph())
    summ = e.explore("s1", "org-a")["independence_summary"]
    assert summ["evidence_count"] >= 1
    assert summ["independent_source_count"] >= 1


def test_read_only_no_mutation():
    """explorer는 read-only — graph mutation 미노출."""
    e = GraphExplorer(_zone(), _graph())
    for bad in ("apply", "create_node", "create_edge", "persist"):
        assert not hasattr(e, bad), f"read-only 위반: {bad} 노출"


def test_determinism():
    """동일 입력 → 동일 출력."""
    e = GraphExplorer(_zone(), _graph())
    a = e.explore("s1", "org-a")
    b = e.explore("s1", "org-a")
    assert a == b
