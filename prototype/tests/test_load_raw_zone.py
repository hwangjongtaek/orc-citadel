"""raw 존 읽기 — 샤드 스트리밍 계약 TDD (03 §2.1 레이아웃 개정).

`load_raw_zone` 은 코퍼스 **전량을 RAM 에 상주**시킨다 (RawStore + meta 이중 보유,
2026-09-20 실측 105,271건/content 1.13GB). 1,000만 건에서는 원격 125GB 를 넘긴다.
재처리 입력 경로(`rebuild_zones`)를 제너레이터로 바꿔 그 축을 제거한다.
"""
from __future__ import annotations

import inspect
import pathlib

from orc_citadel.load_raw_zone import iter_raw_zone, load_raw_zone
from orc_citadel.raw_shard import RawShardStore


def _seed(raw: pathlib.Path) -> RawShardStore:
    store = RawShardStore(raw)
    store.append("s1", "http://a/1", b"<html>alpha</html>", {})
    store.append("s1", "http://a/2", b"<html>beta</html>", {})
    store.append("s2", "http://b/9", b"<html>gamma</html>", {})
    store.flush()
    return store


def test_iter_raw_zone_streams_shards(tmp_path):
    """재처리 입력은 제너레이터 — 리스트로 materialize 하지 않는다."""
    raw = tmp_path / "raw"
    _seed(raw)

    docs = iter_raw_zone(raw)
    assert inspect.isgenerator(docs)
    got = {d["url"]: d["content"] for d in docs}
    assert got == {"http://a/1": b"<html>alpha</html>",
                   "http://a/2": b"<html>beta</html>",
                   "http://b/9": b"<html>gamma</html>"}


def test_iter_raw_zone_filters_by_source(tmp_path):
    """source 화이트리스트 — rebuild_zones --source 경로."""
    raw = tmp_path / "raw"
    _seed(raw)

    assert [d["url"] for d in iter_raw_zone(raw, ["s2"])] == ["http://b/9"]


def test_iter_raw_zone_yields_meta_shape_of_pipeline(tmp_path):
    """파이프라인이 읽는 키(doc_id·source_id·url·content)를 그대로 낸다."""
    raw = tmp_path / "raw"
    _seed(raw)

    doc = next(iter_raw_zone(raw, ["s2"]))
    assert set(doc) == {"doc_id", "source_id", "url", "content"}
    assert doc["source_id"] == "s2"
    assert doc["doc_id"].startswith("doc-")


def test_load_raw_zone_reads_shards(tmp_path):
    """스모크 경로의 (store, metas) 계약은 유지하되 입력은 샤드다."""
    raw = tmp_path / "raw"
    _seed(raw)

    store, metas = load_raw_zone(raw)
    assert len(metas) == 3
    assert store.raw_bytes(metas[0]["doc_id"]) == metas[0]["content"]


def test_load_raw_zone_on_missing_dir_is_empty(tmp_path):
    """미생성 raw 디렉터리는 빈 결과 — 첫 런이 예외로 죽지 않는다."""
    store, metas = load_raw_zone(tmp_path / "absent")
    assert metas == []
    assert store.has("doc-000000000000000000000000") is False
