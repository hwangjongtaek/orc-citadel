"""S26 Investigation subgraph 질의 — canonical view-rewrite + progressive (06 §8.1·§8.3) TDD.

조사(Investigation) 중심 그래프 조회:
- 진입점: scope 엔터티(seed) → canonical 대표로 rewrite (§5.2 view-rewrite 필수 wrapper).
- 동치류(SAME_AS*0..) 전체 fold — merged-away member를 별도 엔터티로 노출하지 않음.
- hop 제한 BFS + relationship 타입 필터 + 기본 :Authoritative/:Deleted 제외 (§4.1).
- 프로그래시브 공개: hop/페이지 제한, 상한 초과 시 요약 축약 (§8.3).
"""
from __future__ import annotations

from orc_citadel.graph_service import GraphService


def _node(key, nid, **props):
    return {"mutation_id": f"mut-{key}", "idempotency_key": f"k-{key}", "op": "create_node",
            "payload": {"id": nid, "props": props, "labels": []}}


def _edge(key, from_id, to_id, etype, **props):
    return {"mutation_id": f"mut-{key}", "idempotency_key": f"k-{key}", "op": "create_edge",
            "payload": {"type": etype, "from": from_id, "to": to_id, "props": props}}


def _merge(key, member, canonical):
    return {"mutation_id": f"mut-{key}", "idempotency_key": f"k-{key}", "op": "merge_entity",
            "payload": {"member": member, "canonical": canonical}}


def _graph():
    """병합된 엔터티 동치류 + ABOUT/SUPPORTS/CONTRADICTS 가진 그래프.

    - org-tsmc(seed, canonical) + org-tsmc-us(member, merged) 동치류.
    - claim clm-1: ABOUT org-tsmc; SUPPORTS (evd-1); CONTRADICTS (evd-2).
    - claim clm-2: ABOUT org-tsmc-us(merged member) — view-rewrite로 fold돼야 함.
    - org-other: unrelated claim clm-3 (범위 밖).
    """
    g = GraphService()
    g.apply([
        _node(1, "org-tsmc"), _node(2, "org-tsmc-us"), _node(3, "org-other"),
        _node(4, "clm-1"), _node(5, "clm-2"), _node(6, "clm-3"),
        _node(7, "evd-1"), _node(8, "evd-2"),
        _merge(9, "org-tsmc-us", "org-tsmc"),
        # ABOUT: entity → claim.
        _edge(10, "org-tsmc", "clm-1", "ABOUT"),
        _edge(11, "org-tsmc-us", "clm-2", "ABOUT"),   # merged member — fold 대상
        _edge(12, "org-other", "clm-3", "ABOUT"),
        # evidence: SUPPORTS / CONTRADICTS → claim.
        _edge(13, "evd-1", "clm-1", "SUPPORTS", strength=0.8),
        _edge(14, "evd-2", "clm-1", "CONTRADICTS", conflict_type="value_conflict"),
    ])
    return g


def test_canonical_rewrite_folds_equivalence_class():
    """seed=org-tsmc → 동치류(SAME_AS*0..) 전체 claim fold (canonical view-rewrite, §5.2/§8.1).

    org-tsmc-us(merged)에 ABOUT된 clm-2도 포함돼야 하고, org-tsmc/sum이 따로 노출 안 됨.
    """
    g = _graph()
    res = g.investigation_subgraph(seed="org-tsmc", hops=1)
    claims = {c["id"] for c in res["claims"]}
    assert "clm-1" in claims
    assert "clm-2" in claims          # merged member의 claim이 fold됨
    assert "clm-3" not in claims      # 범위 밖
    # canonical 대표 1개 + 동치류 정체성.
    entities = {e["id"] for e in res["entities"]}
    assert "org-tsmc" in entities
    assert "org-tsmc-us" not in entities  # merged member는 별도 노출 금지 (§8.1 view-rewrite)


def test_rewrite_member_seed_resolves_to_canonical():
    """seed가 merged member(org-tsmc-us)여도 canonical 대표로 rewrite 후 동치류 fold."""
    g = _graph()
    res = g.investigation_subgraph(seed="org-tsmc-us", hops=1)
    claims = {c["id"] for c in res["claims"]}
    assert "clm-1" in claims and "clm-2" in claims


def test_includes_supports_and_contradicts_evidence():
    """claim의 SUPPORTS/CONTRADICTS 근거 증거 포함 (06 §8.1)."""
    g = _graph()
    res = g.investigation_subgraph(seed="org-tsmc", hops=1)
    ev = res["evidence"]
    assert {e["id"] for e in ev} == {"evd-1", "evd-2"}
    # 지지/반박 구분 필드 (관계 reification, 06 §2.2).
    rels = {(e["from"], e["type"]) for e in res["relationships"]}
    assert ("evd-1", "SUPPORTS") in rels
    assert ("evd-2", "CONTRADICTS") in rels


def test_default_filters_authoritative_not_deleted():
    """Deleted 노드는 기본 제외 (§4.1)."""
    g = _graph()
    g.apply([_node(20, "clm-del"), _edge(21, "org-tsmc", "clm-del", "ABOUT"),
             {"mutation_id": "mut-22", "idempotency_key": "k-22", "op": "delete",
              "payload": {"id": "clm-del"}}])
    res = g.investigation_subgraph(seed="org-tsmc", hops=1)
    assert "clm-del" not in {c["id"] for c in res["claims"]}


def test_hop_limited_progressive_bounded():
    """hop 제한(+ relationship 타입 필터) — 1-hop: entity의 claim까지만, 2-hop 포화 안."""
    g = GraphService()
    g.apply([
        _node(1, "org-a"), _node(2, "clm-a"), _node(3, "clm-a2"),
        _node(4, "evd-a"), _edge(10, "org-a", "clm-a", "ABOUT"),
        _edge(11, "org-a", "clm-a2", "ABOUT"),
        _edge(12, "evd-a", "clm-a", "SUPPORTS"),
        _edge(13, "evd-a", "clm-a2", "SUPPORTS"),  # 1-hop 밖 (evidence→claim2)
    ])
    res = g.investigation_subgraph(seed="org-a", hops=1, limit=10)
    assert len(res["evidence"]) <= 1  # hops=1 → evidence가 2번째 claim까지 확장 안 함(경계)


def test_progressive_limit_returns_summary_signal():
    """페이지 limθ 상한 초과 시 요약 축약 신호 (§8.3) — truncated 표시."""
    g = GraphService()
    events = [_node(1, "org-a")]
    events += [_node(100 + i, f"clm-{i}") for i in range(20)]
    events += [_edge(200 + i, "org-a", f"clm-{i}", "ABOUT") for i in range(20)]
    g.apply(events)
    res = g.investigation_subgraph(seed="org-a", hops=1, limit=5)
    assert len(res["claims"]) == 5
    assert res.get("truncated") is True  # 상한 초과 요약 신호
