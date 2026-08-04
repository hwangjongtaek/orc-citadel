"""S11 Assertion materialization (설계 03 §6.2·§7, ADR-306) — TDD.

게이트로 promoted된 claim의 정규 삼항 Assertion을 bitemporal(valid+transaction)로
materialize한다. Claim→Assertion emission 계약: 동일 claim 재실행 시 중복 materialize
금지(idempotency, 03 §7·§5), append-only create_node 이벤트로 생성 (§7.1).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from orc_citadel.assertions import Assertion, materialize
from orc_citadel.extract_claims import ClaimCandidate, claim_id_for


def _claim(pred: str = "announces", subj: str = "org-1",
           obj: str | None = None, valid_to=None,
           mutation: str = "mut-0001") -> ClaimCandidate:
    return ClaimCandidate(
        claim_candidate_id=claim_id_for("doc-1", 0, 0, 10, pred),
        doc_id="doc-1", predicate=pred, subject_id=subj, object_id=obj,
        object_literal=None, modality="asserted", polarity="positive",
        confidence=0.8, seg_order=0, char_start=0, char_end=10,
        surface_fragment="will host", event_type_hint=None, status="promoted",
    )


def _now() -> datetime:
    return datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)


def test_materialize_basic():
    """promoted claim → 정규 삼항 Assertion (bitemporal)."""
    c = _claim()
    a = materialize(c, observed_at=_now(), mutation="mut-0001")
    assert a.assertion_id.startswith("asr-")
    assert a.subject_id == "org-1"
    assert a.predicate == "announces"
    assert a.object_id is None  # object_literal XOR
    # transaction time: tx_from=observed, tx_to=null(현재 버전).
    assert a.tx_from == _now()
    assert a.tx_to is None
    assert a.mutation_id == "mut-0001"
    # valid time 미상 → null + time_precision unknown.
    assert a.time_precision == "unknown"


def test_materialize_deterministic_id():
    """동일 claim → 동일 asr- (idempotency, 03 §5)."""
    c = _claim()
    a1 = materialize(c, observed_at=_now(), mutation="mut-1")
    a2 = materialize(c, observed_at=_now(), mutation="mut-1")
    assert a1.assertion_id == a2.assertion_id


def test_materialize_object_literal_xor():
    """object_literal 있으면 object_id 없음 (02 §2.4 XOR)."""
    c = _claim(obj="org-2")
    a = materialize(c, observed_at=_now(), mutation="mut-1")
    assert a.object_id == "org-2"
    assert a.object_literal is None


def test_provenance_ref_links_claim():
    """Assertion은 promoted claim(source span)을 provenance로 참조 (03 §8)."""
    c = _claim()
    a = materialize(c, observed_at=_now(), mutation="mut-1")
    assert c.claim_candidate_id in (a.provenance_ref or [])


def test_tx_time_immutable_version():
    """tx_to=null은 현재 버전 — supersede 후속에서 close (03 §6.2 ADR-303/307)."""
    c = _claim()
    a = materialize(c, observed_at=_now(), mutation="mut-1")
    assert a.tx_to is None  # 열린 현재 버전


def test_valid_from_to():
    """valid time 반영 (있으면 not null, 없으면 unknown)."""
    # prototype claim은 valid 없음 → unknown. 필드 정합성만 확인.
    a = materialize(_claim(), observed_at=_now(), mutation="mut-1")
    assert a.valid_from is None
    assert a.valid_to is None
    assert a.time_precision == "unknown"
