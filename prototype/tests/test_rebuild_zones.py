"""Rebuild contracts for the shared normalized/curated Iceberg warehouse."""

from __future__ import annotations

import pathlib



def test_build_curated_resets_only_curated_namespace(tmp_path: pathlib.Path) -> None:
    from orc_citadel.curated_zone import CuratedZone
    from orc_citadel.iceberg_zone import NormalizedZone
    from orc_citadel.parse import extract_html
    from scripts.rebuild_zones import build_curated

    root = tmp_path / "iceberg"
    normalized = NormalizedZone(root)
    normalized.initialize()
    raw = b"<html><title>kept</title><p>Normalized survives.</p></html>"
    normalized.persist("source", "https://e/kept", raw,
                       extract_html(raw, "https://e/kept"))
    normalized.close()

    result = build_curated([], root)
    assert result["docs"] == 0
    reopened_normalized = NormalizedZone(root)
    curated = CuratedZone(root)
    try:
        assert reopened_normalized.counts()["documents"] == 1
        assert len(curated.tables()) == 18
    finally:
        reopened_normalized.close()
        curated.close()

def test_build_normalized_publishes_committed_empty_snapshot(tmp_path: pathlib.Path) -> None:
    from orc_citadel.iceberg_zone import NormalizedZone
    from scripts.rebuild_zones import build_normalized

    root = tmp_path / "iceberg"
    out = build_normalized([], root)

    reopened = NormalizedZone(root)
    try:
        assert out["ok"] == 0 and out["fail"] == 0
        assert reopened.counts() == {"documents": 0, "segments": 0}
    finally:
        reopened.close()


def test_rebuild_streams_raw_without_materializing(tmp_path, monkeypatch):
    """재처리는 raw 샤드를 스트리밍으로 두 번 읽는다 — 코퍼스를 RAM 에 올리지 않는다.

    전량 적재(`load_raw_zone`)는 105,271건/1.13GB 실측(2026-09-20)으로 RSS 가 raw
    bytes 와 1:1 이라 1,000만 건에서 원격 125GB 를 넘긴다 (03 §2.1 개정 동기).
    """
    import scripts.rebuild_zones as rz
    from orc_citadel.raw_shard import RawShardStore

    raw, data = tmp_path / "raw", tmp_path / "data"
    data.mkdir()
    store = RawShardStore(raw)
    store.append("s1", "http://a/1", b"<html><body>Alpha Corp ships chips.</body></html>", {})
    store.append("s1", "http://a/2", b"<html><body>Beta Inc builds servers.</body></html>", {})
    store.flush()

    monkeypatch.setattr(rz, "RAW", raw)
    monkeypatch.setattr(rz, "DATA", data)

    # 전량 적재 경로를 아예 들고 있지 않다 (import 되어 있으면 다시 새어든다).
    assert not hasattr(rz, "load_raw_zone")
    assert rz.rebuild() == 0
    assert (data / "iceberg" / "catalog.sqlite").exists()

    from orc_citadel.iceberg_zone import NormalizedZone
    zone = NormalizedZone(data / "iceberg")
    try:
        assert len(zone.documents()) == 2
    finally:
        zone.close()
