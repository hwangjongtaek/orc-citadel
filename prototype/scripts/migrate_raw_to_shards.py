"""per-doc raw 레이아웃 → parquet 샤드 1회 변환 (03 §2.1 개정 이행).

    python -m scripts.migrate_raw_to_shards            # data/raw 전체
    python -m scripts.migrate_raw_to_shards --raw /경로

옛 레이아웃 `<raw>/<source>/doc/<doc_id>/{content.bin,fetch.json}` 을 읽어
`<raw>/<source>/shard-*.parquet` 로 옮긴다. **원본은 지우지 않는다** — 건수·
bytes 를 확인한 뒤 운영자가 지운다. content-hash 가 doc_id 이므로 재실행은
무중복(skipped 로 집계).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

_REPO = pathlib.Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from orc_citadel.raw_shard import RawShardStore  # noqa: E402

RAW = _REPO / "data" / "raw"


def migrate(raw_dir: pathlib.Path = RAW) -> dict:
    """옛 레이아웃을 샤드로 옮기고 {sources, migrated, skipped} 반환."""
    raw_dir = pathlib.Path(raw_dir)
    store = RawShardStore(raw_dir)
    sources: dict[str, int] = {}
    migrated = skipped = 0
    if raw_dir.is_dir():
        for source_dir in sorted(p for p in raw_dir.iterdir() if p.is_dir()):
            doc_root = source_dir / "doc"
            if not doc_root.is_dir():
                continue
            source_id = source_dir.name
            sources[source_id] = 0
            for doc_dir in sorted(doc_root.iterdir()):
                content_bin = doc_dir / "content.bin"
                if not content_bin.is_file():
                    continue
                meta = {}
                fetch_json = doc_dir / "fetch.json"
                if fetch_json.is_file():
                    try:
                        meta = json.loads(fetch_json.read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        meta = {}
                meta = dict(meta) if isinstance(meta, dict) else {}
                url = meta.pop("url", "")
                meta.pop("doc_id", None)
                _doc_id, created = store.append(source_id, url, content_bin.read_bytes(), meta)
                if created:
                    migrated += 1
                    sources[source_id] += 1
                else:
                    skipped += 1
            store.flush()
    return {"sources": sources, "migrated": migrated, "skipped": skipped}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", default=str(RAW), help="raw 존 경로 (기본 data/raw)")
    args = ap.parse_args()
    summary = migrate(pathlib.Path(args.raw))
    for source_id, n in sorted(summary["sources"].items()):
        print(f"  {source_id:<32} {n:>8,}")
    print(f"변환 {summary['migrated']:,}건 · 기존 유지 {summary['skipped']:,}건 "
          f"— 원본 트리는 그대로다 (확인 후 수동 삭제)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
