"""S4 near-dup 후보 탐색을 LSH 밴딩으로 — 계약 TDD (04 §4, ADR-403 유지).

기존 `_cascade_cluster` 는 그룹 대표 × 전체 문서를 전수 비교한다 — 2026-09-20 실측
(arXiv 실문서) 250→4,000건에서 배증비가 2.00→2.41 로 올라가는 O(N²) 이고,
1,000만 건 투영은 선형항 36h + 이차항 ≈4.1년이라 성립하지 않는다.

밴딩은 **판정 자체를 바꾸지 않는다** — 후보를 좁힐 뿐, 병합 여부는 종전처럼
`_jaccard_est >= threshold` 가 정한다 (임계 0.90 유지). 바뀌는 것은 재현율이
확률적이 된다는 점이며, 그 값은 실측해 기록한다.
"""
from __future__ import annotations

from orc_citadel import dedup as dd
from orc_citadel.dedup import Deduplicator, band_keys


def _doc(did, text, pubtime="2026-08-01T00:00:00+00:00", stype="press"):
    return {"doc_id": did, "text": text, "publication_time": pubtime, "source_type": stype}


def _corpus(n: int) -> list[dict]:
    """서로 무관한 n건 — 어떤 쌍도 임계를 넘지 않는다."""
    return [_doc(f"doc-{i:04d}",
                 f"Report {i} covers supplier {i} shipping unit {i} to fab {i} in region {i}. "
                 f"Analysts tracked line {i} and noted capacity {i} for quarter {i} of year {i}.")
            for i in range(n)]


def test_band_keys_are_deterministic_and_cover_signature(tmp_path):
    """같은 서명 → 같은 밴드 키. 밴드는 서명을 빠짐없이 분할한다."""
    sig = list(range(dd.MINHASH_PERMS))

    first, second = band_keys(sig), band_keys(sig)

    assert first == second
    assert len(first) == dd.LSH_BANDS
    covered = [v for _idx, rows in first for v in rows]
    assert covered == sig  # 분할 — 중복·누락 없음


def test_identical_signatures_share_every_band():
    """동일 문서는 모든 밴드에서 같은 버킷 — 후보로 반드시 잡힌다."""
    sig = [i * 7 % 101 for i in range(dd.MINHASH_PERMS)]

    assert band_keys(sig) == band_keys(list(sig))


def test_disjoint_signatures_share_no_band():
    """완전히 다른 서명은 한 밴드도 공유하지 않는다 — 후보에서 빠진다."""
    a = band_keys([0] * dd.MINHASH_PERMS)
    b = band_keys([1] * dd.MINHASH_PERMS)

    assert not (set(a) & set(b))


def test_near_dup_still_merges_through_banding():
    """밴딩을 거쳐도 임계 이상 near-dup 은 같은 클러스터로 남는다 (판정 불변)."""
    base = ("NVIDIA will host a conference call on Wednesday to discuss its financial results. "
            "The results cover the second quarter of fiscal year 2027 which ended July 26 2026. "
            "Executives will take questions from analysts about data center demand and HBM supply.")
    docs = [_doc("doc-a", base), _doc("doc-b", base + " Inc.")]

    clusters = Deduplicator().dedup(docs)

    assert len(clusters) == 1
    assert set(clusters[0].member_doc_ids) | {clusters[0].root_doc_id} == {"doc-a", "doc-b"}


def test_candidate_comparisons_are_far_below_all_pairs(monkeypatch):
    """무관 문서 코퍼스에서 비교 횟수가 전수 비교보다 현저히 적다 — 이차항 제거의 실증."""
    docs = _corpus(120)
    calls = {"n": 0}
    original = dd._jaccard_est

    def counted(a, b):
        calls["n"] += 1
        return original(a, b)

    monkeypatch.setattr(dd, "_jaccard_est", counted)
    Deduplicator().dedup(docs)

    all_pairs = len(docs) * len(docs)
    assert calls["n"] < all_pairs / 10, f"후보 비교 {calls['n']} — 전수 {all_pairs} 대비 축소 부족"


def test_unrelated_corpus_yields_one_cluster_each():
    """후보 축소가 무관 문서를 잘못 묶지 않는다 (정밀도 불변)."""
    docs = _corpus(60)

    clusters = Deduplicator().dedup(docs)

    assert len(clusters) == 60


def test_dedup_exposes_signatures_for_persistence():
    """전량 재빌드 경로도 서명을 남길 수 있어야 한다.

    서명을 증분 경로만 쓰면, full rebuild 이후 `dup_signatures` 가 비어 다음 증분
    승격이 기존 코퍼스와의 복제를 못 본다 — 조용한 품질 저하.
    """
    # MIN_TEXT_CHARS 이상이어야 near 판정 대상 → 서명이 생긴다.
    docs = [_doc(f"doc-{i}", f"Supplier {i} report. " * 30) for i in range(3)]
    sink: dict = {}

    Deduplicator().dedup(docs, signature_sink=sink)

    assert set(sink) == {d["doc_id"] for d in docs}
    signature, text_hash = sink[docs[0]["doc_id"]]
    assert len(signature) == dd.MINHASH_PERMS
    assert len(text_hash) == 64  # sha256 hex
