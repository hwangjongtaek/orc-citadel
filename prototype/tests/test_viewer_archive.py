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


# --- 페이지네이션·서버측 필터 (실측 10만+ 문서에서 /archive 가 멈추던 회귀) ------

@pytest.fixture
def many_docs(tmp_path):
    """normalized 존에 문서 12건 persist — 페이지 경계를 실측으로 넘긴다."""
    from orc_citadel.duckdb_zone import NormalizedZone
    from orc_citadel.parse import extract_html

    norm_db = str(tmp_path / "oc.duckdb")
    z = NormalizedZone(norm_db)
    z.initialize()
    for i in range(12):
        src = "official-nvidia" if i % 2 == 0 else "press-semi"
        # 문서마다 다른 발행 시각 — publication 정렬이 doc_id 정렬과 갈리게.
        html = (HTML.replace(b"NVIDIA Sets", b"NVIDIA Sets %d" % i)
                    .replace(b"2026-08-01T14:00:00", b"2026-08-%02dT14:00:00" % (i + 1)))
        z.persist(src, f"https://e/{i}", html, extract_html(html, f"https://e/{i}"))
    z.close()
    return norm_db


def _api(norm_db, qs, raw="none"):
    self = types.SimpleNamespace(normalized_db=norm_db, raw_dir=raw,
                                 curated_clusters=0,
                                 facade=types.SimpleNamespace(zone=_Z()))
    return json.loads(Handler._api_archive(self, qs))


def test_archive_pages_documents_and_reports_totals(many_docs):
    """응답은 한 페이지다 — limit/offset 이 SQL 로 내려가고 total 은 전체 실측."""
    r = _api(many_docs, {"limit": "5"})
    assert len(r["normalized_documents"]) == 5
    page = r["normalized_page"]
    assert (page["limit"], page["offset"], page["total"]) == (5, 0, 12)
    assert r["normalized_counts"]["documents"] == 12   # 존 전체는 그대로 노출

    second = _api(many_docs, {"limit": "5", "offset": "5"})
    assert second["normalized_page"]["offset"] == 5
    first_ids = [d["doc_id"] for d in r["normalized_documents"]]
    assert [d["doc_id"] for d in second["normalized_documents"]] != first_ids
    # doc_id 정렬은 결정적이라 페이지가 겹치거나 빠지지 않는다.
    tail = _api(many_docs, {"limit": "50"})["normalized_documents"]
    assert [d["doc_id"] for d in tail][:5] == first_ids


def test_archive_limit_is_clamped_not_unbounded(many_docs):
    """limit 은 상한(500)으로 클램프 — 전량 직렬화 경로를 다시 열지 않는다."""
    from orc_citadel.viewer import ARCHIVE_LIMIT_DEFAULT, ARCHIVE_LIMIT_MAX

    assert _api(many_docs, {"limit": "99999"})["normalized_page"]["limit"] == ARCHIVE_LIMIT_MAX
    assert _api(many_docs, {"limit": "x"})["normalized_page"]["limit"] == ARCHIVE_LIMIT_DEFAULT
    assert _api(many_docs, {"offset": "-3"})["normalized_page"]["offset"] == 0


def test_archive_filters_and_facets_are_server_side(many_docs):
    """facet·검색·doc_ids 는 SQL 축 — 카운트는 페이지 밖 문서까지 실측."""
    r = _api(many_docs, {"limit": "2"})
    assert r["facets"]["source_type"] == {"official": 6, "press": 6}

    only = _api(many_docs, {"limit": "50", "source_type": "press"})
    assert only["normalized_page"]["total"] == 6
    assert all(d["source_id"] == "press-semi" for d in only["normalized_documents"])
    # facet 선택은 facet 카운트를 좁히지 않는다 (해제용 chip 이 사라지면 안 됨).
    assert only["facets"]["source_type"] == {"official": 6, "press": 6}

    src = _api(many_docs, {"limit": "50", "source": "official-nvidia"})
    assert src["normalized_page"]["total"] == 6

    hit = _api(many_docs, {"limit": "50", "q": "e/7"})   # url ILIKE
    assert [d["url"] for d in hit["normalized_documents"]] == ["https://e/7"]
    assert hit["facets"]["source_type"] == {"press": 1}  # facet 은 검색 범위 실측

    ids = [d["doc_id"] for d in r["normalized_documents"]]
    picked = _api(many_docs, {"doc_ids": ",".join(ids)})
    assert [d["doc_id"] for d in picked["normalized_documents"]] == ids


def test_archive_sort_by_publication(many_docs):
    """sort=publication — publication_time 내림차순(NULL 후행), 미지원 값은 doc_id."""
    r = _api(many_docs, {"limit": "50", "sort": "publication"})
    pubs = [str(d["publication_time"] or "") for d in r["normalized_documents"]]
    assert pubs == sorted(pubs, reverse=True)
    assert len(set(pubs)) == 12                      # 동일 값 정렬로 통과하지 않게
    by_id = [d["doc_id"] for d in _api(many_docs, {"limit": "50"})["normalized_documents"]]
    assert [d["doc_id"] for d in r["normalized_documents"]] != by_id
    assert r["normalized_page"]["sort"] == "publication"
    assert _api(many_docs, {"sort": "bogus"})["normalized_page"]["sort"] == "doc_id"


def test_archive_role_filter_uses_cluster_map(tmp_path, many_docs):
    """role 은 curated dup_clusters 축 — doc_id 교집합으로 좁히고 전역 카운트를 낸다."""
    import duckdb

    root = duckdb.connect(many_docs, read_only=True).execute(
        "SELECT doc_id FROM documents ORDER BY doc_id LIMIT 1").fetchone()[0]

    class _ZR:
        def clusters(self):
            return [{"cluster_id": "c1", "root_doc_id": root,
                     "member_doc_ids": [root], "independent_addition_doc_ids": [],
                     "dedup_method": "minhash"}]

    self = types.SimpleNamespace(normalized_db=many_docs, raw_dir="none",
                                 facade=types.SimpleNamespace(zone=_ZR()))
    r = json.loads(Handler._api_archive(self, {"limit": "50", "role": "root"}))
    assert [d["doc_id"] for d in r["normalized_documents"]] == [root]
    assert r["facets"]["cluster_role"] == {"root": 1}
    # 일치 문서가 없는 role 은 정직 빈 (필터 무시하고 전량 반환 금지).
    none = json.loads(Handler._api_archive(self, {"limit": "50", "role": "derived"}))
    assert none["normalized_documents"] == [] and none["normalized_page"]["total"] == 0
