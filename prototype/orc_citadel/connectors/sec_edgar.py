"""SEC EDGAR 커넥터 (04 §1.3 gov) — S14 정식 구현.

SEC는 선언형 User-Agent(`Name ContactEmail`)를 필수로 요구하고 최대 10 req/s 제한.
기본 HTTP client(WebFetch 포함)는 403 차단 → 반드시 선언 UA 헤더를 주입한다 (04 §1.4).

discover: `data.sec.gov/submissions/{CIK}.json` (no-key, free) — filing index에서
  accessionNumber·primaryDocument·reportDate를 읽어 `DiscoveredRef`를 yield.
fetch   : primaryDocument URL → filing 원문 (선언 UA 포함).
robots·rate limit(≤10 req/s)는 FetchFramework(커넥터 밖 공통)가 강제 (04 §1.3).
allow_redistribute=false (11 §5.4) — store-only.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from .base import DiscoveredRef, FetchResult, SourceConnector

# 선언형 User-Agent — SEC가 요구하는 "Name ContactEmail" 형태 (04 §1.4).
SEC_UA = "OrcCitadel-Research research@example.com"
# 관련 테스트가 참조하는 별칭 (가독·일관).
USER_AGENT = SEC_UA

EDGAR_BASE = "https://www.sec.gov/Archives"

# 대상 CIK 후보 (04 §1.4 — AI 반도체·데이터센터 공급망, 확장 가능).
CIKS = {"NVDA": "1045810", "TSM": "1046179"}


def pad_cik(cik: str) -> str:
    """SEC는 CIK를 10자리 zero-padded로 요구 (7자리 1045810 → 0001045810)."""
    return cik.zfill(10)


def submission_url_for(cik: str) -> str:
    """CIK submissions (filing index) API URL — 10자리 패딩 필수."""
    return f"https://data.sec.gov/submissions/{pad_cik(cik)}.json"


class SecEdgarConnector(SourceConnector):
    source_type = "gov"

    def _http_get(self, url: str, headers: dict | None = None) -> bytes:
        """GET with declared UA (SEC 403 방지). 테스트에서 모크 대상."""
        import urllib.request

        hdrs = {"User-Agent": SEC_UA}
        if headers:
            hdrs.update(headers)
        req = urllib.request.Request(url, headers=hdrs)
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read()

    def discover(self, config: dict, cursor: str | None):
        """CIK filing index → filing refs (last_modified=reportDate).

        config: {"cik": [cik, ...]} — 없으면 기본 CIKS 사전.
        cursor: 사용 안 함 (지원 filing index는 단일 API; 대량은 아래 확장).

        기본은 `data.sec.gov/submissions/{CIK}.json` 공식 API. 이 엔드포인트는 일부
        환경(데이터센터 IP)에서 SEC가 404 차단하므로, 실패 시 `www.sec.gov` browse-edgar
        경로로 폴백한다 (라이브 검증으로 확인된 환경 제약 — 04 §1.4 폴백 정합).
        """
        ciks = config.get("cik") or list(CIKS.values())
        for cik in ciks:
            try:
                yield from self._discover_submissions(cik)
            except Exception:
                yield from self._discover_browse(cik)

    def _discover_submissions(self, cik: str):
        """data.sec.gov submissions API 경로."""
        body = self._http_get(submission_url_for(cik))
        data = json.loads(body.decode("utf-8", errors="replace"))
        recent = (data.get("filings") or {}).get("recent") or {}
        accs = recent.get("accessionNumber") or []
        docs = recent.get("primaryDocument") or []
        dates = recent.get("reportDate") or []
        for i in range(len(accs)):
            acc = accs[i]
            doc = docs[i] if i < len(docs) else ""
            date = dates[i] if i < len(dates) else None
            acc_clean = acc.replace("-", "")
            url = f"{EDGAR_BASE}/edgar/data/{pad_cik(cik)}/{acc_clean}/{doc}"
            if not doc:
                continue
            hint = None
            if date:
                try:
                    hint = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                except ValueError:
                    hint = None
            yield DiscoveredRef(url=url, hint_modified=hint)

    def _discover_browse(self, cik: str):
        """fallback: www.sec.gov browse-edgar (IP 차단 환경에서 동작).

        HTML browse 결과에서 filing 링크를 정규식으로 추출 (prototype 최소)."""
        cik10 = pad_cik(cik)
        url = (f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
               f"&CIK={cik10}&type=&dateb=&owner=include&count=10")
        html = self._http_get(url).decode("utf-8", errors="replace")
        import re

        # browse-edgar의 filing 행: /Archives/edgar/data/{CIK}/{ACC}/{DOC}.htm  링크.
        for m in re.finditer(r'href="(/Archives/edgar/data/[^"]+?\.htm)"', html):
            yield DiscoveredRef(url="https://www.sec.gov" + m.group(1), hint_modified=None)

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
