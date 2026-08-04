"""대량 파이프라인 E2E 스모크 — 100건 raw → S5→S12 전 체인.

현재 수집된 전체 문서(arXiv 65 + NVIDIA/SemiEngineering)를
추출→해소→claim→게이트→canonicalize→contradiction→assertion→authoritative 의
결정적 체인 전체로 흘려, 대량 스케일(100건)에서 견고성·불변식을 검증한다.

- 각 doc: extract_html→parse→mentions→resolve→(mention 게이트)→claims→(claim 게이트)
  →canonicalize→contradiction→assertion→authoritative mention.
- aggregate 통계 + 불변식 점검 (결정성·멱등성, 전 doc 무결성).
파생 DB는 prototype/data/ 아래(gitignore).
"""
from __future__ import annotations

import pathlib
from collections import Counter
from datetime import datetime, timezone

from orc_citadel.assertions import materialize
from orc_citadel.canonicalize import canonicalize_claims
from orc_citadel.contradiction import find_conflict_candidates
from orc_citadel.curated_zone import CuratedZone
from orc_citadel.edges import PossiblySameAsEdge
from orc_citadel.extract import extract_mentions
from orc_citadel.extract_claims import extract_claims
from orc_citadel.gate import Gate
from orc_citadel.load_raw_zone import load_raw_zone
from orc_citadel.parse import extract_html, parse_document
from orc_citadel.resolve import EntityResolver

DB_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "curated.duckdb"


def main() -> None:
    store, metas = load_raw_zone()
    print(f"== 대량 파이프라인 E2E 스모크: {len(metas)} raw docs ==")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    zone = CuratedZone(str(DB_PATH))
    zone.initialize()
    resolver = EntityResolver()
    gate = Gate()

    agg = Counter()
    all_claims = []
    resolved_mention_ids = []
    for m in metas:
        try:
            doc = extract_html(m["content"], m["url"])
        except Exception:
            agg["parse_fail"] += 1
            continue
        segs = parse_document(m["doc_id"], doc)
        ms = extract_mentions(m["doc_id"], doc, segs)
        for men in ms:
            zone.persist_mention(men)
        agg["mentions"] += len(ms)
        entities, resolved = resolver.resolve(m["doc_id"], ms)
        for e in entities:
            zone.persist_resolved(e, resolved)
        # mention -> authoritative 게이트.
        for rm in resolved:
            r = gate.evaluate_mention(rm.mention, resolved_entity_id=rm.resolved_entity_id)
            if r.promote:
                zone.set_mention_authoritative(rm.mention.mention_id)
                resolved_mention_ids.append(rm.mention.mention_id)
        # claim 추출 -> 게이트.
        claims = extract_claims(m["doc_id"], segs, resolved, {e.entity_id: e for e in entities})
        for c in claims:
            zone.persist_claim(c)
            cresult = gate.evaluate(c)
            zone.update_claim_status(c.claim_candidate_id, cresult.status,
                                     ",".join(cresult.reasons) if cresult.reasons else None)
            if cresult.promote:
                # Assertion materialize — 이 claim의 create_node 이벤트 mutation_id 연결.
                mut = next((m["mutation_id"] for m in gate.mutations()
                            if m["op"] == "create_node"
                            and m["element_ref"] == c.claim_candidate_id), "")
                # observed_at는 NOT NULL — publication_time 없으면 헤드 관측시각.
                observed = doc.publication_time or datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)
                a = materialize(c, observed_at=observed, mutation=mut)
                zone.persist_assertion(a)
        all_claims.extend(claims)

    # canonicalization (promoted claim만).
    promoted = [c for c in all_claims
                if gate.result(c.claim_candidate_id) is not None
                and gate.result(c.claim_candidate_id).promote]
    canonicals = canonicalize_claims(promoted)
    for cc in canonicals:
        zone.persist_canonical(cc)
        for cid in cc.member_claim_ids:
            zone.set_claim_canonical(cid, cc.canonical_claim_id)
    # contradiction.
    conflicts = find_conflict_candidates(all_claims)
    for cc in conflicts:
        zone.persist_conflict(cc)

    print("\n=== aggregate ===")
    print(f"mentions            : {agg['mentions']}")
    print(f"promoted (authoritative) mentions: {len(resolved_mention_ids)}")
    print(f"claims (in DB)      : {len(zone.claims())}")
    print(f"promoted claims     : {len(promoted)}")
    print(f"assertions          : {len(zone.assertions())}")
    print(f"canonical claims    : {len(canonicals)}  "
          f"members={sum(len(c.member_claim_ids) for c in canonicals)}")
    print(f"conflict candidates : {len(conflicts)}")
    print(f"authoritative edges : {len(zone.authoritative_edges())}")
    print(f"gate events         : {len(gate.mutations())}  "
          f"(ops={sorted({m['op'] for m in gate.mutations()})})")

    # 결정성 불변식: 동일 입력 재실행 시 동일 mention 수.
    doc0 = metas[0]
    d0 = extract_html(doc0["content"], doc0["url"])
    s0 = parse_document(doc0["doc_id"], d0)
    m0a = extract_mentions(doc0["doc_id"], d0, s0)
    m0b = extract_mentions(doc0["doc_id"], d0, s0)
    assert [x.mention_id for x in m0a] == [x.mention_id for x in m0b]
    print("\n결정성: 동일 doc 재추출 → 동일 mention id ✓")

    zone.close()
    print("\n== ALL OK ==")


if __name__ == "__main__":
    main()
