"""S11 Assertion Materialization (설계 03 §6.2·§7, ADR-306).

게이트로 promoted된 claim의 **정규 삼항 Assertion**을 bitemporal(valid + transaction
두 시간 축)로 materialize한다. Claim→Assertion emission 계약: 동일 claim 재실행 시
중복 materialize 금지(결정적 asr- id, idempotency 03 §5·§7), 생성은 append-only
create_node 이벤트로 (§7.1 — prototype은 mutation_id로 연결).

- 정규 삼항: `(subject_id, predicate, object_id|object_literal)` — object XOR (§6.2).
- transaction time: tx_from=observed, tx_to=null(현재 버전). supersede 시 이전 버전의
  tx_to close는 후속(ADR-303/307).
- valid time: claim의 valid_from/to·time_precision. 미상은 null + `unknown`.
- provenance_ref: promoted claim(source span) 참조 (03 §8).
- system-versioned projection — append-only graph_mutations에서 재구축 가능 (§7.2).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime

from .extract_claims import ClaimCandidate

# materialization 규칙 식별 — 변경 시 bump (03 §5, 재생성).
ASSERTION_VERSION = "a1"


@dataclass(frozen=True)
class Assertion:
    assertion_id: str
    claim_id: str
    subject_id: str
    predicate: str
    object_id: str | None
    object_literal: object | None
    valid_from: datetime | None
    valid_to: datetime | None
    time_precision: str
    tx_from: datetime
    tx_to: datetime | None
    supersedes_id: str | None
    mutation_id: str
    provenance_ref: tuple = field(default_factory=tuple)
    ontology_version: str = ""  # 02 §2 — 저장 element 필수. 추출 단계 버전 승격(03 §6.2).

    def to_row(self) -> dict:
        return {
            "assertion_id": self.assertion_id,
            "claim_id": self.claim_id,
            "subject_id": self.subject_id,
            "predicate": self.predicate,
            "object_id": self.object_id,
            "object_literal": self.object_literal,
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "time_precision": self.time_precision,
            "tx_from": self.tx_from,
            "tx_to": self.tx_to,
            "supersedes_id": self.supersedes_id,
            "mutation_id": self.mutation_id,
            "provenance_ref": list(self.provenance_ref),
            "ontology_version": self.ontology_version,
        }


def assertion_id_for(claim_id: str) -> str:
    """결정적 asr- ID (claim_id 기반, idempotency 03 §5)."""
    return "asr-" + hashlib.sha256(claim_id.encode()).hexdigest()[:24]


def materialize(
    claim: ClaimCandidate,
    observed_at: datetime,
    mutation: str | None = None,
) -> Assertion:
    """promoted claim → Assertion (정규 삼항·bitemporal·기본 provenance)."""
    return Assertion(
        assertion_id=assertion_id_for(claim.claim_candidate_id),
        claim_id=claim.claim_candidate_id,
        subject_id=claim.subject_id,
        predicate=claim.predicate,
        object_id=claim.object_id,
        object_literal=claim.object_literal,
        valid_from=getattr(claim, "valid_from", None),
        valid_to=getattr(claim, "valid_to", None),
        time_precision=getattr(claim, "time_precision", "unknown") or "unknown",
        tx_from=observed_at,
        tx_to=None,
        supersedes_id=None,
        mutation_id=mutation or "",
        provenance_ref=(
            # prototype은 promoted claim을 extraction_record의 참조(원본)로 사용.
            # claim(과 그 span)이 extraction_record·source span의 경로를 담는다 (§8.1).
            claim.claim_candidate_id,
        ),
        ontology_version=getattr(claim, "ontology_version", "") or "",
    )
