"""parquet 스냅샷 export (specs/ui-overhaul-astryx TS-7, Step 16a).

DuckDB 존을 외부 도구(DuckDB UI 사이드카)가 읽을 parquet 로 내보낸다.
설계 계약:

- **`.duckdb` 직접 attach 금지의 대체물**: 뷰어가 curated.duckdb 를 RW 로 상시
  점유한다(실측 — viewer._build). 외부 도구는 parquet 만 읽는다.
- **원자 교체**: `<zone>.new` 디렉터리에 전부 성공한 뒤에만 live 와 교체,
  직전 스냅샷은 `<zone>.bak` — 읽는 중 반쯤 교체된 상태가 없다 (rebuild_zones 승계).
- **실패 시 직전 유지**: export 실패한 존은 live 디렉터리를 건드리지 않는다.
- **비차단**: safe_snapshot 은 예외를 전파하지 않는다 — 런은 항상 성공.
- **잠금 폴백**: read_only 접속이 잠금으로 실패하면 정지 파일 복사 후 복사본을
  연다 (뷰어 RW 점유와 공존).
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from orc_citadel.parquet_snapshot import safe_snapshot, snapshot_zones


def _make_zone_db(path: Path, table: str = "documents", rows: int = 3) -> None:
    c = duckdb.connect(str(path))
    c.execute(f"CREATE TABLE {table} (id INTEGER, name VARCHAR)")
    for i in range(rows):
        c.execute(f"INSERT INTO {table} VALUES (?, ?)", [i, f"row-{i}"])
    c.close()


def test_snapshot_exports_all_tables_per_zone(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    _make_zone_db(data / "oc.duckdb", "documents")
    _make_zone_db(data / "curated.duckdb", "mentions")

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
    _make_zone_db(data / "oc.duckdb")
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
    _make_zone_db(data / "oc.duckdb")
    snapshot_zones(data)
    marker = data / "parquet" / "normalized" / "documents.parquet"
    before = marker.read_bytes()

    # 존 DB 를 깨뜨린다 → export 실패 → 직전 스냅샷 그대로
    (data / "oc.duckdb").write_bytes(b"not a duckdb file")
    res = snapshot_zones(data)
    assert res["zones"]["normalized"]["ok"] is False
    assert res["zones"]["normalized"]["error"]
    assert marker.read_bytes() == before


def test_missing_zone_db_is_honest_skip(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    _make_zone_db(data / "oc.duckdb")
    res = snapshot_zones(data)  # curated.duckdb 없음
    assert res["zones"]["normalized"]["ok"] is True
    assert res["zones"]["curated"]["ok"] is False
    assert "없음" in res["zones"]["curated"]["error"]
    assert not (data / "parquet" / "curated").exists()


def test_locked_db_falls_back_to_file_copy(tmp_path: Path) -> None:
    """뷰어가 RW 점유 중이어도 export 된다 — 정지 파일 복사 폴백."""
    data = tmp_path / "data"
    data.mkdir()
    _make_zone_db(data / "curated.duckdb", "mentions")
    holder = duckdb.connect(str(data / "curated.duckdb"))  # RW 점유 (뷰어 역할)
    try:
        res = snapshot_zones(data, zones={"curated": "curated.duckdb"})
        assert res["zones"]["curated"]["ok"] is True, res
        assert (data / "parquet" / "curated" / "mentions.parquet").is_file()
    finally:
        holder.close()


def test_safe_snapshot_never_raises(tmp_path: Path) -> None:
    res = safe_snapshot(data_dir=tmp_path / "does-not-exist")
    assert res["exported"] is False
    assert res.get("error") or all(
        not z["ok"] for z in res.get("zones", {}).values())


def test_scheduler_hook_is_wired_and_non_blocking(monkeypatch) -> None:
    """run_collect 종료 지점에서 snapshot 훅이 불리고, 실패해도 런이 산다."""
    import scripts.scheduler_runner as sr

    calls: list[str] = []

    def boom(**kw):  # noqa: ANN003
        calls.append("snapshot")
        return {"exported": False, "error": "simulated"}

    monkeypatch.setattr("orc_citadel.parquet_snapshot.safe_snapshot", boom)
    monkeypatch.setattr(
        "scripts.nightly_collect.main", lambda slo_log=None: {"total_new": 0,
                                                              "sources": {}})
    monkeypatch.setattr(sr, "_flush_metrics", lambda *a, **k: None)
    sr.run_collect()  # 예외 없이 끝나야 한다
    assert calls == ["snapshot"]
