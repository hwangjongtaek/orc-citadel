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

import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from orc_citadel.connectors.arxiv import ArxivConnector
from orc_citadel.connectors.rss import RssConnector
from orc_citadel.fetch import FetchFramework
from orc_citadel.raw_shard import RawShardStore

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


_SHARD_STORES: dict[pathlib.Path, RawShardStore] = {}


def _shard_store(raw_dir: pathlib.Path | None = None) -> RawShardStore:
    """raw 디렉터리별 샤드 스토어 — 수집 런 동안 쓰기 버퍼를 공유한다."""
    base = pathlib.Path(raw_dir or RAW).resolve()
    if base not in _SHARD_STORES:
        _SHARD_STORES[base] = RawShardStore(base)
    return _SHARD_STORES[base]


def flush_raw(raw_dir: pathlib.Path | None = None) -> None:
    """버퍼 잔량을 샤드로 확정한다 — 각 수집 함수가 반환 직전에 호출한다."""
    _shard_store(raw_dir).flush()


def _save_zone(source_id: str, url: str, content: bytes, meta: dict,
               raw_dir: pathlib.Path | None = None,
               minio_store=None) -> tuple[str, bool]:
    """raw 3-zone 저장 — content-hash idempotency.

    returns (doc_id, created): created=True 새 저장, False 이미 존재(재개 무중복).

    저장 백엔드:
    - `minio_store` 제공 시 → MinIO 객체 스토어(② `MinioRawStore`)에 §2.1 객체 키로 영속.
    - 미제공 시 로컬 fs `data/raw/<source>/shard-*.parquet` (기존 default).
    샤드 쓰기는 버퍼링되므로 수집 함수는 반환 직전 `flush_raw()` 로 확정한다.
    `meta` 의 governance(11) 필드 license/robots_allowed 는 기본값이 채워진다
    (04 §1.4 재배포 제한 정합).
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

    return _shard_store(raw_dir).append(source_id, url, content, meta)


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
    flush_raw()
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


def collect_rss(feed_url: str, source_id: str, slo_log=None, known_urls=None) -> dict:
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
        _save_zone(source_id, url, content,
                   {"http_status": 200, "content_type": hdrs.get("Content-Type"),
                    "hint_modified": ref.hint_modified.isoformat() if ref.hint_modified else None})
        counts["saved"] += 1
        if slo_log is not None:
            slo_log.record_collect(source_id, url, ok=True)
    flush_raw()
    return counts


def collect_sitemap(sitemap_url: str, source_id: str, slo_log=None, known_urls=None) -> dict:
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
        _save_zone(source_id, url, content,
                   {"http_status": 200, "content_type": hdrs.get("Content-Type"),
                    "hint_modified": ref.hint_modified.isoformat() if ref.hint_modified else None})
        counts["saved"] += 1
        if slo_log is not None:
            slo_log.record_collect(source_id, url, ok=True)
    flush_raw()
    return counts


def collect_urls(urls: list[str], source_id: str, slo_log=None, known_urls=None) -> dict:
    """허가된 고정 공식 URL만 수집한다 (URL allowlist + S1 idempotency)."""
    counts = {"saved": 0, "skipped": 0, "errors": 0}
    known = known_urls or set()
    for url in urls:
        if url in known:
            counts["skipped"] += 1
            continue
        try:
            content, headers = _get(url)
            _doc_id, created = _save_zone(
                source_id, url, content,
                {"http_status": 200, "content_type": headers.get("Content-Type"),
                 "collection_policy": "reviewed_fixed_url"},
            )
        except Exception:
            counts["errors"] += 1
            if slo_log is not None:
                slo_log.record_collect(source_id, url, ok=False)
            continue
        counts["saved" if created else "skipped"] += 1
        if slo_log is not None:
            slo_log.record_collect(source_id, url, ok=True)
    flush_raw()
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
                         known_urls=None) -> dict:
    """URL 을 열거하는 인덱스를 받아 대상 문서를 수집한다 (04 §1.3).

    config: `url`(인덱스) · `format`("delimited"|"json") ·
      delimited: `delimiter`·`field`·`base_url`·`skip_prefixes`
      json: `records`(목록 경로)·`url_field`

    인덱스에 같은 문서가 여러 번 실려도 한 번만 받는다 — EDGAR `master.idx` 는
    공동제출을 CIK 별로 중복 수록한다(2025Q4 중복률 29.7% 실측, 2026-09-20 조사).
    """
    counts = {"saved": 0, "skipped": 0, "errors": 0}
    known = set(known_urls or ())
    try:
        payload, _headers = _with_retry(lambda: _get(config["url"]))
    except Exception:
        counts["errors"] += 1
        if slo_log is not None:
            slo_log.record_collect(source_id, config["url"], ok=False)
        return counts

    seen: set[str] = set()
    for url in _index_urls(config, payload):
        if url in seen:
            continue           # 인덱스 중복 수록 — 재fetch 금지.
        seen.add(url)
        if url in known:
            counts["skipped"] += 1
            continue
        try:
            content, headers = _with_retry(lambda: _get(url))
            _doc_id, created = _save_zone(
                source_id, url, content,
                {"http_status": 200, "content_type": headers.get("Content-Type"),
                 "collection_policy": "index_stream"})
        except Exception:
            counts["errors"] += 1
            if slo_log is not None:
                slo_log.record_collect(source_id, url, ok=False)
            continue
        known.add(url)
        counts["saved" if created else "skipped"] += 1
        if slo_log is not None:
            slo_log.record_collect(source_id, url, ok=True)

    flush_raw()
    return counts


def _archive_entries(payload: bytes):
    """zip / tar(.gz) 의 (엔트리 경로, bytes) 를 순서대로 낸다. 해석 불가면 예외."""
    import io
    import tarfile
    import zipfile

    if zipfile.is_zipfile(io.BytesIO(payload)):
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                data = archive.read(info)
                if data:
                    yield info.filename, data
        return
    with tarfile.open(fileobj=io.BytesIO(payload)) as archive:  # tar/tar.gz/tar.bz2
        for member in archive.getmembers():
            if not member.isfile():
                continue
            handle = archive.extractfile(member)
            if handle is None:
                continue
            data = handle.read()
            if data:
                yield member.name, data


def collect_bulk_archive(archive_url: str, source_id: str, slo_log=None,
                         known_urls=None) -> dict:
    """아카이브 1개를 받아 **내부 엔트리를 개별 문서로** 저장한다 (04 §1.3 download).

    엔트리 식별자는 `{archive_url}#{entry_path}` — 아카이브 URL 하나로는 내부를
    구분할 수 없어 URL-skip(04 §2.1)이 성립하지 않기 때문이다. `doc_id` 는 종전처럼
    엔트리 bytes 의 content-hash 다 (03 §2.1 불변).
    """
    counts = {"saved": 0, "skipped": 0, "errors": 0}
    known = set(known_urls or ())
    try:
        payload, _headers = _with_retry(lambda: _get(archive_url))
    except Exception:
        counts["errors"] += 1
        if slo_log is not None:
            slo_log.record_collect(source_id, archive_url, ok=False)
        return counts

    try:
        entries = list(_archive_entries(payload))
    except Exception:
        # 아카이브로 해석되지 않는 바이트 — 0건 성공으로 위장하지 않는다.
        counts["errors"] += 1
        if slo_log is not None:
            slo_log.record_collect(source_id, archive_url, ok=False)
        return counts

    for entry_path, data in entries:
        doc_url = f"{archive_url}#{entry_path}"
        if doc_url in known:
            counts["skipped"] += 1
            continue
        try:
            _doc_id, created = _save_zone(
                source_id, doc_url, data,
                {"http_status": 200, "collection_policy": "bulk_archive_entry"})
        except Exception:
            counts["errors"] += 1
            if slo_log is not None:
                slo_log.record_collect(source_id, doc_url, ok=False)
            continue
        known.add(doc_url)
        counts["saved" if created else "skipped"] += 1
        if slo_log is not None:
            slo_log.record_collect(source_id, doc_url, ok=True)

    flush_raw()
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


def collect_paged_api(config: dict, source_id: str, slo_log=None, known_urls=None) -> dict:
    """커서/오프셋 JSON API 페이징 수집 — 레코드 1건 = 문서 1건 (04 §1.2).

    config: `url`(base) · `records`(레코드 목록 경로, `a.b` 표기) · 다음 중 하나
      - 커서형: `cursor_param`, `next_field`
      - 오프셋형: `offset_param`, `limit_param`, `page_size`, 선택 `max_offset`
    레코드 URL 은 `url_field` 우선, 없으면 `{base}#{id_field 값}` 합성.
    """
    counts = {"saved": 0, "skipped": 0, "errors": 0}
    known = set(known_urls or ())
    base = config["url"]
    records_path = config.get("records", "results")
    cursor_param, next_field = config.get("cursor_param"), config.get("next_field")
    offset_param = config.get("offset_param")
    page_size = int(config.get("page_size", 100))
    max_offset = config.get("max_offset")
    cursor, offset = None, 0

    while True:
        params: dict = {}
        if offset_param:
            params[config.get("limit_param", "limit")] = page_size
            params[offset_param] = offset
        if cursor and cursor_param:
            params[cursor_param] = cursor
        url = _page_url(base, params)
        try:
            raw, _headers = _with_retry(lambda: _get(url))
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
                    source_id, doc_url, json.dumps(record, ensure_ascii=False,
                                                   sort_keys=True).encode(),
                    {"http_status": 200, "content_type": "application/json"})
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
                flush_raw()
                raise ResultCapReached(
                    f"{source_id}: offset {offset} 가 max_offset {max_offset} 에 도달 — "
                    "수집 구간을 더 잘게 나눠야 한다 (조용한 누락 방지)")
            continue
        cursor = payload.get(next_field) if next_field else None
        if not cursor:
            break

    flush_raw()
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
    flush_raw()
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

    print(f"== 대형 수집 러너 (limit={args.limit}, windows={args.windows}) ==")
    RAW.mkdir(parents=True, exist_ok=True)

    if not args.skip_rss:
        for source_id, (kind, spec) in SOURCES.items():
            known = _stored_urls(source_id)
            print(f"[{source_id}] {kind} 수집 (known_urls={len(known)}건 skip 후보)")
            c = COLLECTORS[kind](spec, source_id, known_urls=known)
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
