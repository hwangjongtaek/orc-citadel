"""per-doc 레이아웃 → 샤드 1회 변환 — 계약 TDD (03 §2.1 개정 이행).

변환은 raw 존을 건드리는 유일한 경로다. 원본을 지우지 않고(운영자 판단), 변환
결과가 **doc_id 집합·bytes·수집 메타에서 원본과 같음**을 스스로 검증한다.
"""
from __future__ import annotations

import json

from orc_citadel.raw_shard import RawShardStore
from scripts.migrate_raw_to_shards import migrate


def _legacy_doc(raw, source, doc_id, content, meta):
    d = raw / source / "doc" / doc_id
    d.mkdir(parents=True)
    (d / "content.bin").write_bytes(content)
    (d / "fetch.json").write_text(json.dumps(meta), encoding="utf-8")


def test_migrate_preserves_doc_ids_bytes_and_meta(tmp_path):
    raw = tmp_path / "raw"
    _legacy_doc(raw, "s1", "doc-aaa", b"<html>alpha</html>",
                {"url": "http://a/1", "fetched_at": "2026-09-18T00:00:00+00:00",
                 "http_status": 200, "robots_allowed": True, "license": "gov-public"})
    _legacy_doc(raw, "s1", "doc-bbb", b"<html>beta</html>", {"url": "http://a/2"})

    summary = migrate(raw)

    assert summary == {"sources": {"s1": 2}, "migrated": 2, "skipped": 0}
    store = RawShardStore(raw)
    by_url = {r["url"]: r for r in store.fetch_records()}
    assert set(by_url) == {"http://a/1", "http://a/2"}
    assert by_url["http://a/1"]["http_status"] == 200
    assert by_url["http://a/1"]["license"] == "gov-public"
    assert by_url["http://a/1"]["fetched_at"] == "2026-09-18T00:00:00+00:00"
    assert {d["content"] for d in store.iter_docs()} == {b"<html>alpha</html>",
                                                         b"<html>beta</html>"}


def test_migrate_leaves_source_tree_in_place(tmp_path):
    """원본 삭제는 변환기의 일이 아니다 — 검증 후 운영자가 지운다."""
    raw = tmp_path / "raw"
    _legacy_doc(raw, "s1", "doc-aaa", b"x", {"url": "http://a/1"})

    migrate(raw)

    assert (raw / "s1" / "doc" / "doc-aaa" / "content.bin").exists()


def test_migrate_is_idempotent(tmp_path):
    """두 번 돌려도 중복 저장되지 않는다 (content-hash 불변식)."""
    raw = tmp_path / "raw"
    _legacy_doc(raw, "s1", "doc-aaa", b"x", {"url": "http://a/1"})

    migrate(raw)
    second = migrate(raw)

    assert second == {"sources": {"s1": 0}, "migrated": 0, "skipped": 1}
    assert sum(1 for _ in RawShardStore(raw).iter_docs()) == 1


def test_migrate_without_legacy_tree_is_noop(tmp_path):
    """변환할 옛 레이아웃이 없으면 아무 일도 하지 않는다."""
    assert migrate(tmp_path / "raw") == {"sources": {}, "migrated": 0, "skipped": 0}
