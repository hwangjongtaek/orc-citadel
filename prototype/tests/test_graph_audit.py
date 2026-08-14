"""Phase 2 DoD ② — Entity merge 감사·rollback (설계 06 §5.3, 불변식 §3-3) TDD.

모든 merge_entity는 대응 unmerge 로 reversible 해야 하고, 병합 이력을 감사 조회할
수 있어야 한다 (오병합 복구 — precision-first, ADR-1001·ADR-605).
- `merge_audit(entity_id)`: 해당 entity 의 병합 이력(누가·resolution_ref·SAME_AS)을
  read-only 조회.
- `audit_rollback(entity_id, resolution_ref)`: 감사 결과 기준 오병합 판정 시 해당
  병합을 unmerge(06 §5.3) 로 revert — 그 뒤 노드는 원래 canonical 로 돌아간다.
- read-only 감사 + 가역 rollback (불변식 §3-3 append-only replay).

Atomic TDD: Red → Green.
"""
from __future__ import annotations

import pytest

from orc_citadel.graph_service import GraphService


def _node(evt_id, key, nid, name=None, label="Authoritative"):
    p = {"name": name} if name is not None else {}
    return {"mutation_id": evt_id, "idempotency_key": key, "op": "create_node",
            "payload": {"id": nid, "label": label, "props": p}}


def _merge(evt_id, key, member, canonical, res="res-1", actor="pipeline"):
    return {"mutation_id": evt_id, "idempotency_key": key, "op": "merge_entity",
            "resolution_ref": res,
            "payload": {"member": member, "canonical": canonical, "actor": actor}}


def _unmerge(evt_id, key, member, canonical, res="res-1"):
    return {"mutation_id": evt_id, "idempotency_key": key, "op": "unmerge",
            "resolution_ref": res,
            "payload": {"member": member, "canonical": canonical}}


def _merged_graph():
    """two nodes + 한 번의 resolve 병합 (actor=pipeline, res=res-42)."""
    g = GraphService()
    g.apply([
        _node("n1", "k1", "org-a", name="A"),
        _node("n2", "k2", "org-b", name="B"),
        _merge("m1", "k3", "org-a", "org-b", res="res-42", actor="human:reviewer"),
    ])
    return g


def test_merge_audit_reports_resolution():
    """병합 감사 — member 의 병합 이력에 canonical·resolution_ref·actor 노출 (06 §5.3)."""
    g = _merged_graph()
    audit = g.merge_audit("org-a")
    # 동치류 대표(org-b)로 rewrite 된 병합 1건.
    assert audit["entity_id"] == "org-a"
    assert audit["canonical_id"] == "org-b"
    assert len(audit["merges"]) == 1
    m = audit["merges"][0]
    assert m["to"] == "org-b"
    assert m["resolution_ref"] == "res-42"
    assert m["decided_by"] == "human:reviewer"


def test_merge_audit_unmerged_entity_no_merges():
    """병합되지 않은(독립) entity 의 감사 — merges 비어있음 (오병합 아님)."""
    g = _merged_graph()
    audit = g.merge_audit("org-b")  # canonical 은 자체 병합 없음.
    assert audit["canonical_id"] is None
    assert audit["merges"] == []


def test_audit_rollback_reverts_merge():
    """오병합 판정 → rollback(해당 resolution 의 unmerge) → 원래 canonical 로 복구."""
    g = _merged_graph()
    g.audit_rollback("org-a", "res-42")
    # unmerge 로 SAME_AS 제거 + canonical 원복 (06 §5.3).
    assert g.node("org-a")["canonical_id"] is None
    assert g.node("org-a")["merged"] is False
    # SAME_AS 엣지 제거 — org-a 가 org-b 로 rewrite 안 됨.
    assert not any(n["type"] == "SAME_AS" for n in g.neighbors("org-a"))


def test_audit_rollback_is_idempotent():
    """rollback 은 unmerge 이벤트 — 재실행해도 안전 (idempotent, 불변식 §3-6)."""
    g = _merged_graph()
    g.audit_rollback("org-a", "res-42")
    g.audit_rollback("org-a", "res-42")  # 두 번째 호출 no-op.
    assert g.node("org-a")["canonical_id"] is None


def test_audit_rollback_unrelated_ref_noop():
    """감사 시점에 찾은 resolution_ref 가 아니면 rollback no-op (정확한 복구)."""
    g = _merged_graph()
    g.audit_rollback("org-a", "res-999")  # 존재하지 않는 reserve.
    assert g.node("org-a")["canonical_id"] == "org-b"  # 유지.


def test_audit_is_read_only():
    """merge_audit 은 조회만 — 그래프 상태 불변 (read-only, 불변식 §3-3)."""
    g = _merged_graph()
    before = [n["id"] for n in g.nodes()]
    g.merge_audit("org-a")
    after = [n["id"] for n in g.nodes()]
    assert before == after
    assert g.node("org-a")["canonical_id"] == "org-b"
