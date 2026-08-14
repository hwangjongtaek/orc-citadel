"""P1 트랙 a — viewer 조사 그래프(War Table) 렌더링 데이터.

`_api_investigate` 응답이 조사 subgraph(entities·relationships·relation_paths·
independence_summary)를 포함하는지 검증 — browser War Table 렌더링의 데이터 계약.
read-only 결정적 (불변식 §3-3).
"""
from __future__ import annotations

import json
import types

from orc_citadel.curated_zone import CuratedZone
from orc_citadel.pipeline_runner import run_pipeline
from orc_citadel.viewer import Handler

NVIDIA_HTML = b"""<html><head>
<title>NVIDIA Conference Call</title>
<meta property="article:published_time" content="2026-08-01T14:00:00+00:00"/>
</head><body><article>
<h1>NVIDIA Sets Conference Call</h1>
<p>NVIDIA will host a conference call on Wednesday, August 26.</p>
<p>NVIDIA powers the data center and announces new accelerator products.</p>
</article></body></html>"""


def _build_facade():
    from orc_citadel.viewer import _build

    # _build() 는 Module-level DB(실 data/duckdb)를 씀 — 여기선 인메모리 파이프라인으로 대체.
    z = CuratedZone(":memory:")
    z.initialize()
    run_pipeline([{"source_id": "test", "url": "https://e/n",
                   "doc_id": "doc-viewer00000000000000001", "content": NVIDIA_HTML}], z)
    from orc_citadel.api_facade import ApiFacade
    from orc_citadel.graph_service import GraphService

    g = GraphService()
    events = []
    for a in z.assertions():
        for seq, (node, uid) in enumerate(((a["subject_id"], f"n-{a['assertion_id']}"),
                                           (a["claim_id"], f"n2-{a['assertion_id']}"))):
            events.append({"mutation_id": uid, "idempotency_key": uid,
                           "op": "create_node", "payload": {"id": node, "props": {}}})
        events.append({"mutation_id": f"e-{a['assertion_id']}",
                       "idempotency_key": f"e-{a['assertion_id']}",
                       "op": "create_edge",
                       "payload": {"type": "ABOUT", "from": a["subject_id"],
                                   "to": a["claim_id"], "props": {}}})
    g.apply(events)
    return ApiFacade(z, g)


def test_investigate_response_includes_wargraph_subgraph():
    """_api_investigate 가 subgraph(War Table 데이터) 를 응답에 포함."""
    facade = _build_facade()
    subj = facade.zone.assertions()[0]["subject_id"]
    # Handler._api_investigate 는 self.facade 만 사용 — stub self 로 unbound 호출.
    self = types.SimpleNamespace(facade=facade)
    resp = json.loads(Handler._api_investigate(self, {"subject": subj}))
    assert resp["subject_id"] == subj
    # War Table — 조사 subgraph (entities·relationships) + relation_paths + independence
    sg = resp["subgraph"]
    assert "entities" in sg and "relationships" in sg
    assert any(e["id"] == subj for e in sg["entities"])
    assert any(rl["from"] == subj for rl in sg["relationships"])
    assert "relation_paths" in resp
    assert "independence_summary" in resp
    assert resp["audit"]["passed"] is True


def test_investigate_response_exposes_planned_subclaims():
    """_api_investigate 가 Planner(07 §3.2)의 subclaim 트리를 응답에 노출."""
    facade = _build_facade()
    subj = facade.zone.assertions()[0]["subject_id"]
    self = types.SimpleNamespace(facade=facade)
    resp = json.loads(Handler._api_investigate(self, {"subject": subj}))
    assert "planned_subclaims" in resp
    planned = resp["planned_subclaims"]
    assert isinstance(planned, list) and planned
    # known/gap 라벨 필수 (07 §3.2 불변식) — 그래프 지식이면 known.
    assert all("known" in p and "gap_reason" in p for p in planned)
    assert any(p["known"] for p in planned)


def test_investigate_response_exposes_retrieval():
    """_api_investigate 가 SEARCH 스테이지의 retrieved 후보를 응답에 노출 (07 §4)."""
    facade = _build_facade()
    subj = facade.zone.assertions()[0]["subject_id"]
    self = types.SimpleNamespace(facade=facade)
    resp = json.loads(Handler._api_investigate(self, {"subject": subj}))
    assert "retrieved" in resp
    assert isinstance(resp["retrieved"], list)
    # read-only — retrieved는 조회 산출물, 응답이 zone을 수정하지 않음.
    assert len(facade.zone.assertions()) >= 1
