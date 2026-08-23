"""P1 viewer — Chronicle Vault (`/chronicle`) 데이터 계약.

`/api/chronicle` 응답이 bitemporal assertions(초기: 현재 tx 또는 as-of 저격)·
supersedes 체인·graph-replay 정직 상태를 포함하는지 검증 — 시간 탐색 데이터.
read-only 결정적 (불변식 §3-3). graph_replay 는 postgres SoT 의존 — 미가동 시
available=False(§6.2 honest-gap) 로 표기.
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
                   "doc_id": "doc-chronicle0000000000000001", "content": HTML}], z)
    g = GraphService()
    for a in z.assertions():
        g.apply([{"mutation_id": f"n-{a['assertion_id']}",
                  "idempotency_key": f"n-{a['assertion_id']}",
                  "op": "create_node",
                  "payload": {"id": a["subject_id"], "props": {}}}])
    return ApiFacade(z, g)


def _chronicle(self):
    return json.loads(Handler._api_chronicle(self, {}))


def test_chronicle_lists_assertions_with_bitemporal_cols():
    facade = _build_facade()
    self = types.SimpleNamespace(facade=facade, postgres_available=False)
    r = _chronicle(self)
    assert r["assertions"]  # 현재 tx assertions 비어 있지 않음.
    a = r["assertions"][0]
    for key in ("assertion_id", "subject_id", "predicate", "valid_from",
                "valid_to", "tx_from", "tx_to", "supersedes_id"):
        assert key in a
    # supersedes 체인 — 정직 list (빈 가능).
    assert isinstance(r["supersedes_chain"], list)


def test_chronicle_replay_honest_not_measured():
    """postgres SoT 미가동 → graph-replay available=False (honest-gap)."""
    facade = _build_facade()
    self = types.SimpleNamespace(facade=facade, postgres_available=False)
    r = _chronicle(self)
    assert r["graph_replay"]["available"] is False
    assert "as_of" in r
