"""S9 canonicalization 스모크 — 실수집 → claim → 게이트 → CanonicalClaim 영속.

동일 (subject, predicate) blocking 그룹에서 겹치는 span claim들이 1 CanonicalClaim으로
묶이는지 실데이터로 검증하고, canonical_claims + MEMBER_OF 엣지 + claim.canonical_claim_id를
curated zone에 영속한다 (설계 05 §4, 02 §2.4·§3.1). 파생 DB는 prototype/data/ 아래(gitignore).
"""
from __future__ import annotations

import pathlib

from orc_citadel.canonicalize import canonicalize_claims
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
    print(f"== S9 canonicalization 스모크: {len(metas)} real docs ==")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():  # 신선한 schema (derived, gitignored).
        DB_PATH.unlink()

    zone = CuratedZone(str(DB_PATH))
    zone.initialize()
    resolver = EntityResolver()
    gate = Gate()

    all_claims = []
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
        all_claims.extend(claims)

    # canonicalization — promoted claim들만 (게이트 통과) 대상을 묶는다.
    promoted = [c for c in all_claims
                if gate.result(c.claim_candidate_id) is not None
                and gate.result(c.claim_candidate_id).promote]
    print(f"promoted claims: {len(promoted)}")

    canonicals = canonicalize_claims(promoted)
    member_by_id = {}
    for cc in canonicals:
        zone.persist_canonical(cc)
        for cid in cc.member_claim_ids:
            member_by_id[cid] = cc.canonical_claim_id
            zone.set_claim_canonical(cid, cc.canonical_claim_id)
    print(f"canonical claims: {len(canonicals)}")

    print("\nCanonicalClaims (동일 subject+predicate+표현 → 1개):")
    for cc in zone.canonical_claims():
        print(f"  {cc['canonical_claim_id'][:14]} {cc['subject_id'][:10]} "
              f"{cc['predicate']:<10} members={len(cc['member_claim_ids'])} "
              f"text={cc['canonical_text'][:32]!r}")

    mo = zone.member_of()
    print(f"\nMEMBER_OF edges: {len(mo)}")
    rows = zone.claims()
    filled = [r for r in rows if r["canonical_claim_id"]]
    print(f"claims with canonical_claim_id set: {len(filled)}/{len(rows)}")

    zone.close()
    print("\n== ALL OK ==")


if __name__ == "__main__":
    main()
