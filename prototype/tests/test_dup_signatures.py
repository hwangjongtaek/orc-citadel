"""MinHash 서명 영속 — 계약 TDD (04 §4.2 재생성 계약, 증분 승격 전제).

서명 계산은 문서당 **12.4ms 실측**(2026-09-20, LSH 밴딩 후 선형)이고 문서 내용에만
의존한다. 매 승격마다 코퍼스 전량을 다시 계산하면 1,000만 건에서 36시간이 그대로
남으므로, 문서당 1회 계산한 값을 존에 남겨 증분 승격이 재사용한다.

`dedup_version` 이 바뀌면(분할·정규화·MinHash 파라미터 변경) 서명은 재생성 대상이라
버전을 함께 저장한다.
"""
from __future__ import annotations

from orc_citadel.curated_zone import CuratedZone
from orc_citadel.dedup import DEDUP_VERSION


def _zone() -> CuratedZone:
    zone = CuratedZone(":memory:")
    zone.initialize()
    return zone


def test_signature_roundtrip():
    zone = _zone()
    zone.persist_signature("doc-a", [3, 1, 4, 1, 5])

    assert zone.signatures() == {"doc-a": [3, 1, 4, 1, 5]}


def test_signature_upsert_is_idempotent():
    """같은 doc 재영속은 중복 행을 만들지 않는다 (결정적 재실행)."""
    zone = _zone()
    zone.persist_signature("doc-a", [1, 2])
    zone.persist_signature("doc-a", [1, 2])

    assert zone.signatures() == {"doc-a": [1, 2]}


def test_signatures_are_scoped_to_dedup_version():
    """다른 dedup_version 의 서명은 섞이지 않는다 — 파라미터 변경 시 재생성 대상."""
    zone = _zone()
    zone.persist_signature("doc-a", [1, 2])
    zone.persist_signature("doc-b", [3, 4], dedup_version="d-next")

    assert zone.signatures() == {"doc-a": [1, 2]}
    assert zone.signatures(dedup_version="d-next") == {"doc-b": [3, 4]}


def test_signatures_default_to_current_dedup_version():
    zone = _zone()
    zone.persist_signature("doc-a", [1, 2], dedup_version=DEDUP_VERSION)

    assert list(zone.signatures(dedup_version=DEDUP_VERSION)) == ["doc-a"]


def test_signatures_on_empty_zone_is_empty():
    assert _zone().signatures() == {}


def test_text_hash_index_groups_exact_duplicates():
    """정확 복제(① content hash) 축은 서명과 함께 남긴다.

    MinHash near 판정은 짧은 본문(MIN_TEXT_CHARS 미만)을 제외하므로, 그 구간의
    정확 복제는 text_hash 로만 묶인다 — 전량 재빌드 경로가 하던 일과 같다.
    """
    zone = _zone()
    zone.persist_signature("doc-a", [1, 2], text_hash="h1")
    zone.persist_signature("doc-b", [3, 4], text_hash="h1")
    zone.persist_signature("doc-c", [5, 6], text_hash="h2")

    assert zone.text_hash_index() == {"h1": ["doc-a", "doc-b"], "h2": ["doc-c"]}


def test_band_candidates_queries_only_matching_buckets():
    """후보 조회는 밴드 키 일치 행만 돌려준다 — 전체 서명을 메모리에 올리지 않는다.

    전량 적재는 1,000만 건에서 서명만 ~5GB(64×BIGINT/doc)라 nightly 마다 코퍼스
    크기에 비례하는 비용이 된다.
    """
    from orc_citadel.dedup import MINHASH_PERMS, band_keys

    half = MINHASH_PERMS // 2
    sig_a = [1] * half + [2] * half
    sig_b = [1] * half + [9] * half          # 앞 절반 밴드를 doc-a 와 공유
    sig_c = [7] * MINHASH_PERMS              # 한 밴드도 공유하지 않음
    zone = _zone()
    zone.persist_signature("doc-a", sig_a, text_hash="ha")
    zone.persist_signature("doc-b", sig_b, text_hash="hb")
    zone.persist_signature("doc-c", sig_c, text_hash="hc")

    got = zone.band_candidates(band_keys(sig_a))

    assert got == {"doc-a": sig_a, "doc-b": sig_b}


def test_band_candidates_is_empty_without_match():
    from orc_citadel.dedup import MINHASH_PERMS, band_keys

    zone = _zone()
    zone.persist_signature("doc-a", [1] * MINHASH_PERMS, text_hash="ha")

    assert zone.band_candidates(band_keys([5] * MINHASH_PERMS)) == {}
