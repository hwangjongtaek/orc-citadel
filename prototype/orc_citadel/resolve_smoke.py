"""S6 해소 스모크 — 실수집 문서 → L1 mention 추출 → 결정적 해소(entity) → curated 영속.

NVIDIA(gazetteer, ticker NVDA) + NVDA(ticker) 가 shared identifier로 한 entity(SAME_AS),
TSMC(ticker TSM) 3건 → 한 entity, GeForce NOW/RTX 각 1 entity로 해소되는지 실데이터로
검증. entities·mention.resolved_entity_id를 curated zone에 영속·조회한다 (설계 03 §4).
파생 DB는 prototype/data/ 아래(gitignore).
"""
from __future__ import annotations

import pathlib
from collections import defaultdict

from orc_citadel.curated_zone import CuratedZone
from orc_citadel.extract import extract_mentions
from orc_citadel.load_raw_zone import load_raw_zone
from orc_citadel.parse import extract_html, parse_document
from orc_citadel.resolve import EntityResolver

DB_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "curated.duckdb"


def main() -> None:
    store, metas = load_raw_zone()
    print(f"== S6 해소(결정적 stage-1) 스모크: {len(metas)} real docs ==")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    zone = CuratedZone(str(DB_PATH))
    zone.initialize()

    resolver = EntityResolver()
    surf_count: dict[str, int] = defaultdict(int)
    surf_entities: dict[str, set[str]] = defaultdict(set)
    for m in metas:
        doc = extract_html(m["content"], m["url"])
        segs = parse_document(m["doc_id"], doc)
        ms = extract_mentions(m["doc_id"], doc, segs)
        for men in ms:
            zone.persist_mention(men)
        entities, resolved = resolver.resolve(m["doc_id"], ms)
        for e in entities:
            zone.persist_resolved(e, resolved)
        for rm in resolved:
            surf_count[rm.surface_text] += 1
            surf_entities[rm.surface_text].add(rm.resolved_entity_id)

    # 해소 요약 — 표면형별 서로 다른 entity 수 (1 = 완전 해소).
    print("\nmentions→entities per surface (1 = fully resolved):")
    for surf in sorted(surf_count):
        ok = "✓" if len(surf_entities[surf]) == 1 else "✗"
        print(f"  {ok} {surf:<16} mentions={surf_count[surf]:>2} entities={len(surf_entities[surf])}")

    ents = zone.entities()
    print(f"\npersisted entities: {len(ents)}")
    for e in ents:
        print(f"  {e['entity_id'][:14]}  {e['canonical_name']:<12} type={e['mention_type']:<13} "
              f"ids={e['identifiers']} forms={e['surface_forms']}")

    zone.close()
    print("\n== ALL OK ==")


if __name__ == "__main__":
    main()
