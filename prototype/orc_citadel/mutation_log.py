"""Mutation log (03 §7) — append-only event store + idempotency.

- append-only: 이벤트 수정·삭제 금지 (불변식 §3-3, 03 §7.2).
- idempotency_key unique: 동일 key 재수신 시 no-op (불변식 §3-6).
- 내용 기반 dedup: 동일 source_span 재처리 시 중복 claim element 생성 방지 (DoD ②).
"""
from __future__ import annotations

from dataclasses import dataclass

from .identity import new_ulid
from .raw_store import RawStore, SegmentRef


class IdempotencyViolation(Exception):
    """동일 idempotency_key의 재사용 위반 (불변식 §3-6). prototype 예비."""


@dataclass
class Mutation:
    mutation_id: str
    idempotency_key: str
    op: str
    doc_id: str
    source_span: tuple[str, int, int]
    payload: dict


class MutationLog:
    """Append-only mutation log.

    `store`는 claim element의 실제 기록(추적) 대상. mutation은 store에 존재하는
    claim(claim_id)을 payload로 가리키며, 동일 source_span 재처리 시 중복 생성하지
    않는다 (DoD ②, 03 §7).
    """

    def __init__(self, store: RawStore) -> None:
        self._store = store
        self._mutations: list[Mutation] = []
        self._by_key: dict[str, Mutation] = {}
        self._claims_by_span: dict[tuple[str, int, int], str] = {}

    def apply(self, doc_id: str, op: str, source_span: tuple[str, int, int], idempotency_key: str) -> str:
        """mutation 적용. 동일 key 재실행·동일 span 재처리는 no-op (03 §7.2)."""
        existing = self._by_key.get(idempotency_key)
        if existing is not None:
            return existing.mutation_id

        span_key = source_span
        if span_key in self._claims_by_span:
            return self._claims_by_span[span_key]

        # claim element를 store에 기록 (provenance_ref 부여) — 1개만 생성
        segment_id, char_start, char_end = source_span
        claim_id = new_ulid("clm")
        self._store.record_claim(claim_id, SegmentRef(segment_id, char_start, char_end))

        mut = Mutation(
            mutation_id=new_ulid("mut"),
            idempotency_key=idempotency_key,
            op=op,
            doc_id=doc_id,
            source_span=source_span,
            payload={"claim_id": claim_id},
        )
        self._mutations.append(mut)
        self._by_key[mut.idempotency_key] = mut
        if op == "create_claim":
            self._claims_by_span[span_key] = claim_id
        return mut.mutation_id

    def all_mutations(self) -> list[Mutation]:
        return list(self._mutations)

    def claims_for(self, source_span: tuple[str, int, int]) -> list[str]:
        claim_id = self._claims_by_span.get(source_span)
        return [claim_id] if claim_id else []
