"""Atomic Parquet snapshots streamed from the shared Iceberg warehouse."""

from __future__ import annotations

from pathlib import Path

import duckdb

from orc_citadel.parquet_snapshot import safe_snapshot, snapshot_zones
from orc_citadel.curated_zone import CuratedZone
from orc_citadel.iceberg_zone import NormalizedZone
from orc_citadel.parse import extract_html


def _make_curated(root: Path) -> None:
    zone = CuratedZone(root)
    zone.initialize()
    zone.close()


def _make_normalized(root: Path, rows: int = 3) -> None:
    zone = NormalizedZone(root)
    zone.initialize()
    for i in range(rows):
        raw = f"<html><title>row-{i}</title><p>Body {i}.</p></html>".encode()
        zone.persist("src-test", f"https://e/{i}", raw,
                     extract_html(raw, f"https://e/{i}"))
    zone.close()


def test_snapshot_exports_all_tables_per_zone(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    _make_normalized(data / "iceberg")
    _make_curated(data / "iceberg")

    res = snapshot_zones(data)

    assert res["zones"]["normalized"]["ok"] is True
    assert res["zones"]["curated"]["ok"] is True
    norm = data / "parquet" / "normalized" / "documents.parquet"
    cur = data / "parquet" / "curated" / "mentions.parquet"
    assert norm.is_file() and cur.is_file()
    # parquet 이 실제로 읽힌다 (내용 왕복)
    n = duckdb.connect().execute(
        f"SELECT count(*) FROM read_parquet('{norm}')").fetchone()[0]
    assert n == 3


def test_snapshot_swaps_atomically_and_keeps_bak(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    _make_normalized(data / "iceberg")
    snapshot_zones(data)

    # 두 번째 스냅샷 — 직전 스냅샷은 .bak 으로 남는다
    snapshot_zones(data)
    live = data / "parquet" / "normalized"
    bak = data / "parquet" / "normalized.bak"
    assert live.is_dir() and bak.is_dir()
    assert (bak / "documents.parquet").is_file()
    # 잔재 없는 완결 상태 — .new 가 남아 있으면 교체가 중간에 끊긴 것
    assert not (data / "parquet" / "normalized.new").exists()


def test_failed_zone_keeps_previous_snapshot(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    _make_normalized(data / "iceberg")
    snapshot_zones(data)
    marker = data / "parquet" / "normalized" / "documents.parquet"
    before = marker.read_bytes()

    # Catalog corruption makes export fail while preserving the prior live directory.
    (data / "iceberg" / "catalog.sqlite").write_bytes(b"not a sqlite file")
    res = snapshot_zones(data)
    assert res["zones"]["normalized"]["ok"] is False
    assert res["zones"]["normalized"]["error"]
    assert marker.read_bytes() == before


def test_missing_curated_namespace_is_honest_failure(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    _make_normalized(data / "iceberg")
    res = snapshot_zones(data)
    assert res["zones"]["normalized"]["ok"] is True
    assert res["zones"]["curated"]["ok"] is False
    assert res["zones"]["curated"]["error"]
    assert not (data / "parquet" / "curated").exists()




def test_safe_snapshot_never_raises(tmp_path: Path) -> None:
    res = safe_snapshot(data_dir=tmp_path / "does-not-exist")
    assert res["exported"] is False
    assert res.get("error") or all(
        not z["ok"] for z in res.get("zones", {}).values())


def test_scheduler_collection_does_not_snapshot_async_partial_corpus(monkeypatch) -> None:
    """The promotion consumer owns zone writes, so collection cannot snapshot afterward."""
    import scripts.scheduler_runner as sr

    calls: list[str] = []

    def snapshot_would_race(**kw):  # noqa: ANN003
        calls.append("snapshot")
        return {"exported": True}

    monkeypatch.setattr("orc_citadel.parquet_snapshot.safe_snapshot", snapshot_would_race)
    monkeypatch.setattr(
        "scripts.nightly_collect.main", lambda slo_log=None: {"total_new": 1,
                                                              "sources": {}})
    monkeypatch.setattr(sr, "_flush_metrics", lambda *a, **k: None)
    sr.run_collect()

    assert calls == []
