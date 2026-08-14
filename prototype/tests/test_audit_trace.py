"""Synthesis·Audit 증거 역추적 chain (설계 07 §3.8·§3.9) TDD.

Audit Agent — 보고서의 모든 검증가능 문장을 claim·source span으로 **역추적**하고
무출처·미역추적 문장을 차단 (§3.9 불변식 §3-5 · 인용 연결률 = 1.0, 10 §1.3).

- trace(statements, zone): 문장 → claim_ref → extraction_record(segment_id·
  char span) → document provenance chain 역추적. 출력 {trace: [{statement_ref,
  claim_ref, source_span, verified}], blocked_statements[]} (§3.9).
- fact/asserted 문장은 반드시 claim_ref + 유효한 source span으로 역추적.
- prediction/opinion 무출처 허용 (연결률 분모 제외, 10 §1.3).
- 역추적 불가(claim_ref 없음 / extraction_record 없음) → verified=False·blocked.
- **read-only** (불변식 §3-3) · 결정적.

Atomic TDD: Red → Green.
"""
from __future__ import annotations

import pytest

from orc_citadel.synthesis import Audit, Synthesizer, SynthesisReport
from orc_citadel.curated_zone import CuratedZone


def _zone_with_provenance() -> CuratedZone:
    """claim + extraction_record(span)이 존재하는 존."""
    from orc_citadel.assertions import materialize
    from orc_citadel.extract import Mention
    from orc_citadel.extract_claims import ClaimCandidate
    from datetime import datetime, timezone

    z = CuratedZone(":memory:")
    z.initialize()
    cc = ClaimCandidate(
        claim_candidate_id="clm-a", doc_id="doc-a", predicate="announces",
        subject_id="org-a", object_id="org-b", object_literal=None,
        modality="asserted", polarity="positive", confidence=0.8,
        seg_order=0, char_start=240, char_end=300, surface_fragment="x",
        event_type_hint=None, status="promoted")
    z.persist_claim(cc)
    z.persist_mention(Mention(mention_id="men-a", doc_id="doc-a",
                              segment_id="doc-a#p0", surface_text="org-a",
                              mention_type="ORG", char_start=240, char_end=300,
                              context_window="org-a announces org-b"))
    z.persist_assertion(materialize(cc, observed_at=datetime(2026, 1, 1,
                                                             tzinfo=timezone.utc),
                                    mutation="mut-a"))
    # provenance — 추출 기록(span) 영속.
    z.persist_extraction_record(element_id="clm-a", doc_id="doc-a",
                                segment_id="doc-a#p0", char_start=240,
                                char_end=300, content_hash="h")
    return z


def _statements():
    return [
        {"text": "org-a는 announces 한다", "modality": "asserted",
         "claim_ref": "clm-a"},
        {"text": "향후 예측문", "modality": "prediction", "claim_ref": None},
    ]


def test_trace_reverse_trace_to_span():
    """asserted 문장이 claim_ref→extraction_record span까지 역추적 → verified."""
    z = _zone_with_provenance()
    audit = Audit()
    tr = audit.trace(_statements(), z)
    assert tr["verified_statements"] == 1
    row = next(t for t in tr["trace"]
               if t["statement_ref"] == "st0")
    assert row["claim_ref"] == "clm-a"
    # source span — segment_id + char span (provenance chain, §3.9·03 §8).
    assert row["source_span"]["segment_id"] == "doc-a#p0"
    assert row["source_span"]["char_start"] == 240
    assert row["source_span"]["char_end"] == 300
    assert row["verified"] is True


def test_trace_unattributed_asserted_blocked():
    """asserted가 claim_ref 없음 → blocked (무출처 차단, 불변식 §3-5)."""
    z = _zone_with_provenance()
    audit = Audit()
    tr = audit.trace([{"text": "무출처 주장", "modality": "asserted",
                       "claim_ref": None}], z)
    assert tr["verified_statements"] == 0
    assert len(tr["blocked_statements"]) == 1
    b = tr["blocked_statements"][0]
    assert b["modality"] == "asserted"
    assert "claim_ref" in str(b["reason"])


def test_trace_missing_provenance_blocked():
    """claim_ref 있으나 extraction_record(span) 부재 → verified=False·blocked."""
    z = _zone_with_provenance()
    # clm-x 는 claim_ref만, extraction_record 없음.
    tr = Audit().trace([{"text": "x", "modality": "asserted",
                         "claim_ref": "clm-x"}], z)
    assert tr["verified_statements"] == 0
    assert len(tr["blocked_statements"]) == 1


def test_trace_linkage_ratio_100():
    """검증가능 문장 모두 역추적 → 연결률 = 1.0 (10 §1.3, 불변식 §3-5)."""
    z = _zone_with_provenance()
    tr = Audit().trace(_statements(), z)
    # prediction 은 무출처 허용 → 분모(검증가능)에서 제외.
    assert tr["verifiable"] == 1
    assert tr["linked"] == 1
    assert tr["linkage_ratio"] == pytest.approx(1.0)


def test_audit_verify_blocked_on_unverified():
    """역추적 실패(blocked) 존재 시 audit.passed=False (§3.9)."""
    z = _zone_with_provenance()
    audit = Audit()
    tr = audit.trace([{"text": "무출처", "modality": "asserted",
                       "claim_ref": None}], z)
    verdict = audit.verify_from_trace(tr)
    assert verdict["passed"] is False
    assert verdict["violations"]


def test_read_only_no_mutation():
    """audit은 read-only — 쓰기·mutation 미노출."""
    a = Audit()
    for bad in ("apply", "persist", "create_node", "create_edge", "insert"):
        assert not hasattr(a, bad), f"read-only 위반: {bad} 노출"


def test_determinism():
    """동일 입력 → 동일 trace."""
    z = _zone_with_provenance()
    a = Audit().trace(_statements(), z)
    b = Audit().trace(_statements(), z)
    assert a == b
