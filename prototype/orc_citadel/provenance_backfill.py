"""근거 기록의 원문 해시 backfill (03 §8).

`pipeline_runner` 가 `content_hash` 를 남기지 않던 시기의 추출 기록은 NULL 이다.
엔진 감사는 그 span 을 통과시키지만 리포트 검증기는 원문에 묶이지 않은 span 을
거른다 — 그래서 그 claim 을 근거로 한 조사는 리포트가 비었다.

원문 저장소(raw shard)에 그 문서가 있으면 그 해시를 채운다. **없으면 지어내지 않고
NULL 로 둔다** (honest-gap §6.2) — 세어서 알린다. 이미 채워진 기록은 건드리지 않아
멱등이다. 이미 저장된 조사 결과(report/audit_trace)는 불변이라 바뀌지 않는다 —
그 조사들은 새로 실행해야 한다.
"""
from __future__ import annotations

import hashlib
import json
import pathlib


def backfill_content_hashes(data_dir: str | pathlib.Path, *,
                            dry_run: bool = True) -> dict:
    from .curated_zone import CuratedZone
    from .raw_shard import RawShardStore

    root = pathlib.Path(data_dir)
    zone = CuratedZone(root / "iceberg")
    try:
        zone.initialize()
        missing = {r["extraction_id"]: r["doc_id"]
                   for r in zone.extraction_records() if not r["content_hash"]}
        hashes: dict[str, str] = {}
        if missing:
            raw = RawShardStore(root / "raw")
            for doc_id in set(missing.values()):
                # 메타의 해시에 기대지 않는다 — 정의가 "원문 바이트의 sha256" 이므로 원문이
                # 있으면 직접 계산한다 (메타에 해시가 없던 옛 샤드도 복구된다).
                try:
                    content = raw.get_content(doc_id)
                except KeyError:
                    continue
                hashes[doc_id] = "sha256:" + hashlib.sha256(content).hexdigest()
        assignments = {eid: hashes[doc] for eid, doc in missing.items() if doc in hashes}
        if assignments and not dry_run:
            zone.set_extraction_content_hashes(assignments)
        return {"missing": len(missing), "resolvable": len(assignments),
                "unresolvable": len(missing) - len(assignments),
                "applied": bool(assignments) and not dry_run}
    finally:
        zone.close()


def main() -> int:
    import argparse
    import os

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=os.environ.get("ORC_DATA_DIR", "data"))
    parser.add_argument("--apply", action="store_true",
                        help="실제로 채운다 (기본은 dry-run — 대상 수만 본다)")
    args = parser.parse_args()
    report = backfill_content_hashes(args.data_dir, dry_run=not args.apply)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"[provenance-backfill] {'적용' if args.apply else 'dry-run'}: "
          f"누락 {report['missing']} · 채움 가능 {report['resolvable']} · "
          f"원문 없음 {report['unresolvable']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
