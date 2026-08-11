"""arXiv OAI-PMH 커넥터 (04 §1.3 research).

arXiv는 API 폴리시상 OAI-PMH 엔드포인트가 공식 수집 경로이며 1req/3s 제한.
prototype은 Abstract 커넥터 계약에 맞춘 최소 골격이다. 실수집은 04 §1.4
"arXiv adv. search(라이선스 허용)" 경로의 리스트 API를 별도로 확장한다.
"""
from __future__ import annotations

import hashlib
import urllib.parse
from datetime import datetime, timezone

from .base import DiscoveredRef, FetchResult, SourceConnector

ARXIV_SEARCH = "https://export.arxiv.org/api/query"


class ArxivConnector(SourceConnector):
    source_type = "research"

    def _http_get(self, url: str) -> bytes:
        import urllib.request

        req = urllib.request.Request(url, headers={"User-Agent": "OrcCitadel/0.1 (prototype; research)"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read()

    def discover(self, config: dict, cursor: str | None):
        query = config.get("query") or "cat:cs.CR OR cat:cs.AI"
        params = urllib.parse.urlencode({"search_query": query, "start": cursor or 0, "max_results": 100})
        xml = self._http_get(f"{ARXIV_SEARCH}?{params}")
        body = xml.decode("utf-8", errors="replace")
        # Atom <entry><id>가 doc url, <published>가 날짜.
        import re

        for entry in re.findall(r"<entry>(.*?)</entry>", body, re.S):
            m_id = re.search(r"<id>\s*(.*?)\s*</id>", entry, re.S)
            m_pub = re.search(r"<published>\s*(.*?)\s*</published>", entry, re.S)
            if not m_id:
                continue
            url = m_id.group(1).strip()
            hint = None
            if m_pub:
                try:
                    hint = datetime.fromisoformat(m_pub.group(1).strip().replace("Z", "+00:00"))
                except ValueError:
                    hint = None
            yield DiscoveredRef(url=url, hint_modified=hint)

    def discover_entries(self, config: dict, cursor: str | None):
        """페이지 Atom 응답의 (id url, <entry> 원문 XML bytes)를 낸다.

        04 §1.4 metadata(CC0) 경로 — entry 자체가 raw 문서가 되므로 문서당
        추가 HTTP GET이 없다.
        """
        query = config.get("query") or "cat:cs.CR OR cat:cs.AI"
        params = urllib.parse.urlencode({"search_query": query, "start": cursor or 0,
                                         "max_results": config.get("max_results", 100)})
        xml = self._http_get(f"{ARXIV_SEARCH}?{params}")
        body = xml.decode("utf-8", errors="replace")
        import re

        for entry in re.findall(r"<entry>(.*?)</entry>", body, re.S):
            m_id = re.search(r"<id>\s*(.*?)\s*</id>", entry, re.S)
            if not m_id:
                continue
            yield m_id.group(1).strip(), f"<entry>{entry}</entry>".encode("utf-8")

    def fetch(self, ref: DiscoveredRef, prior_etag: str | None) -> FetchResult:
        content = self._http_get(ref.url)
        return FetchResult(
            url=ref.url,
            content=content,
            content_hash="sha256:" + hashlib.sha256(content).hexdigest(),
            http_status=200,
            response_headers={"content-type": "application/atom+xml"},
            fetched_at=datetime.now(timezone.utc),
            unchanged=False,
        )
