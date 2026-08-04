"""S5 추출 + curated 영속 스모크 — 실수집 6건 → L1 mention 추출 → curated zone 영속·조회.

실수집 raw → extract_html → parse → extract_mentions → CuratedZone.persist_mention →
mentions() 조회로 span 왕복(offset·surface 정합)을 검증하고, Parquet export까지 확인한다.
S4 dedup cluster도 같은 curated zone에 영속해 출처 계보와 한 곳에 모은다.
파생 DB는 prototype/data/ 아래(gitignore).
"""
from __future__ import annotations

import pathlib

from orc_citadel.curated_zone import CuratedZone
from orc_citadel.dedup import Deduplicator
from orc_citadel.extract import extract_mentions
from orc_citadel.load_raw_zone import load_raw_zone
from orc_citadel.parse import extract_html, parse_document

DB_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "curated.duckdb"


def main() -> None:
    store, metas = load_raw_zone()
    print(f"== S5 추출+curated 영속 스모크: {len(metas)} real docs ==")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    zone = CuratedZone(str(DB_PATH))
    zone.initialize()

    ok = 0
    total_mentions = 0
    for m in metas:
        doc = extract_html(m["content"], m["url"])
        segs = parse_document(m["doc_id"], doc)
        mentions = extract_mentions(m["doc_id"], doc, segs)
        for men in mentions:
            zone.persist_mention(men)
        total_mentions += len(mentions)
        # span 왕복: mention span으로 clean text를 slice하면 surface 정합.
        spans_ok = all(doc.text[men.char_start:men.char_end] == men.surface_text
                       for men in mentions)
        if spans_ok:
            ok += 1
            print(f"  [OK] {m['source_id']:<26} mentions={len(mentions):>2} "
                  f"{[mm.surface_text for mm in mentions][:4]}")
        else:
            print(f"  [FAIL span] {m['source_id']} {m['url'][:40]}")

    # curated 조회 검증
    rows = zone.mentions()
    print(f"\npersisted mentions: {len(rows)} (span OK {ok}/{len(metas)})")
    by_type = {}
    for r in rows:
        by_type[r["mention_type"]] = by_type.get(r["mention_type"], 0) + 1
    print(f"by type: {by_type}")

    # S4 dedup cluster를 같은 curated zone에 영속 (출처 계보 + 추출 동일 zone).
    doc_rows = []
    for m in metas:
        doc = extract_html(m["content"], m["url"])
        doc_rows.append({
            "doc_id": m["doc_id"],
            "text": doc.text,
            "publication_time": doc.publication_time,
            "source_id": m["source_id"],
        })
    clusters = Deduplicator().dedup(doc_rows)
    # cluster_id는 결정적(불변) — 여기선 순번으로 생성해 영속 계약만 검증.
    for i, c in enumerate(clusters):
        zone.persist_cluster(
            f"clus-{i+1}", c.root_doc_id, list(c.member_doc_ids),
            list(c.independent_addition_doc_ids), c.dedup_method,
        )
    print(f"dedup clusters persisted: {len(clusters)}")

    # Parquet export
    pq = DB_PATH.parent / "curated-parquet"
    zone.export_parquet(pq)
    print(f"parquet: {sorted(p.name for p in pq.glob('*.parquet'))}")

    zone.close()
    print(f"\n== ALL OK (total mentions {total_mentions}) ==")


if __name__ == "__main__":
    main()
