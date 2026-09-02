"""Viewer fidelity — page-4 보조 블록 (Gate·Watchtower·Archive·Chronicle·Spire).

각 페이지의 미구현 보조 블록 중 **실데이터로 정직하게 채울 수 있는** 것만 추가했는지:
- Gate: Campaign 카드(coverage·value·독립·predicate) + 공간 quick-enter
- Watchtower: source 상태 타일 + normalized publication_time 기반 실측 freshness
- Archive: modality/source facet + 문서 상세 패널 (클라이언트 실데이터)
- Chronicle: as-of 상태 카드 분해 + War Table 딥링크
- Spire: 트리거 필터 행 (정직 빈 카운트)
read-only 결정적 (불변식 §3-3).
"""
from __future__ import annotations

import json
import types

import pytest

from orc_citadel.curated_zone import CuratedZone
from orc_citadel.pipeline_runner import run_pipeline
from orc_citadel.viewer import Handler
from orc_citadel import viewer_pages as VP


@pytest.fixture
def norm_db(tmp_path):
    from orc_citadel.duckdb_zone import NormalizedZone
    from orc_citadel.parse import extract_html

    html = (b"<html><head><title>NVIDIA Call</title>"
            b"<meta property=\"article:published_time\" "
            b"content=\"2026-08-01T14:00:00+00:00\"/></head>"
            b"<body><article><h1>NVIDIA Call</h1>"
            b"<p>NVIDIA announces new accelerator products.</p>"
            b"</article></body></html>")
    path = str(tmp_path / "oc.duckdb")
    z = NormalizedZone(path)
    z.initialize()
    doc = extract_html(html, "https://e/n")
    z.persist("test", "https://e/n", html, doc)
    z.close()
    return path


@pytest.fixture
def raw_dir(tmp_path):
    raw = tmp_path / "raw"
    for src, n in (("official-nvidia", 2), ("press-tomshardware", 1)):
        for i in range(n):
            d = raw / src / "doc" / f"doc-{src}-{i}"
            d.mkdir(parents=True)
            (d / "content.bin").write_bytes(b"<h1>x</h1>")
            (d / "fetch.json").write_text('{"url": "https://e"}')
    return str(raw)


def _facade():
    from orc_citadel.api_facade import ApiFacade
    from orc_citadel.graph_service import GraphService

    z = CuratedZone(":memory:")
    z.initialize()
    run_pipeline([{"source_id": "test", "url": "https://e/n",
                   "doc_id": "doc-aux000000000000000000001",
                   "content": (b"<html><head><title>NVIDIA Call</title>"
                               b"<meta property=\"article:published_time\" "
                               b"content=\"2026-08-01T14:00:00+00:00\"/></head>"
                               b"<body><article><h1>NVIDIA Call</h1>"
                               b"<p>NVIDIA announces new accelerator products.</p>"
                               b"</article></body></html>")}], z)
    g = GraphService()
    return ApiFacade(z, g)


# --- Watchtower 실측 freshness --------------------------------------------------

def test_watchtower_includes_freshness_tile(norm_db, raw_dir):
    self = types.SimpleNamespace(facade=_facade(), raw_dir=raw_dir,
                                 normalized_db=norm_db)
    r = json.loads(Handler._api_watchtower(self, {}))
    assert "freshness" in r
    # normalized publication_time 실측 → measured=True, 아니면 정직 not-measured.
    fr = r["freshness"]
    assert "measured" in fr and isinstance(fr["measured"], bool)
    assert isinstance(r["sources"], list) and r["sources"]


# --- Gate: 캠페인 카드 재료 (coverage/predicates 실데이터) ----------------------

def test_gate_cards_material_exists():
    # Gate 가 카드 렌더 재료를 실측으로 제공하는지 = /api/table + /api/gate 병합.
    self = types.SimpleNamespace(facade=_facade())
    t = json.loads(Handler._api_table(self, {}))
    assert all({"coverage", "predicates", "value",
                "independent_source_count"} <= set(s) for s in t["subjects"])
    assert 'id="gate-spaces"' in VP.PAGE_GATE
    assert 'id="gate-cards"' in VP.PAGE_GATE


# --- Archive: facet + 상세 패널 -------------------------------------------------

def test_archive_has_facet_and_codex():
    assert 'id="archive-facets"' in VP.PAGE_ARCHIVE
    assert 'id="archive-codex"' in VP.PAGE_ARCHIVE


# --- Chronicle: as-of 상태 카드 + War Table 딥링크 ------------------------------

def test_chronicle_has_state_cards_and_deeplink():
    assert 'id="chron-state"' in VP.PAGE_CHRONICLE
    assert 'id="chron-deeplink"' in VP.PAGE_CHRONICLE


# --- Spire: 트리거 필터 행 (정직 빈 피드 유지) ----------------------------------

def test_spire_trigger_filter_rows():
    assert 'id="spire-triggers"' in VP.PAGE_SPIRE
    # honest-gap 유지: alerts=[] 정직 빈 피드는 계속 유효.
    self = types.SimpleNamespace(facade=_facade())
    r = json.loads(Handler._api_spire(self, {}))
    assert r["alerts"] == [] and len(r["trigger_catalog"]) == 5


# --- War Table: URL as-of 파라미터 부트스트랩 ----------------------------------

def test_table_url_asof_bootstrap():
    assert "URLSearchParams" in VP.PAGE_TABLE
    assert "as_of_valid" in VP.PAGE_TABLE or "valid_at" in VP.PAGE_TABLE



# --- 인라인 JS 문법 가드 (node --check) --------------------------------------
# 라이브 스모크에서 chronicle 스크립트의 `qs` 재선언(SyntaxError)이 패널을 통째로
# blank 시켰다. Python 테스트는 인라인 JS를 실행하지 못해 놓친다 — 각 페이지의
# <script> 블록을 node 로 parse 만 시켜 문법 회귀를 봉인한다.
import re
import shutil
import subprocess


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
@pytest.mark.parametrize("page", [
    VP.PAGE_GATE, VP.PAGE_TABLE, VP.PAGE_WATCHTOWER, VP.PAGE_SPIRE,
    VP.PAGE_ARCHIVE, VP.PAGE_CHRONICLE, VP.PAGE_WITNESSES, VP.PAGE_COUNCIL,
])
def test_page_inline_js_parses(page, tmp_path):
    scripts = re.findall(r"<script>(.*?)</script>", page, flags=re.S)
    assert scripts, "본문에 <script> 가 있어야 한다"
    for i, js in enumerate(scripts):
        f = tmp_path / f"page_{i}.js"
        f.write_text(js, encoding="utf-8")
        r = subprocess.run(["node", "--check", str(f)],
                           capture_output=True, text=True)
        assert r.returncode == 0, f"JS 문법 오류 (script {i}):\n{r.stderr}"
