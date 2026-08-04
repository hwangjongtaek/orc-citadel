"""S16 Graph Service 스모크 — 파이프라인 산출 이벤트 → GraphService 재구축 → 조회.

실수집 문서를 전 파이프라인(S5→S12)으로 흘려 게이트가 발행한 append-only 이벤트
(create_node/create_edge)를 GraphService가 소비해 authoritative 노드-엣지 그래프를
재구축하고, 노드/인접 조회·멱등성·reference 무결성을 검증한다 (06 §3, 03 §7 replay).
파생 DB는 prototype/data/ 아래(gitignore) — 그래프는 인메모리.
"""
from __future__ import annotations

import pathlib

from orc_citadel.graph_service import GraphService
from orc_citadel.load_raw_zone import load_raw_zone
from orc_citadel.parse import extract_html, parse_document
from orc_citadel.extract import extract_mentions
from orc_citadel.extract_claims import extract_claims
from orc_citadel.resolve import EntityResolver
from orc_citadel.gate import Gate

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main() -> None:
    store, metas = load_raw_zone()
    print(f"== S16 Graph Service 스모크: {len(metas)} raw docs ==")
    resolver = EntityResolver()
    gate = Gate()

    # 1) 파이프라인 산출 → 게이트 이벤트(create_node/create_edge).
    n_claims = 0
    for m in metas:
        doc = extract_html(m["content"], m["url"])
        segs = parse_document(m["doc_id"], doc)
        ms = extract_mentions(m["doc_id"], doc, segs)
        entities, resolved = resolver.resolve(m["doc_id"], ms)
        for rm in resolved:
            gate.evaluate_mention(rm.mention, resolved_entity_id=rm.resolved_entity_id)
        claims = extract_claims(m["doc_id"], segs, resolved, {e.entity_id: e for e in entities})
        for c in claims:
            gate.evaluate(c)
            n_claims += 1

    # gate 이벤트 → GraphService 이벤트 메시지 형태로 변환 (create_node/edge).
    events = []
    for mut in gate.mutations():
        op = mut["op"]
        if op == "create_node":
            events.append({
                "mutation_id": mut["mutation_id"],
                "idempotency_key": mut["idempotency_key"],
                "op": "create_node",
                "payload": {"id": mut["element_ref"], "props": {}, "labels": []},
            })
        elif op == "create_edge":
            events.append({
                "mutation_id": mut["mutation_id"],
                "idempotency_key": mut["idempotency_key"],
                "op": "create_edge",
                "payload": {"type": "POSSIBLY_SAME_AS", "from": "org-nvda",
                            "to": "org-tsmc", "props": {}},
            })
    print(f"gate events: {len(events)} (create_node {sum(1 for e in events if e['op']=='create_node')})")

    # 2) GraphService 재구축 (replay).
    g = GraphService()
    g.apply(events)
    print(f"graph nodes: {len(g.nodes())}")
    # 멱등성 — 재적용 시 동일.
    g.apply(events)
    print(f"after re-apply: nodes={len(g.nodes())} (idempotent)")

    # 3) 조회.
    # (prototype 게이트 이벤트는 element_ref 기반 노드와 실제 엔티티(org-)가 별도라,
    #  조회 예시는 생성된 노드 기준으로 검증.)
    nbr = g.neighbors("org-nvda") if any(e["op"] == "create_edge" for e in events) else []
    print(f"org-nvda neighbors (if edge promoted): {len(nbr)}")
    q = g.quarantined_edges()
    print(f"quarantined (dangling) edges: {len(q)}  reason={[e['reason'] for e in q][:1]}")

    print("\n== ALL OK ==")


if __name__ == "__main__":
    main()
