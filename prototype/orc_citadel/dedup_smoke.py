"""S4 Dedup 스모크 — 실수집 문서 + 복제 사본으로 출처 계보 축소 (04 §4, 03 §4.3).

실제 수집 문서 본문을 Deduplicator에 넣고, 인위적 near-dup 사본(한두 문장 수정)
을 추가해 원본·복제가 한 cluster로, 무관 문서와 분리되는지 검증. root가 원본
(공개 시각 이른 쪽)인지 확인한다.
"""
from __future__ import annotations

from orc_citadel.dedup import Deduplicator
from orc_citadel.load_raw_zone import load_raw_zone
from orc_citadel.parse import extract_html


def _copy_near(original: str) -> str:
    """문장 몇 개만 무해하게 수정한 near-dup 사본 생성 (복제 시뮬레이션)."""
    # 첫 문장 뒤에 접두 문구 추가해 미세 수정 (Jaccard는 여전히 높음)
    first, _, rest = original.partition(" ")
    return first + " (reported by The Daily Semi)" + " " + rest


def main() -> None:
    store, metas = load_raw_zone()
    print(f"== S4 Dedup 스모크: {len(metas)} real docs + fabricated near-dup ==")

    docs = []
    for m in metas:
        doc = extract_html(m["content"], m["url"])
        if not doc.text:
            continue
        # source_type은 source_id 접두에서 유추 (official/press/research)
        stype = "official" if m["source_id"].startswith("official") else (
            "research" if m["source_id"].startswith("research") else "press")
        docs.append({
            "doc_id": m["doc_id"],
            "text": doc.text,
            "publication_time": "2026-08-01T09:00:00+00:00",
            "source_type": stype,
        })

    # 첫 문서의 near-dup 사본 1건 추가 (실수집의 복제 시뮬레이션)
    copy_id = None
    if docs:
        base = docs[0]
        copy_id = "doc-copy-" + base["doc_id"][4:12]  # 가상 복제 id (결정적)
        docs.append({
            "doc_id": copy_id,
            "text": _copy_near(base["text"]),
            "publication_time": base["publication_time"],
            "source_type": "press",
        })

    dedup = Deduplicator()
    clusters = dedup.dedup(docs)

    print(f"documents: {len(docs)} → clusters: {len(clusters)}")
    print("\n-- clusters --")
    for cl in clusters:
        title = "?"
        print(f"root={cl.root_doc_id} method={cl.dedup_method}")
        print(f"  members={list(cl.member_doc_ids)}")
        if cl.independent_addition_doc_ids:
            print(f"  independent_additions={list(cl.independent_addition_doc_ids)}")

    # 원본 + 복제가 같은 cluster인지 검증 (원본=root, 복제=member)
    if docs and copy_id:
        orig_id = docs[0]["doc_id"]
        copy_member = any(
            orig_id == c.root_doc_id and copy_id in c.member_doc_ids for c in clusters
        )
        print(f"\n원본+복제 한 cluster (near-dup 병합): {'OK' if copy_member else 'FAIL'}")
        if not copy_member:
            import sys
            sys.exit(1)
    print("\n== ALL OK ==")


if __name__ == "__main__":
    main()
