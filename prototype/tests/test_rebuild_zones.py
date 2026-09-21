"""rebuild_zones — 교체(_swap)가 DuckDB WAL 사이드카를 함께 옮기는지.

2026-09-10 prod 실측 사고: `_swap` 이 `curated.duckdb` 만 교체하고 구 DB 의
`curated.duckdb.wal` 을 방치 → DuckDB 가 새 DB 파일 옆의 남의 WAL 을
재생하려다 CatalogException("Table ... already exists") → viewer 크래시 루프.

계약: live 의 WAL 은 .bak 의 WAL 로 따라가고, new 의 WAL(비정상 종료 잔재)은
교체 후에도 새 live 와 짝이 맞아야 한다 — 교체 후 live 옆에 남의 WAL 금지.
"""

from __future__ import annotations

import pathlib

from scripts.rebuild_zones import _swap


def test_swap_moves_stale_live_wal_aside(tmp_path: pathlib.Path) -> None:
    """구 live 의 WAL 이 새 DB 옆에 남으면 안 된다 — .bak 의 WAL 로 따라간다."""
    live = tmp_path / "curated.duckdb"
    live.write_bytes(b"old-db")
    (tmp_path / "curated.duckdb.wal").write_bytes(b"old-wal")
    new = tmp_path / "curated.duckdb.new"
    new.write_bytes(b"new-db")

    _swap(new, live)

    assert live.read_bytes() == b"new-db"
    assert (tmp_path / "curated.duckdb.bak").read_bytes() == b"old-db"
    # 사고의 핵심: 새 live 옆에 구 WAL 이 남아 있으면 안 된다.
    assert not (tmp_path / "curated.duckdb.wal").exists(), \
        "구 WAL 이 새 DB 와 짝이 되어 재생 충돌 (2026-09-10 prod 사고)"
    assert (tmp_path / "curated.duckdb.bak.wal").read_bytes() == b"old-wal"


def test_swap_carries_new_wal_to_live_name(tmp_path: pathlib.Path) -> None:
    """new 가 WAL 을 남긴 채 교체되면(비정상 종료) 새 이름과 짝이 맞아야 한다."""
    live = tmp_path / "curated.duckdb"
    live.write_bytes(b"old-db")
    new = tmp_path / "curated.duckdb.new"
    new.write_bytes(b"new-db")
    (tmp_path / "curated.duckdb.new.wal").write_bytes(b"new-wal")

    _swap(new, live)

    assert live.read_bytes() == b"new-db"
    assert (tmp_path / "curated.duckdb.wal").read_bytes() == b"new-wal"
    assert not (tmp_path / "curated.duckdb.new.wal").exists()


def test_swap_without_existing_live(tmp_path: pathlib.Path) -> None:
    """첫 적재 — live 부재여도 동작 (기존 계약 유지)."""
    live = tmp_path / "curated.duckdb"
    new = tmp_path / "curated.duckdb.new"
    new.write_bytes(b"new-db")

    _swap(new, live)

    assert live.read_bytes() == b"new-db"


def test_build_normalized_clears_stale_wal(tmp_path: pathlib.Path) -> None:
    """normalized 는 직접 재작성 — 남의 stale WAL 이 남아 있으면 재생 시도로 죽는다."""
    from scripts.rebuild_zones import build_normalized

    path = tmp_path / "oc.duckdb"
    (tmp_path / "oc.duckdb.wal").write_bytes(b"stale-garbage")

    out = build_normalized([], path)

    assert out["ok"] == 0 and out["fail"] == 0
    assert not (tmp_path / "oc.duckdb.wal").exists() or \
        (tmp_path / "oc.duckdb.wal").read_bytes() != b"stale-garbage"


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
    assert (data / "oc.duckdb").exists()

    from orc_citadel.duckdb_zone import NormalizedZone
    zone = NormalizedZone(str(data / "oc.duckdb"))
    try:
        assert len(zone.documents()) == 2
    finally:
        zone.close()
