"""공용 RSS 커넥터 (04 §1.3 press/official/gov feed).

RSS discover → 피드 내 item url 열거, fetch → 단일 url bytes.
robots·rate limit은 FetchFramework가 강제하므로 커넥터는 discover 규칙과
HTTP 응답 파싱만 담당한다. 테스트에서 `_http_get`을 mock 하여 오프라인 검증.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from .base import DiscoveredRef, FetchResult, SourceConnector

# RSS <item> 하나의 <link>/<pubDate> 추출. 최소 파싱은 정규식으로 (stdlib만 사용).
_ITEM = re.compile(r"<item>(.*?)</item>", re.S | re.I)
_ITEM_LINK = re.compile(r"<link>\s*(.*?)\s*</link>", re.S | re.I)
_ITEM_DATE = re.compile(r"<pubDate>\s*(.*?)\s*</pubDate>", re.S | re.I)


def _parse_rfc2822(text: str) -> datetime | None:
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(text.strip())
    except Exception:
        return None


class RssConnector(SourceConnector):
    """범용 press/official/gov 피드를 소비한다. source_type은 호출 컨텍스트가 정한다."""

    source_type = "press"

    def _http_get(self, url: str) -> bytes:
        """실제 GET. prototype은 urllib 최소 구현; 테스트에서 mock 대상."""
        import urllib.request

        req = urllib.request.Request(url, headers={"User-Agent": "OrcCitadel/0.1 (prototype; research)"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read()

    def discover(self, feed_url: str, cursor: str | None):
        """피드 url을 첫 위치 인자로 받는다 (테스트 계약: discover(url, cursor))."""
        xml = self._http_get(feed_url)
        body = xml.decode("utf-8", errors="replace")
        for item in _ITEM.findall(body):
            link = _ITEM_LINK.search(item)
            if not link:
                continue
            url = link.group(1).strip()
            if not url:
                continue
            date_m = _ITEM_DATE.search(item)
            hint = _parse_rfc2822(date_m.group(1)) if date_m else None
            yield DiscoveredRef(url=url, hint_modified=hint)

    def fetch(self, ref: DiscoveredRef, prior_etag: str | None) -> FetchResult:
        content = self._http_get(ref.url)
        return FetchResult(
            url=ref.url,
            content=content,
            content_hash="sha256:" + hashlib.sha256(content).hexdigest(),
            http_status=200,
            response_headers={"content-type": "application/octet-stream"},
            fetched_at=datetime.now(timezone.utc),
            unchanged=False,
        )
