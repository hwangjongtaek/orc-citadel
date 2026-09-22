"""Atomic Parquet snapshots streamed from normalized and curated Iceberg tables."""
from __future__ import annotations

import shutil
from pathlib import Path

DEFAULT_ZONES: dict[str, str] = {
    "normalized": "iceberg",
    "curated": "iceberg",
}


def _export_normalized(root: Path, out_dir: Path) -> int:
    from .iceberg_zone import NormalizedZone

    zone = NormalizedZone(root)
    try:
        zone.initialize()
        zone.export_parquet(out_dir)
        return len(zone.tables())
    finally:
        zone.close()


def _export_curated(root: Path, out_dir: Path) -> int:
    from .curated_zone import CuratedZone

    zone = CuratedZone(root, read_only=True)
    try:
        zone.export_parquet(out_dir)
        return len(zone.tables())
    finally:
        zone.close()


def _swap(new: Path, live: Path) -> None:
    """Replace one exported zone atomically while retaining its prior snapshot."""
    backup = live.with_name(live.name + ".bak")
    if backup.exists():
        shutil.rmtree(backup)
    if live.exists():
        live.rename(backup)
    new.rename(live)


def snapshot_zones(data_dir: Path | str,
                   zones: dict[str, str] | None = None) -> dict:
    """Export zones independently; one failure does not hide another zone's result."""
    data = Path(data_dir)
    out_root = data / "parquet"
    out_root.mkdir(parents=True, exist_ok=True)
    result: dict = {"zones": {}}
    for zone_name, storage_name in (zones or DEFAULT_ZONES).items():
        storage = data / storage_name
        live = out_root / zone_name
        new = out_root / f"{zone_name}.new"
        if not storage.is_dir():
            result["zones"][zone_name] = {"ok": False, "error": f"{storage_name} 없음"}
            continue
        try:
            if new.exists():
                shutil.rmtree(new)
            count = (_export_normalized(storage, new) if zone_name == "normalized"
                     else _export_curated(storage, new))
            _swap(new, live)
            result["zones"][zone_name] = {"ok": True, "tables": count}
        except Exception as exc:  # noqa: BLE001 — zones fail independently
            shutil.rmtree(new, ignore_errors=True)
            result["zones"][zone_name] = {
                "ok": False, "error": f"{type(exc).__name__}: {exc}",
            }
    return result


def safe_snapshot(*, data_dir: Path | str | None = None,
                  zones: dict[str, str] | None = None) -> dict:
    """Non-raising wrapper used by scheduled metrics flushing."""
    try:
        if data_dir is None:
            data_dir = Path(__file__).resolve().parent.parent / "data"
        result = snapshot_zones(data_dir, zones=zones)
        result["exported"] = any(zone["ok"] for zone in result["zones"].values())
        return result
    except Exception as exc:  # noqa: BLE001 — scheduler runs must survive export failure
        return {"exported": False, "zones": {},
                "error": f"{type(exc).__name__}: {exc}"}


if __name__ == "__main__":
    import json

    print(json.dumps(safe_snapshot(), ensure_ascii=False, indent=2))
