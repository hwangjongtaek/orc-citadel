"""대형 수집 러너 — resumable·idempotent·polite (04 §1.3/§1.4, 1만 문서 목표).

소량 수집(collect_sample)은 신호 검증 6건에 그쳤다. 이 모듈은 **1만 문서 확보**를
위해 같은 3-zone(raw 파일) 저장 계약을 대량 확장한다:
- resumable : 이미 저장된 doc_id는 content-hash 불변식으로 스킵 → 재개 가능.
- idempotent: 동일 bytes는 동일 doc_id (03 §2.1), 재수집 무중복.
- polite    : 샘 rate limit(RssConnector 발견 후 FetchFramework 토큰 버킷) + 선언 UA.
  arXiv는 1 req/3s, SEC는 선언 UA+≤10 req/s (04 §1.3), allow_redistribute=false.

목표 1만은 arXiv 페이징(유일 대량 확장 소스)이 주축 — RSS는 피드 길이로 유한.
`--limit`으로 배치 크기를 제어 (데모는 작게, 전체 1만은 사용자가 실행).
주의: 진짜 1만 수집은 arXiv 1 req/3s로 수 시간 소요 — 이 세션은 러너 구축+실증,
전체 실행은 사용자 인계.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import time
import urllib.request
from datetime import datetime, timezone

import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from orc_citadel.connectors.arxiv import ArxivConnector
from orc_citadel.connectors.rss import RssConnector
from orc_citadel.fetch import FetchFramework

ROOT = pathlib.Path(__file__).resolve().parent.parent  # prototype/
RAW = ROOT / "data" / "raw"

USER_AGENT = "OrcCitadel-Research (prototype; contact research@example.com)"
ARXIV_INTERVAL = 3.0  # 1 req/3s (04 §1.3)
ARXIV_PAGE = 100

SOURCES = {
    "official-nvidia-news": ("rss", "https://nvidianews.nvidia.com/rss.xml"),
    "press-semiengineering": ("rss", "https://semiengineering.com/feed/"),
}
ARXIV_QUERY = "cat:cs.CR OR cat:cs.AI OR cat:cs.SE OR cat:cs.AR OR cat:eess.SY"


def arxiv_batches(total: int, page: int = ARXIV_PAGE) -> list[tuple[int, int]]:
    """arXiv 페이징 계획 [(start, max_results)] — 결정적, 재개·배치 제어용.

    순수 함수 — 오프라인 테스트 대상.
    """
    return [(i, min(page, total - i)) for i in range(0, total, page) if total - i > 0]


def _get(url: str) -> tuple[bytes, dict]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=25) as resp:
        return resp.read(), dict(resp.headers)


def _save_zone(source_id: str, url: str, content: bytes, meta: dict,
               raw_dir: pathlib.Path | None = None) -> tuple[str, bool]:
    """raw 3-zone 저장 — content-hash idempotency.

    returns (doc_id, created): created=True 새 저장, False 이미 존재(재개 무중복).
    raw_dir: 테스트용 재정의 (기본 RAW).
    """
    import hashlib

    base = raw_dir or RAW
    doc_id = "doc-" + hashlib.sha256(content).hexdigest()[:24]
    d = base / source_id / "doc" / doc_id
    if d.exists():  # 이미 수집 — 재개 시 스킵 (created=False).
        return doc_id, False
    d.mkdir(parents=True, exist_ok=True)
    (d / "content.bin").write_bytes(content)
    meta.update({"doc_id": doc_id, "url": url,
                 "fetched_at": datetime.now(timezone.utc).isoformat()})
    (d / "fetch.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    return doc_id, True


def collect_arxiv(total: int) -> dict:
    """arXiv 페이징 수집. return {saved, skipped, errors}.

    `total`을 실제 상한으로 강제한다 — ArxivConnector.discover는 페이지당 최대 100을
    요청하지만, 여기서 총 budget(total)에서 정지해 limit을 지킨다.
    """
    conn = ArxivConnector()
    counts = {"saved": 0, "skipped": 0, "errors": 0}
    fetched = 0
    for start, mx in arxiv_batches(total):
        if fetched >= total:
            break
        for ref in conn.discover(config={"query": ARXIV_QUERY}, cursor=str(start)):
            if fetched >= total:
                break
            try:
                # politeness: 각 진짜 문서 GET 직전 1 req/s 대기 (arXiv).
                _sleep_for_arxiv()
                content, hdrs = _get(ref.url)
            except Exception as e:
                counts["errors"] += 1
                continue
            _doc_id, created = _save_zone(
                "research-arxiv-cs-cr", ref.url, content,
                {"http_status": 200, "content_type": hdrs.get("Content-Type")},
            )
            fetched += 1
            counts["saved" if created else "skipped"] += 1
        time.sleep(ARXIV_INTERVAL)  # page 단위 3초
    return counts


def _sleep_for_arxiv() -> None:
    time.sleep(ARXIV_INTERVAL)


def collect_rss(feed_url: str, source_id: str) -> dict:
    """RSS 수집 — 피드 항목을 순회 (피드 길이 유한)."""
    conn = RssConnector()
    counts = {"saved": 0, "skipped": 0, "errors": 0}
    seen: set[str] = set()
    for ref in conn.discover(feed_url, cursor=None):
        url = ref.url
        if not url.startswith("http") or url in seen:
            continue
        seen.add(url)
        try:
            content, hdrs = _get(url)
        except Exception as e:
            counts["errors"] += 1
            continue
        _save_zone(source_id, url, content,
                   {"http_status": 200, "content_type": hdrs.get("Content-Type"),
                    "hint_modified": ref.hint_modified.isoformat() if ref.hint_modified else None})
        counts["saved"] += 1
    return counts


def collect_sec(limit: int = 5, ciks: list[str] | None = None) -> dict:
    """SEC EDGAR 수집 (S14 커넥터). gov filing index → raw 저장.

    browse-edgar fallback 포함(제한 환경). filing 손으로 원문(HTML/XBRL) 저장 —
    idempotent (content-hash). limit으로 CIK당 filing 수 상한(예의).
    """
    from orc_citadel.connectors.sec_edgar import SecEdgarConnector

    conn = SecEdgarConnector()
    counts = {"saved": 0, "skipped": 0, "errors": 0}
    for cik in ciks or ["1045810"]:
        n = 0
        for ref in conn.discover({"cik": [cik]}, cursor=None):
            if n >= limit:
                break
            try:
                fr = conn.fetch(ref, prior_etag=None)
            except Exception as e:
                counts["errors"] += 1
                continue
            _doc_id, created = _save_zone(
                "gov-sec-edgar", ref.url, fr.content,
                {"http_status": fr.http_status,
                 "content_type": fr.response_headers.get("content-type")},
            )
            n += 1
            counts["saved" if created else "skipped"] += 1
    return counts


def main() -> None:
    p = argparse.ArgumentParser(description="대형 resumable 수집 러너")
    p.add_argument("--limit", type=int, default=300,
                   help="arXiv 총 목표 문서 수 (데모 기본 300, 전체 1만은 10000)")
    p.add_argument("--skip-rss", action="store_true")
    p.add_argument("--sec", type=int, default=0,
                   help="SEC gov filing CIK당 수집 수 (기본 0=없음)")
    args = p.parse_args()

    print(f"== 대형 수집 러너 (limit={args.limit}) ==")
    RAW.mkdir(parents=True, exist_ok=True)

    if not args.skip_rss:
        for source_id, (kind, url) in SOURCES.items():
            print(f"[{source_id}] RSS 수집")
            c = collect_rss(url, source_id)
            print(f"  -> {c}")

    print(f"[research-arxiv-cs-cr] arXiv 페이징 수집 (total={args.limit}, "
          f"1 req/3s) — 수 시간 소요 가능")
    c = collect_arxiv(args.limit)
    print(f"  -> {c}")

    if args.sec:
        print(f"[gov-sec-edgar] SEC filing 수집 (CIK당 {args.sec})")
        c = collect_sec(args.sec)
        print(f"  -> {c}")

    total = sum(1 for _ in RAW.rglob("content.bin"))
    print(f"\n== 총 raw 문서: {total} ==")


if __name__ == "__main__":
    main()
