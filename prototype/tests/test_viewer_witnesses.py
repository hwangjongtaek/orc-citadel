"""Viewer fidelity — Hall of Witnesses (`/witnesses`) · Council Chamber (`/council`).

원문 왕복(§3-2): `/api/document` 가 normalized 세그먼트를 read-only 로 노출해
provenance trail 의 (segment_id, char_start, char_end) 를 원문 하이라이트로 되옮긴다.
Council 은 기존 조사 보고서(get_investigation_report) 조회만 — 조사 실행은 범위 밖.
"""
from __future__ import annotations

import json
import types

import pytest

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


@pytest.fixture
def norm_db(tmp_path):
    from orc_citadel.duckdb_zone import NormalizedZone
    from orc_citadel.parse import extract_html

    path = str(tmp_path / "oc.duckdb")
    z = NormalizedZone(path)
    z.initialize()
    doc = extract_html(HTML, "https://e/n")
    z.persist("test", "https://e/n", HTML, doc)
    z.close()
    return path


def _facade():
    from orc_citadel.api_facade import ApiFacade
    from orc_citadel.graph_service import GraphService

    z = CuratedZone(":memory:")
    z.initialize()
    run_pipeline([{"source_id": "test", "url": "https://e/n",
                   "doc_id": "doc-wit000000000000000000001", "content": HTML}], z)
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


def test_document_endpoint_returns_segments(norm_db):
    """`/api/document` — doc_id 의 segments 를 read-only 노출 (원문 왕복)."""
    doc_id = "doc-wit000000000000000000001"
    self = types.SimpleNamespace(facade=_facade(), normalized_db=norm_db)
    # 파이프라인 doc_id 는 content hash base — 실제 id 를 zone 에서 취한다.
    claims = self.facade.zone.claims()
    doc_id = claims[0]["doc_id"] if claims and "doc_id" in claims[0] else doc_id
    # normalized 존에는 test HTML 의 sha256 doc_id 로 persist 됨 — documents() 로 확인.
    from orc_citadel.duckdb_zone import NormalizedZone
    nz = NormalizedZone(norm_db)
    real = nz.documents()[0]["doc_id"]
    nz.close()
    self = types.SimpleNamespace(facade=_facade(), normalized_db=norm_db)
    r = json.loads(Handler._api_document(self, {"doc": real}))
    assert r["doc_id"] == real
    assert r["segments"] and all({"segment_id", "ord", "kind", "text",
                                  "char_start", "char_end"} <= set(s)
                                  for s in r["segments"])


def test_document_endpoint_honest_empty(norm_db):
    """미존재/미가동 DB 는 정직 빈 segments."""
    self = types.SimpleNamespace(facade=_facade(), normalized_db=norm_db)
    r = json.loads(Handler._api_document(self, {"doc": "doc-does-not-exist"}))
    assert r["segments"] == [] or r.get("available") is False


def test_council_report_read_only():
    """`/api/council?subject=` — 기존 조사 보고서(결론·predicate·open_questions·signal)."""
    facade = _facade()
    subj = facade.zone.assertions()[0]["subject_id"]
    self = types.SimpleNamespace(facade=facade)
    r = json.loads(Handler._api_council(self, {"subject": subj}))
    assert r["subject_id"] == subj
    assert "confidence" in r and "by_predicate" in r
    assert "open_questions" in r and "signal" in r
    assert r["execution"]["available"] is False  # 조사 실행은 쓰기 → 범위 밖 정직

