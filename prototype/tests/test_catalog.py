"""S28 API/출력 계층 — 검색 가능한 소비 카탈로그 (설계 09 §1.4·§2.2) TDD.

파이프라인 산출(어세션·그래프)을 **read-only** 쿼리 계층으로 노출한다 (불변식 §3-3,
그래프 직접 write 금지, 09 §2.2).
- 어세션 카탈로그: subject/predicate 필터 + **cursor 페이지네이션**(09 §1.4, opaque
  cursor, ULID 시간정렬) + 선택적 time-travel(as_of, 09 §2.2).
- 그래프 카탈로그: 노드/이웃/조사 subgraph 조회 재사용 (06 §8, S25/S26).
- 소비 형식: items[] + page(next_cursor/limit) — UI·검색 입력.
"""
from __future__ import annotations

from datetime import datetime, timezone

from orc_citadel.catalog import Catalog, CatalogGraph
from orc_citadel.curated_zone import CuratedZone


def _dt(s): return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def _populate_zone() -> tuple[CuratedZone, str]:
    """어세션 3건 + 엔티티/그래프 노드가 담긴 zone."""
    from orc_citadel.assertions import materialize
    from orc_citadel.extract_claims import ClaimCandidate

    z = CuratedZone(":memory:")
    z.initialize()

    def _claim(cid, subj, pred, obj):
        return ClaimCandidate(
            claim_candidate_id=cid, doc_id="doc-1", predicate=pred, subject_id=subj,
            object_id=obj, object_literal=None, modality="asserted",
            polarity="positive", confidence=0.8, seg_order=0, char_start=0,
            char_end=4, surface_fragment="x", event_type_hint=None, status="candidate")

    a1 = materialize(_claim("clm-1", "org-nvda", "announces", "org-cowos"),
                     observed_at=_dt("2026-02-01T00:00:00"), mutation="mut-1")
    a2 = materialize(_claim("clm-2", "org-tsmc", "announces", "org-cowos"),
                     observed_at=_dt("2026-03-01T00:00:00"), mutation="mut-2")
    a3 = materialize(_claim("clm-3", "org-nvda", "powers", "org-dc"),
                     observed_at=_dt("2026-04-01T00:00:00"), mutation="mut-3")
    for a in (a1, a2, a3):
        z.persist_assertion(a)
    return z, a1.assertion_id


def test_catalog_assertions_cursor_pagination():
    """어세션 카탈로그 — cursor 페이지네이션 (09 §1.4, items+page)."""
    z, _ = _populate_zone()
    c = Catalog(z)
    page1 = c.assertions(limit=2)
    assert len(page1["items"]) == 2
    assert "next_cursor" in page1["page"]
    assert page1["page"]["limit"] == 2
    assert page1["page"]["next_cursor"] is not None  # 2개 초과 → 다음 페이지.
    page2 = c.assertions(limit=2, cursor=page1["page"]["next_cursor"])
    assert len(page2["items"]) == 1  # 남은 1건.
    assert page2["page"]["next_cursor"] is None  # 마지막 페이지.


def test_catalog_assertions_filter_subject():
    """subject 필터 — 일치 어세션만."""
    z, _ = _populate_zone()
    c = Catalog(z)
    res = c.assertions(subject_id="org-nvda")
    assert {a["subject_id"] for a in res["items"]} == {"org-nvda"}
    assert len(res["items"]) == 2


def test_catalog_assertions_filter_predicate():
    """predicate 필터 — announces만."""
    z, _ = _populate_zone()
    c = Catalog(z)
    res = c.assertions(predicate="announces")
    assert {a["predicate"] for a in res["items"]} == {"announces"}
    assert len(res["items"]) == 2


def test_catalog_assertions_time_travel():
    """time-travel: as_of 필터로 특정 관측 시점의 어세션만 (09 §2.2)."""
    z, a1id = _populate_zone()
    c = Catalog(z)
    # T_t=2026-02-15: a1(tx 02-01)은 믿던 상태, a2/a3(이후)는 아직 미관측.
    res = c.assertions(as_of_tx=_dt("2026-02-15T00:00:00"))
    assert len(res["items"]) == 1
    assert res["items"][0]["assertion_id"] == a1id


def test_catalog_graph_query():
    """그래프 카탈로그 — 노드/이웃/조사 subgraph 재사용 (06 §8)."""
    from orc_citadel.graph_service import GraphService as GS

    g = GS()
    g.apply([{"mutation_id": "m1", "idempotency_key": "k1", "op": "create_node",
              "payload": {"id": "org-a", "props": {}, "labels": []}},
             {"mutation_id": "m2", "idempotency_key": "k2", "op": "create_node",
              "payload": {"id": "clm-1", "props": {}, "labels": []}},
             {"mutation_id": "m3", "idempotency_key": "k3", "op": "create_edge",
              "payload": {"type": "ABOUT", "from": "org-a", "to": "clm-1", "props": {}}}])
    c = CatalogGraph(g)
    assert c.node("org-a")["id"] == "org-a"
    nbrs = c.neighbors("org-a")
    assert any(n["id"] == "clm-1" and n["type"] == "ABOUT" for n in nbrs)
    sub = c.investigation_subgraph("org-a", hops=1)
    assert sub["entity"] == "org-a"
    assert any(cl["id"] == "clm-1" for cl in sub["claims"])


def test_catalog_read_only():
    """그래프 카탈로그는 read-only — mutation API 노출 안 함 (불변식 §3-3)."""
    from orc_citadel.graph_service import GraphService as GS
    g = GS()
    c = CatalogGraph(g)
    assert not hasattr(c, "apply")
    assert not hasattr(c, "create_node")
