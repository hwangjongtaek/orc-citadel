"""DuckDB 영속화 스모크 — 실수집 문서를 정규화 zone에 영속·조회 (design 03 §3).

실수집 raw 파일 → extract_html → parse → NormalizedZone.persist →
DuckDB documents()/segments() 조회로 offset 왕복을 검증하고, raw HTML과의
연결(내용 기반 doc_id)을 확인한다. 파생 DB는 prototype/data/ 아래(gitignore).
"""
from __future__ import annotations

import pathlib

from orc_citadel.duckdb_zone import NormalizedZone
from orc_citadel.load_raw_zone import load_raw_zone
from orc_citadel.parse import extract_html
from orc_citadel.identity import doc_id_for

DB_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "oc.duckdb"


def main() -> None:
    store, metas = load_raw_zone()
    print(f"== DuckDB 영속화 스모크: {len(metas)} real docs ==")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    zone = NormalizedZone(str(DB_PATH))
    zone.initialize()
    ok = 0
    for m in metas:
        html = m["content"]
        doc = extract_html(html, m["url"])
        doc_id = zone.persist(m["source_id"], m["url"], html, doc)
        expected = doc_id_for(html)
        # 조회해서 offset 왕복 검증
        segs = zone.segments(doc_id)
        roundtrip = all(doc.text[s["char_start"]:s["char_end"]] == s["text"] for s in segs)
        if doc_id == expected and roundtrip:
            ok += 1
            print(f"  [OK] {m['source_id']:<28} segs={len(segs):>3} {doc.title[:40]}")
        else:
            print(f"  [FAIL] {m['source_id']} {m['url'][:50]}")

    docs = zone.documents()
    print(f"\npersisted documents: {len(docs)} (roundtrip OK {ok}/{len(metas)})")
    from collections import Counter
    print(f"by source: {dict(Counter(d['source_id'] for d in docs))}")
    total_segs = sum(len(zone.segments(d["doc_id"])) for d in docs)
    print(f"total segments: {total_segs}")

    # (선택) Parquet export 스모크 — 조회/그래프 입력용 (05 이후).
    pq = DB_PATH.parent / "parquet"
    pq.mkdir(parents=True, exist_ok=True)
    zone.export_parquet(pq)
    print(f"parquet exported to {pq}: {sorted(p.name for p in pq.glob('*.parquet'))}")

    zone.close()
    print("\n== ALL OK ==")


if __name__ == "__main__":
    main()
