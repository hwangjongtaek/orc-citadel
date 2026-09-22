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
import tempfile
import urllib.error
import urllib.request

import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from orc_citadel.connectors.arxiv import ArxivConnector
from orc_citadel.connectors.rss import RssConnector
from orc_citadel.fetch import FetchFramework
from orc_citadel.raw_shard import RawShardStore
from orc_citadel.event_stream import EventEnvelope
from orc_citadel.collection_outbox import (
    CollectionEventOutbox,
    fetch_correlation_id,
)

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
    "press-tomshardware": ("rss", "https://www.tomshardware.com/feeds/all"),
    "gov-bis-exportcontrol": ("sitemap", "https://www.bis.gov/sitemap.xml"),
    # gov-chips-nist 제외 (2026-08-18): NIST 동적 페이지 본문이 매 요청 달라져
    # content-hash 기반 doc_id 가 매 런 새로 발급 → 중복 저장(80→고유 40 실측).
    # URL 기반 idempotency(04 §2.1 hash(source_id,url,fetch_window)) 전환 전까지 보류.
}

# User-confirmed 2026-09-18: Blizzard permits automated collection and raw
# storage for these official BlizzCon records. Native RSS/sitemap is absent, so
# the reviewed URLs are intentionally explicit and bounded.
SOURCES["official-blizzard-blizzcon-2026"] = (
    "urls",
    [
        "https://news.blizzard.com/en-us/article/24301453/everything-announced-at-blizzcon-2026-opening-ceremony",
        "https://news.blizzard.com/en-us/article/24303675/thats-a-wrap-on-blizzcon-2026",
    ],
)
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
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024
MAX_ARCHIVE_ENTRY_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_EXPANDED_BYTES = 8 * 1024 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 100_000
MAX_ARCHIVE_EXPANSION_RATIO = 200
MAX_ZIP_CENTRAL_DIRECTORY_BYTES = 128 * 1024 * 1024
_ARCHIVE_CHUNK_SIZE = 1024 * 1024


class ArchiveLimitExceeded(ValueError):
    """An archive exceeds the bounded collection resource contract."""




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


def _download_to_file(url: str, output, *, chunk_size: int = 1024 * 1024) -> dict:
    """Retry a bounded streaming download directly into a seekable spool."""
    def download() -> dict:
        output.seek(0)
        output.truncate(0)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=25) as resp:
            headers = dict(resp.headers)
            total = 0
            while chunk := resp.read(chunk_size):
                total += len(chunk)
                if total > MAX_ARCHIVE_BYTES:
                    raise ArchiveLimitExceeded(
                        f"compressed archive exceeds {MAX_ARCHIVE_BYTES} bytes")
                output.write(chunk)
        output.seek(0)
        return headers

    return _with_retry(download)


_SHARD_STORES: dict[pathlib.Path, RawShardStore] = {}


def _shard_store(raw_dir: pathlib.Path | None = None) -> RawShardStore:
    """raw 디렉터리별 샤드 스토어 — 수집 런 동안 쓰기 버퍼를 공유한다."""
    base = pathlib.Path(raw_dir or RAW).resolve()
    if base not in _SHARD_STORES:
        _SHARD_STORES[base] = RawShardStore(base)
    return _SHARD_STORES[base]


def _fetch_meta(source_id: str, url: str, meta: dict, *,
                response_headers: dict | None = None,
                fetch_window: str = "full") -> dict:
    stored = {key: value for key, value in meta.items() if value is not None}
    stored["fetch_window"] = fetch_window
    stored["fetch_correlation_id"] = fetch_correlation_id(
        source_id, url, fetch_window)
    if response_headers:
        stored["response_headers"] = dict(response_headers)
    return stored


def _reconcile_and_publish(source_id: str, event_producer, *,
                           raw_dir: pathlib.Path | None = None,
                           minio_store=None, flush: bool = False) -> None:
    if flush:
        flush_raw(raw_dir, minio_store)
    if event_producer is None:
        return
    store = minio_store if minio_store is not None else _shard_store(raw_dir)
    outbox = CollectionEventOutbox(pathlib.Path(raw_dir or RAW).parent)
    outbox.reconcile(store.iter_records([source_id]))
    while outbox.drain(event_producer):
        pass


def flush_raw(raw_dir: pathlib.Path | None = None, minio_store=None) -> None:
    """Commit pending rows in the selected backend at a collector boundary."""
    (minio_store if minio_store is not None else _shard_store(raw_dir)).flush()


def _event_id(event_type: str, idempotency_key: str) -> str:
    import hashlib

    digest = hashlib.sha256(f"{event_type}:{idempotency_key}".encode()).hexdigest()[:24]
    return f"evt-{digest}"




def _publish_result_cap(config: dict, source_id: str, offset: int,
                        event_producer) -> None:
    if event_producer is None:
        return
    import hashlib
    from datetime import datetime, timezone

    context = {
        "source_id": source_id,
        "window": config.get("fetch_window", config["url"]),
        "limit": int(config["max_offset"]),
        "offset": offset,
    }
    key = "cap:" + hashlib.sha256(
        json.dumps(context, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    event_producer.publish(EventEnvelope(
        event_version=1,
        event_id=_event_id("result_cap_reached", key),
        stage="S1",
        event_type="result_cap_reached",
        status="terminal",
        input_ref=config["url"],
        output_ref=None,
        idempotency_key=key,
        correlation_id="corr-" + key.removeprefix("cap:")[:24],
        attempt_count=0,
        occurred_at=datetime.now(timezone.utc),
        payload=context,
    ))


def _save_zone(source_id: str, url: str, content: bytes, meta: dict,
               raw_dir: pathlib.Path | None = None,
               minio_store=None) -> tuple[str, bool]:
    """raw 3-zone 저장 — content-hash idempotency.

    returns (doc_id, created): created=True 새 저장, False 이미 존재(재개 무중복).

    저장 백엔드:
    - `minio_store` provided: MinIO source-sharded Parquet objects.
    - otherwise: local `data/raw/<source>/shard-*.parquet` objects.
    Both backends buffer rows, so collectors flush their selected store before returning.
    `meta` 의 governance(11) 필드 license/robots_allowed 는 기본값이 채워진다
    (04 §1.4 재배포 제한 정합).
    """
    import hashlib

    if minio_store is not None:
        # MinIO 백엔드 — content-hash doc_id 로 재개 스킵 판별 후 put(② 저장소).
        doc_id = "doc-" + hashlib.sha256(content).hexdigest()[:24]
        existing = minio_store.has(doc_id, source_id=source_id)
        meta = dict(meta)
        meta.setdefault("license", "unknown")
        meta.setdefault("robots_allowed", True)
        minio_store.put(source_id, url, content, meta)
        return doc_id, not existing

    return _shard_store(raw_dir).append(source_id, url, content, meta)


def collect_arxiv(total: int, windows: int = 0, slo_log=None, minio_store=None,
                  event_producer=None) -> dict:
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
    source_id = "research-arxiv-cs-cr"
    _reconcile_and_publish(
        source_id, event_producer, minio_store=minio_store)

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
                fetch_window = f"{dw[0]}/{dw[1]}" if dw is not None else "full"
                _doc_id, created = _save_zone(
                    source_id, url, raw,
                    _fetch_meta(
                        source_id, url,
                        {"http_status": 200,
                         "content_type": "application/atom+xml;type=entry"},
                        fetch_window=fetch_window,
                    ),
                    minio_store=minio_store,
                )
                fetched += 1
                counts["saved" if created else "skipped"] += 1
                if slo_log is not None:
                    # SLO-05 — fetch 성공한 문서는 저장 성공으로 기록 (시도 1건).
                    slo_log.record_collect("research-arxiv-cs-cr", url, ok=True)
    _reconcile_and_publish(
        source_id, event_producer, minio_store=minio_store, flush=True)
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


def collect_rss(feed_url: str, source_id: str, slo_log=None, known_urls=None,
                minio_store=None, event_producer=None) -> dict:
    """RSS 수집 — 피드 항목을 순회 (피드 길이 유한).

    SLO-05(11 §2.3) 측정용 `slo_log` 주입 시 fetch 성공/실패를 `record_collect`
    로 기록한다. 기본 None → 동작 무변경 (Spec 1.0.0, 선택 주입).

    `known_urls`(이전 런 저장 URL 집합, 04 §2.1 S1 idempotency) 제공 시 **이미
    저장된 URL 은 재수집(fetch) 하지 않고 skip** — 동일 URL 의 다른 형식/미세변화
    재수집으로 신규-중복 doc_id 가 생기는 것(§2.2 버전 보존과 무관한 재-harvest) 을
    방지한다. content-hash dedup(S2)과 달리 URL 기준 재수집 차단.
    """
    conn = RssConnector()
    counts = {"saved": 0, "skipped": 0, "errors": 0}
    seen: set[str] = set()
    known = known_urls or set()
    _reconcile_and_publish(
        source_id, event_producer, minio_store=minio_store)
    for ref in conn.discover(feed_url, cursor=None):
        url = ref.url
        if not url.startswith("http") or url in seen:
            continue
        seen.add(url)
        if url in known:  # S1 — 이미 이전 런 저장 URL → 재수집 skip (04 §2.1).
            counts["skipped"] += 1
            continue
        try:
            content, hdrs = _get(url)
        except Exception as e:
            counts["errors"] += 1
            if slo_log is not None:
                slo_log.record_collect(source_id, url, ok=False)
            continue
        _save_zone(
            source_id, url, content,
            _fetch_meta(
                source_id, url,
                {"http_status": 200,
                 "hint_modified": ref.hint_modified.isoformat()
                 if ref.hint_modified else None},
                response_headers=hdrs,
            ),
            minio_store=minio_store,
        )
        counts["saved"] += 1
        if slo_log is not None:
            slo_log.record_collect(source_id, url, ok=True)
    _reconcile_and_publish(
        source_id, event_producer, minio_store=minio_store, flush=True)
    return counts


def collect_sitemap(sitemap_url: str, source_id: str, slo_log=None, known_urls=None,
                    minio_store=None, event_producer=None) -> dict:
    """sitemap 기반 정책 소스 수집 (BIS 등 RSS 없는 gov, 04 §1.4 신규).

    `SitemapConnector.discover` 로 sitemap `<loc>` 을 열거 → 각 URL `_get`·`_save_zone`.
    RSS 커넥터 통합 수집과 동일: robots 개방 + sitemap 정적 XML + content-hash/URL
    idempotency(S1·S2). `known_urls`(이전 런 저장 URL) 제공 시 이미 저장 URL 은
    재수집 하지 않고 skip (04 §2.1).
    """
    from orc_citadel.connectors.sitemap import SitemapConnector

    conn = SitemapConnector()
    counts = {"saved": 0, "skipped": 0, "errors": 0}
    seen: set[str] = set()
    known = known_urls or set()
    _reconcile_and_publish(
        source_id, event_producer, minio_store=minio_store)
    for ref in conn.discover(sitemap_url, cursor=None):
        url = ref.url
        if not url.startswith("http") or url in seen:
            continue
        seen.add(url)
        if url in known:  # S1 — 이미 이전 런 저장 URL → 재수집 skip (04 §2.1).
            counts["skipped"] += 1
            continue
        try:
            content, hdrs = _get(url)
        except Exception:
            counts["errors"] += 1
            if slo_log is not None:
                slo_log.record_collect(source_id, url, ok=False)
            continue
        _save_zone(
            source_id, url, content,
            _fetch_meta(
                source_id, url,
                {"http_status": 200,
                 "hint_modified": ref.hint_modified.isoformat()
                 if ref.hint_modified else None},
                response_headers=hdrs,
            ),
            minio_store=minio_store,
        )
        counts["saved"] += 1
        if slo_log is not None:
            slo_log.record_collect(source_id, url, ok=True)
    _reconcile_and_publish(
        source_id, event_producer, minio_store=minio_store, flush=True)
    return counts


def collect_urls(urls: list[str], source_id: str, slo_log=None, known_urls=None,
                 minio_store=None, event_producer=None) -> dict:
    """허가된 고정 공식 URL만 수집한다 (URL allowlist + S1 idempotency)."""
    counts = {"saved": 0, "skipped": 0, "errors": 0}
    known = known_urls or set()
    _reconcile_and_publish(
        source_id, event_producer, minio_store=minio_store)
    for url in urls:
        if url in known:
            counts["skipped"] += 1
            continue
        try:
            content, headers = _get(url)
            meta = _fetch_meta(
                source_id, url,
                {"http_status": 200,
                 "collection_policy": "reviewed_fixed_url"},
                response_headers=headers,
            )
            if minio_store is None:
                _doc_id, created = _save_zone(source_id, url, content, meta)
            else:
                _doc_id, created = _save_zone(
                    source_id, url, content, meta, minio_store=minio_store)
        except Exception:
            counts["errors"] += 1
            if slo_log is not None:
                slo_log.record_collect(source_id, url, ok=False)
            continue
        counts["saved" if created else "skipped"] += 1
        if slo_log is not None:
            slo_log.record_collect(source_id, url, ok=True)
    _reconcile_and_publish(
        source_id, event_producer, minio_store=minio_store, flush=True)
    return counts


def _index_urls(config: dict, payload: bytes):
    """인덱스 payload 에서 문서 URL 을 순서대로 낸다 (중복 제거는 호출자 몫)."""
    if config.get("format") == "json":
        data = json.loads(payload)
        for record in _json_path(data, config.get("records", "results")):
            url = record.get(config.get("url_field", "url")) if isinstance(record, dict) else record
            if url:
                yield str(url)
        return
    delimiter = config.get("delimiter", "|")
    field = int(config.get("field", 0))
    base_url = config.get("base_url", "")
    skip_prefixes = tuple(config.get("skip_prefixes", ()))
    for line in payload.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or (skip_prefixes and line.startswith(skip_prefixes)):
            continue
        parts = line.split(delimiter)
        if len(parts) <= field:
            continue
        value = parts[field].strip()
        if not value:
            continue
        yield value if value.startswith("http") else base_url + value


def collect_index_stream(config: dict, source_id: str, slo_log=None,
                         known_urls=None, minio_store=None, event_producer=None) -> dict:
    """Collect documents enumerated by a bounded URL index."""
    counts = {"saved": 0, "skipped": 0, "errors": 0}
    known = set(known_urls or ())
    _reconcile_and_publish(
        source_id, event_producer, minio_store=minio_store)
    try:
        payload, _headers = _with_retry(lambda: _get(config["url"]))
    except Exception:
        counts["errors"] += 1
        if slo_log is not None:
            slo_log.record_collect(source_id, config["url"], ok=False)
        _reconcile_and_publish(
            source_id, event_producer, minio_store=minio_store, flush=True)
        return counts

    seen: set[str] = set()
    for url in _index_urls(config, payload):
        if url in seen:
            continue
        seen.add(url)
        if url in known:
            counts["skipped"] += 1
            continue
        try:
            content, headers = _with_retry(lambda: _get(url))
            _doc_id, created = _save_zone(
                source_id, url, content,
                _fetch_meta(
                    source_id, url,
                    {"http_status": 200, "collection_policy": "index_stream"},
                    response_headers=headers,
                    fetch_window=str(config.get("fetch_window") or "full"),
                ),
                minio_store=minio_store,
            )
        except Exception:
            counts["errors"] += 1
            if slo_log is not None:
                slo_log.record_collect(source_id, url, ok=False)
            continue
        known.add(url)
        counts["saved" if created else "skipped"] += 1
        if slo_log is not None:
            slo_log.record_collect(source_id, url, ok=True)

    _reconcile_and_publish(
        source_id, event_producer, minio_store=minio_store, flush=True)
    return counts


def _read_archive_entry(handle, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while chunk := handle.read(min(_ARCHIVE_CHUNK_SIZE, limit - total + 1)):
        total += len(chunk)
        if total > limit:
            raise ArchiveLimitExceeded(
                f"decompressed archive entry exceeds {limit} bytes")
        chunks.append(chunk)
    return b"".join(chunks)



def _check_zip_directory(archive_file) -> None:
    """Reject oversized ZIP central directories before ZipFile materializes them."""
    import struct

    archive_file.seek(0, 2)
    end = archive_file.tell()
    tail_size = min(end, 65_557)
    archive_file.seek(end - tail_size)
    tail = archive_file.read(tail_size)
    marker = tail.rfind(b"PK\x05\x06")
    if marker < 0 or len(tail) - marker < 22:
        raise ArchiveLimitExceeded("zip end-of-directory record is missing")
    eocd_offset = end - tail_size + marker
    (_signature, disk_number, directory_disk, entries_on_disk, entries,
     directory_size, directory_offset, _comment_size) = struct.unpack(
        "<4s4H2LH", tail[marker:marker + 22])

    if (entries == 0xFFFF or entries_on_disk == 0xFFFF
            or directory_size == 0xFFFFFFFF
            or directory_offset == 0xFFFFFFFF):
        locator_offset = eocd_offset - 20
        if locator_offset < 0:
            raise ArchiveLimitExceeded("zip64 directory locator is missing")
        archive_file.seek(locator_offset)
        locator = archive_file.read(20)
        if len(locator) != 20:
            raise ArchiveLimitExceeded("zip64 directory locator is truncated")
        signature, locator_disk, zip64_offset, disk_count = struct.unpack(
            "<4sLQL", locator)
        if signature != b"PK\x06\x07":
            raise ArchiveLimitExceeded("zip64 directory locator is invalid")
        archive_file.seek(zip64_offset)
        record = archive_file.read(56)
        if len(record) != 56:
            raise ArchiveLimitExceeded("zip64 directory record is truncated")
        (signature, _record_size, _made_by, _needed, disk_number,
         directory_disk, entries_on_disk, entries, directory_size,
         directory_offset) = struct.unpack("<4sQ2H2L4Q", record)
        if signature != b"PK\x06\x06" or locator_disk != 0 or disk_count != 1:
            raise ArchiveLimitExceeded("multi-disk zip archives are unsupported")

    if disk_number != 0 or directory_disk != 0 or entries_on_disk != entries:
        raise ArchiveLimitExceeded("multi-disk zip archives are unsupported")
    if entries > MAX_ARCHIVE_ENTRIES:
        raise ArchiveLimitExceeded(
            f"archive exceeds {MAX_ARCHIVE_ENTRIES} entries")
    if directory_size > MAX_ZIP_CENTRAL_DIRECTORY_BYTES:
        raise ArchiveLimitExceeded(
            "zip central directory exceeds "
            f"{MAX_ZIP_CENTRAL_DIRECTORY_BYTES} bytes")
    if directory_offset + directory_size > eocd_offset:
        raise ArchiveLimitExceeded("zip central directory bounds are invalid")
    archive_file.seek(0)

def _archive_entries(archive_file):
    """Yield bounded decompressed zip/tar entries from a seekable spool."""
    import tarfile
    import zipfile

    archive_file.seek(0, 2)
    compressed_size = archive_file.tell()
    expanded_limit = min(
        MAX_ARCHIVE_EXPANDED_BYTES,
        max(_ARCHIVE_CHUNK_SIZE,
            compressed_size * MAX_ARCHIVE_EXPANSION_RATIO),
    )
    entry_count = 0
    expanded_total = 0

    def entry_limit(declared_size: int) -> int:
        nonlocal entry_count
        entry_count += 1
        if entry_count > MAX_ARCHIVE_ENTRIES:
            raise ArchiveLimitExceeded(
                f"archive exceeds {MAX_ARCHIVE_ENTRIES} entries")
        if declared_size > MAX_ARCHIVE_ENTRY_BYTES:
            raise ArchiveLimitExceeded(
                f"decompressed archive entry exceeds "
                f"{MAX_ARCHIVE_ENTRY_BYTES} bytes")
        remaining = expanded_limit - expanded_total
        if declared_size > remaining:
            raise ArchiveLimitExceeded(
                f"decompressed archive exceeds {expanded_limit} bytes")
        return min(MAX_ARCHIVE_ENTRY_BYTES, remaining)

    archive_file.seek(0)
    if zipfile.is_zipfile(archive_file):
        _check_zip_directory(archive_file)
        archive_file.seek(0)
        with zipfile.ZipFile(archive_file) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                limit = entry_limit(info.file_size)
                with archive.open(info) as handle:
                    data = _read_archive_entry(handle, limit)
                expanded_total += len(data)
                if data:
                    yield info.filename, data
        return
    archive_file.seek(0)
    with tarfile.open(fileobj=archive_file, mode="r|*") as archive:
        for member in archive:
            if not member.isfile():
                continue
            limit = entry_limit(member.size)
            handle = archive.extractfile(member)
            if handle is None:
                continue
            with handle:
                data = _read_archive_entry(handle, limit)
            expanded_total += len(data)
            if data:
                yield member.name, data


def collect_bulk_archive(archive_url: str, source_id: str, slo_log=None,
                         known_urls=None, minio_store=None, event_producer=None) -> dict:
    """Store each non-empty archive entry as one raw document."""
    counts = {"saved": 0, "skipped": 0, "errors": 0}
    known = set(known_urls or ())
    _reconcile_and_publish(
        source_id, event_producer, minio_store=minio_store)
    try:
        with tempfile.TemporaryFile() as archive_file:
            headers = _download_to_file(archive_url, archive_file)
            for entry_path, data in _archive_entries(archive_file):
                doc_url = f"{archive_url}#{entry_path}"
                if doc_url in known:
                    counts["skipped"] += 1
                    continue
                try:
                    _doc_id, created = _save_zone(
                        source_id, doc_url, data,
                        _fetch_meta(
                            source_id, doc_url,
                            {"http_status": 200,
                             "collection_policy": "bulk_archive_entry"},
                            response_headers=headers,
                        ),
                        minio_store=minio_store,
                    )
                except Exception:
                    counts["errors"] += 1
                    if slo_log is not None:
                        slo_log.record_collect(source_id, doc_url, ok=False)
                    continue
                known.add(doc_url)
                counts["saved" if created else "skipped"] += 1
                if slo_log is not None:
                    slo_log.record_collect(source_id, doc_url, ok=True)
    except Exception:
        counts["errors"] += 1
        if slo_log is not None:
            slo_log.record_collect(source_id, archive_url, ok=False)
    _reconcile_and_publish(
        source_id, event_producer, minio_store=minio_store, flush=True)
    return counts


class ResultCapReached(RuntimeError):
    """페이징이 API 결과 상한에 닿았다 — 조용한 누락 대신 실패로 알린다.

    기존 `_arxiv_date_windows` 는 10k 를 넘는 월을 말없이 버렸다 (2026-09-20 확인).
    상한에 닿으면 소스 설정이 구간을 더 잘게 나눠야 한다는 신호이므로 전파한다.
    """


def _json_path(payload: dict, path: str):
    """`a.b.c` 표기로 중첩 필드를 꺼낸다. 없으면 빈 리스트."""
    node = payload
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return []
        node = node[part]
    return node if isinstance(node, list) else []


def _page_url(base: str, params: dict) -> str:
    """base 에 쿼리 파라미터를 덧붙인다 (기존 쿼리 보존)."""
    if not params:
        return base
    joiner = "&" if "?" in base else "?"
    return base + joiner + "&".join(f"{k}={v}" for k, v in params.items())


def collect_paged_api(config: dict, source_id: str, slo_log=None, known_urls=None,
                      minio_store=None, event_producer=None) -> dict:
    """Collect one raw document per cursor/offset API record."""
    counts = {"saved": 0, "skipped": 0, "errors": 0}
    known = set(known_urls or ())
    _reconcile_and_publish(
        source_id, event_producer, minio_store=minio_store)
    base = config["url"]
    records_path = config.get("records", "results")
    cursor_param, next_field = config.get("cursor_param"), config.get("next_field")
    offset_param = config.get("offset_param")
    page_size = int(config.get("page_size", 100))
    max_offset = config.get("max_offset")
    cursor, offset = None, 0
    fetch_window = str(config.get("fetch_window") or "full")

    while True:
        params: dict = {}
        if offset_param:
            params[config.get("limit_param", "limit")] = page_size
            params[offset_param] = offset
        if cursor and cursor_param:
            params[cursor_param] = cursor
        url = _page_url(base, params)
        try:
            raw, headers = _with_retry(lambda: _get(url))
            payload = json.loads(raw)
        except Exception:
            counts["errors"] += 1
            if slo_log is not None:
                slo_log.record_collect(source_id, url, ok=False)
            break
        records = _json_path(payload, records_path)
        if not records:
            break
        for record in records:
            doc_url = record.get(config["url_field"]) if config.get("url_field") else None
            if not doc_url:
                doc_url = f"{base}#{record.get(config.get('id_field', 'id'), '')}"
            if doc_url in known:
                counts["skipped"] += 1
                continue
            try:
                _doc_id, created = _save_zone(
                    source_id, doc_url,
                    json.dumps(record, ensure_ascii=False, sort_keys=True).encode(),
                    _fetch_meta(
                        source_id, doc_url,
                        {"http_status": 200, "content_type": "application/json"},
                        response_headers=headers,
                        fetch_window=fetch_window,
                    ),
                    minio_store=minio_store,
                )
            except Exception:
                counts["errors"] += 1
                if slo_log is not None:
                    slo_log.record_collect(source_id, doc_url, ok=False)
                continue
            known.add(doc_url)
            counts["saved" if created else "skipped"] += 1
            if slo_log is not None:
                slo_log.record_collect(source_id, doc_url, ok=True)
        if offset_param:
            offset += page_size
            if max_offset is not None and offset >= int(max_offset):
                _reconcile_and_publish(
                    source_id, event_producer,
                    minio_store=minio_store, flush=True)
                _publish_result_cap(config, source_id, offset, event_producer)
                raise ResultCapReached(
                    f"{source_id}: offset {offset} 가 max_offset {max_offset} 에 도달 — "
                    "수집 구간을 더 잘게 나눠야 한다 (조용한 누락 방지)")
            continue
        cursor = payload.get(next_field) if next_field else None
        if not cursor:
            break

    _reconcile_and_publish(
        source_id, event_producer, minio_store=minio_store, flush=True)
    return counts


def collect_sec(limit: int = 5, ciks: list[str] | None = None, slo_log=None,
                minio_store=None, event_producer=None) -> dict:
    """SEC EDGAR 수집 (S14 커넥터). gov filing index → raw 저장.

    browse-edgar fallback 포함(제한 환경). filing 손으로 원문(HTML/XBRL) 저장 —
    idempotent (content-hash). limit으로 CIK당 filing 수 상한(예의).

    SLO-05(11 §2.3) 측정용 `slo_log` 주입 시 fetch 성공/실패를 `record_collect`
    로 기록한다. 기본 None → 동작 무변경 (Spec 1.0.0, 선택 주입).
    """
    from orc_citadel.connectors.sec_edgar import SecEdgarConnector

    conn = SecEdgarConnector()
    counts = {"saved": 0, "skipped": 0, "errors": 0}
    source_id = "gov-sec-edgar"
    _reconcile_and_publish(
        source_id, event_producer, minio_store=minio_store)
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
                source_id, ref.url, fr.content,
                _fetch_meta(
                    source_id, ref.url,
                    {"http_status": fr.http_status},
                    response_headers=fr.response_headers,
                ),
                minio_store=minio_store,
            )
            n += 1
            counts["saved" if created else "skipped"] += 1
            if slo_log is not None:
                slo_log.record_collect("gov-sec-edgar", ref.url, ok=True)
    _reconcile_and_publish(
        source_id, event_producer, minio_store=minio_store, flush=True)
    return counts


# kind → 수집 함수. 러너·nightly·viewer 러너가 공유하는 단일 디스패치 (04 §1.3).
COLLECTORS = {
    "rss": collect_rss,
    "sitemap": collect_sitemap,
    "urls": collect_urls,
    "paged_api": collect_paged_api,
    "bulk_archive": collect_bulk_archive,
    "index_stream": collect_index_stream,
}


def _stored_urls(source_id: str, raw_dir=None) -> set[str]:
    """해당 source 의 기존 저장 URL 집합 — S1 재수집 방지용 (04 §2.1 idempotency).

    샤드 컬럼 조회 — 동일 코퍼스 103,224건에서 18.9s(fetch.json 전수 파싱) →
    0.02s 실측 (2026-09-20). 결정적·read-only.
    """
    return _shard_store(raw_dir).stored_urls(source_id)


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
    from orc_citadel.event_stream import KafkaEventProducer
    event_producer = KafkaEventProducer.from_env()

    print(f"== 대형 수집 러너 (limit={args.limit}, windows={args.windows}) ==")
    RAW.mkdir(parents=True, exist_ok=True)

    if not args.skip_rss:
        for source_id, (kind, spec) in SOURCES.items():
            known = _stored_urls(source_id)
            kwargs = {"known_urls": known, "event_producer": event_producer}
            print(f"[{source_id}] {kind} 수집 (known_urls={len(known)}건 skip 후보)")
            c = COLLECTORS[kind](spec, source_id, **kwargs)
            print(f"  -> {c}")

    print(f"[research-arxiv-cs-cr] arXiv metadata 페이징 수집 (total={args.limit}, "
          f"windows={args.windows}, 페이지당 1 req/3s)")
    c = collect_arxiv(
        args.limit, windows=args.windows, event_producer=event_producer)
    print(f"  -> {c}")

    if args.sec:
        print(f"[gov-sec-edgar] SEC filing 수집 (CIK당 {args.sec})")
        c = collect_sec(args.sec, event_producer=event_producer)
        print(f"  -> {c}")

    total = sum(1 for _ in RAW.rglob("content.bin"))
    print(f"\n== 총 raw 문서: {total} ==")


if __name__ == "__main__":
    main()
