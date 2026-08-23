"""P1 viewer — Citadel Gate (`/`) 데이터 계약.

`/api/gate` 응답이 존 카운트(raw/normalized/curated)·랭킹 top N·신호 분포를
포함하는지 검증 — Gate 대시보드 렌더링 데이터. read-only 결정적 (불변식 §3-3).
"""
from __future__ import annotations

import json
import types

import pytest
from pathlib import Path

from orc_citadel.curated_zone import CuratedZone
from orc_citadel.pipeline_runner import run_pipeline
from orc_citadel.viewer import Handler


class _SampleDir:
    """테스트용 인젝션 디렉터리 — raw 파일 트리 + normalized DuckDB."""

    def __init__(self, raw: Path, norm: str):
        self.raw = str(raw)
        self.norm = norm
        # raw 트리: <raw>/<source>/doc/<doc_id>/content.bin (+ fetch.json)
        self.raw_sources = [
            {"source_id": "src-a", "doc_count": 2},
            {"source_id": "src-b", "doc_count": 1},
        ]
        self.raw_docs = 3
        self.norm_docs = 1


@pytest.fixture
def sample_dirs(tmp_path):
    from orc_citadel.duckdb_zone import NormalizedZone
    from orc_citadel.parse import extract_html

    raw = tmp_path / "raw"
    for src, n in (("src-a", 2), ("src-b", 1)):
        for i in range(n):
            d = raw / src / "doc" / f"doc-{src}-{i}"
            d.mkdir(parents=True)
            (d / "content.bin").write_bytes(b"<h1>x</h1>")
            (d / "fetch.json").write_text('{"url": "https://e"}')
    # normalized DuckDB — 문서 1건 persist (norm_docs=1).
    norm_db = str(tmp_path / "oc.duckdb")
    z = NormalizedZone(norm_db)
    z.initialize()
    doc = extract_html(HTML, "https://e/n")
    z.persist("test", "https://e/n", HTML, doc)
    z.close()
    return _SampleDir(raw, norm_db)

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
                   "doc_id": "doc-gate00000000000000000001", "content": HTML}], z)
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


def _gate(self):
    return json.loads(Handler._api_gate(self, {}))


def test_gate_includes_zone_counts_and_ranking(sample_dirs):
    facade = _build_facade()
    self = types.SimpleNamespace(facade=facade, raw_dir=sample_dirs.raw,
                                 normalized_db=sample_dirs.norm)
    r = _gate(self)
    # curated 카운트 — 인메모리 facade 자료 (assertions ≥1).
    assert r["curated"]["assertions"] >= 1
    assert r["curated"]["entities"] >= 1
    # ranking top N — value 내림차순·비어 있지 않음.
    assert isinstance(r["ranking_top"], list) and r["ranking_top"]
    assert all({"subject_id", "rank", "value", "signal"} <= set(x) for x in r["ranking_top"])
    # 신호 분포 dict.
    assert isinstance(r["signal_distribution"], dict)


def test_gate_includes_raw_and_normalized_counts(sample_dirs):
    facade = _build_facade()
    self = types.SimpleNamespace(facade=facade, raw_dir=sample_dirs.raw,
                                 normalized_db=sample_dirs.norm)
    r = _gate(self)
    assert r["raw_doc_count"] == sample_dirs.raw_docs
    assert r["raw_sources"] == sample_dirs.raw_sources
    # normalized 문서 수 — 주입 db 의 documents 수와 일치.
    assert r["normalized_counts"]["documents"] == sample_dirs.norm_docs
