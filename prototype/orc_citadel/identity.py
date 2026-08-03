"""ID 규칙 (design README §2.2).

- `doc_id` = "doc-" + sha256(raw_bytes)[:24] — 내용 기반 결정적 (03 §2.1).
- 기타 엔터티는 ULID 유사 순번(시간 정렬). 여기서는 결정성·유일성만 보장하는
  간단한 ULID 포맷으로 대체한다 (prototype 범위).
"""
from __future__ import annotations

import hashlib
import secrets


def doc_id_for(data: bytes) -> str:
    """내용 기반 결정적 doc_id. 동일 bytes → 동일 ID, 다른 bytes → 다른 ID."""
    return "doc-" + hashlib.sha256(data).hexdigest()[:24]


def new_ulid(prefix: str = "gen") -> str:
    """시간 정렬·유일한 ULID 유사 ID. prototype에선 랜덤 블록으로 충분."""
    return f"{prefix}-{secrets.token_hex(8)}"
