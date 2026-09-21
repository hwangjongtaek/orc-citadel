"""증분 승격 — 계약 TDD (블로커 ③).

nightly 승격은 신규 1건만 들어와도 raw 전량을 다시 빌드한다. dedup 이 O(N²)라
(2026-09-20 실측, LSH 밴딩 전) 1,000만 건에서는 성립하지 않고, 밴딩 후에도 전량
서명 재계산만 36시간이다. 증분 승격은 **아직 존에 없는 문서만** 처리한다.

증분 안전성 (2026-09-20 코드 확인):
- 추출·세그먼트: 문서 로컬 ✅
- 엔터티 해소: `entity_id` 가 (type, canonical, identifiers) 해시라 배치 무관 ✅
- claim·assertion: 결정적 ID upsert ✅
- dedup: 영속 서명 + LSH 후보 조회로 **기존 코퍼스 전체와** 비교 ✅
- canonicalize: 배치 내 승격 claim 끼리만 묶인다 — 정직 표기 (§6.2)
"""
from __future__ import annotations

import pathlib

import pytest

from orc_citadel.curated_zone import CuratedZone
from orc_citadel.duckdb_zone import NormalizedZone
from orc_citadel.incremental_promote import new_doc_ids, promote_incremental
from orc_citadel.raw_shard import RawShardStore

HTML = b"""<html><head>
<title>NVIDIA Conference Call</title>
<meta property="article:published_time" content="2026-08-01T14:00:00+00:00"/>
</head><body><article>
<h1>NVIDIA Sets Conference Call</h1>
<p>NVIDIA will host a conference call on Wednesday, August 26.</p>
<p>NVIDIA powers the data center and announces new accelerator products.</p>
</article></body></html>"""


def _html(tag: str) -> bytes:
    return HTML.replace(b"<h1>", b"<h1>" + tag.encode() + b" ")


@pytest.fixture
def workspace(tmp_path):
    raw, data = tmp_path / "raw", tmp_path / "data"
    data.mkdir()
    return raw, data


def _seed(raw: pathlib.Path, tags: list[str]) -> RawShardStore:
    store = RawShardStore(raw)
    for tag in tags:
        store.append("official-nvidia-news", f"https://e/{tag}", _html(tag), {})
    store.flush()
    return store


def test_new_doc_ids_is_empty_when_zone_matches_shards(workspace):
    raw, data = workspace
    _seed(raw, ["a", "b"])
    promote_incremental(raw, data)

    assert new_doc_ids(raw, data / "oc.duckdb") == []


def test_new_doc_ids_lists_only_unpromoted_docs(workspace):
    raw, data = workspace
    _seed(raw, ["a", "b"])
    promote_incremental(raw, data)
    store = _seed(raw, ["c"])

    got = new_doc_ids(raw, data / "oc.duckdb")

    expected = [d["doc_id"] for d in store.iter_docs() if d["url"].endswith("/c")]
    assert got == expected


def test_promote_creates_zones_on_first_run(workspace):
    raw, data = workspace
    _seed(raw, ["a", "b"])

    summary = promote_incremental(raw, data)

    assert summary["new_docs"] == 2
    zone = NormalizedZone(str(data / "oc.duckdb"))
    try:
        assert len(zone.documents()) == 2
    finally:
        zone.close()


def test_promote_appends_without_reprocessing_existing(workspace):
    """두 번째 런은 신규 1건만 처리하고 기존 2건을 다시 만들지 않는다."""
    raw, data = workspace
    _seed(raw, ["a", "b"])
    promote_incremental(raw, data)
    _seed(raw, ["c"])

    summary = promote_incremental(raw, data)

    assert summary["new_docs"] == 1
    zone = NormalizedZone(str(data / "oc.duckdb"))
    try:
        assert len(zone.documents()) == 3
    finally:
        zone.close()


def test_promote_is_noop_when_nothing_new(workspace):
    raw, data = workspace
    _seed(raw, ["a"])
    promote_incremental(raw, data)

    assert promote_incremental(raw, data) == {"new_docs": 0, "mentions": 0, "claims": 0,
                                              "promoted_claims": 0, "clusters": 0}


def test_promote_persists_signature_per_new_doc(workspace):
    """서명은 문서당 1회 계산해 남긴다 — 다음 승격이 재계산하지 않는다."""
    raw, data = workspace
    _seed(raw, ["a", "b"])
    promote_incremental(raw, data)

    zone = CuratedZone(str(data / "curated.duckdb"))
    try:
        assert len(zone.signatures()) == 2
    finally:
        zone.close()


def test_promote_detects_duplicate_against_previously_promoted_doc(workspace):
    """신규 문서가 **기존 코퍼스**의 문서와 복제 관계면 같은 클러스터로 묶인다.

    배치 내부만 보는 dedup 으로는 잡히지 않는 축 — 영속 서명 + LSH 후보 조회의 존재 이유다.
    """
    raw, data = workspace
    store = RawShardStore(raw)
    store.append("official-nvidia-news", "https://e/1", _html("dup"), {})
    store.flush()
    promote_incremental(raw, data)

    # 같은 본문에 공백 하나만 추가 — 다른 doc_id, 사실상 동일 문서.
    store2 = RawShardStore(raw)
    store2.append("press-semiengineering", "https://e/2", _html("dup") + b" ", {})
    store2.flush()
    promote_incremental(raw, data)

    zone = CuratedZone(str(data / "curated.duckdb"))
    try:
        clusters = zone.clusters()
    finally:
        zone.close()
    merged = [c for c in clusters if len(c["member_doc_ids"]) >= 1]
    assert merged, "기존 코퍼스와의 복제 관계가 클러스터로 남지 않았다"


def test_promote_processes_in_bounded_batches(workspace, monkeypatch):
    """신규분을 한 번에 적재하지 않는다 — 콜드 스타트(전 코퍼스가 신규)에서도 메모리가 유한.

    샤드 스트리밍으로 없앤 RAM 축이 승격 입구에서 되살아나면 의미가 없다.
    """
    import orc_citadel.incremental_promote as ip

    raw, data = workspace
    _seed(raw, [f"t{i}" for i in range(7)])
    monkeypatch.setattr(ip, "BATCH_SIZE", 2)

    sizes = []
    original = ip.run_pipeline
    monkeypatch.setattr(ip, "run_pipeline",
                        lambda metas, zone, **kw: sizes.append(len(metas)) or original(metas, zone, **kw))

    summary = promote_incremental(raw, data)

    assert summary["new_docs"] == 7
    assert max(sizes) <= 2, f"배치 크기 초과: {sizes}"
    assert sum(sizes) == 7


CLAIM_SENTENCE = (b"<p>NVIDIA powers the data center and announces new accelerator products.</p>")


def _article(tag: str, extra: bytes) -> bytes:
    return (b"<html><head><title>" + tag.encode() + b"</title>"
            b'<meta property="article:published_time" content="2026-08-01T14:00:00+00:00"/>'
            b"</head><body><article><h1>" + tag.encode() + b"</h1>"
            + CLAIM_SENTENCE + extra + b"</article></body></html>")


def test_canonicalizes_new_claim_with_previously_promoted_equivalent(workspace):
    """새 문서의 claim 이 **이전 런에서 승격된** 동치 claim 과 한 캐노니컬로 묶인다.

    배치 내부만 보는 캐노니컬화로는 닿지 않는 축 — 증분 승격이 영향받는
    (subject, predicate) 블록을 존에서 되읽어 함께 판정한다 (05 §4.1 blocking).
    """
    raw, data = workspace
    first = RawShardStore(raw)
    first.append("official-nvidia-news", "https://e/1", _article("First", b"<p>Alpha context.</p>"), {})
    first.flush()
    promote_incremental(raw, data)

    second = RawShardStore(raw)
    second.append("press-semiengineering", "https://e/2",
                  _article("Second", b"<p>Totally different trailing context here.</p>"), {})
    second.flush()
    promote_incremental(raw, data)

    zone = CuratedZone(str(data / "curated.duckdb"))
    try:
        canonicals = zone.canonical_claims()
        claims = zone.claims()
    finally:
        zone.close()
    promoted = [c for c in claims if c["status"] == "promoted"]
    assert len(promoted) >= 2, f"두 문서 모두 승격돼야 비교가 성립: {promoted}"
    assert any(len(c["member_claim_ids"]) >= 2 for c in canonicals), \
        f"이전 런의 동치 claim 과 묶이지 않았다: {canonicals}"
