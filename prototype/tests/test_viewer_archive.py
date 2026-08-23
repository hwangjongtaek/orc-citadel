"""P1 viewer — Grand Archive (`/archive`) 데이터 계약.

`/api/archive` 응답이 normalized documents(+segments)·raw source 목록·dedup
cluster 수를 포함하는지 검증 — 문서 탐색 데이터. raw/normalized 형식 구분 표기
(04 §2.2 — 서로 다른 형식일 뿐 "중복" 아님). read-only 결정적 (불변식 §3-3).
"""
from __future__ import annotations

import json
import types

import pytest
from pathlib import Path

from orc_citadel.viewer import Handler

HTML = b"""<html><head>
<title>NVIDIA Conference Call</title>
<meta property="article:published_time" content="2026-08-01T14:00:00+00:00"/>
</head><body><article>
<h1>NVIDIA Sets Conference Call</h1>
<p>NVIDIA will host a conference call on Wednesday, August 26.</p>
<p>NVIDIA powers the data center and announces new accelerator products.</p>
</article></body></html>"""


class _Z:
    def clusters(self):
        return []  # dedup cluster 미발견 (정직 0)


@pytest.fixture
def archive_dirs(tmp_path):
    from orc_citadel.duckdb_zone import NormalizedZone
    from orc_citadel.parse import extract_html

    # normalized db — 문서 2건 persist (segment 포함).
    norm_db = str(tmp_path / "oc.duckdb")
    z = NormalizedZone(norm_db)
    z.initialize()
    html2 = HTML.replace(b"NVIDIA", b"AMD")
    doc1 = extract_html(HTML, "https://e/1")
    doc2 = extract_html(html2, "https://e/2")
    z.persist("official-nvidia", "https://e/1", HTML, doc1)
    z.persist("official-nvidia", "https://e/2", html2, doc2)
    z.close()

    # raw 존 — nvidia 2건·press 1건.
    raw = tmp_path / "raw"
    for src, n in (("official-nvidia", 2), ("press-semi", 1)):
        for i in range(n):
            d = raw / src / "doc" / f"doc-{src}-{i}"
            d.mkdir(parents=True)
            (d / "content.bin").write_bytes(b"<h1>x</h1>")
            (d / "fetch.json").write_text('{"url": "https://e"}')

    raw_str = str(raw)
    norm_str = str(norm_db)

    class _D:
        norm = norm_str
        raw = raw_str
        norm_docs = 2
        raw_sources = [
            {"source_id": "official-nvidia", "doc_count": 2},
            {"source_id": "press-semi", "doc_count": 1},
        ]
        raw_docs = 3
    return _D()


def _archive(self):
    return json.loads(Handler._api_archive(self, {}))


def test_archive_lists_normalized_documents(archive_dirs):
    self = types.SimpleNamespace(normalized_db=archive_dirs.norm,
                                 raw_dir=archive_dirs.raw,
                                 curated_clusters=0,
                                 facade=types.SimpleNamespace(zone=_Z()))
    r = _archive(self)
    assert len(r["normalized_documents"]) == archive_dirs.norm_docs
    assert r["normalized_counts"]["documents"] == archive_dirs.norm_docs
    # 각 문서에 segment 수 첨부 (목업 Codex 블록).
    assert all("segments" in d and isinstance(d["segments"], int) for d in r["normalized_documents"])
    # raw 전 영역 자격 (2026-08-23): publication_time 은 datetime → JSON str.
    assert all("publication_time" in d for d in r["normalized_documents"])


def test_archive_lists_raw_sources_and_clusters(archive_dirs):
    self = types.SimpleNamespace(normalized_db=archive_dirs.norm,
                                 raw_dir=archive_dirs.raw,
                                 curated_clusters=0,
                                 facade=types.SimpleNamespace(zone=_Z()))
    r = _archive(self)
    assert r["raw_doc_count"] == archive_dirs.raw_docs
    assert r["raw_sources"] == archive_dirs.raw_sources
    # dedup cluster 수 (정직 — 주입 0).
    assert r["dedup_clusters"] == 0
    # raw/normalized 형식 구분 주석 (중복 아님).
    assert "중복" in r["format_note"] or "형식" in r["format_note"]
