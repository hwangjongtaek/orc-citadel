"""S11 assertions 스모크 — 실수집 → claim → 게이트(promote) → Assertion materialize → 영속.

promoted claim의 정규 삼항 Assertion(bitemporal: valid+transaction)을 materialize하고
curated zone에 영속한다. append-only create_node 이벤트(게이트) ↔ Assertion projection
재구축 관계 확인. 파생 DB는 prototype/data/ 아래(gitignore).
"""
from __future__ import annotations

import pathlib
from datetime import datetime, timezone

from orc_citadel.assertions import materialize
from orc_citadel.curated_zone import CuratedZone
from orc_citadel.extract import extract_mentions
from orc_citadel.extract_claims import extract_claims
from orc_citadel.gate import Gate
from orc_citadel.load_raw_zone import load_raw_zone
from orc_citadel.parse import extract_html, parse_document
from orc_citadel.resolve import EntityResolver

DB_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "curated.duckdb"


def main() -> None:
    store, metas = load_raw_zone()
    print(f"== S11 Assertion materialization 스모크: {len(metas)} real docs ==")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    zone = CuratedZone(str(DB_PATH))
    zone.initialize()
    resolver = EntityResolver()
    gate = Gate()
    observed = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)

    n_promoted = n_asserted = 0
    for m in metas:
        doc = extract_html(m["content"], m["url"])
        segs = parse_document(m["doc_id"], doc)
        ms = extract_mentions(m["doc_id"], doc, segs)
        for men in ms:
            zone.persist_mention(men)
        entities, resolved = resolver.resolve(m["doc_id"], ms)
        for e in entities:
            zone.persist_resolved(e, resolved)
        claims = extract_claims(m["doc_id"], segs, resolved, {e.entity_id: e for e in entities})
        for c in claims:
            zone.persist_claim(c)
            result = gate.evaluate(c)
            zone.update_claim_status(c.claim_candidate_id, result.status,
                                     ",".join(result.reasons) if result.reasons else None)
            if result.promote:
                n_promoted += 1
                # promoted claim → Assertion materialize (emission 계약, 03 §6.2).
                mut = gate.mutations()[-1]  # 마지막 create_node 이벤트(mutation_id).
                a = materialize(c, observed_at=observed, mutation=mut["mutation_id"])
                zone.persist_assertion(a)
                n_asserted += 1

    print(f"promoted claims: {n_promoted} → assertions materialized: {n_asserted}")
    for r in zone.assertions():
        print(f"  {r['assertion_id'][:12]} {r['subject_id'][:9]} "
              f"{r['predicate']:<10} tx_from={r['tx_from'].isoformat()[:19]} "
              f"tx_to={r['tx_to']} mut={r['mutation_id']}")
    ev = gate.mutations()
    print(f"\nappend-only create_node events: {len(ev)} (Assertion projection 재구축 입력)")

    zone.close()
    print("\n== ALL OK ==")


if __name__ == "__main__":
    main()
