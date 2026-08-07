"""S47 Synthesis/Audit (설계 07 §9.3, README §3-5) — 트랙 최종 TDD.

조사 루프(S46) 결과와 S30 subject 결론을 합성해 report 생성 + Audit evidence-first
불변식 검증 (07 §9.3: 검증 subgraph 문장만, 무출처는 prediction만).

- conclusion: S30 결론 봉투 (09 §4 — 단일 게이지 금지).
- statement: evidence-first — claim_ref(provenance) 소유.
- open_questions: gap subclaim (미충족 질문, 09 §3).
- Audit: 무출처 fact/asserted → violation; prediction 무출처 허용.
- **read-only** (불변식 §3-3).

Atomic TDD: Red → Green.
"""
from __future__ import annotations

import pytest

from orc_citadel.synthesis import Synthesizer, SynthesisReport
from orc_citadel.curated_zone import CuratedZone


def _zone() -> CuratedZone:
    from orc_citadel.assertions import materialize
    from orc_citadel.extract import Mention
    from orc_citadel.extract_claims import ClaimCandidate
    from datetime import datetime, timezone

    z = CuratedZone(":memory:")
    z.initialize()
    claims = [("clm-a", "doc-a", "org-a", "announces", "org-b"),
              ("clm-b", "doc-b", "org-a", "announces", "org-b")]
    for i, (cid, doc, subj, pred, obj) in enumerate(claims):
        cc = ClaimCandidate(
            claim_candidate_id=cid, doc_id=doc, predicate=pred, subject_id=subj,
            object_id=obj, object_literal=None, modality="asserted",
            polarity="positive", confidence=0.8, seg_order=i, char_start=0,
            char_end=4, surface_fragment="x", event_type_hint=None, status="promoted")
        z.persist_claim(cc)
        z.persist_mention(Mention(mention_id=f"men-{cid}", doc_id=doc,
                                  segment_id=f"{doc}#s0", surface_text=subj,
                                  mention_type="ORG", char_start=0, char_end=4,
                                  context_window=None))
        z.persist_assertion(materialize(cc, observed_at=datetime(2026, 1, 1,
                                                                 tzinfo=timezone.utc),
                                        mutation=f"mut-{cid}"))
    return z


def _inv_result(subject_id, gaps, coverage=1.0):
    from orc_citadel.investigation_runner import InvestigationResult
    return InvestigationResult(
        subject_id=subject_id, coverage=coverage,
        subclaims=[], gaps=gaps, counter_evidence=[], iterations=1,
        terminated_by="coverage",
        token_usage={"input_tokens": 0, "output_tokens": 0, "calls": 0})


def test_synthesis_conclusion_envelope():
    """conclusion — S30 결론 봉투 (09 §4 단일 게이지 금지)."""
    z = _zone()
    inv = _inv_result("org-a", [])
    rep = Synthesizer(z).synthesize(inv, "org-a")
    c = rep.conclusion
    for k in ("value", "evidence_count", "independent_source_count", "basis", "dimensions"):
        assert k in c, f"결론 봉투 필드 부재: {k}"
    assert 0.0 <= c["value"] <= 1.0


def test_statements_evidence_first():
    """statement — fact/asserted는 claim_ref(provenance) 소유 (evidence-first)."""
    z = _zone()
    inv = _inv_result("org-a", [])
    rep = Synthesizer(z).synthesize(inv, "org-a")
    asserted = [s for s in rep.statements if s["modality"] in ("fact", "asserted")]
    for s in asserted:
        assert s["claim_ref"], "asserted/fact 무출처 — evidence-first 위반"
    # 적어도 1개 asserted 문장 존재 (결론 반영).
    assert asserted


def test_open_questions_from_gaps():
    """gap subclaim → open_questions 포함 (아직 증거 부족)."""
    z = _zone()
    inv = _inv_result("org-a", ["s-gap"])
    rep = Synthesizer(z).synthesize(inv, "org-a")
    oq = rep.open_questions
    assert any(q["reason"] is not None for q in oq)


def test_audit_passes_evidence_first():
    """잘 생성된 report — audit passed, 위반 없음."""
    z = _zone()
    inv = _inv_result("org-a", [])
    rep = Synthesizer(z).synthesize(inv, "org-a")
    audit = rep.audit
    assert audit["violations"] == []
    assert audit["passed"] is True


def test_audit_catches_unattributed_asserted():
    """asserted statement가 claim_ref 없음 → audit violation (README §3-5)."""
    z = _zone()
    inv = _inv_result("org-a", [])
    # 잘못된 statement 직접 주입 — 무출처 asserted.
    bad_report = SynthesisReport(
        subject_id="org-a", conclusion={"value": 0.5}, statements=[
            {"text": "무근거 주장", "modality": "asserted", "claim_ref": None}],
        open_questions=[], audit={})
    from orc_citadel.synthesis import Audit
    audit = Audit().verify(bad_report)
    assert audit["passed"] is False
    assert len(audit["violations"]) >= 1


def test_read_only_no_mutation():
    """synthesizer는 read-only — 쓰기·mutation 미노출."""
    s = Synthesizer(_zone())
    for bad in ("apply", "persist", "create_node", "create_edge", "insert"):
        assert not hasattr(s, bad), f"read-only 위반: {bad} 노출"


def test_determinism():
    """동일 입력 → 동일 report."""
    z = _zone()
    inv = _inv_result("org-a", [])
    a = Synthesizer(z).synthesize(inv, "org-a")
    b = Synthesizer(z).synthesize(inv, "org-a")
    assert a == b
