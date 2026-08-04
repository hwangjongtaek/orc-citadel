"""S17 Applier 전 op — merge/unmerge/supersede + bitemporal AS-OF (06 §3·§5·§6, 03 §6) TDD.

GraphService 확장: merge_entity(SAME_AS 동치류 collapse + canonical)·unmerge(역연산,
resolution_ref 특정)·supersede(SUPERSEDES 엣지 + 구 버전 tx_to close)·AS-OF(valid/tx
시간 질의). precision-first — 오병합은 unmerge로 reversible (불변식 §3-3).
"""
from __future__ import annotations

import pytest

from orc_citadel.graph_service import GraphService


def _node(evt_id, key, nid, **props):
    return {"mutation_id": evt_id, "idempotency_key": key, "op": "create_node",
            "payload": {"id": nid, "props": props, "labels": []}}


def _merge(evt_id, key, member, canonical, res="res-1", actor="pipeline"):
    return {"mutation_id": evt_id, "idempotency_key": key, "op": "merge_entity",
            "resolution_ref": res,
            "payload": {"member": member, "canonical": canonical, "actor": actor}}


def _unmerge(evt_id, key, member, canonical, res="res-1"):
    return {"mutation_id": evt_id, "idempotency_key": key, "op": "unmerge",
            "resolution_ref": res,
            "payload": {"member": member, "canonical": canonical}}


def _supersede(evt_id, key, new_id, old_id, at="2026-08-03T12:00:00Z", reason="정정"):
    return {"mutation_id": evt_id, "idempotency_key": key, "op": "supersede",
            "payload": {"new_id": new_id, "superseded_id": old_id,
                        "superseded_at": at, "reason": reason}}


# --- merge_entity (§5.1) -----------------------------------------------------

def test_merge_entity_same_as_and_canonical():
    """merge_entity → SAME_AS 엣지 + member.canonical_id + :Merged (06 §5.1)."""
    g = GraphService()
    g.apply([
        _node("m1", "k1", "org-a", name="A"),
        _node("m2", "k2", "org-b", name="B"),
        _merge("m3", "k3", "org-a", "org-b", res="res-42"),
    ])
    assert g.node("org-a")["canonical_id"] == "org-b"
    assert g.node("org-a")["merged"] is True
    # SAME_AS 엣지 (member→canonical).
    assert any(n["id"] == "org-b" and n["type"] == "SAME_AS" for n in g.neighbors("org-a"))


def test_merge_needs_both_nodes():
    """merge 대상 노드 미존재 → quarantine (reference, 02 §4-3)."""
    g = GraphService()
    g.apply([_node("m1", "k1", "org-a"), _merge("m2", "k2", "org-a", "org-missing")])
    assert g.node("org-a")["canonical_id"] is None  # 병합 안 됨
    assert g.quarantined_edges()  # dangling 사유


# --- unmerge (§5.3) ----------------------------------------------------------

def test_unmerge_reverses_merge():
    """unmerge → SAME_AS 제거·canonical_id 원복·:Merged 해제 (reversible, §5.3)."""
    g = GraphService()
    g.apply([
        _node("m1", "k1", "org-a"), _node("m2", "k2", "org-b"),
        _merge("m3", "k3", "org-a", "org-b", res="res-7"),
    ])
    assert g.node("org-a")["canonical_id"] == "org-b"
    g.apply([_unmerge("m4", "k4", "org-a", "org-b", res="res-7")])
    assert g.node("org-a")["canonical_id"] is None
    assert g.node("org-a")["merged"] is False
    # SAME_AS 엣지 제거 — 원복.
    assert not any(n["type"] == "SAME_AS" for n in g.neighbors("org-a"))


def test_unmerge_no_prior_merge_noop():
    """병합 없던 쌍의 unmerge는 no-op (안전)."""
    g = GraphService()
    g.apply([_node("m1", "k1", "org-a"), _unmerge("m2", "k2", "org-a", "org-b")])
    assert g.node("org-a")["canonical_id"] is None


# --- supersede (§6) ----------------------------------------------------------

def test_supersede_sets_tx_to_and_edge():
    """supersede → 신버전 SUPERSEDES 구버전 + 구버전 tx_to close (06 §6)."""
    g = GraphService()
    g.apply([
        _node("m1", "k1", "asr-old", claim="c1"),
        _node("m2", "k2", "asr-new", claim="c1"),
        _supersede("m3", "k3", "asr-new", "asr-old", at="2026-08-03T12:00:00Z", reason="정정"),
    ])
    # 구버전은 그래프에 남되 tx_to close ("현재 아님").
    assert g.node("asr-old")["tx_to"] == "2026-08-03T12:00:00Z"
    assert g.node("asr-new")["tx_to"] is None  # 현재 버전
    # SUPERSEDES 엣지 (new→old).
    assert any(n["id"] == "asr-old" and n["type"] == "SUPERSEDES" for n in g.neighbors("asr-new"))


# --- AS-OF (bitemporal, 03 §6.3) ---------------------------------------------

def test_asof_only_current_tx():
    """AS-OF transaction: tx_to=null인 버전만 현재 (03 §6.3)."""
    g = GraphService()
    g.apply([
        _node("m1", "k1", "asr-1", claim="c", value="old"),
        _node("m2", "k2", "asr-2", claim="c", value="new"),
        _supersede("m3", "k3", "asr-2", "asr-1"),
    ])
    current = g.as_of(claim="c")
    assert current["value"] == "new"  # 현재 버전 = superseding (tx_to null)


def test_as_of_valid_time():
    """valid time 존재 시 필터 (AS-OF valid, 03 §6.3)."""
    g = GraphService()
    g.apply([
        _node("m1", "k1", "asr-v", claim="c", valid_from="2025-01-01", valid_to=None),
        _node("m2", "k2", "asr-v2", claim="c", valid_from="2026-01-01", valid_to=None),
    ])
    # 하한 2025-06-01에 유효한 버전 (valid_from ≤ T_v).
    got = g.as_of(claim="c", valid_at="2025-06-01")
    assert got["id"] == "asr-v"
