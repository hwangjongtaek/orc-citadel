"""S32 조사/근거/그래프 API 파사드 (설계 09 §2·§3) TDD.

read-only 프로젝션 4종(S28-S31)을 09 §2 조사 중심 **엔드포인트 wire 계약**으로 노출하는
**API 파사드** — 순수 핸들러 `(zone, graph, **params) -> dict`가 09 §2·§3 응답 JSON
스키마를 그대로 생성한다. FastAPI 서버 없이 결정적·TDD로 검증 (신규 의존 금지).

- get_claim            : GET /v1/claims/{id} — claim 상세 + 09 §4 confidence 봉투 (S29).
- get_claim_evidence   : GET /v1/claims/{id}/evidence — 지지/반박 근거 + cursor (09 §2.3).
- get_evidence_provenance: GET /v1/evidence/{id}/provenance — Trail 객체 (09 §2.3).
- get_investigation_report: GET /v1/investigations/{id}/report — 09 §3 결론 봉투 + open_questions (S30).
- get_graph_node / get_graph_expand: 노드·인접 확장 cursor (09 §2.2, S28).

**read-only** (불변식 §3-3) — 조회 전용, 쓰기·영속·그래프 mutation 미노출, 상태 불변.

Atomic TDD: Red → Green → Refactor.
"""
from __future__ import annotations

import pytest

from orc_citadel.api_facade import ApiFacade
from orc_citadel.curated_zone import CuratedZone


def _populate_zone() -> CuratedZone:
    z = CuratedZone(":memory:")
    z.initialize()
    return z


def _seed_claims(z: CuratedZone, claims: list[dict]) -> None:
    """claims: {cid, subj, pred, obj, doc} → claim + mention + assertion."""
    from orc_citadel.assertions import materialize
    from orc_citadel.extract import Mention
    from orc_citadel.extract_claims import ClaimCandidate
    from datetime import datetime, timezone

    for i, c in enumerate(claims):
        cc = ClaimCandidate(
            claim_candidate_id=c["cid"], doc_id=c["doc"], predicate=c["pred"],
            subject_id=c["subj"], object_id=c.get("obj"), object_literal=None,
            modality="asserted", polarity="positive", confidence=0.8,
            seg_order=i, char_start=0, char_end=4, surface_fragment="x",
            event_type_hint=None, status="promoted",
        )
        z.persist_claim(cc)
        m = Mention(
            mention_id=f"men-{c['cid']}", doc_id=c["doc"], segment_id=f"{c['doc']}#s0",
            surface_text=c["subj"], mention_type="ORG",
            char_start=0, char_end=4, context_window=None,
        )
        z.persist_mention(m)
        z.set_mention_authoritative(m.mention_id)
        a = materialize(cc, observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                        mutation=f"mut-{c['cid']}")
        z.persist_assertion(a)


def _make_graph():
    from orc_citadel.graph_service import GraphService as GS

    g = GS()
    g.apply([
        {"mutation_id": "m1", "idempotency_key": "k1", "op": "create_node",
         "payload": {"id": "clm-a", "props": {}, "labels": []}},
        {"mutation_id": "m2", "idempotency_key": "k2", "op": "create_node",
         "payload": {"id": "clm-b", "props": {}, "labels": []}},
        {"mutation_id": "m3", "idempotency_key": "k3", "op": "create_node",
         "payload": {"id": "org-a", "props": {}, "labels": []}},
        {"mutation_id": "m4", "idempotency_key": "k4", "op": "create_edge",
         "payload": {"type": "ABOUT", "from": "org-a", "to": "clm-a", "props": {}}},
    ])
    return g


# --- get_claim -------------------------------------------------------------

def test_get_claim_detail_and_confidence():
    """claim 상세 + 09 §4 confidence 봉투 (S29)."""
    z = _populate_zone()
    _seed_claims(z, [
        {"cid": "clm-a", "doc": "d1", "subj": "org-a", "pred": "announces", "obj": "org-b"},
        {"cid": "clm-b", "doc": "d2", "subj": "org-a", "pred": "announces", "obj": "org-b"},
    ])
    f = ApiFacade(z, _make_graph())
    claim = f.get_claim("clm-a")
    assert claim is not None
    assert claim["claim_id"] == "clm-a"
    assert claim["subject_id"] == "org-a"
    assert claim["predicate"] == "announces"
    for k in ("value", "evidence_count", "independent_source_count", "basis", "dimensions"):
        assert k in claim["confidence"], f"봉투 필드 부재: {k}"
    # clm-a의 주장은 2문서 지지 → evidence_count 2.
    assert claim["confidence"]["evidence_count"] == 2


def test_get_claim_missing():
    """미존재 claim → None."""
    z = _populate_zone()
    f = ApiFacade(z, _make_graph())
    assert f.get_claim("clm-zzz") is None


# --- get_claim_evidence ----------------------------------------------------

def test_get_claim_evidence_support():
    """지지 근거 + cursor 페이지 (09 §2.3)."""
    z = _populate_zone()
    _seed_claims(z, [
        {"cid": "clm-a", "doc": "d1", "subj": "org-a", "pred": "announces", "obj": "org-b"},
        {"cid": "clm-b", "doc": "d2", "subj": "org-a", "pred": "announces", "obj": "org-b"},
    ])
    f = ApiFacade(z, _make_graph())
    res = f.get_claim_evidence("clm-a")
    assert "items" in res and "page" in res
    assert res["page"]["limit"] == 30
    # 지지 근거 2건 (2 문서).
    assert len(res["items"]) == 2
    assert all(it["relation"] == "supports" for it in res["items"])
    for k in ("evidence_id", "relation", "strength", "source_doc"):
        assert k in res["items"][0]


def test_get_claim_evidence_cursor_pagination():
    """근거 cursor 페이지네이션 — limit, next_cursor."""
    z = _populate_zone()
    _seed_claims(z, [
        {"cid": "clm-a", "doc": "d1", "subj": "org-a", "pred": "announces", "obj": "org-b"},
        {"cid": "clm-b", "doc": "d2", "subj": "org-a", "pred": "announces", "obj": "org-b"},
    ])
    f = ApiFacade(z, _make_graph())
    page1 = f.get_claim_evidence("clm-a", limit=1)
    assert len(page1["items"]) == 1
    assert page1["page"]["next_cursor"] is not None
    page2 = f.get_claim_evidence("clm-a", limit=1, cursor=page1["page"]["next_cursor"])
    assert len(page2["items"]) == 1
    assert page2["page"]["next_cursor"] is None  # 마지막.


def test_get_claim_evidence_no_evidence():
    """근거 없는 claim → empty items, next_cursor null."""
    z = _populate_zone()
    # clm-a만 (1 문서) — 근거 1.
    _seed_claims(z, [
        {"cid": "clm-a", "doc": "d1", "subj": "org-a", "pred": "announces", "obj": "org-b"},
    ])
    f = ApiFacade(z, _make_graph())
    res = f.get_claim_evidence("clm-a")
    assert len(res["items"]) <= 1
    if res["items"]:
        assert res["page"]["next_cursor"] is None


# --- get_evidence_provenance -----------------------------------------------

def test_get_evidence_provenance_trail():
    """Trail 객체 (09 §2.3): evidence→claim→doc step."""
    z = _populate_zone()
    _seed_claims(z, [
        {"cid": "clm-a", "doc": "d1", "subj": "org-a", "pred": "announces", "obj": "org-b"},
        {"cid": "clm-b", "doc": "d2", "subj": "org-a", "pred": "announces", "obj": "org-b"},
    ])
    f = ApiFacade(z, _make_graph())
    # clm-a의 근거 1건의 evidence_id 가져옴.
    items = f.get_claim_evidence("clm-a")["items"]
    evid = items[0]["evidence_id"]
    trail = f.get_evidence_provenance(evid)
    assert trail is not None
    assert trail["evidence_id"] == evid
    assert "trail" in trail
    steps = {s["step"] for s in trail["trail"]}
    assert "claim" in steps
    assert "document" in steps


# --- get_investigation_report ----------------------------------------------

def test_get_investigation_report():
    """09 §3 결론 봉투 + by_predicate + open_questions (S30)."""
    z = _populate_zone()
    _seed_claims(z, [
        {"cid": "clm-a", "doc": "d1", "subj": "org-a", "pred": "announces", "obj": "org-b"},
        {"cid": "clm-b", "doc": "d2", "subj": "org-a", "pred": "announces", "obj": "org-b"},
    ])
    f = ApiFacade(z, _make_graph())
    report = f.get_investigation_report("org-a")
    assert report is not None
    assert report["subject_id"] == "org-a"
    assert "confidence" in report
    assert "by_predicate" in report
    assert "open_questions" in report
    assert report["by_predicate"]["announces"]["count"] == 2


def test_get_investigation_report_missing():
    """미존재 subject → None."""
    z = _populate_zone()
    f = ApiFacade(z, _make_graph())
    assert f.get_investigation_report("org-zzz") is None


# --- get_graph_node / get_graph_expand --------------------------------------

def test_get_graph_node():
    """노드 상세 (09 §2.2, S28)."""
    g = _make_graph()
    f = ApiFacade(_populate_zone(), g)
    node = f.get_graph_node("clm-a")
    assert node is not None and node["id"] == "clm-a"
    assert f.get_graph_node("missing") is None


def test_get_graph_expand():
    """인접 확장 cursor (09 §2.2 progressive disclosure)."""
    g = _make_graph()
    f = ApiFacade(_populate_zone(), g)
    res = f.get_graph_expand("org-a")
    assert "items" in res and "page" in res
    assert any(it["id"] == "clm-a" and it["type"] == "ABOUT" for it in res["items"])
    if res["items"]:
        assert res["page"]["next_cursor"] is None  # 인접 1건.


# --- read-only (불변식 §3-3) ------------------------------------------------

def test_read_only_no_mutation():
    """파사드는 read-only — 쓰기·영속·그래프 mutation 미노출, 상태 불변."""
    z = _populate_zone()
    _seed_claims(z, [
        {"cid": "clm-a", "doc": "d1", "subj": "org-a", "pred": "announces", "obj": "org-b"},
    ])
    g = _make_graph()
    f = ApiFacade(z, g)
    for bad in ("apply", "persist", "create_node", "create_edge", "insert", "delete"):
        assert not hasattr(f, bad), f"read-only 위반: {bad} 노출"
