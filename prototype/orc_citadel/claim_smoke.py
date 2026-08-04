"""S7 claim 추출 스모크 — 실수집 → 해소 → 규칙 claim 추출 → curated 영속·조회.

NVIDIA 공시 doc에서 `announces`(earnings conference call) claim을 결정적 규칙으로
추출하고, source_span(clean text 축)으로 segment 텍스트를 slice하면 surface_fragment가
재현되는지(provenance 왕복) 검증한다. claim_candidates는 03 §4.2 status=candidate로
curated zone에 영속. SemiEngineering(본문 컨테이너 크롬만)은 규칙 매칭 0건 — precision.
파생 DB는 prototype/data/ 아래(gitignore).
"""
from __future__ import annotations

import pathlib
from collections import Counter

from orc_citadel.curated_zone import CuratedZone
from orc_citadel.extract import extract_mentions
from orc_citadel.extract_claims import extract_claims
from orc_citadel.load_raw_zone import load_raw_zone
from orc_citadel.parse import extract_html, parse_document
from orc_citadel.resolve import EntityResolver

DB_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "curated.duckdb"


def main() -> None:
    store, metas = load_raw_zone()
    print(f"== S7 claim 추출(규칙 기반) 스모크: {len(metas)} real docs ==")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    zone = CuratedZone(str(DB_PATH))
    zone.initialize()
    resolver = EntityResolver()

    by_source: Counter = Counter()
    total = 0
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
        # provenance 왕복: source_span으로 segment slice → surface_fragment 일치.
        rd_ok = True
        for c in claims:
            zone.persist_claim(c)
            seg = segs[c.seg_order]
            if seg.text[c.char_start:c.char_end] != c.surface_fragment:
                rd_ok = False
        by_source[m["source_id"]] += len(claims)
        total += len(claims)
        ok = "✓" if rd_ok else "✗"
        print(f"  {ok} {m['source_id']:<24} claims={len(claims):>2} "
              f"{[c.predicate for c in claims][:3]}")
        if not rd_ok:
            print(f"    ! span roundtrip FAIL: {m['url'][:40]}")

    print(f"\ntotal claims: {total}  by source: {dict(by_source)}")
    db_claims = zone.claims()
    print(f"persisted claim_candidates: {len(db_claims)}")
    for c in db_claims[:6]:
        print(f"  {c['predicate']:<10} subj={c['subject_id'][:12]:<14} "
              f"hint={c['event_type_hint']:<16} frag={c['surface_fragment'][:40]!r}")

    zone.close()
    print("\n== ALL OK ==")


if __name__ == "__main__":
    main()
