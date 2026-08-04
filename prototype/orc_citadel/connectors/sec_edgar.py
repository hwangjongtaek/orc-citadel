"""SEC EDGAR 커넥터 (04 §1.3 gov).

SEC는 10 req/s 제한 + User-Agent 선언(ex: contact 이메일) 요구. prototype은
filing Machine Readable Renditions(CDEK/XBRL)을 타겟으로 하는 최소 골격.
robots(SEC robots.txt는 full-text 허용)과 rate limit은 FetchFramework가 강제.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from .base import DiscoveredRef, FetchResult, SourceConnector


class SecEdgarConnector(SourceConnector):
    source_type = "gov"

    def _http_get(self, url: str) -> bytes:
        import urllib.request

        # SEC는 선언된 User-Agent(+연락처)를 요구 — 04 §1.3 준수.
        ua = "OrcCitadel-Research research@example.com"
        req = urllib.request.Request(url, headers={"User-Agent": ua})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read()

    def discover(self, config: dict, cursor: str | None):
        # prototype: json index를 cursor로 소비한다고 가정 (실수집에서 확장).
        # 빈 이터레이터 — 구체 구현 전까지 안전하게 소비 가능.
        return iter(())

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
