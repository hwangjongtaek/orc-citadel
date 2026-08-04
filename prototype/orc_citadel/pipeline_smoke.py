"""E2E 파이프라인 스모크 — 실수집 문서 최초 엔드투엔드 (DoD ①).

실제 수집 HTML → extract_html(S3) → parse_document(segment) → MutationLog claim
→ resolve_claim 왕복. 결과 claim.text가 정규화 본문에서 복원되는지 검증하며,
upstream raw HTML과의 연결(해시·URL)을 보인다. (04 §3, 03 §3, DoD ①)
"""
from __future__ import annotations

import hashlib
from collections import Counter

from orc_citadel.identity import doc_id_for
from orc_citadel.load_raw_zone import load_raw_zone
from orc_citadel.mutation_log import MutationLog
from orc_citadel.parse import extract_html, parse_document
from orc_citadel.raw_store import RawStore


def _roundtrip_one(store: RawStore, ml: MutationLog, m: dict) -> dict:
    """문서 하나를 raw→extract→segment→claim→resolve로 왕복. 결과 요약 반환."""
    html = m["content"]
    html_doc_id = m["doc_id"]  # sha256(html)[:24]

    doc = extract_html(html, m["url"])
    # 정규화 clean text layer도 raw에 저장 (immutable, 내용 기반 idempotent)
    text_doc_id = store.put(m["source_id"], m["url"], doc.text.encode())

    segments = parse_document(text_doc_id, doc)
    if not segments:
        return {"ok": False, "reason": "no segments", **m}

    # 첫 번째 문장 segment를 claim source로 선택
    seg = segments[0]
    span = (seg.segment_id, seg.char_start, seg.char_end)
    ml.apply(text_doc_id, "create_claim", source_span=span,
             idempotency_key=f"{html_doc_id}:{seg.segment_id}")
    claim_ids = ml.claims_for(source_span=span)
    if not claim_ids:
        return {"ok": False, "reason": "no claim", **m}
    resolved = store.resolve_claim(claim_ids[0])

    ok = (
        resolved.segment_id == seg.segment_id
        and resolved.text == seg.text
        and resolved.text in doc.text
        and doc_id_for(doc.text.encode()) == text_doc_id
        and resolved.content_hash == text_doc_id
        and store.has(html_doc_id)
    )
    return {
        "ok": ok,
        "source": m["source_id"],
        "url": m["url"],
        "title": doc.title,
        "segments": len(segments),
        "claim_text": resolved.text[:60],
    }


def main() -> None:
    store, metas = load_raw_zone()
    ml = MutationLog(store)
    print(f"== E2E 파이프라인 스모크: {len(metas)} real collected docs ==")

    results = [_roundtrip_one(store, ml, m) for m in metas]
    ok = [r for r in results if r.get("ok")]
    bad = [r for r in results if not r.get("ok")]
    print(f"roundtrip OK: {len(ok)}/{len(results)}")
    print(f"by source: {dict(Counter(r['source'] for r in ok))}")
    print("segments/doc: " + ", ".join(str(r["segments"]) for r in ok))

    print("\n-- claim text (실제 수집 문서에서 왕복 복원된 문장) --")
    for r in ok[:5]:
        print(f"  [{r['source']}] {r['claim_text']!r}")

    if bad:
        print("\n!! 실패:")
        for r in bad:
            print(f"  {r['source']} {r['url'][:60]}: {r.get('reason')}")
        raise SystemExit(1)
    print("\n== ALL OK ==")


if __name__ == "__main__":
    main()
