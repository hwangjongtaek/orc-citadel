"""S12 edge-gate 스모크 — 실수집 mention authoritative 게이트 + edge 게이트 (05 §6).

mention(span·해소 entity·type) 게이트로 authoritative 노드 승격을 검증하고,
POSSIBLY_SAME_AS edge 후보(score·resolution_ref) 게이트로 create_edge 승격을 확인한다.
SAME_AS 자동 병합은 결정적 식별자만(ADR-507) — edge는 후보/승격만. 파생 DB gitignore.
"""
from __future__ import annotations

import pathlib

from orc_citadel.curated_zone import CuratedZone
from orc_citadel.edges import PossiblySameAsEdge
from orc_citadel.extract import extract_mentions
from orc_citadel.gate import Gate
from orc_citadel.load_raw_zone import load_raw_zone
from orc_citadel.parse import extract_html, parse_document
from orc_citadel.resolve import EntityResolver

DB_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "curated.duckdb"


def main() -> None:
    store, metas = load_raw_zone()
    print(f"== S12 mention/edge 게이트 스모크: {len(metas)} real docs ==")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    zone = CuratedZone(str(DB_PATH))
    zone.initialize()
    resolver = EntityResolver()
    gate = Gate()

    # 실수집 mention → 게이트 → authoritative 노드.
    n_men = n_promoted = 0
    for m in metas:
        doc = extract_html(m["content"], m["url"])
        segs = parse_document(m["doc_id"], doc)
        ms = extract_mentions(m["doc_id"], doc, segs)
        entities, resolved = resolver.resolve(m["doc_id"], ms)
        for rm in resolved:
            zone.persist_mention(rm.mention)
        for e in entities:
            zone.persist_resolved(e, resolved)  # resolved_entity_id 반영
        # 해소된 mention만 authoritative 게이트 통과 대상.
        for rm in resolved:
            n_men += 1
            result = gate.evaluate_mention(rm.mention, resolved_entity_id=rm.resolved_entity_id)
            if result.promote:
                n_promoted += 1
                zone.set_mention_authoritative(rm.mention.mention_id)

    print(f"mentions: {n_men} → authoritative(promoted): {n_promoted}")

    # 합성 POSSIBLY_SAME_AS edge 후보 → edge 게이트 → create_edge 승격·영속.
    e = PossiblySameAsEdge(
        edge_id="psa-nvda-tsmc", entity_a_id="org-nvda", entity_b_id="org-tsmc",
        score=0.75, blocking_key="norm_name", resolution_ref="res-synth",
        judged_by="pipeline",
    )
    er = gate.evaluate_edge(e)
    if er.promote:
        zone.persist_edge(e)  # prototype — edge만 영속 (노드 생성은 06 그래프 후속)
    print(f"synth POSSIBLY_SAME_AS edge: promote={er.promote} ({er.status})")

    auth = zone.authoritative_edges()
    print(f"authoritative edges persisted: {len(auth)}")
    for r in auth:
        print(f"  {r['edge_id']} {r['entity_a_id']}~{r['entity_b_id']} "
              f"[{r['relation']}] score={r['score']} ref={r['resolution_ref']}")

    # authoritative mention 수 (DB 반영).
    db_auth = [r for r in zone.mentions() if r["authoritative"]]
    ev = gate.mutations()
    print(f"\nauthoritative mentions in DB: {len(db_auth)}  gate events: {len(ev)} "
          f"(ops={sorted({m['op'] for m in ev})})")

    zone.close()
    print("\n== ALL OK ==")


if __name__ == "__main__":
    main()
