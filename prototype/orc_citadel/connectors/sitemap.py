"""sitemap 커넥터 (04 §1.4 신규 — RSS 없는 gov 정책/수출통제 소스용).

BIS(수출통제) 등 RSS 를 노출하지 않는 정부 정책 사이트는 robots.txt 가 열려 있고
(robots `Allow: /`, 2026-08-19 실측) sitemap.xml 으로 수집 대상 URL 을 정적 열거할 수
있다. 본 커넥터는 sitemap `<loc>` 을 discover 해 각 정책 문서 URL 을 열거하고,
fetch 는 해당 페이지 HTML bytes 를 취득한다 — RSS 커넥터와 동일 2단계 계약(04 §1.2).

- `discover(sitemap_url, cursor)` → sitemap.xml fetch, `<loc>` → DiscoveredRef
  (`lastmod` 가 있으면 hint_modified 로 파싱, 없으면 None).
- `fetch(ref, prior_etag)` → 대상 URL GET → FetchResult (content-hash·http 200).
- robots·rate limit 은 fetch 프레임워크가 강제한다(커넥터는 discover/fetch 파싱만).
- source_type=gov (수출통제 규제 기관).
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from .base import DiscoveredRef, FetchResult, SourceConnector

_SITEMAP_URL = re.compile(r"<url>(.*?)</url>", re.S | re.I)
_LOC = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.S | re.I)
_LASTMOD = re.compile(r"<lastmod>\s*(.*?)\s*</lastmod>", re.S | re.I)


def _parse_iso_date(text: str) -> datetime | None:
    """ISO-8601 날짜(YYYY-MM-DD 또는 full timestamp) 파싱. 실패 시 None."""
    try:
        return datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except Exception:
        return None


class SitemapConnector(SourceConnector):
    """sitemap 정책 문서 소스 (BIS 등 RSS 없는 gov)."""

    source_type = "gov"

    def _http_get(self, url: str) -> bytes:
        """실제 GET. prototype 은 urllib 최소 구현; 테스트에서 mock 대상."""
        import urllib.request

        req = urllib.request.Request(url, headers={"User-Agent": "OrcCitadel/0.1 (prototype; research)"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read()

    def discover(self, sitemap_url: str, cursor: str | None):
        """sitemap 의 <loc> 마다 DiscoveredRef (lastmod → hint_modified)."""
        xml = self._http_get(sitemap_url)
        body = xml.decode("utf-8", errors="replace")
        for block in _SITEMAP_URL.findall(body):
            loc = _LOC.search(block)
            if not loc:
                continue
            url = loc.group(1).strip()
            if not url:
                continue
            lm = _LASTMOD.search(block)
            hint = _parse_iso_date(lm.group(1)) if lm else None
            yield DiscoveredRef(url=url, hint_modified=hint)

    def fetch(self, ref: DiscoveredRef, prior_etag: str | None) -> FetchResult:
        content = self._http_get(ref.url)
        return FetchResult(
            url=ref.url,
            content=content,
            content_hash="sha256:" + hashlib.sha256(content).hexdigest(),
            http_status=200,
            response_headers={"content-type": "text/html; charset=utf-8"},
            fetched_at=datetime.now(timezone.utc),
            unchanged=False,
        )
