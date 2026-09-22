"""Normalized Iceberg zone contract (design 03 §3.1·§3.2).

NormalizedZone persists documents/segments with content-derived identity:
- persist(doc) then documents()/segments(doc_id) round-trips
- same (doc_id, parser_version) is idempotent
- a parser-version bump retains both versioned outputs
- UTF-8 offsets remain character-based
"""
from dataclasses import replace
import pytest

from orc_citadel.iceberg_zone import NormalizedZone
from orc_citadel.parse import extract_html, parse_document
from orc_citadel.identity import doc_id_for

# 실제 NVIDIA 보도자료 형태 + UTF-8 스마트인용부호(다중 바이트) 포함
HTML = b"""<html><head>
<title>NVIDIA Sets Conference Call | NVIDIA Newsroom</title>
</head><body><div class="article-body">
<p>NVIDIA said \xe2\x80\x9cchip demand rose.\xe2\x80\x9d The datacenter segment grew sharply and HBM sales doubled.</p>
<p>Results cover fiscal year 2027, which ended July 26, 2026.</p>
</div></body></html>"""


@pytest.fixture()
def zone():
    z = NormalizedZone(":memory:")
    z.initialize()
    yield z
    z.close()


def test_zone_creates_schema(zone):
    tables = zone.tables()
    assert "documents" in tables
    assert "segments" in tables


def test_persist_and_query_documents(zone):
    doc = extract_html(HTML, "https://nvidianews.nvidia.com/news/x")
    source_id, url = "src-official-nvidia-news", "https://nvidianews.nvidia.com/news/x"
    # doc_id는 원문 raw HTML 기반 (설계 03 §2.1, provenance anchor)
    zone.persist(source_id, url, HTML, doc)

    rows = zone.documents()
    assert len(rows) == 1
    d = rows[0]
    assert d["source_id"] == source_id
    assert d["url"] == url
    assert "Conference Call" in d["title"]
    assert d["parser_version"] == doc.parser_version
    # char_len: clean text 문자의 수 (UTF-8 다중 바이트여도 chars)
    assert d["char_len"] == len(doc.text)
    # doc_id는 원문 내용 기반 (sha256[HTML]) — raw zone과 연결
    assert d["doc_id"] == doc_id_for(HTML)


def test_persist_segments_query(zone):
    doc = extract_html(HTML, "https://nvidianews.nvidia.com/news/x")
    source_id = "src-official-nvidia-news"
    url = "https://nvidianews.nvidia.com/news/x"
    zone.persist(source_id, url, HTML, doc)

    doc_rows = zone.documents()
    doc_id = doc_rows[0]["doc_id"]
    segs = zone.segments(doc_id)
    assert len(segs) >= 2
    for s in segs:
        # char offset으로 text slice → 재현 (ADR-302, UTF-8에서 chars 기준)
        assert doc.text[s["char_start"]:s["char_end"]] == s["text"]


def test_persist_is_idempotent(zone):
    """동일 (doc_id, parser_version) 재persist → documents/segments 중복 없음 (04 §3.3)."""
    doc = extract_html(HTML, "https://nvidianews.nvidia.com/news/x")
    url = "https://nvidianews.nvidia.com/news/x"
    zone.persist("src-official-nvidia-news", url, HTML, doc)
    zone.persist("src-official-nvidia-news", url, HTML, doc)

    assert len(zone.documents()) == 1
    doc_id = zone.documents()[0]["doc_id"]
    # segments도 중복 없이 (doc_id 같은 segment_id)
    assert len(zone.segments(doc_id)) == len({s["segment_id"] for s in zone.segments(doc_id)})
    # 재persist 후에도 문서 row는 1개
    assert len(zone.documents()) == 1


def test_same_version_repersist_replaces_old_segments(zone):
    """같은 version 재파싱에서 사라진 segment가 Iceberg에 잔존하면 안 된다."""
    doc = extract_html(HTML, "https://nvidianews.nvidia.com/news/x")
    shorter = replace(doc, text="Only one sentence remains.")
    url = "https://nvidianews.nvidia.com/news/x"
    zone.persist("src-official-nvidia-news", url, HTML, doc)
    assert len(zone.segments(doc_id_for(HTML))) > 1

    zone.persist("src-official-nvidia-news", url, HTML, shorter)

    segments = zone.segments(doc_id_for(HTML))
    assert [segment["text"] for segment in segments] == ["Only one sentence remains."]


def test_parser_version_bump_retains_each_version(zone):
    """같은 raw의 parser-version별 산출물은 공존하고 동일 버전만 upsert한다."""
    doc_v1 = extract_html(HTML, "https://nvidianews.nvidia.com/news/x")
    doc_v2 = replace(doc_v1, parser_version="p2")
    url = "https://nvidianews.nvidia.com/news/x"
    zone.persist("src-official-nvidia-news", url, HTML, doc_v1)
    zone.persist("src-official-nvidia-news", url, HTML, doc_v2)
    zone.persist("src-official-nvidia-news", url, HTML, doc_v2)

    rows = zone.documents()
    assert {(row["doc_id"], row["parser_version"]) for row in rows} == {
        (doc_id_for(HTML), doc_v1.parser_version),
        (doc_id_for(HTML), "p2"),
    }
    assert {row["parser_version"] for row in zone.segments(doc_id_for(HTML))} == {
        doc_v1.parser_version,
        "p2",
    }


def test_doc_id_is_content_deterministic_across_persist(zone):
    """내용 기반 doc_id — 동일 raw HTML은 동일 doc_id (불변식 §3-6)."""
    doc = extract_html(HTML, "https://nvidianews.nvidia.com/news/x")
    zone.persist("src-official-nvidia-news", "https://nvidianews.nvidia.com/news/x", HTML, doc)
    doc_id = zone.documents()[0]["doc_id"]
    assert doc_id == doc_id_for(HTML)


def test_export_parquet(tmp_path, zone):
    """documents/segments를 Parquet으로 내보내기 (05 이후 조회·그래프 입력용)."""
    doc = extract_html(HTML, "https://nvidianews.nvidia.com/news/x")
    zone.persist("src-official-nvidia-news", "https://nvidianews.nvidia.com/news/x", HTML, doc)
    zone.export_parquet(str(tmp_path))
    assert (tmp_path / "documents.parquet").exists()
    assert (tmp_path / "segments.parquet").exists()
    # 몇 줄 읽어 재현 (Parquet가 실제 대조)
    import duckdb
    n = duckdb.connect().execute(f"SELECT count(*) FROM '{tmp_path / 'segments.parquet'}'").fetchone()[0]
    assert n == len(zone.segments(zone.documents()[0]["doc_id"]))
