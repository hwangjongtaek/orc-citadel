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
import sqlite3
import tempfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from itertools import islice

import pyarrow.parquet as pq

from .curated_zone import CuratedZone
from .dedup import (DEDUP_VERSION, JACCARD_THRESHOLD, MIN_TEXT_CHARS, _finalize,
                    _jaccard_est, _minhash, band_keys, shingles)
from .iceberg_zone import NormalizedZone
from .parse import extract_html
from .canonicalize import canonicalize_claims
from .contradiction import find_conflict_candidates
from .extract_claims import ClaimCandidate
from .pipeline_runner import run_pipeline
from .identity import doc_id_for
from .raw_shard import RawShardStore

# 한 번에 존에 올리는 문서 수 — 콜드 스타트(전 코퍼스가 신규)에서도 메모리를 유한하게.
BATCH_SIZE = 1_000

_EMPTY_SUMMARY = {
    "new_docs": 0,
    "mentions": 0,
    "claims": 0,
    "promoted_claims": 0,
    "clusters": 0,
}


@dataclass(frozen=True)
class PromotionInputError(ValueError):
    """A referenced raw document cannot be promoted as valid input."""

    doc_id: str
    reason: str
    source_id: str | None = None

    def __str__(self) -> str:
        prefix = f"{self.source_id}/" if self.source_id is not None else ""
        return f"{prefix}{self.doc_id}: {self.reason}"


class MissingRawDocument(PromotionInputError):
    """The requested content-addressed raw document does not exist."""


class PromotionDataError(PromotionInputError):
    """The requested raw document exists but cannot be parsed."""


def new_doc_ids(raw_dir, normalized_root) -> Iterator[str]:
    """Yield raw doc IDs absent from Iceberg in deterministic order.

    The anti-join lives in a temporary on-disk SQLite database. Arrow streams only
    ``doc_id`` from each raw shard, so cold-start memory stays bounded without a
    Python corpus-sized set.
    """
    shards = sorted(pathlib.Path(raw_dir).glob("*/shard-*.parquet"))
    if not shards:
        return
    zone = NormalizedZone(normalized_root)
    try:
        zone.initialize()
        with tempfile.TemporaryDirectory(prefix="orc-citadel-antijoin-") as scratch:
            conn = sqlite3.connect(pathlib.Path(scratch) / "ids.sqlite")
            conn.execute("CREATE TABLE promoted(doc_id TEXT PRIMARY KEY)")
            conn.execute("CREATE TABLE raw(doc_id TEXT PRIMARY KEY)")
            for chunk in _batched(zone.iter_document_ids(), BATCH_SIZE):
                conn.executemany("INSERT OR IGNORE INTO promoted VALUES (?)",
                                 ((doc_id,) for doc_id in chunk))
            for shard in shards:
                for batch in pq.ParquetFile(shard).iter_batches(
                        batch_size=BATCH_SIZE, columns=["doc_id"]):
                    conn.executemany("INSERT OR IGNORE INTO raw VALUES (?)",
                                     ((doc_id,) for doc_id in batch.column(0).to_pylist()))
            conn.commit()
            cursor = conn.execute(
                "SELECT doc_id FROM raw WHERE NOT EXISTS "
                "(SELECT 1 FROM promoted WHERE promoted.doc_id=raw.doc_id) ORDER BY doc_id")
            while rows := cursor.fetchmany(BATCH_SIZE):
                for (doc_id,) in rows:
                    yield doc_id
            conn.close()
    finally:
        zone.close()


def promote_incremental(raw_dir, data_dir) -> dict:
    """신규 문서만 승격하고 요약을 반환한다."""
    totals = dict(_EMPTY_SUMMARY)
    ids = new_doc_ids(pathlib.Path(raw_dir), pathlib.Path(data_dir) / "iceberg")
    for batch in _batched(ids, BATCH_SIZE):
        result = promote_doc_ids(raw_dir, data_dir, batch)
        for key, value in result.items():
            totals[key] += value
    return totals


def _bounded(items: Iterable, label: str) -> list:
    bounded = list(islice(items, BATCH_SIZE + 1))
    if len(bounded) > BATCH_SIZE:
        raise ValueError(f"{label} batch exceeds BATCH_SIZE={BATCH_SIZE}")
    return bounded


def promote_doc_ids(raw_dir, data_dir, ids: Iterable[str]) -> dict:
    """Promote a bounded set of content IDs for manual callers."""
    requested = list(dict.fromkeys(_bounded(ids, "promotion")))
    if not requested:
        return dict(_EMPTY_SUMMARY)
    for doc_id in requested:
        if not isinstance(doc_id, str) or not doc_id:
            raise MissingRawDocument(str(doc_id), "doc_id must be a non-empty string")

    store = RawShardStore(raw_dir)
    raw_docs: dict[str, dict] = {}
    for doc in store.iter_docs(doc_ids=requested):
        raw_docs.setdefault(doc["doc_id"], doc)
    return _promote_documents(data_dir, requested, raw_docs)


def promote_raw_refs(raw_dir, data_dir,
                     refs: Iterable[tuple[str, str]]) -> dict:
    """Promote bounded exact ``(source_id, doc_id)`` raw references."""
    requested_refs = list(dict.fromkeys(_bounded(refs, "raw reference")))
    if not requested_refs:
        return dict(_EMPTY_SUMMARY)
    for source_id, doc_id in requested_refs:
        if not isinstance(source_id, str) or not source_id:
            raise MissingRawDocument(str(doc_id), "source_id must be a non-empty string")
        if not isinstance(doc_id, str) or not doc_id:
            raise MissingRawDocument(str(doc_id), "doc_id must be a non-empty string")

    store = RawShardStore(raw_dir)
    exact = {
        (doc["source_id"], doc["doc_id"]): doc
        for doc in store.iter_docs(
            source_ids=list(dict.fromkeys(source for source, _ in requested_refs)),
            doc_ids=list(dict.fromkeys(doc_id for _, doc_id in requested_refs)),
        )
    }
    for source_id, doc_id in requested_refs:
        if (source_id, doc_id) not in exact:
            raise MissingRawDocument(
                doc_id, f"raw document not found for source {source_id}", source_id)
    for source_id, doc_id in requested_refs:
        doc = exact[(source_id, doc_id)]
        if doc_id_for(doc["content"]) != doc_id:
            raise PromotionDataError(
                doc_id, "raw content hash does not match doc_id", source_id)

    requested_ids = list(dict.fromkeys(doc_id for _, doc_id in requested_refs))
    canonical: dict[str, dict] = {}
    for doc in store.iter_docs(doc_ids=requested_ids):
        if doc_id_for(doc["content"]) != doc["doc_id"]:
            continue
        current = canonical.get(doc["doc_id"])
        if current is None or (doc["source_id"], doc["url"]) < (
                current["source_id"], current["url"]):
            canonical[doc["doc_id"]] = doc

    # Normalized identity is content-based and has one source/url slot. Resolve
    # every same-content reference to the lexicographically smallest immutable
    # raw provenance, so redelivery order cannot flip normalized metadata.
    groups: list[tuple[dict[str, dict], dict[str, str]]] = []
    for source_id, doc_id in requested_refs:
        doc = canonical[doc_id]
        for raw_docs, error_sources in groups:
            if doc_id not in raw_docs:
                raw_docs[doc_id] = doc
                error_sources[doc_id] = source_id
                break
        else:
            groups.append(({doc_id: doc}, {doc_id: source_id}))

    totals = dict(_EMPTY_SUMMARY)
    for raw_docs, error_sources in groups:
        result = _promote_documents(
            data_dir, list(raw_docs), raw_docs, error_sources=error_sources)
        for key, value in result.items():
            totals[key] += value
    return totals


def _promote_documents(data_dir, requested: list[str],
                       raw_docs: dict[str, dict], *,
                       error_sources: dict[str, str] | None = None) -> dict:
    error_sources = error_sources or {}
    for doc_id in requested:
        doc = raw_docs.get(doc_id)
        if doc is None:
            raise MissingRawDocument(doc_id, "raw document not found")
        if doc_id_for(doc["content"]) != doc_id:
            raise PromotionDataError(
                doc_id, "raw content hash does not match doc_id",
                error_sources.get(doc_id, doc["source_id"]))

    data_dir = pathlib.Path(data_dir)
    normalized = NormalizedZone(data_dir / "iceberg")
    curated = CuratedZone(data_dir / "iceberg")
    try:
        normalized.initialize()
        curated.initialize()
        promoted = {row["doc_id"] for row in normalized.documents(requested)}
        metas = []
        pending = []
        texts: dict[str, str] = {}
        for doc_id in requested:
            doc = raw_docs[doc_id]
            try:
                parsed = extract_html(doc["content"], doc["url"])
            except Exception as exc:
                raise PromotionDataError(
                    doc_id, f"raw document parse failed: {exc}",
                    error_sources.get(doc_id, doc["source_id"])) from exc
            pending.append((doc["source_id"], doc["url"], doc["content"], parsed))
            texts[doc_id] = parsed.text
            metas.append(doc)

        normalized.persist_many(pending)
        # 배치 하나를 커밋 수십~수백 개로 쪼개지 않는다 — curated 쓰기는 행마다
        # Iceberg 스냅샷을 만들었고(2026-09-23 prod: mentions 행 589/스냅샷 476),
        # 그 메타데이터 폭증은 compaction 을 나중에 얹어도 따라잡지 못한다.
        # 배치 안의 읽기(밴드 후보·블록 조회)는 해당 테이블만 먼저 내려 정합을
        # 유지한다 — 배치 내 중복 탐지 동작은 그대로다.
        with curated.batched_writes():
            result = run_pipeline(metas, curated, dedup=False, reconcile=False)
            totals = {
                "new_docs": sum(doc_id not in promoted for doc_id in requested),
                "mentions": result.mentions,
                "claims": result.claims,
                "promoted_claims": result.promoted_claims,
                "clusters": _dedup_against_corpus(curated, normalized, texts),
            }
            _reconcile_against_corpus(curated, [m["doc_id"] for m in metas])
        return dict(_EMPTY_SUMMARY) if promoted == set(requested) else totals
    finally:
        curated.close()
        normalized.close()


def _batched(items: Iterable[str], size: int):
    batch = []
    for item in items:
        batch.append(item)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


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
        assignments: dict[str, str | None] = {}
        for cc in canonicalize_claims(promoted):
            curated.persist_canonical(cc)
            for claim_id in cc.member_claim_ids:
                assignments[claim_id] = cc.canonical_claim_id
        # claim 마다 존을 되읽으면 배치 버퍼가 그때마다 내려간다 — 블록 단위
        # 판정이니 할당도 한 번에 내린다.
        curated.set_claims_canonical(assignments)
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
    # 배치 안에서 이미 처리한 문서는 **존이 아니라 메모리로** 본다. 존을 되읽으면
    # 미커밋 서명을 내리느라 배치가 문서마다 끊기고(문서당 1커밋), 그 flush 가
    # 배치 시간의 대부분을 먹는다 — 코퍼스 175건에서 배치 43.6s 중 40.5s 가
    # 이 루프였다. 가시성은 그대로다: 문서 i 는 여전히 앞선 문서 0..i-1 을 본다.
    seen_signatures: dict[str, list[int]] = {}
    seen_bands: dict[tuple[int, str], list[str]] = {}
    seen_hashes: dict[str, list[str]] = {}
    pending_signatures: list[tuple[str, list[int], str]] = []
    for doc_id in sorted(texts):
        text = texts[doc_id]
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        members = set(curated.docs_with_text_hash(text_hash))
        members.update(seen_hashes.get(text_hash, ()))
        sig = _minhash(shingles(text)) if len(text) >= MIN_TEXT_CHARS else None
        if sig is not None:
            keys = band_keys(sig)
            # 후보만 SQL 로 가져온다 — 코퍼스 전체 서명을 적재하지 않는다.
            candidates = dict(curated.band_candidates(keys))
            for band_idx, rows in keys:
                for other in seen_bands.get((band_idx, repr(tuple(rows))), ()):
                    candidates.setdefault(other, seen_signatures[other])
            for other, other_sig in sorted(candidates.items()):
                if other != doc_id and _jaccard_est(sig, other_sig) >= JACCARD_THRESHOLD:
                    members.add(other)
            seen_signatures[doc_id] = sig
            for band_idx, rows in keys:
                seen_bands.setdefault((band_idx, repr(tuple(rows))), []).append(doc_id)
        seen_hashes.setdefault(text_hash, []).append(doc_id)
        pending_signatures.append((doc_id, sig or [], text_hash))
        members.discard(doc_id)
        if members:
            groups.append(sorted(members | {doc_id}))

    for doc_id, signature, text_hash in pending_signatures:
        curated.persist_signature(doc_id, signature, text_hash=text_hash,
                                  dedup_version=DEDUP_VERSION)

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
    by_id = {d["doc_id"]: d for d in normalized.documents(doc_ids)}
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
