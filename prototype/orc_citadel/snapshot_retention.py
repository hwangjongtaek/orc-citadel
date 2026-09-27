"""스냅샷 보존 — 메타데이터 부채 정리 (03 §4, handoff §8-1).

쓰기 경로 배치화로 **새로 쌓이는** 커밋은 잡았지만 사고 때 쌓인 이력은 남는다
(2026-09-27 prod: `claim_candidates` 602 · `mentions` 482, 전 테이블 1,681).
이건 디스크 낭비에 그치지 않는다 — 프로파일에서 커밋마다 table metadata 를
deepcopy 하는 데 **911k 호출 / 17.1s** 가 나왔고, 그 크기는 곧 스냅샷 목록
길이다. 즉 이력이 길수록 읽기도 쓰기도 느려진다.

**정직 경계 (§6.2):** PyIceberg 0.12 는 `expire_snapshots` 만 제공하고 **데이터
파일 병합(compaction)은 없다.** 따라서 이 모듈은 메타데이터 부채를 정리할 뿐,
작은 파일 문제를 해결하지 않는다 — 현재 스냅샷이 참조하는 파일 수는 그대로다.
그 절반은 다른 엔진(Spark 등)을 들이는 별도 결정이다.

이력을 지우는 작업이므로 안전장치가 계약의 중심이다:
- **현재 스냅샷은 지우지 않는다.** PyIceberg 가 branch/tag head 를 보호하고,
  이 모듈도 계획 단계에서 제외한다 (두 겹).
- **나이와 무관하게 최근 N개는 남긴다.** 롤백 여지를 나이가 이기면 안 된다.
- **dry-run 이 기본 검토 수단이다.** 무엇이 사라질지 먼저 보여준다.
"""
from __future__ import annotations

import datetime as dt
import pathlib

RETENTION_DAYS = 7
MIN_RETAINED = 3


def plan_expiry(snapshots, *, now: dt.datetime, retention_days: int,
                min_retained: int, current_id: int | None = None) -> list[int]:
    """지울 스냅샷 id — 순수·결정적 (커밋하지 않는다).

    최신순 `min_retained` 개와 보존 창 안의 스냅샷은 남긴다. `current_id` 는
    라이브러리 보호와 별개로 여기서도 제외한다 (두 겹의 안전장치).
    """
    ordered = sorted(snapshots, key=lambda s: s.timestamp_ms)
    keep_recent = {s.snapshot_id for s in ordered[-min_retained:]} if min_retained else set()
    cutoff_ms = int((now - dt.timedelta(days=retention_days)).timestamp() * 1000)
    return [s.snapshot_id for s in ordered
            if s.timestamp_ms < cutoff_ms
            and s.snapshot_id not in keep_recent
            and s.snapshot_id != current_id]


def _expire_table(table, doomed: list[int]) -> None:
    table.maintenance.expire_snapshots().by_ids(doomed).commit()


def expire_zone_snapshots(data_dir: str | pathlib.Path, *,
                          retention_days: int = RETENTION_DAYS,
                          min_retained: int = MIN_RETAINED,
                          now: dt.datetime | None = None,
                          dry_run: bool = False) -> dict[str, dict[str, int]]:
    """두 존 전 테이블의 오래된 스냅샷을 정리하고 테이블별 결과를 돌려준다."""
    from .curated_zone import CuratedZone
    from .iceberg_zone import NormalizedZone

    now = now or dt.datetime.now(dt.timezone.utc)
    root = pathlib.Path(data_dir) / "iceberg"
    normalized = NormalizedZone(root)
    curated = CuratedZone(root)
    report: dict[str, dict[str, int]] = {}
    try:
        normalized.initialize()
        curated.initialize()
        targets = [(curated, name) for name in curated.tables()]
        targets += [(normalized, name) for name in ("documents", "segments")]
        for zone, name in targets:
            table = zone._table(name)
            snapshots = list(table.snapshots())
            current = table.current_snapshot()
            doomed = plan_expiry(
                snapshots, now=now, retention_days=retention_days,
                min_retained=min_retained,
                current_id=current.snapshot_id if current else None)
            report[name] = {"before": len(snapshots), "expired": len(doomed)}
            if doomed and not dry_run:
                _expire_table(table, doomed)
        return report
    finally:
        curated.close()
        normalized.close()


def main() -> int:
    import argparse
    import json
    import os

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=os.environ.get("ORC_DATA_DIR", "data"))
    parser.add_argument("--retention-days", type=int, default=RETENTION_DAYS)
    parser.add_argument("--min-retained", type=int, default=MIN_RETAINED)
    parser.add_argument("--apply", action="store_true",
                        help="실제로 지운다 (기본은 dry-run — 무엇이 사라질지만 본다)")
    args = parser.parse_args()
    report = expire_zone_snapshots(
        args.data_dir, retention_days=args.retention_days,
        min_retained=args.min_retained, dry_run=not args.apply)
    total = sum(row["expired"] for row in report.values())
    mode = "적용" if args.apply else "dry-run"
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"[retention] {mode}: 스냅샷 {total}개 대상 "
          f"(보존 {args.retention_days}일 · 최소 {args.min_retained}개)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
