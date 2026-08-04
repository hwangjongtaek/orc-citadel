"""FetchFramework — politeness(robots·rate limit) 강제 (04 §1.2).

robots.txt 허용 여부 + 토큰 버킷 rate limiting을 커넥터 호출 전에 검사한다.
벌금은 RuntimeError를 일으켜 호출 컨텍스트가 실패를 명시적으로 받는다.
실 세부 정책(backoff, 재시도)은 소량 실수집에서 커넥터별로 확장한다.
"""
from __future__ import annotations

import time
import urllib.parse

from .connectors.base import DiscoveredRef


class FetchFramework:
    """robots 허용 체크 + token-bucket rate limit 을 가진 fetch 지휘부."""

    def __init__(self, rps: float = 10.0) -> None:
        self.rps = rps
        # token bucket: 최대 burst=rps, 1개 토큰을 1/rps 초마다 보충.
        self._tokens = float(rps)
        self._last_refill = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        self._tokens = min(float(self.rps), self._tokens + (now - self._last_refill) * self.rps)
        self._last_refill = now

    def robots_allowed(self, url: str) -> bool:
        """prototype: robots.txt를 실제로 GET하지 않고 전체 허용 가정.
        SEC/secure 서브도메인 등 제외 규칙은 소량 실수집에서 확장한다."""
        return True

    def _consume(self) -> None:
        self._refill()
        if self._tokens < 1.0:
            raise RuntimeError("rate limit exceeded")
        self._tokens -= 1.0

    def fetch(self, ref: DiscoveredRef) -> bytes:
        """robots 미허용 또는 rate limit 소진 시 RuntimeError."""
        if not self.robots_allowed(ref.url):
            raise RuntimeError(f"robots disallows {ref.url}")
        self._consume()
        # 커넥터별 fetch는 외부에서 주입되는 것으로 가정 (prototype은 bytes 가정).
        raise NotImplementedError("FetchFramework.fetch는 커넥터 dispatch를 외부에서 연결")


def _url_profile(url: str) -> str:
    """robots 체크 단위(origin)를 반환."""
    p = urllib.parse.urlparse(url)
    return f"{p.scheme}://{p.netloc}"
