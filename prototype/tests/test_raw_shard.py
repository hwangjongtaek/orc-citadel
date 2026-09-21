"""raw 존 parquet 샤드 저장 — 계약 TDD (03 §2.1 레이아웃 개정).

doc당 디렉터리+2파일 레이아웃은 1,000만 건에서 inode(3/doc)·전수 스캔(18.9s/103k)·
전량 RAM 상주로 성립하지 않는다 (2026-09-20 실측). 샤드는 같은 불변식을 유지한 채
그 세 축을 바꾼다:
- 동일 bytes → 동일 doc_id, 재저장 no-op (03 §2.1, 불변식 §3-6)
- 기록된 샤드는 수정 금지 — 추가분은 항상 새 샤드 (raw immutable append-only)
- 재처리 입력은 스트리밍 — 코퍼스 전량을 메모리에 올리지 않는다
"""
from __future__ import annotations

import inspect

import pytest

from orc_citadel.identity import doc_id_for
from orc_citadel.raw_shard import RawShardStore


def test_append_roundtrips_content_bytes_and_doc_id(tmp_path):
    """저장 bytes 는 무손실 왕복하고 doc_id 는 기존 content-hash 규칙 그대로다."""
    store = RawShardStore(tmp_path)
    content = b"<html>\xed\x95\x9c\xea\xb8\x80 body</html>"
    doc_id, created = store.append("s1", "http://a/1", content, {})
    store.flush()

    assert created is True
    assert doc_id == doc_id_for(content)
    assert store.get_content(doc_id) == content


def test_same_bytes_appended_twice_is_no_op(tmp_path):
    """동일 bytes 재수집은 created=False·행 미증가 (재개 무중복)."""
    store = RawShardStore(tmp_path)
    store.append("s1", "http://a/1", b"same", {})
    store.flush()
    doc_id, created = store.append("s1", "http://a/1", b"same", {})
    store.flush()

    assert created is False
    assert [d["doc_id"] for d in store.iter_docs()] == [doc_id]


def test_stored_urls_is_scoped_to_source(tmp_path):
    """skip 인덱스는 해당 source 의 URL 만 돌려준다 (04 §2.1 S1 재수집 방지)."""
    store = RawShardStore(tmp_path)
    store.append("s1", "http://a/1", b"x", {})
    store.append("s1", "http://a/2", b"y", {})
    store.append("s2", "http://b/9", b"z", {})
    store.flush()

    assert store.stored_urls("s1") == {"http://a/1", "http://a/2"}
    assert store.stored_urls("s2") == {"http://b/9"}


def test_stored_urls_on_empty_source_is_empty_set(tmp_path):
    """미수집 source 조회는 빈 집합 — 첫 런이 예외로 죽지 않는다."""
    assert RawShardStore(tmp_path).stored_urls("never-collected") == set()


def test_iter_docs_streams_instead_of_materializing(tmp_path):
    """재처리 입력은 제너레이터 — 코퍼스 전량을 리스트로 만들지 않는다."""
    store = RawShardStore(tmp_path, shard_size=2)
    for i in range(5):
        store.append("s1", f"http://a/{i}", f"body-{i}".encode(), {})
    store.flush()

    docs = store.iter_docs()
    assert inspect.isgenerator(docs)
    got = {d["url"]: d["content"] for d in docs}
    assert got == {f"http://a/{i}": f"body-{i}".encode() for i in range(5)}


def test_iter_docs_can_filter_by_source(tmp_path):
    """source 화이트리스트 — rebuild_zones --source 경로가 이걸 쓴다."""
    store = RawShardStore(tmp_path)
    store.append("s1", "http://a/1", b"x", {})
    store.append("s2", "http://b/9", b"z", {})
    store.flush()

    assert [d["source_id"] for d in store.iter_docs(["s2"])] == ["s2"]


def test_shard_rolls_over_at_configured_size(tmp_path):
    """샤드는 shard_size 마다 끊긴다 — 단일 거대 파일도, doc당 파일도 아니다."""
    store = RawShardStore(tmp_path, shard_size=2)
    for i in range(5):
        store.append("s1", f"http://a/{i}", f"body-{i}".encode(), {})
    store.flush()

    shards = sorted((tmp_path / "s1").glob("shard-*.parquet"))
    assert len(shards) == 3  # 2 + 2 + 1
    assert sum(1 for _ in store.iter_docs()) == 5


def test_written_shards_are_never_rewritten(tmp_path):
    """raw 는 immutable append-only — 이미 쓴 샤드의 bytes 는 불변 (03 §2.1)."""
    store = RawShardStore(tmp_path, shard_size=2)
    store.append("s1", "http://a/1", b"one", {})
    store.append("s1", "http://a/2", b"two", {})
    store.flush()
    first = sorted((tmp_path / "s1").glob("shard-*.parquet"))[0]
    before = first.read_bytes()

    store.append("s1", "http://a/3", b"three", {})
    store.flush()

    assert first.read_bytes() == before
    assert len(sorted((tmp_path / "s1").glob("shard-*.parquet"))) == 2


def test_fetch_records_carry_governance_fields(tmp_path):
    """viewer intake·governance 패널이 읽는 필드는 샤드에서 그대로 나온다 (11 §5.4)."""
    store = RawShardStore(tmp_path)
    store.append("s1", "http://a/1", b"x", {"http_status": 200})
    store.flush()

    (record,) = store.fetch_records()
    assert record["source_id"] == "s1"
    assert record["url"] == "http://a/1"
    assert record["http_status"] == 200
    assert record["robots_allowed"] is True   # 기본값 (04 §1.1)
    assert record["license"] == "unknown"     # 기본값 — 미선언을 참으로 만들지 않는다
    assert record["fetched_at"]               # 수집 시각 실측 (Watchtower intake)


def test_get_content_raises_for_unknown_doc(tmp_path):
    """미보유 doc 조회는 조용한 빈 bytes 가 아니라 KeyError (정직 실패)."""
    store = RawShardStore(tmp_path)
    store.append("s1", "http://a/1", b"x", {})
    store.flush()

    with pytest.raises(KeyError):
        store.get_content("doc-000000000000000000000000")


def test_count_by_source_aggregates_without_reading_content(tmp_path):
    """source 별 건수는 집계 쿼리로 — 재처리 로그·viewer 가 전수 스캔 없이 쓴다."""
    store = RawShardStore(tmp_path, shard_size=2)
    for i in range(3):
        store.append("s1", f"http://a/{i}", f"a{i}".encode(), {})
    store.append("s2", "http://b/9", b"b9", {})
    store.flush()

    assert store.count_by_source() == {"s1": 3, "s2": 1}
    assert store.count_by_source(["s2"]) == {"s2": 1}
    assert store.count_by_source(["absent"]) == {}


def test_append_preserves_declared_fetched_at(tmp_path):
    """meta 가 수집 시각을 이미 알고 있으면 그것을 보존한다 (기존 코퍼스 이관 경로).

    미선언이면 현재 시각을 찍는다 — 수집 런의 기존 동작.
    """
    store = RawShardStore(tmp_path)
    store.append("s1", "http://a/1", b"old", {"fetched_at": "2026-09-18T00:00:00+00:00"})
    store.append("s1", "http://a/2", b"new", {})
    store.flush()

    by_url = {r["url"]: r["fetched_at"] for r in store.fetch_records()}
    assert by_url["http://a/1"] == "2026-09-18T00:00:00+00:00"
    assert by_url["http://a/2"] and by_url["http://a/2"] != "2026-09-18T00:00:00+00:00"
