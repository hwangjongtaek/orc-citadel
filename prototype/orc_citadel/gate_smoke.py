"""S8 게이트 스모크 — 실수집 → claim 추출 → 그래프 반영 게이트(승격/quarantine) → 영속.

실수집 6건의 claim 후보를 설계 05 §6 게이트로 평가해 promoted/quarantined 상태를
claim_candidates에 영속하고, append-only 승격 이벤트(create_node) 로그를 확인한다.
임계값은 placeholder (05 §6→10 위임). 파생 DB는 prototype/data/ 아래(gitignore).
"""
from __future__ import annotations

import pathlib
from collections import Counter

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
    print(f"== S8 그래프 반영 게이트 스모크: {len(metas)} real docs ==")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():  # 신선한 게이트 평가 (derived, gitignored).
        DB_PATH.unlink()

    zone = CuratedZone(str(DB_PATH))
    zone.initialize()
    resolver = EntityResolver()
    gate = Gate()

    status_count: Counter = Counter()
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
            zone.update_claim_status(
                c.claim_candidate_id, result.status,
                ",".join(result.reasons) if result.reasons else None,
            )
            status_count[result.status] += 1

    print(f"\ngate verdicts: {dict(status_count)}")
    ev = gate.mutations()
    print(f"append-only promote events (create_node): {len(ev)}")

    rows = zone.claims()
    print(f"persisted claim_candidates: {len(rows)} (status 전이 포함)")
    for r in rows:
        print(f"  {r['status']:<12} {r['predicate']:<10} conf={r['confidence']:.2f} "
              f"hint={r['event_type_hint']:<16} reason={r['quarantine_reason']}")

    zone.close()
    print("\n== ALL OK ==")


if __name__ == "__main__":
    main()
