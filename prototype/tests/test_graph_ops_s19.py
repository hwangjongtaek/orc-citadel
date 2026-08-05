"""S19 delete·rollback·quarantine 워크플로 (06 §3·§7, 05 §8) — TDD.

그래프 소프트 삭제(:Deleted, 물리 삭제 금지) + 역이벤트 rollback + quarantine review
상태 전이(05 §8.1)·human review as data(§8.2). 기본 조회서 :Deleted 제외(06 §4.1).
"""
from __future__ import annotations

import pytest

from orc_citadel.graph_service import GraphService
from orc_citadel.review import ReviewQueue


def _node(evt_id, key, nid, **props):
    return {"mutation_id": evt_id, "idempotency_key": key, "op": "create_node",
            "payload": {"id": nid, "props": props, "labels": []}}


def _delete(evt_id, key, nid):
    return {"mutation_id": evt_id, "idempotency_key": key, "op": "delete",
            "payload": {"id": nid, "deleted_at": "2026-08-03T12:00:00Z"}}


# --- delete / soft-delete (06 §3.2) ------------------------------------------

def test_delete_soft_deletes_node():
    """delete → :Deleted + deleted_at, 기본 조회 제외 (06 §3.2·§4.1)."""
    g = GraphService()
    g.apply([_node("m1", "k1", "org-a", name="A")])
    g.apply([_delete("m2", "k2", "org-a")])
    # 기본 조회에서 제외.
    assert g.node("org-a") is None or g.node("org-a").get("deleted") is True
    assert all(n["id"] != "org-a" for n in g.nodes())
    # include_deleted로는 보임 + 삭제 시각.
    with_deleted = g.nodes(include_deleted=True)
    n = next(n for n in with_deleted if n["id"] == "org-a")
    assert n["deleted_at"] == "2026-08-03T12:00:00Z"


def test_delete_requires_existing_node_manual():
    """delete는 노드 존재해야 (없으면 no-op 안전)."""
    g = GraphService()
    g.apply([_delete("m1", "k1", "org-missing")])  # 존재 전 삭제 → 안전 no-op
    assert g.nodes() == []


# --- rollback (06 §7.4, 역이벤트) --------------------------------------------

def test_create_node_rollback_via_delete():
    """create_node 역이벤트 = delete → revert (rollback, 로그 보존)."""
    g = GraphService()
    g.apply([_node("m1", "k1", "org-x")])
    assert len(g.nodes()) == 1
    g.apply([_delete("m2", "k2", "org-x")])  # 역이벤트
    assert g.nodes() == []  # revert


# --- quarantine review 워크플로 (05 §8.1) ------------------------------------

def test_review_state_transition_approve():
    """pending→in_review→approved → 승격(re-promote)."""
    rq = ReviewQueue()
    rq.enqueue("clm-1", original={"predicate": "announces"}, reason="low_confidence")
    assert rq.status("clm-1") == "pending"
    rq.assign("clm-1", "human:jane")
    assert rq.status("clm-1") == "in_review"
    rq.approve("clm-1", reviewer="human:jane")
    assert rq.status("clm-1") == "approved"


def test_review_reject():
    """rejected → 근거 남기고 폐기."""
    rq = ReviewQueue()
    rq.enqueue("clm-2", original={"predicate": "eats"}, reason="unk_predicate")
    rq.assign("clm-2", "human:jane")
    rq.reject("clm-2", reviewer="human:jane", reason="미등록 predicate — 폐기")
    assert rq.status("clm-2") == "rejected"


def test_review_escalate():
    """escalated → 온톨로지 proposal (05 §8.1)."""
    rq = ReviewQueue()
    rq.enqueue("clm-3", original={}, reason="unk_predicate")
    rq.assign("clm-3", "human:jane")
    rq.escalate("clm-3", reviewer="human:jane")
    assert rq.status("clm-3") == "escalated"


def test_human_review_as_data():
    """골든셋: 원출력·결정·이유·reviewer 저장 (05 §8.2, 불변식 §3-7)."""
    rq = ReviewQueue()
    rq.enqueue("clm-4", original={"predicate": "supplies"}, reason="ambiguous")
    rq.assign("clm-4", "human:jane")
    rq.reject("clm-4", reviewer="human:jane",
              reason="predicate는 supplies가 아니라 depends_on")
    rec = rq.history("clm-4")
    assert rec["human_decision"]["verdict"] == "rejected"
    assert rec["reason"]  # 이유 필수
    assert rec["reviewer"] == "human:jane"
    assert rec["original_model_output"] == {"predicate": "supplies"}


def test_approve_requires_reviewer():
    """approve/correct는 reviewer 필수 (05 §8.2)."""
    rq = ReviewQueue()
    rq.enqueue("clm-5", original={}, reason="low")
    with pytest.raises(ValueError):
        rq.approve("clm-5", reviewer="")
