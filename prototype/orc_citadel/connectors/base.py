"""Scout 커넥터 계약 (design 04 §1.2).

`discover → fetch` 2단계. 네트워크·저장은 분리하여 fetch를 idempotent·재실행 가능하게.
politeness(robots·rate limit·backoff)는 fetch 프레임워크(orc_citadel.fetch)가 강제한다.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class DiscoveredRef:
    url: str
    hint_modified: datetime | None = None
    extra: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class FetchResult:
    url: str
    content: bytes
    content_hash: str
    http_status: int
    response_headers: dict[str, str]
    fetched_at: datetime | None = None
    unchanged: bool = False


class SourceConnector(ABC):
    """모든 커넥터가 구현하는 추상. discover는 URL 열거, fetch는 단일 bytes 취득."""

    source_type: str = ""

    @abstractmethod
    def discover(self, config: dict, cursor: str | None):
        """수집 대상 URL 열거 → DiscoveredRef iterator."""

    @abstractmethod
    def fetch(self, ref: DiscoveredRef, prior_etag: str | None) -> FetchResult:
        """단일 URL을 조건부 GET으로 fetch → FetchResult."""
