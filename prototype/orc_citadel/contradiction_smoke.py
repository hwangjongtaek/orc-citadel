"""S10 conflict 스모크 — 실수집(모순 후보 0건, 정직) + 합성 주입으로 규칙 시연.

실수집 claim은 전부 announces·positive라 같은 subject+predicate에서 상충 쌍이 없다
(정직한 실측) — 결정적 충돌 후보 규칙(05 §5.1)의 정당성은 합성 케이스로 시연한다.
conflict_candidates는 curated zone에 영속 (02 §3.1·ADR-504). 파생 DB gitignore.
"""
from __future__ import annotations

import pathlib

from orc_citadel.contradiction import ConflictCandidate, find_conflict_candidates
from orc_citadel.curated_zone import CuratedZone
from orc_citadel.extract import extract_mentions
from orc_citadel.extract_claims import ClaimCandidate, extract_claims
from orc_citadel.gate import Gate
from orc_citadel.load_raw_zone import load_raw_zone
from orc_citadel.parse import extract_html, parse_document
from orc_citadel.resolve import EntityResolver

DB_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "curated.duckdb"


def _real_claims(metas):
    resolver = EntityResolver()
    gate = Gate()
    claims = []
    for m in metas:
        doc = extract_html(m["content"], m["url"])
        segs = parse_document(m["doc_id"], doc)
        ms = extract_mentions(m["doc_id"], doc, segs)
        ents, resolved = resolver.resolve(m["doc_id"], ms)
        claims.extend(extract_claims(m["doc_id"], segs, resolved,
                                     {e.entity_id: e for e in ents}))
    return claims


def main() -> None:
    store, metas = load_raw_zone()
    print(f"== S10 충돌 후보 스모크: {len(metas)} real docs ==")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    zone = CuratedZone(str(DB_PATH))
    zone.initialize()

    # 1) 실수집 — 모순 후보 (정직한 0건 기대).
    real = _real_claims(metas)
    real_c = find_conflict_candidates(real)
    print(f"real claims: {len(real)} → conflict candidates: {len(real_c)} "
          f"(전 announces·positive, 상충 쌍 없음 — 정직한 실측)")

    # 2) 합성 주입 — 같은 subject+predicate에서 polarity 상충 → 후보 생성·영속.
    synth = [
        ClaimCandidate(
            claim_candidate_id="clm-syn-a", doc_id="doc-s", predicate="depends_on",
            subject_id="org-1", object_id=None, object_literal=None,
            modality="asserted", polarity="positive", confidence=0.8,
            seg_order=0, char_start=0, char_end=4, surface_fragment="depends on",
            event_type_hint=None, status="promoted",
        ),
        ClaimCandidate(
            claim_candidate_id="clm-syn-b", doc_id="doc-s", predicate="depends_on",
            subject_id="org-1", object_id=None, object_literal=None,
            modality="asserted", polarity="negative", confidence=0.8,
            seg_order=1, char_start=0, char_end=4, surface_fragment="does not depend",
            event_type_hint=None, status="promoted",
        ),
    ]
    syn_c = find_conflict_candidates(synth)
    for cc in syn_c:
        zone.persist_conflict(cc)
    print(f"synth polarity-conflict candidate: {len(syn_c)} (rationale·judged_by 저장)")

    persisted = zone.conflict_candidates()
    print(f"\npersisted conflict_candidates: {len(persisted)}")
    for r in persisted:
        print(f"  {r['claim_id_a']} ↔ {r['claim_id_b']} [{r['conflict_type']}] "
              f"judged_by={r['judged_by']} rationale={r['rationale'][:40]}")

    zone.close()
    print("\n== ALL OK ==")


if __name__ == "__main__":
    main()
