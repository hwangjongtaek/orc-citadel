"""Stream raw shards into the shared normalized and curated Iceberg warehouse.

Each Iceberg commit is snapshot-atomic. Curated rebuilds reset only namespace
``curated`` and leave normalized tables in the same warehouse untouched.
"""

from __future__ import annotations

import argparse
import pathlib
import resource
import sys
import time
from collections import Counter
from itertools import islice

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from orc_citadel.curated_zone import CuratedZone  # noqa: E402
from orc_citadel.iceberg_zone import NormalizedZone  # noqa: E402
from orc_citadel.load_raw_zone import iter_raw_zone  # noqa: E402
from orc_citadel.raw_shard import RawShardStore  # noqa: E402
from orc_citadel.parse import extract_html  # noqa: E402
from orc_citadel.pipeline_runner import run_pipeline  # noqa: E402

DATA = ROOT / "data"
RAW = DATA / "raw"


def _rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)




def build_normalized(metas, root: pathlib.Path, total: int = 0) -> dict:
    """Commit raw input to Iceberg in bounded batches."""
    zone = NormalizedZone(root)
    zone.initialize()
    t0 = time.perf_counter()
    ok = fail = 0
    pending = []
    for i, m in enumerate(metas, 1):
        try:
            doc = extract_html(m["content"], m["url"])
            pending.append((m["source_id"], m["url"], m["content"], doc))
            ok += 1
        except Exception:
            fail += 1
        if len(pending) == 1_000:
            zone.persist_many(pending)
            pending.clear()
        if i % 5000 == 0:
            _log(f"  normalized {i:>7,}/{total:,}  ok={ok:,} fail={fail:,} "
                 f"rss={_rss_mb():.0f}MB")
    zone.persist_many(pending)
    elapsed = time.perf_counter() - t0
    docs = zone.counts()["documents"]
    zone.close()
    return {"ok": ok, "fail": fail, "documents": docs, "elapsed_s": round(elapsed, 1)}


def build_curated(metas, root: pathlib.Path) -> dict:
    """Rebuild curated tables through the pipeline without touching normalized."""
    zone = CuratedZone(root)
    zone.initialize()
    zone.reset()
    t0 = time.perf_counter()
    result = run_pipeline(metas, zone)
    elapsed = time.perf_counter() - t0
    out = {
        "docs": result.docs, "parse_fail": result.parse_fail,
        "mentions": result.mentions,
        "authoritative_mentions": result.authoritative_mentions,
        "claims": result.claims, "promoted_claims": result.promoted_claims,
        "assertions": len(zone.assertions()), "entities": len(zone.entities()),
        "elapsed_s": round(elapsed, 1),
    }
    zone.close()
    return out


def rebuild(*, limit: int | None = None, sources=None,
            skip_normalized: bool = False, skip_curated: bool = False) -> int:
    """raw 존 → normalized·curated 재적재. 반환값은 종료 코드 (0=성공).

    CLI(`main`)와 nightly 스케줄러가 같이 쓰는 진입점 — argv 파싱과 분리한다.
    """
    _log(f"raw 스캔 — {RAW}")
    t0 = time.perf_counter()
    by_source = Counter(RawShardStore(RAW).count_by_source(sources))
    total = sum(by_source.values())
    if limit:
        total = min(total, limit)
    _log(f"raw {total:,} docs  {time.perf_counter() - t0:.1f}s  rss={_rss_mb():.0f}MB")
    for src, n in sorted(by_source.items()):
        _log(f"  {src:<28} {n:>7,}")
    if not total:
        _log("raw 문서 없음 — 중단")
        return 1

    def _docs():
        """재처리 입력 스트림 — 존마다 새로 연다 (제너레이터는 재사용 불가)."""
        stream = iter_raw_zone(RAW, sources)
        return islice(stream, limit) if limit else stream

    if not skip_normalized:
        root = DATA / "iceberg"
        _log("normalized Iceberg 적재…")
        stats = build_normalized(_docs(), root, total)
        _log(f"normalized 완료 {stats}")

    if not skip_curated:
        root = DATA / "iceberg"
        _log("curated Iceberg 적재 (run_pipeline)…")
        stats = build_curated(_docs(), root)
        _log(f"curated 완료 {stats}")
        if stats["promoted_claims"] == 0 and stats["claims"] > 0:
            # 승격 0 은 게이트 배선이 끊겼다는 신호다 (ADR-305 provenance 등).
            _log("⚠ 승격 claim 0 — 게이트 배선 확인 필요.")
            return 2

    _log(f"완료 — 총 {time.perf_counter() - t0:.1f}s  maxRSS {_rss_mb():.0f}MB")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, help="문서 상한 (파일럿)")
    ap.add_argument("--source", action="append", help="source_id 화이트리스트 (반복 가능)")
    ap.add_argument("--skip-normalized", action="store_true")
    ap.add_argument("--skip-curated", action="store_true")
    args = ap.parse_args()
    return rebuild(limit=args.limit, sources=args.source,
                   skip_normalized=args.skip_normalized,
                   skip_curated=args.skip_curated)


if __name__ == "__main__":
    raise SystemExit(main())
