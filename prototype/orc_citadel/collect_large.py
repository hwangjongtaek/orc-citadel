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
import urllib.error
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
# 페이지당 1000: metadata 경로는 호출 수 자체를 줄이는 것이 anti-bot 429 회피에 유효
# (1만 = API 10회). arXiv API의 대량 슬라이스 사용 패턴.
ARXIV_PAGE = 1000

SOURCES = {
    "official-nvidia-news": ("rss", "https://nvidianews.nvidia.com/rss.xml"),
    "official-amd-ir": ("rss", "https://ir.amd.com/news-events/press-releases/rss"),
    "press-semiengineering": ("rss", "https://semiengineering.com/feed/"),
    # gov-chips-nist 제외 (2026-08-18): NIST 동적 페이지 본문이 매 요청 달라져
    # content-hash 기반 doc_id 가 매 런 새로 발급 → 중복 저장(80→고유 40 실측).
    # URL 기반 idempotency(04 §2.1 hash(source_id,url,fetch_window)) 전환 전까지 보류.
}
ARXIV_QUERY = "cat:cs.CR OR cat:cs.AI OR cat:cs.SE OR cat:cs.AR OR cat:eess.SY"


def arxiv_batches(total: int, page: int = ARXIV_PAGE) -> list[tuple[int, int]]:
    """arXiv 페이징 계획 [(start, max_results)] — 결정적, 재개·배치 제어용.

    순수 함수 — 오프라인 테스트 대상.
    """
    return [(i, min(page, total - i)) for i in range(0, total, page) if total - i > 0]


def arxiv_windows(total: int, windows: int = 10, page: int = ARXIV_PAGE) -> list[tuple[int, int]]:
    """날짜 윈도우 별 페이징 계획 — 단일 쿼리 10k 한계(S50) 우회.

    arXiv 단일 검색 쿼리는 `start > ~10000` 에서 HTTP 500 을 반환(S49+ 실측)하므로,
    총량 `total` 을 `windows` 개의 독립 날짜 윈도우 쿼리로 배분해 **각 윈도우 내 start 는
    항상 < 10k 가 되게** 한다. 각 윈도우 자체는 04 §1.4(metadata CC0) 동일 경로.

    반환 루프 순서: 각 윈도우의 페이지를 순회 — [(start, ε/윈도우), (start, ...)].
    순수 함수 — 오프라인 테스트 대상. windows≤total 가정 시 균등 배분.
    """
    wins = max(1, windows)
    per = max(1, total // wins)  # 윈도우당 할당량 (소진분은 마지막 윈도우로).
    out: list[tuple[int, int]] = []
    for w in range(wins):
        remaining = total - w * per
        if remaining <= 0:
            break
        quota = min(per, remaining)
        # 윈도우 내 페이징 — start 는 0, page, 2*page... 로 최대 10k 미만 유지.
        for s in range(0, quota, page):
            out.append((s, min(page, quota - s)))
    return out


RETRYABLE_HTTP = {429, 500, 502, 503, 504}


class _EmptyPage(Exception):
    """arXiv API가 일시적으로 빈 결과를 반환하는 quirk — transient로 재시도."""


def _with_retry(fn, retries: int = 5):
    """transient HTTP 실패(429/5xx) 지수 backoff 재시도 (01 §4 retry 경로).

    Retry-After 헤더가 있으면 우선, 없으면 30s·2^n (상한 300s). 마지막 시도
    실패는 그대로 전파 — 데이터 결함(4xx 등)은 재시도 대상이 아니다.
    """
    for attempt in range(retries):
        try:
            return fn()
        except urllib.error.HTTPError as e:
            if e.code not in RETRYABLE_HTTP or attempt == retries - 1:
                raise
            ra = (e.headers.get("Retry-After") or "").strip() if e.headers else ""
            delay = float(ra) if ra.isdigit() else min(30.0 * 2 ** attempt, 300.0)
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError, ConnectionError, _EmptyPage):
            # 네트워크 계층 transient (SSL read timeout·DNS·연결 거부·빈 페이지).
            if attempt == retries - 1:
                raise
            time.sleep(min(30.0 * 2 ** attempt, 300.0))


def _get(url: str) -> tuple[bytes, dict]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=25) as resp:
        return resp.read(), dict(resp.headers)


def _save_zone(source_id: str, url: str, content: bytes, meta: dict,
               raw_dir: pathlib.Path | None = None,
               minio_store=None) -> tuple[str, bool]:
    """raw 3-zone 저장 — content-hash idempotency.

    returns (doc_id, created): created=True 새 저장, False 이미 존재(재개 무중복).

    저장 백엔드:
    - `minio_store` 제공 시 → MinIO 객체 스토어(② `MinioRawStore`)에 §2.1 객체 키로 영속.
    - 미제공 시 로컬 fs `data/raw/<source>/doc/<doc_id>/...` (기존 default).
    `meta` 는 fetch.json 에 병합되며 governance(11) 필드 license/robots_allowed 기본값이
    채워진다 (04 §1.4 재배포 제한 정합).
    """
    import hashlib

    if minio_store is not None:
        # MinIO 백엔드 — content-hash doc_id 로 재개 스킵 판별 후 put(② 저장소).
        doc_id = "doc-" + hashlib.sha256(content).hexdigest()[:24]
        existing = minio_store.has(doc_id)
        meta = dict(meta)
        meta.setdefault("license", "unknown")
        meta.setdefault("robots_allowed", True)
        minio_store.put(source_id, url, content, meta)
        return doc_id, not existing

    base = raw_dir or RAW
    doc_id = "doc-" + hashlib.sha256(content).hexdigest()[:24]
    d = base / source_id / "doc" / doc_id
    if d.exists():  # 이미 수집 — 재개 시 스킵 (created=False).
        return doc_id, False
    d.mkdir(parents=True, exist_ok=True)
    (d / "content.bin").write_bytes(content)
    meta.setdefault("license", "unknown")
    meta.setdefault("robots_allowed", True)
    meta.update({"doc_id": doc_id, "url": url,
                 "fetched_at": datetime.now(timezone.utc).isoformat()})
    (d / "fetch.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    return doc_id, True


def collect_arxiv(total: int, windows: int = 0, slo_log=None) -> dict:
    """arXiv 페이징 metadata 수집. return {saved, skipped, errors}.

    04 §1.4 metadata(CC0) 경로: API Atom 응답의 <entry> 원문 XML을 그대로 raw
    문서로 저장한다 — 문서당 abs 페이지 GET 없음(anti-bot 429 회피, 정책 준수).

    S50 — 단일 쿼리의 `start>~10k` HTTP 500 한계를 우회해 대량(10k+)을 수집한다.
    `windows>0` 이면 date_window 로 총량을 나눠 각 날짜 구간을 독립 쿼리(각 start<10k)로
    페이징한다 (S49+ 실측: 10k 한계). 그렇지 않으면 기존 단일 쿼리 배치(arcbatches).

    SLO-05(수집 성공률, 11 §2.3) 측정용 `slo_log`(`SloObservationLog`)가 주입되면
    문서별 시도/성공을 `record_collect` 로 기록한다. 기본 None → 동작 무변경
    (Spec 1.0.0, 관측은 선택 주입).
    """
    conn = ArxivConnector()
    counts = {"saved": 0, "skipped": 0, "errors": 0}
    fetched = 0

    if windows > 0:
        # 날짜 윈도우 별 독립 쿼리 — 각 윈도우는 최신 ~10k 로 배분 (start<10k 유지).
        dateranges = _arxiv_date_windows(windows)
    else:
        dateranges = [None]  # 단일 쿼리 (start 만 증가, 시작 10k 과거 데이터 호환).

    for wi, dw in enumerate(dateranges):
        if fetched >= total:
            break
        # 윈도우 별 최대 할당 ← 총량을 windows 로 균등 배분.
        per_window = max(1, total // max(1, len(dateranges)))
        for start, mx in arxiv_windows(per_window, windows=1, page=ARXIV_PAGE):
            if fetched >= total:
                break
            _sleep_for_arxiv()  # politeness: 페이지 API 호출 전 1 req/3s 대기.

            def _page() -> list:
                cfg = {"query": ARXIV_QUERY, "max_results": mx}
                if dw is not None:
                    cfg["date_window"] = dw
                entries = list(conn.discover_entries(config=cfg, cursor=str(start)))
                if not entries:
                    raise _EmptyPage(f"start={start} window={wi}")
                return entries

            try:
                # 페이지 호출이 10회뿐이므로 재시도 인내를 넉넉히 (호출당 최대 ~22분).
                entries = _with_retry(_page, retries=8)
            except _EmptyPage:
                break  # 재시도에도 빈 페이지 → 이 윈도우 결과 소진.
            except urllib.error.HTTPError:
                # 지속 5xx(재시도 소진) 페이지는 전체 실행을 죽이지 않고 errors 로 집계 후
                # 다음 배치로 계속 — S49+ resumable(한 페이지 때문에 100k 실행 중단 방지).
                counts["errors"] += 1
                continue
            for url, raw in entries:
                if fetched >= total:
                    break
                _doc_id, created = _save_zone(
                    "research-arxiv-cs-cr", url, raw,
                    {"http_status": 200, "content_type": "application/atom+xml;type=entry"},
                )
                fetched += 1
                counts["saved" if created else "skipped"] += 1
                if slo_log is not None:
                    # SLO-05 — fetch 성공한 문서는 저장 성공으로 기록 (시도 1건).
                    slo_log.record_collect("research-arxiv-cs-cr", url, ok=True)
    return counts


def _arxiv_date_windows(n_windows: int, start: str = "202608112359") -> list[tuple[str, str]]:
    """과거로 후진하는 `n_windows` 월 구간 (start,end) — 각 <~10k 결과를 목표.

    결정적 순수 함수 (역사 기반, 2026-08 현재). arXiv 는 start>~10k 에서 500(S50)이므로
    **미수집 과거 연대부터** 윈도우를 흝는다 — 각 윈도우가 단일 쿼리의 10k 한계를
    넘지 않게 1개월 구간으로 잡아, 재실행마다 새 (미수집) 연대를 채워 100k 로 누적한다.
    반환은 최신→과거 순 [("YYYYMMDDHHMM","YYYYMMDDHHMM"), ...] (start 인자는 상한).
    """
    import datetime as _dt

    y, m = int(start[:4]), int(start[4:6])
    out: list[tuple[str, str]] = []
    for _ in range(n_windows):
        if y < 2007:  # arXiv 시작(1991) 이전 방지 — 하한 가드.
            break
        first = _dt.date(y, m, 1)
        # 해당 월 시작·끝 (YYYYMMDD0000 .. 말일 2359).
        start_s = first.strftime("%Y%m%d") + "0000"
        if m == 12:
            last = _dt.date(y, 12, 31)
        else:
            last = _dt.date(y, m + 1, 1) - _dt.timedelta(days=1)
        end_s = last.strftime("%Y%m%d") + "2359"
        out.append((start_s, end_s))
        # 이전 달로 후진.
        if m == 1:
            y, m = y - 1, 12
        else:
            m -= 1
    return out


def _sleep_for_arxiv() -> None:
    time.sleep(ARXIV_INTERVAL)


def collect_rss(feed_url: str, source_id: str, slo_log=None) -> dict:
    """RSS 수집 — 피드 항목을 순회 (피드 길이 유한).

    SLO-05(11 §2.3) 측정용 `slo_log` 주입 시 fetch 성공/실패를 `record_collect`
    로 기록한다. 기본 None → 동작 무변경 (Spec 1.0.0, 선택 주입).
    """
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
            if slo_log is not None:
                slo_log.record_collect(source_id, url, ok=False)
            continue
        _save_zone(source_id, url, content,
                   {"http_status": 200, "content_type": hdrs.get("Content-Type"),
                    "hint_modified": ref.hint_modified.isoformat() if ref.hint_modified else None})
        counts["saved"] += 1
        if slo_log is not None:
            slo_log.record_collect(source_id, url, ok=True)
    return counts


def collect_sec(limit: int = 5, ciks: list[str] | None = None, slo_log=None) -> dict:
    """SEC EDGAR 수집 (S14 커넥터). gov filing index → raw 저장.

    browse-edgar fallback 포함(제한 환경). filing 손으로 원문(HTML/XBRL) 저장 —
    idempotent (content-hash). limit으로 CIK당 filing 수 상한(예의).

    SLO-05(11 §2.3) 측정용 `slo_log` 주입 시 fetch 성공/실패를 `record_collect`
    로 기록한다. 기본 None → 동작 무변경 (Spec 1.0.0, 선택 주입).
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
                if slo_log is not None:
                    slo_log.record_collect("gov-sec-edgar", ref.url, ok=False)
                continue
            _doc_id, created = _save_zone(
                "gov-sec-edgar", ref.url, fr.content,
                {"http_status": fr.http_status,
                 "content_type": fr.response_headers.get("content-type")},
            )
            n += 1
            counts["saved" if created else "skipped"] += 1
            if slo_log is not None:
                slo_log.record_collect("gov-sec-edgar", ref.url, ok=True)
    return counts


def main() -> None:
    p = argparse.ArgumentParser(description="대형 resumable 수집 러너")
    p.add_argument("--limit", type=int, default=300,
                   help="arXiv 총 목표 문서 수 (데모 기본 300, 전체 1만은 10000)")
    p.add_argument("--skip-rss", action="store_true")
    p.add_argument("--sec", type=int, default=0,
                   help="SEC gov filing CIK당 수집 수 (기본 0=없음)")
    p.add_argument("--windows", type=int, default=0,
                   help="arXiv 날짜 윈도우 수 (S50 10k 한계 우회 — 과거 연대 채움. "
                        "0=단일 쿼리)")
    args = p.parse_args()

    print(f"== 대형 수집 러너 (limit={args.limit}, windows={args.windows}) ==")
    RAW.mkdir(parents=True, exist_ok=True)

    if not args.skip_rss:
        for source_id, (kind, url) in SOURCES.items():
            print(f"[{source_id}] RSS 수집")
            c = collect_rss(url, source_id)
            print(f"  -> {c}")

    print(f"[research-arxiv-cs-cr] arXiv metadata 페이징 수집 (total={args.limit}, "
          f"windows={args.windows}, 페이지당 1 req/3s)")
    c = collect_arxiv(args.limit, windows=args.windows)
    print(f"  -> {c}")

    if args.sec:
        print(f"[gov-sec-edgar] SEC filing 수집 (CIK당 {args.sec})")
        c = collect_sec(args.sec)
        print(f"  -> {c}")

    total = sum(1 for _ in RAW.rglob("content.bin"))
    print(f"\n== 총 raw 문서: {total} ==")


if __name__ == "__main__":
    main()
