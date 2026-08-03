"""Raw zone (03 §2) — immutable object store + provenance resolver.

- raw: source_id/doc_id/content.bin + fetch.json (doc_id = sha256[:24], 내용 기반).
- 불변식: 동일 URL 변경분은 새 doc_id로 보존(덮어쓰기 금지, 03 §2.1).
- provenance 왕복 해석(§8.1): claim → extraction → segment → raw bytes.
"""
from __future__ import annotations

from dataclasses import dataclass

from .identity import doc_id_for, new_ulid


@dataclass
class _RawEntry:
    source_id: str
    url: str
    content: bytes
    doc_id: str


@dataclass
class SegmentRef:
    """claim의 source span → 세그먼트·원문 offset 참조."""

    segment_id: str
    char_start: int
    char_end: int


@dataclass
class ClaimResolved:
    """provenance 왕복 해석 결과 (claim → 원문까지)."""

    claim_id: str
    segment_id: str
    char_start: int
    char_end: int
    text: str
    raw_bytes: bytes
    content_hash: str
    provenance_ref: list[str]


class RawStore:
    """초기 도메인 in-memory raw zone (prototype). 파일/DuckDB 영속화는 증분."""

    def __init__(self) -> None:
        self._raw: dict[str, _RawEntry] = {}
        self._extractions: dict[str, dict] = {}

    # ---- S2 raw zone ----
    def put(self, source_id: str, url: str, content: bytes) -> str:
        """raw 저장. 내용 기반 doc_id 반환. 동일 bytes는 no-op, 변경분은 새 doc_id."""
        doc_id = doc_id_for(content)
        if doc_id not in self._raw:
            self._raw[doc_id] = _RawEntry(source_id=source_id, url=url, content=content, doc_id=doc_id)
        return doc_id

    def has(self, doc_id: str) -> bool:
        return doc_id in self._raw

    def raw_bytes(self, doc_id: str) -> bytes:
        return self._raw[doc_id].content

    # ---- S5 curated: claim + extraction record (provenance) ----
    def record_claim(self, claim_id: str, source: SegmentRef) -> None:
        """claim과 그 원문 source span을 기록 (extraction_record 생성, 03 §8.2).

        text는 항상 원문 raw bytes에서 offset으로 복원한다 — 왕복 일관성의 단일 경로.
        (claim이 담은 segment_id → doc_id, offset → slice)
        """
        doc_id = source.segment_id.split("#")[0]
        raw = self._raw[doc_id]
        ext_id = new_ulid("ext")
        self._extractions[claim_id] = {
            "ext_id": ext_id,
            "segment_id": source.segment_id,
            "char_start": source.char_start,
            "char_end": source.char_end,
            "doc_id": raw.doc_id,
            "content_hash": raw.doc_id,
        }

    def resolve_claim(self, claim_id: str) -> ClaimResolved:
        """claim의 provenance를 따라 원문 bytes·offset까지 왕복 복원 (03 §8.1)."""
        ex = self._extractions[claim_id]
        doc_id = ex["doc_id"]
        raw = self._raw[doc_id]
        text = raw.content[ex["char_start"]:ex["char_end"]].decode()
        return ClaimResolved(
            claim_id=claim_id,
            segment_id=ex["segment_id"],
            char_start=ex["char_start"],
            char_end=ex["char_end"],
            text=text,
            raw_bytes=raw.content,
            content_hash=raw.doc_id,
            provenance_ref=[ex["ext_id"]],
        )
