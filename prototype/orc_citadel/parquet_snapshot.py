"""DuckDB 존 → parquet 스냅샷 export (specs/ui-overhaul-astryx TS-7, Step 16a).

외부 브라우징 도구(DuckDB UI 사이드카)가 읽을 스냅샷을 만든다. 존의 `.duckdb`
를 외부에서 직접 attach 하는 것은 금지 — 뷰어가 curated.duckdb 를 RW 로 상시
점유하고(viewer._build), DuckDB 는 프로세스 간 단일 writer XOR 다중 reader 라
잠금 충돌이 실측으로 재현된다. 대신 여기서 만든 parquet 만 읽는다.

- **원자 교체**: `<zone>.new` 디렉터리에 전 테이블 export 성공 후에만 live 와
  교체, 직전은 `<zone>.bak`(rebuild_zones._swap 승계) — 읽는 중 반쯤 교체 방지.
- **존 독립·실패 시 직전 유지**: 한 존이 실패해도 다른 존은 진행되고, 실패한
  존의 live 스냅샷은 건드리지 않는다.
- **잠금 폴백**: read_only 접속이 잠금으로 실패하면 정지 파일을 복사해 복사본을
  read_only 로 연다. 쓰기 도중 복사본이 찢어지면 열기가 실패하고 해당 존만
  실패로 남는다(직전 스냅샷 유지) — 비차단 계약과 정합.
- **safe_snapshot 은 절대 raise 하지 않는다** (run_metrics.safe_flush 와 동일
  계약) — 스케줄러 런은 export 실패와 무관하게 성공한다.

수동 재수출(신선도가 필요할 때):  python -m orc_citadel.parquet_snapshot
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

# 존 이름 → data/ 아래 DB 파일명. DuckDB UI 가 읽는 디렉터리 이름이 존 이름.
DEFAULT_ZONES: dict[str, str] = {
    "normalized": "oc.duckdb",
    "curated": "curated.duckdb",
}


def _connect_ro(db_path: Path, scratch: Path):
    """read_only 접속 — 잠금(다른 프로세스 RW 점유) 시 정지 파일 복사 폴백."""
    import duckdb

    try:
        return duckdb.connect(str(db_path), read_only=True)
    except duckdb.Error:
        copy = scratch / db_path.name
        shutil.copy2(db_path, copy)
        wal = db_path.with_suffix(db_path.suffix + ".wal")
        if wal.exists():
            shutil.copy2(wal, scratch / wal.name)
        return duckdb.connect(str(copy), read_only=True)


def _export_zone(db_path: Path, out_dir: Path) -> int:
    """존의 모든 테이블을 out_dir 에 COPY. 성공한 테이블 수 반환, 실패는 raise."""
    with tempfile.TemporaryDirectory(dir=out_dir.parent) as scratch:
        conn = _connect_ro(db_path, Path(scratch))
        try:
            tables = [r[0] for r in conn.execute("SHOW TABLES").fetchall()]
            out_dir.mkdir(parents=True, exist_ok=True)
            for t in tables:
                conn.execute(
                    f'COPY "{t}" TO \'{out_dir / f"{t}.parquet"}\' (FORMAT PARQUET)'
                )
        finally:
            conn.close()
    return len(tables)


def _swap(new: Path, live: Path) -> None:
    """rebuild_zones._swap 의 디렉터리판 — live 는 .bak 으로 남긴다."""
    bak = live.with_name(live.name + ".bak")
    if bak.exists():
        shutil.rmtree(bak)
    if live.exists():
        live.rename(bak)
    new.rename(live)


def snapshot_zones(data_dir: Path | str,
                   zones: dict[str, str] | None = None) -> dict:
    """존별 parquet 스냅샷 — 존 단위 원자 교체. 존 실패는 결과에 담고 진행."""
    data = Path(data_dir)
    out_root = data / "parquet"
    out_root.mkdir(parents=True, exist_ok=True)
    result: dict = {"zones": {}}
    for zone, db_name in (zones or DEFAULT_ZONES).items():
        db = data / db_name
        live = out_root / zone
        new = out_root / f"{zone}.new"
        if not db.is_file():
            result["zones"][zone] = {"ok": False, "error": f"{db_name} 없음"}
            continue
        try:
            if new.exists():  # 직전 런이 중간에 죽은 잔재
                shutil.rmtree(new)
            n = _export_zone(db, new)
            _swap(new, live)
            result["zones"][zone] = {"ok": True, "tables": n}
        except Exception as e:  # noqa: BLE001 — 존 독립 실패 격리
            shutil.rmtree(new, ignore_errors=True)
            result["zones"][zone] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return result


def safe_snapshot(*, data_dir: Path | str | None = None,
                  zones: dict[str, str] | None = None) -> dict:
    """비차단 래퍼 — 절대 raise 하지 않는다 (run_metrics.safe_flush 계약)."""
    try:
        if data_dir is None:
            data_dir = Path(__file__).resolve().parent.parent / "data"
        res = snapshot_zones(data_dir, zones=zones)
        res["exported"] = any(z["ok"] for z in res["zones"].values())
        return res
    except Exception as e:  # noqa: BLE001 — 스케줄러 런을 죽이지 않는다
        return {"exported": False, "zones": {}, "error": f"{type(e).__name__}: {e}"}


if __name__ == "__main__":
    import json

    print(json.dumps(safe_snapshot(), ensure_ascii=False, indent=2))
