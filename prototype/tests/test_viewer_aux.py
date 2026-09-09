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


# --- Spire: 정직 빈 피드 유지 ---------------------------------------------------

def test_spire_honest_empty_feed():
    # honest-gap 유지: alerts=[] 정직 빈 피드는 계속 유효.
    self = types.SimpleNamespace(facade=_facade())
    r = json.loads(Handler._api_spire(self, {}))
    assert r["alerts"] == [] and len(r["trigger_catalog"]) == 5





# --- Wave 1 remaining-gaps: backend API 스키마 스모크 --------------------------
# 계약: local://gaps-contract.md Wave 1 — /api/search·/api/claim 신규,
# table·graph·archive·chronicle·watchtower·investigate 확장. wire 키만 봉인.

RICH_HTML = b"""<html><head>
<title>NVIDIA Conference Call</title>
<meta property="article:published_time" content="2026-08-01T14:00:00+00:00"/>
</head><body><article>
<h1>NVIDIA Sets Conference Call</h1>
<p>NVIDIA will host a conference call on Wednesday, August 26.</p>
<p>NVIDIA powers the data center and announces new accelerator products.</p>
</article></body></html>"""


def _rich_facade(doc_id="doc-auxw1-00000000000000000001"):
    """claims·entities·assertions·ABOUT 그래프가 실측으로 채워진 파사드 (table 패턴)."""
    from orc_citadel.api_facade import ApiFacade
    from orc_citadel.graph_service import GraphService

    z = CuratedZone(":memory:")
    z.initialize()
    run_pipeline([{"source_id": "test", "url": "https://e/n",
                   "doc_id": doc_id, "content": RICH_HTML}], z)
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


@pytest.fixture
def rich_raw(tmp_path):
    """fetch.json 에 fetched_at·http_status·robots_allowed 실측이 들어간 raw 트리."""
    raw = tmp_path / "raw"
    for src, n in (("official-nvidia", 2), ("press-tomshardware", 1)):
        for i in range(n):
            d = raw / src / "doc" / f"doc-{src}-{i}"
            d.mkdir(parents=True)
            (d / "content.bin").write_bytes(b"<h1>x</h1>")
            (d / "fetch.json").write_text(json.dumps({
                "url": "https://e", "doc_id": f"doc-{src}-{i}",
                "fetched_at": "2026-08-18T13:02:51.952687+00:00",
                "http_status": 200, "robots_allowed": True}))
    return str(raw)


def test_search_returns_entities_claims_documents_with_counts():
    """`/api/search?q=` — 3개 존 substring/ILIKE 검색, 각 ≤10 + counts 봉투."""
    facade = _rich_facade()
    self = types.SimpleNamespace(facade=facade)
    r = json.loads(Handler._api_search(self, {"q": "nvidia"}))
    assert r["query"] == "nvidia"
    assert {"entities", "claims", "documents", "counts"} <= set(r)
    assert all(len(r[k]) <= 10 for k in ("entities", "claims", "documents"))
    assert r["entities"] and all({"entity_id", "name", "mention_type"} <= set(e)
                                  for e in r["entities"])
    assert r["counts"]["entities"] >= len(r["entities"])
    # 빈 쿼리는 정직 빈 봉투.
    empty = json.loads(Handler._api_search(self, {"q": ""}))
    assert empty["entities"] == [] and empty["counts"]["entities"] == 0


def test_search_claims_hit_predicate():
    """claims 검색은 facade._claims_rows substring — predicate 'announces' 실측ヒット."""
    facade = _rich_facade()
    self = types.SimpleNamespace(facade=facade)
    r = json.loads(Handler._api_search(self, {"q": "announce"}))
    assert r["claims"], "predicate 일치 claim 있어야 함"
    assert all({"claim_id", "predicate", "object_literal", "subject_id"} <= set(c)
               for c in r["claims"])


def test_search_documents_via_normalized_ilike(tmp_path):
    """documents 는 normalized DuckDB read_only ILIKE — 미가동 DB 는 정직 빈."""
    self = types.SimpleNamespace(facade=_rich_facade(),
                                 normalized_db=str(tmp_path / "missing.duckdb"))
    r = json.loads(Handler._api_search(self, {"q": "nvidia"}))
    assert r["documents"] == []
    from orc_citadel.duckdb_zone import NormalizedZone
    from orc_citadel.parse import extract_html
    path = str(tmp_path / "oc.duckdb")
    z = NormalizedZone(path)
    z.initialize()
    z.persist("test", "https://e/n", RICH_HTML, extract_html(RICH_HTML, "https://e/n"))
    z.close()
    self2 = types.SimpleNamespace(facade=_rich_facade(), normalized_db=path)
    r2 = json.loads(Handler._api_search(self2, {"q": "Conference"}))
    assert r2["documents"] and {"doc_id", "title", "source_id"} <= set(r2["documents"][0])


def test_claim_merges_facade_and_zone_row():
    """`/api/claim?claim=` — get_claim + zone 행 병합 키, 미존재는 not_found."""
    facade = _rich_facade()
    self = types.SimpleNamespace(facade=facade)
    cid = sorted(facade._claims_rows)[0]
    r = json.loads(Handler._api_claim(self, {"claim": cid}))
    assert r["claim_id"] == cid
    for key in ("surface_fragment", "predicate", "object_literal",
                "modality", "doc_id", "subject_id", "confidence"):
        assert key in r, f"claim 병합 키 누락: {key}"
    missing = json.loads(Handler._api_claim(self, {"claim": "clm-missing"}))
    assert missing["error"] == "not_found"


def test_table_extends_entities_and_quarantined():
    """`/api/table` 확장 — entities[≤200]{entity_id,name,mention_type}·quarantined count."""
    facade = _rich_facade()
    # 게이트 결과를 하나 격리로 전이 → status 실측 count 반영.
    cid = sorted(facade._claims_rows)[0]
    facade.zone.update_claim_status(cid, "quarantined", "test_quarantine")
    self = types.SimpleNamespace(facade=facade)
    r = json.loads(Handler._api_table(self, {}))
    assert r["entities"], "entities 실측 비면 안 됨"
    assert all({"entity_id", "name", "mention_type"} <= set(e) for e in r["entities"])
    assert len(r["entities"]) <= 200
    assert r["quarantined"] == 1
    assert "notes" in r and "subjects" in r  # 기존 필드 유지


def test_graph_nodes_carry_labels():
    """`/api/graph` 확장 — subgraph.nodes[].label: entity=canonical_name·claim=predicate."""
    facade = _rich_facade()
    subj = facade.zone.assertions()[0]["subject_id"]
    self = types.SimpleNamespace(facade=facade)
    r = json.loads(Handler._api_graph(self, {"subject": subj}))
    nodes = r["subgraph"]["nodes"]
    assert nodes, "서브그래프 nodes 비면 안 됨"
    by_id = {n["id"]: n["label"] for n in nodes}
    assert by_id[subj] == "NVIDIA"  # entity label = table.entities와 동일 canonical_name
    claim_nodes = [n for n in nodes if n["id"].startswith("clm-")]
    assert claim_nodes and all(n["label"] == "announces" for n in claim_nodes)


def test_archive_extends_roles_and_facets(tmp_path):
    """`/api/archive` 확장 — cluster_role·segment_kinds·url_groups 실측."""
    from orc_citadel.duckdb_zone import NormalizedZone
    from orc_citadel.parse import extract_html

    path = str(tmp_path / "oc.duckdb")
    z = NormalizedZone(path)
    z.initialize()
    z.persist("test", "https://e/n", RICH_HTML, extract_html(RICH_HTML, "https://e/n"))
    z.persist("test", "https://e/n", RICH_HTML + b"<!--v-->",
              extract_html(RICH_HTML + b"<!--v-->", "https://e/n"))  # 동일 URL 2번째
    z.close()
    # 계보: 첫 문서를 root 로 갖는 클러스터 → normalized 문서에 역할 매핑.
    import duckdb
    root_doc = duckdb.connect(path, read_only=True).execute(
        "SELECT doc_id FROM documents ORDER BY doc_id LIMIT 1").fetchone()[0]
    facade = _rich_facade()
    facade.zone.persist_cluster("clus-test-role", root_doc, [root_doc], [], "minhash")
    self = types.SimpleNamespace(facade=facade, normalized_db=path,
                                 raw_dir=str(tmp_path / "none"))
    r = json.loads(Handler._api_archive(self, {}))
    docs = r["normalized_documents"]
    assert all({"cluster_role", "language", "publication_time", "revision_time",
                "parser_version"} <= set(d) for d in docs)
    roles = {d["doc_id"]: d["cluster_role"] for d in docs}
    assert roles[root_doc] == "root"
    assert r["segment_kinds"], "segments GROUP BY 실측"
    assert sum(r["segment_kinds"].values()) > 0
    groups = r["url_groups"]
    assert len(groups) == 1 and groups[0]["url"] == "https://e/n"
    assert groups[0]["count"] == 2 and len(groups[0]["doc_ids"]) <= 5
    # 기존 필드 유지
    assert "normalized_counts" in r and "format_note" in r


def test_chronicle_extends_bounds_and_events():
    """`/api/chronicle` 확장 — bounds(valid/tx min·max)·events(asserted 타임라인)."""
    facade = _rich_facade()
    self = types.SimpleNamespace(facade=facade, postgres_available=False)
    r = json.loads(Handler._api_chronicle(self, {}))
    b = r["bounds"]
    assert {"valid_min", "valid_max", "tx_min", "tx_max"} <= set(b)
    assert b["tx_min"] is not None and b["tx_max"] is not None
    events = r["events"]
    assert events, "assertion 으로부터 이벤트 1건 이상"
    assert all({"assertion_id", "claim_id", "predicate", "kind", "at"} <= set(e)
               for e in events)
    assert {e["kind"] for e in events} <= {"asserted", "closed", "superseded"}
    assert any(e["kind"] == "asserted" for e in events)
    # 기존 필드 유지
    assert r["assertions"] and "supersedes_chain" in r and "as_of" in r


def test_watchtower_intake_last_fetch_governance(rich_raw):
    """`/api/watchtower` 확장 — intake(fetch.json 실측)·last_fetch·governance 표본."""
    Handler._FETCH_CACHE.clear()
    facade = _rich_facade()
    self = types.SimpleNamespace(facade=facade, raw_dir=rich_raw,
                                 normalized_db="")
    r = json.loads(Handler._api_watchtower(self, {}))
    it = r["intake"]
    assert it["measured"] is True and it["window_hours"] == 24
    assert len(it["arrivals_per_hour"]) == 24
    assert sum(b["count"] for b in it["arrivals_per_hour"]) == 3
    assert {s["source_id"] for s in it["last_fetch_by_source"]} == \
        {"official-nvidia", "press-tomshardware"}
    srcs = {s["source_id"]: s for s in r["sources"]}
    assert srcs["official-nvidia"]["last_fetch"] == "2026-08-18T13:02:51.952687+00:00"
    assert srcs["official-nvidia"]["governance"] == \
        {"http_status": 200, "robots_allowed": True}
    # 클래스 레벨 캐시: 경로별 1회 스캔 (resolve 된 절대경로 키).
    assert any(p.endswith("/raw") for p in Handler._FETCH_CACHE)
    r2 = json.loads(Handler._api_watchtower(self, {}))
    assert r2["intake"] == it


def test_watchtower_intake_honest_without_fetched_at(raw_dir):
    """fetch.json 에 fetched_at 없음 → intake measured=False 정직 (honest-gap)."""
    Handler._FETCH_CACHE.clear()
    facade = _rich_facade()
    self = types.SimpleNamespace(facade=facade, raw_dir=raw_dir,
                                 normalized_db="")
    r = json.loads(Handler._api_watchtower(self, {}))
    assert r["intake"]["measured"] is False
    assert r["intake"]["arrivals_per_hour"] == []
    assert all(s["last_fetch"] is None for s in r["sources"])
    assert all(s["governance"] == {"http_status": None, "robots_allowed": None}
               for s in r["sources"])
    Handler._FETCH_CACHE.clear()


def test_investigate_extends_counter_audit_iterations():
    """`/api/investigate` 확장 — counter_evidence 배열·audit_trace·iterations·
    terminated_by·retrieved≤10·computed 문구."""
    facade = _rich_facade()
    subj = facade.zone.assertions()[0]["subject_id"]
    self = types.SimpleNamespace(facade=facade)
    r = json.loads(Handler._api_investigate(self, {"subject": subj}))
    assert r["computed"] == "on-request, non-persistent"
    assert isinstance(r["counter_evidence"], list)
    for ce in r["counter_evidence"]:
        assert "hypotheses" in ce and "negative_queries" in ce
    at = r["audit_trace"]
    assert {"trace", "blocked_statements", "verifiable", "linked",
            "linkage_ratio"} <= set(at)
    assert isinstance(r["iterations"], int) and r["iterations"] >= 1
    assert r["terminated_by"]
    assert len(r["retrieved"]) <= 10
    # 기존 필드 유지
    assert "coverage" in r and "gaps" in r and "conclusion" in r


def test_search_route_wired_and_pages_untouched():
    """라우트 병합 확인: do_GET 분기에 /api/search·/api/claim 존재 (정적 가드)."""
    import inspect
    src = inspect.getsource(Handler.do_GET)
    assert '"/api/search"' in src and '"/api/claim"' in src

