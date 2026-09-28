"""작은 파일 재작성 — 읽기 비용 회수 (03 §4, handoff §8-1).

2026-09-27 실측: 동일한 400행이 **400파일이면 읽기 545.5ms, 1파일이면 3.9ms**
(140배). 읽기 비용은 스냅샷 수가 아니라 데이터 파일 수에 묶인다. 쓰기 배치화는
앞으로 만들어질 파일 수를 잡았고 snapshot expiry 는 메타데이터·커밋 비용을
정리하지만, 사고 때 이미 쌓인 파일의 읽기 부담은 **둘 다 건드리지 못한다.**

PyIceberg 0.12 에는 `rewrite_data_files` 가 없다. 그래서 여기서는 테이블 전량을
읽어 한 번에 덮어쓴다 — **현행 규모에서만 성립하는 방법이다.** `max_rows` 가드가
그 경계를 코드로 박아둔다. 스케일에서는 다른 엔진(Spark 등)을 들이는 별도 결정이
필요하며, 이 모듈이 그 결정을 대신하지 않는다.

데이터를 통째로 바꾸므로 안전장치가 계약의 중심이다:
- 재작성 전후 **내용 digest 를 비교**한다 — 행 수만으로는 부족하다.
- 검증이 실패하면 **이전 스냅샷으로 롤백**하고 예외를 올린다.
- 이미 압축된 테이블은 아무 커밋도 만들지 않는다 (무의미한 스냅샷 금지).
"""
from __future__ import annotations

import hashlib
import json
import pathlib

# 전량을 메모리에 올리므로 상한이 곧 이 방법의 유효 범위다.
MAX_REWRITE_ROWS = 500_000


class RewriteVerificationFailed(RuntimeError):
    """The rewritten table does not match what was read; the table was rolled back."""


def _digest(arrow, sort_by: tuple[str, ...]) -> str:
    """정렬 후 내용 해시 — 파일 배치가 달라도 같은 내용이면 같은 값."""
    rows = arrow.to_pylist()
    key = list(sort_by) or sorted(arrow.column_names)
    rows.sort(key=lambda row: json.dumps(
        [row.get(column) for column in key], sort_keys=True, default=str))
    return hashlib.sha256(
        json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()


def rewrite_table(table, *, sort_by: tuple[str, ...] = (),
                  max_rows: int = MAX_REWRITE_ROWS, _corrupt: bool = False) -> dict:
    """테이블 전량을 한 번에 다시 써서 데이터 파일을 합친다."""
    from pyiceberg.expressions import AlwaysTrue

    files_before = len(list(table.scan().plan_files()))
    arrow = table.scan().to_arrow()
    if arrow.num_rows > max_rows:
        raise ValueError(
            f"{table.name()[-1]}: {arrow.num_rows}행은 재작성 상한 {max_rows}행을 "
            "넘는다 — 전량을 메모리에 올리는 방법이라 여기까지가 유효 범위다")
    if files_before <= 1:
        return {"rewritten": False, "rows": arrow.num_rows,
                "files_before": files_before, "files_after": files_before}

    expected = _digest(arrow, sort_by)
    previous = table.current_snapshot()
    if _corrupt:  # 검증 실패 경로를 실제로 타보기 위한 테스트 전용 주입
        arrow = arrow.slice(0, max(arrow.num_rows - 1, 0))

    table.overwrite(arrow, overwrite_filter=AlwaysTrue())
    table.refresh()
    actual = _digest(table.scan().to_arrow(), sort_by)
    if actual != expected:
        if previous is not None:
            table.manage_snapshots().rollback_to_snapshot(previous.snapshot_id).commit()
            table.refresh()
        raise RewriteVerificationFailed(
            f"{table.name()[-1]}: 재작성 결과가 원본과 다르다 — 이전 스냅샷으로 "
            "되돌렸다 (데이터는 보존됨)")
    return {"rewritten": True, "rows": arrow.num_rows,
            "files_before": files_before,
            "files_after": len(list(table.scan().plan_files()))}


def compact_zone_tables(data_dir: str | pathlib.Path, *,
                        max_rows: int = MAX_REWRITE_ROWS,
                        dry_run: bool = False) -> dict[str, dict]:
    """두 존의 전 테이블을 훑어 파일이 흩어진 것만 재작성한다."""
    from .curated_zone import _IDENTIFIERS, CuratedZone
    from .iceberg_zone import NormalizedZone

    root = pathlib.Path(data_dir) / "iceberg"
    normalized = NormalizedZone(root)
    curated = CuratedZone(root)
    report: dict[str, dict] = {}
    try:
        normalized.initialize()
        curated.initialize()
        targets = [(curated, name, _IDENTIFIERS[name]) for name in curated.tables()]
        targets += [(normalized, "documents", ("doc_id", "parser_version")),
                    (normalized, "segments", ("segment_id", "parser_version"))]
        for zone, name, sort_by in targets:
            table = zone._table(name)
            if dry_run:
                files = len(list(table.scan().plan_files()))
                report[name] = {"rewritten": False, "files_before": files,
                                "files_after": files}
                continue
            report[name] = rewrite_table(table, sort_by=tuple(sort_by),
                                         max_rows=max_rows)
        return report
    finally:
        curated.close()
        normalized.close()


def main() -> int:
    import argparse
    import os

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=os.environ.get("ORC_DATA_DIR", "data"))
    parser.add_argument("--max-rows", type=int, default=MAX_REWRITE_ROWS)
    parser.add_argument("--apply", action="store_true",
                        help="실제로 재작성한다 (기본은 dry-run — 파일 수만 본다)")
    args = parser.parse_args()
    report = compact_zone_tables(args.data_dir, max_rows=args.max_rows,
                                 dry_run=not args.apply)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    before = sum(row["files_before"] for row in report.values())
    after = sum(row["files_after"] for row in report.values())
    mode = "적용" if args.apply else "dry-run"
    print(f"[compaction] {mode}: 데이터 파일 {before} → {after}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
