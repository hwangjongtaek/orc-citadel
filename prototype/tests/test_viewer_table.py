"""P1 viewer fidelity — War Table (`/table`) 데이터 계약.

`/api/table` seed + graph_node/expand(cursor) + provenance trail 이
목업 3+1 패널(Campaign Map · 캔버스 · Inspector · Chronicle) 렌더 재료를
제공하는지 검증. read-only 결정적 (불변식 §3-3). 조사 실행은 범위 밖.
"""
from __future__ import annotations

import json
import types

from orc_citadel.curated_zone import CuratedZone
from orc_citadel.pipeline_runner import run_pipeline
from orc_citadel.viewer import Handler

HTML = b"""<html><head>
<title>NVIDIA Conference Call</title>
<meta property="article:published_time" content="2026-08-01T14:00:00+00:00"/>
</head><body><article>
<h1>NVIDIA Sets Conference Call</h1>
<p>NVIDIA will host a conference call on Wednesday, August 26.</p>
<p>NVIDIA powers the data center and announces new accelerator products.</p>
</article></body></html>"""


def _build_facade():
    from orc_citadel.api_facade import ApiFacade
    from orc_citadel.graph_service import GraphService

    z = CuratedZone(":memory:")
    z.initialize()
    run_pipeline([{"source_id": "test", "url": "https://e/n",
                   "doc_id": "doc-table0000000000000000001", "content": HTML}], z)
    g = GraphService()
    events = []
    for a in z.assertions():
        for node, uid in ((a["subject_id"], f"n-{a['assertion_id']}"),
                          (a["claim_id"], f"n2-{a['assertion_id']}")):
            events.append({"mutation_id": uid, "idempotency_key": uid,
                           "op": "create_node", "payload": {"id": node, "props": {}}})
        events.append({"mutation_id": f"e-{a['assertion_id']}",
                       "idempotency_key": f"e-{a['assertion_id']}",
                       "op": "create_edge",
                       "payload": {"type": "ABOUT", "from": a["subject_id"],
                                   "to": a["claim_id"], "props": {}}})
    g.apply(events)
    return ApiFacade(z, g)


def _h(facade):
    return types.SimpleNamespace(facade=facade)


def test_table_seed_includes_subjects_and_entity_types():
    """`/api/table` 이 Campaign Map 재료(subjects·entity_types)와 정직 빈 노트를 노출."""
    r = json.loads(Handler._api_table(_h(_build_facade()), {}))
    assert r["subjects"], "ranking subjects 비면 안 됨"
    row = r["subjects"][0]
    assert {"subject_id", "rank", "signal", "value",
            "evidence_count", "independent_source_count", "coverage"} <= set(row)
    assert isinstance(r["entity_types"], list) and r["entity_types"]
    assert all({"label", "count"} <= set(t) for t in r["entity_types"])
    assert "contradicts" in r["notes"] and "seer" in r["notes"]


def test_graph_seed_includes_subgraph_for_subject():
    """`/api/graph?subject=` 가 investigation subgraph seed 를 반환."""
    facade = _build_facade()
    subj = facade.zone.assertions()[0]["subject_id"]
    r = json.loads(Handler._api_graph(_h(facade), {"subject": subj}))
    sg = r["subgraph"]
    assert any(e["id"] == subj for e in sg["entities"])
    assert any(rl["from"] == subj for rl in sg["relationships"])
    assert "independence_summary" in r


def test_graph_node_returns_node_or_not_found():
    """`/api/graph_node` — 존재 노드 상세, 미존재는 not_found."""
    facade = _build_facade()
    nid = facade.zone.assertions()[0]["subject_id"]
    r = json.loads(Handler._api_graph_node(_h(facade), {"id": nid}))
    assert r["id"] == nid
    missing = json.loads(Handler._api_graph_node(_h(facade), {"id": "missing"}))
    assert missing["error"] == "not_found"


def test_graph_expand_returns_cursor_envelope():
    """`/api/graph_expand` — 인접 + opaque cursor 봉투 (09 §1.4)."""
    facade = _build_facade()
    nid = facade.zone.assertions()[0]["subject_id"]
    r = json.loads(Handler._api_graph_expand(_h(facade), {"id": nid}))
    assert "items" in r and "page" in r
    assert "next_cursor" in r["page"]
    assert any(it["type"] == "ABOUT" for it in r["items"])


def test_provenance_trail_for_claim_evidence():
    """`/api/provenance` — claim→document trail (09 §2.3)."""
    facade = _build_facade()
    claim = facade.zone.assertions()[0]["claim_id"]
    items = facade.get_claim_evidence(claim)["items"]
    assert items, "파이프라인 claim 에 근거가 있어야 함"
    r = json.loads(Handler._api_provenance(
        _h(facade), {"evidence": items[0]["evidence_id"]}))
    steps = {s["step"] for s in r["trail"]}
    assert "claim" in steps and "document" in steps

