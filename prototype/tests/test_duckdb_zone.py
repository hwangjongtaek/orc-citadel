"""TDD Red — DuckDB normalized zone (design 03 §3.1·§3.2).

NormalizedZone(DuckDB로 영속) 계약:
- documents/segments 스키마 생성 (ephemeral DB로 테스트, 영속 파일 없이)
- persist(doc) 후 documents()/segments(doc_id) 조회 가능
- idempotency: 동일 (doc_id, parser_version) 재persist → 중복 row 없음 (04 §3.3)
- UTF-8 다중 바이트 포함 문서에서도 char offset 정확 (ADR-302)
"""
import pytest

from orc_citadel.duckdb_zone import NormalizedZone
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


def test_parser_version_bump_reparses_not_duplicates(zone):
    """parser_version이 다른 새 실행은 새 row를 만들지만 동일 버전은 upsert (04 §3.3)."""
    doc = extract_html(HTML, "https://nvidianews.nvidia.com/news/x")
    url = "https://nvidianews.nvidia.com/news/x"
    zone.persist("src-official-nvidia-news", url, HTML, doc)  # p1
    # 같은 doc, 동일 버전 → 1 row 유지
    zone.persist("src-official-nvidia-news", url, HTML, doc)
    assert len(zone.documents()) == 1


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
