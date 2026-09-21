"""증분 승격 — 존에 아직 없는 문서만 normalized·curated 로 올린다 (블로커 ③).

전량 재빌드(`scripts/rebuild_zones`)는 파서·추출 버전이 바뀌어 **과거 문서의 산출을
다시 만들어야 할 때** 쓰는 경로로 남는다. nightly 수집 직후의 일상 승격은 이 모듈이
맡는다 — 신규 1건 때문에 코퍼스 전체를 다시 읽지 않는다.

단계별 증분 안전성 (2026-09-20 코드 확인):
- 추출·세그먼트 : 문서 로컬.
- 엔터티 해소   : `entity_id` 가 (type, canonical, identifiers) 해시 → 배치 무관·upsert.
- claim·assertion: 결정적 ID upsert.
- dedup         : 영속 서명(`dup_signatures`) + LSH 밴드 조회로 **기존 코퍼스 전체**와 비교.
- canonicalize  : **배치 내 승격 claim 끼리만 묶인다** — 코퍼스 전역 재캐노니컬은
  전량 재빌드 경로에 남아 있다 (honest-gap §6.2).
"""
from __future__ import annotations

import hashlib
import pathlib

import duckdb

from .curated_zone import CuratedZone
from .dedup import (DEDUP_VERSION, JACCARD_THRESHOLD, MIN_TEXT_CHARS, _finalize,
                    _jaccard_est, _minhash, band_keys, shingles)
from .duckdb_zone import NormalizedZone
from .parse import extract_html
from .canonicalize import canonicalize_claims
from .contradiction import find_conflict_candidates
from .extract_claims import ClaimCandidate
from .pipeline_runner import run_pipeline
from .raw_shard import RawShardStore

# 한 번에 존에 올리는 문서 수 — 콜드 스타트(전 코퍼스가 신규)에서도 메모리를 유한하게.
BATCH_SIZE = 1_000


def new_doc_ids(raw_dir, normalized_db) -> list[str]:
    """샤드에는 있으나 normalized 존에 없는 doc_id — DuckDB anti-join (파이썬 적재 없음)."""
    shards = [str(p) for p in sorted(pathlib.Path(raw_dir).glob("*/shard-*.parquet"))]
    if not shards:
        return []
    normalized_db = pathlib.Path(normalized_db)
    con = duckdb.connect()
    try:
        if not normalized_db.exists():
            rows = con.execute(
                "SELECT DISTINCT doc_id FROM read_parquet(?) ORDER BY doc_id", [shards]
            ).fetchall()
            return [r[0] for r in rows]
        # ATTACH 는 prepared parameter 를 받지 않는다 — 경로는 호출자 소유라 이스케이프만.
        con.execute(f"ATTACH '{str(normalized_db)}' AS zone (READ_ONLY)")
        rows = con.execute(
            """SELECT DISTINCT s.doc_id FROM read_parquet(?) s
               WHERE s.doc_id NOT IN (SELECT doc_id FROM zone.documents)
               ORDER BY s.doc_id""",
            [shards],
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        con.close()


def promote_incremental(raw_dir, data_dir) -> dict:
    """신규 문서만 승격하고 요약을 반환한다."""
    raw_dir, data_dir = pathlib.Path(raw_dir), pathlib.Path(data_dir)
    empty = {"new_docs": 0, "mentions": 0, "claims": 0, "promoted_claims": 0, "clusters": 0}
    ids = new_doc_ids(raw_dir, data_dir / "oc.duckdb")
    if not ids:
        return empty

    store = RawShardStore(raw_dir)
    normalized = NormalizedZone(str(data_dir / "oc.duckdb"))
    curated = CuratedZone(str(data_dir / "curated.duckdb"))
    totals = dict(empty)
    try:
        normalized.initialize()
        curated.initialize()
        for batch in _batched(ids, BATCH_SIZE):
            metas = []
            texts: dict[str, str] = {}
            for doc in store.iter_docs(doc_ids=batch):
                try:
                    parsed = extract_html(doc["content"], doc["url"])
                except Exception:
                    continue
                normalized.persist(doc["source_id"], doc["url"], doc["content"], parsed)
                texts[doc["doc_id"]] = parsed.text
                metas.append(doc)
            if not metas:
                continue
            # dedup 은 영속 서명으로 직접 수행한다 — 배치 내부만 보는 기본 경로는 끈다.
            result = run_pipeline(metas, curated, dedup=False, reconcile=False)
            totals["new_docs"] += len(metas)
            totals["mentions"] += result.mentions
            totals["claims"] += result.claims
            totals["promoted_claims"] += result.promoted_claims
            totals["clusters"] += _dedup_against_corpus(curated, normalized, texts)
            _reconcile_against_corpus(curated, [m["doc_id"] for m in metas])
        return totals
    finally:
        curated.close()
        normalized.close()


def _batched(items: list[str], size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _claim_from_row(row: dict) -> ClaimCandidate:
    """존 행 → ClaimCandidate (캐노니컬·모순 판정 입력 복원)."""
    return ClaimCandidate(
        claim_candidate_id=row["claim_candidate_id"], doc_id=row["doc_id"],
        predicate=row["predicate"], subject_id=row["subject_id"],
        object_id=row["object_id"], object_literal=row["object_literal"],
        modality=row["modality"], polarity=row["polarity"],
        confidence=row["confidence"], seg_order=row["seg_order"],
        char_start=row["char_start"], char_end=row["char_end"],
        surface_fragment=row["surface_fragment"] or "",
        event_type_hint=row["event_type_hint"], status=row["status"],
        ontology_version=row["ontology_version"],
        extraction_model=row["extraction_model"])


def _reconcile_against_corpus(curated: CuratedZone, doc_ids: list[str]) -> None:
    """신규 claim 을 **기존 코퍼스의 같은 블록** claim 과 함께 캐노니컬화·모순 판정한다.

    배치 내부만 보면 이전 런에서 승격된 동치 claim 과 영영 묶이지 않는다. 블록
    ((subject, predicate), 05 §4.1)은 캐노니컬·모순이 공유하는 축이라 한 번만 되읽는다.
    """
    blocks = {(row["subject_id"], row["predicate"])
              for doc_id in doc_ids for row in curated.claims(doc_id)
              if row["subject_id"]}
    if not blocks:
        return
    block_list = sorted(blocks)
    promoted = [_claim_from_row(r)
                for r in curated.claims_in_blocks(block_list, status="promoted")]
    if promoted:
        for cc in canonicalize_claims(promoted):
            curated.persist_canonical(cc)
            for claim_id in cc.member_claim_ids:
                curated.set_claim_canonical(claim_id, cc.canonical_claim_id)
    everything = [_claim_from_row(r) for r in curated.claims_in_blocks(block_list)]
    for conflict in find_conflict_candidates(everything):
        curated.persist_conflict(conflict)


def _dedup_against_corpus(curated: CuratedZone, normalized: NormalizedZone,
                          texts: dict[str, str]) -> int:
    """신규 문서를 기존 코퍼스 전체와 대조해 복제 클러스터를 남긴다.

    후보는 ① 정확 텍스트 해시 일치 ② LSH 밴드 공유 문서로 좁히고, 병합 판정은
    전량 재빌드 경로와 같은 `_jaccard_est >= JACCARD_THRESHOLD` 다.
    """
    groups: list[list[str]] = []
    for doc_id in sorted(texts):
        text = texts[doc_id]
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        members = set(curated.docs_with_text_hash(text_hash))
        sig = _minhash(shingles(text)) if len(text) >= MIN_TEXT_CHARS else None
        if sig is not None:
            # 후보만 SQL 로 가져온다 — 코퍼스 전체 서명을 적재하지 않는다.
            for other, other_sig in sorted(curated.band_candidates(band_keys(sig)).items()):
                if other != doc_id and _jaccard_est(sig, other_sig) >= JACCARD_THRESHOLD:
                    members.add(other)
        curated.persist_signature(doc_id, sig or [], text_hash=text_hash,
                                  dedup_version=DEDUP_VERSION)
        members.discard(doc_id)
        if members:
            groups.append(sorted(members | {doc_id}))

    if not groups:
        return 0
    docs_all = _cluster_doc_meta({m for g in groups for m in g}, normalized, texts)
    for members in groups:
        cluster = _finalize(members, docs_all)
        curated.persist_cluster(
            cluster_id=cluster.cluster_id, root_doc_id=cluster.root_doc_id,
            member_doc_ids=list(cluster.member_doc_ids),
            independent_addition_doc_ids=list(cluster.independent_addition_doc_ids),
            dedup_method=cluster.dedup_method)
    return len(groups)


def _cluster_doc_meta(doc_ids: set[str], normalized: NormalizedZone,
                      texts: dict[str, str]) -> list[dict]:
    """클러스터에 걸린 문서의 root 선정·독립성 판정 입력 (기존 멤버는 존에서 복원)."""
    by_id = {d["doc_id"]: d for d in normalized.documents() if d["doc_id"] in doc_ids}
    out = []
    for doc_id in sorted(doc_ids):
        row = by_id.get(doc_id, {})
        text = texts.get(doc_id)
        if text is None:
            text = " ".join(s["text"] for s in normalized.segments(doc_id))
        publication_time = row.get("publication_time")
        out.append({
            "doc_id": doc_id,
            "text": text,
            "publication_time": publication_time.isoformat()
            if hasattr(publication_time, "isoformat") else (publication_time or ""),
            "source_type": (row.get("source_id") or "").split("-")[0],
        })
    return out
