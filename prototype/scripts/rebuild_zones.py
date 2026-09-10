"""raw 존 전량 → normalized(oc.duckdb) + curated(curated.duckdb) 재적재.

기존에는 대량 적재 드라이버가 없었다. `persist_smoke`·`pipeline_full_smoke` 는
이름 그대로 스모크이고, 특히 `pipeline_full_smoke` 는 **extraction record 를
영속하지 않아 claim 이 `missing_provenance_record`(ADR-305)로 전부 quarantine 된다**
— 실측: 722 claims 중 promoted 0. 정식 진입점 `run_pipeline` 은 그 단계를 포함하고
같은 입력에서 722/722 를 승격시킨다. 이 스크립트는 정식 경로만 쓴다.

    python -m scripts.rebuild_zones            # 전량
    python -m scripts.rebuild_zones --limit 500  # 상한 (파일럿)
    python -m scripts.rebuild_zones --source official-nvidia-news --source gov-sec-edgar

**기존 DB 를 직접 덮어쓰지 않는다.** `<name>.new` 로 만들고 성공 시에만 교체하며,
직전 파일은 `<name>.bak` 으로 남긴다 — 중간에 죽어도 조회 계층이 살아 있게.

⚠ DuckDB 잠금: viewer·스케줄러와 동시에 실행하지 말 것.
"""

from __future__ import annotations

import argparse
import pathlib
import resource
import shutil
import sys
import time
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from orc_citadel.curated_zone import CuratedZone  # noqa: E402
from orc_citadel.duckdb_zone import NormalizedZone  # noqa: E402
from orc_citadel.load_raw_zone import load_raw_zone  # noqa: E402
from orc_citadel.parse import extract_html  # noqa: E402
from orc_citadel.pipeline_runner import run_pipeline  # noqa: E402

DATA = ROOT / "data"
RAW = DATA / "raw"


def _rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _swap(new: pathlib.Path, live: pathlib.Path) -> None:
    """성공한 산출물만 교체하고 직전 파일은 .bak 으로 남긴다.

    DuckDB WAL 사이드카(`<file>.wal`)도 짝지어 옮긴다 — 구 live 의 WAL 이
    새 DB 옆에 남으면 DuckDB 가 남의 WAL 을 재생하려다 CatalogException 으로
    죽는다 (2026-09-10 prod viewer 크래시 루프 실측).
    """

    def _move_with_wal(src: pathlib.Path, dst: pathlib.Path) -> None:
        shutil.move(str(src), str(dst))
        wal = src.parent / (src.name + ".wal")
        if wal.exists():
            shutil.move(str(wal), str(dst.parent / (dst.name + ".wal")))

    if live.exists():
        _move_with_wal(live, live.with_suffix(live.suffix + ".bak"))
    _move_with_wal(new, live)


def build_normalized(metas, path: pathlib.Path) -> dict:
    """documents/segments — Hall of Witnesses 의 원문 왕복이 여기에 의존한다."""
    path.unlink(missing_ok=True)
    zone = NormalizedZone(str(path))
    zone.initialize()
    t0 = time.perf_counter()
    ok = fail = 0
    for i, m in enumerate(metas, 1):
        try:
            doc = extract_html(m["content"], m["url"])
            zone.persist(m["source_id"], m["url"], m["content"], doc)
            ok += 1
        except Exception:
            fail += 1
        if i % 5000 == 0:
            _log(f"  normalized {i:>7,}/{len(metas):,}  ok={ok:,} fail={fail:,} "
                 f"rss={_rss_mb():.0f}MB")
    elapsed = time.perf_counter() - t0
    docs = len(zone.documents())
    zone.close()
    return {"ok": ok, "fail": fail, "documents": docs, "elapsed_s": round(elapsed, 1)}


def build_curated(metas, path: pathlib.Path) -> dict:
    """mentions/entities/claims/assertions — `run_pipeline` 단일 진입점."""
    path.unlink(missing_ok=True)
    zone = CuratedZone(str(path))
    zone.initialize()
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, help="문서 상한 (파일럿)")
    ap.add_argument("--source", action="append", help="source_id 화이트리스트 (반복 가능)")
    ap.add_argument("--skip-normalized", action="store_true")
    ap.add_argument("--skip-curated", action="store_true")
    args = ap.parse_args()

    _log(f"raw 적재 시작 — {RAW}")
    t0 = time.perf_counter()
    _store, metas = load_raw_zone(RAW)
    if args.source:
        keep = set(args.source)
        metas = [m for m in metas if m["source_id"] in keep]
    if args.limit:
        metas = metas[: args.limit]
    _log(f"raw {len(metas):,} docs  {time.perf_counter() - t0:.1f}s  rss={_rss_mb():.0f}MB")
    by_source = Counter(m["source_id"] for m in metas)
    for src, n in sorted(by_source.items()):
        _log(f"  {src:<28} {n:>7,}")
    if not metas:
        _log("raw 문서 없음 — 중단")
        return 1

    if not args.skip_normalized:
        new = DATA / "oc.duckdb.new"
        _log("normalized 적재…")
        stats = build_normalized(metas, new)
        _log(f"normalized 완료 {stats}")
        _swap(new, DATA / "oc.duckdb")

    if not args.skip_curated:
        new = DATA / "curated.duckdb.new"
        _log("curated 적재 (run_pipeline)…")
        stats = build_curated(metas, new)
        _log(f"curated 완료 {stats}")
        if stats["promoted_claims"] == 0 and stats["claims"] > 0:
            # 승격 0 은 게이트 배선이 끊겼다는 신호다 (ADR-305 provenance 등).
            _log("⚠ 승격 claim 0 — 게이트 배선 확인 필요. 교체하지 않는다.")
            return 2
        _swap(new, DATA / "curated.duckdb")

    _log(f"완료 — 총 {time.perf_counter() - t0:.1f}s  maxRSS {_rss_mb():.0f}MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
