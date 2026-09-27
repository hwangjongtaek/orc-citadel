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


def zone_token(data_dir: Path | str) -> tuple:
    """두 존의 현재 스냅샷 토큰 — 같으면 내보낼 것이 없다."""
    from .curated_zone import CuratedZone
    from .iceberg_zone import NormalizedZone

    root = Path(data_dir) / "iceberg"
    normalized = NormalizedZone(root)
    curated = CuratedZone(root, read_only=True)
    try:
        normalized.initialize()
        return (normalized.snapshot_token(), curated.snapshot_token())
    finally:
        curated.close()
        normalized.close()


def watch_zones(data_dir: Path | str, *, interval: float = 900.0,
                iterations: int | None = None, sleep=None, export=None) -> int:
    """존이 움직였을 때만 parquet 를 다시 내보낸다 (상주 루프).

    DuckDB UI 사이드카는 `data/parquet` 만 읽는데 K5 가 scheduler 를 좁히면서
    갱신 주체가 사라졌다(handoff §8-3) — UI 가 마지막 수동 export 에 고정됐다.
    훅을 scheduler 로 되살리면 ADR-107 경계를 다시 열고, 승격 consumer 에 붙이면
    서빙 계층 export 가 승격 hot path 에 끼어든다. 그래서 전용 프로세스가 갖는다.

    **변경이 없으면 내보내지 않는다.** 전량 export 는 코퍼스와 함께 비싸지므로
    스냅샷 토큰으로 거른다. export 실패는 루프를 죽이지 않는다 — 죽으면 UI 가
    영영 멈춘다.
    """
    import time as _time

    sleep = sleep or _time.sleep
    export = export or (lambda root: safe_snapshot(data_dir=root))
    seen: tuple | None = None
    exported = 0
    count = 0
    while iterations is None or count < iterations:
        count += 1
        try:
            token = zone_token(data_dir)
        except Exception as exc:  # noqa: BLE001 — 카탈로그 장애로 루프가 죽으면 안 된다
            print(f"[parquet] 존 상태 조회 실패(재시도): {exc}", flush=True)
            token = None
        if token is not None and token != seen:
            try:
                export(Path(data_dir))
                seen = token
                exported += 1
                print("[parquet] 스냅샷 갱신 완료", flush=True)
            except Exception as exc:  # noqa: BLE001 — 다음 주기에 다시 시도한다
                print(f"[parquet] 스냅샷 갱신 실패(다음 주기 재시도): {exc}",
                      flush=True)
        if iterations is None or count < iterations:
            sleep(interval)
    return exported


def main() -> int:
    import argparse
    import json
    import os

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=os.environ.get("ORC_DATA_DIR"))
    parser.add_argument(
        "--interval", type=float,
        default=float(os.environ.get("PARQUET_SNAPSHOT_INTERVAL_S", "0")),
        help="0 이면 1회 실행 후 종료, >0 이면 그 주기로 상주하며 변경 시에만 갱신")
    args = parser.parse_args()
    if args.interval > 0:
        data_dir = args.data_dir or (Path(__file__).resolve().parent.parent / "data")
        print(f"[parquet] 스냅샷 워처 시작 (interval={args.interval:.0f}s) — "
              "존이 움직였을 때만 갱신", flush=True)
        watch_zones(data_dir, interval=args.interval)
        return 0
    print(json.dumps(safe_snapshot(data_dir=args.data_dir), ensure_ascii=False,
                     indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
