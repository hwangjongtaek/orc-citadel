"""S43 조사 루프 — evidence coverage & gap identification (설계 07 §4, 10 §1.3) TDD.

investigation loop의 evidence coverage(10 §1.3 `covered/planned`)와 graph gap
식별(07 §4 IDENTIFY_GAPS)을 read-only로 계산. subclaim 각각이 근거로 뒷받침되는지
S29 근거 프로젝션으로 판정.

- coverage: 근거 충족 subclaim/전체 (10 §1.3, gate ≥ 0.80).
- covered subclaim: evidence_count > 0 (subject 없는 가설은 항상 gap).
- expected_info_gain: 미충족 subclaim의 Δcoverage 휴리스틱 (07 §2.3).
- **read-only** (불변식 §3-3): 평가만, graph mutation·영속 미노출.

Atomic TDD: Red → Green → Refactor.
"""
from __future__ import annotations

import pytest

from orc_citadel.investigation import InvestigationCoverage, Subclaim
from orc_citadel.curated_zone import CuratedZone


def _zone() -> CuratedZone:
    z = CuratedZone(":memory:")
    z.initialize()
    # 어세션 2건 (subject org-a announce) → 근거 보유.
    from orc_citadel.assertions import materialize
    from orc_citadel.extract import Mention
    from orc_citadel.extract_claims import ClaimCandidate
    from datetime import datetime, timezone

    claims = [
        ("clm-a", "doc-a", "org-a", "announces", "org-b"),
        ("clm-b", "doc-b", "org-a", "announces", "org-b"),
    ]
    for i, (cid, doc, subj, pred, obj) in enumerate(claims):
        cc = ClaimCandidate(
            claim_candidate_id=cid, doc_id=doc, predicate=pred, subject_id=subj,
            object_id=obj, object_literal=None, modality="asserted",
            polarity="positive", confidence=0.8, seg_order=i, char_start=0,
            char_end=4, surface_fragment="x", event_type_hint=None,
            status="promoted")
        z.persist_claim(cc)
        z.persist_mention(Mention(mention_id=f"men-{cid}", doc_id=doc,
                                  segment_id=f"{doc}#s0", surface_text=subj,
                                  mention_type="ORG", char_start=0, char_end=4,
                                  context_window=None))
        z.persist_assertion(materialize(cc, observed_at=datetime(2026, 1, 1,
                                                                 tzinfo=timezone.utc),
                                        mutation=f"mut-{cid}"))
    return z


def test_coverage_ratio():
    """2 subclaim 중 1개 근거 충족 → coverage 0.5 (10 §1.3)."""
    z = _zone()
    cov = InvestigationCoverage(z)
    res = cov.coverage([
        Subclaim(id="s1", subject_id="org-a", text="org-a가 announces?")],  # 근거 보유.
    )
    assert res.coverage == pytest.approx(1.0)
    assert res.subclaims[0].covered is True


def test_coverage_partial_gap():
    """근거 없는 subclaim → gap."""
    z = _zone()
    cov = InvestigationCoverage(z)
    res = cov.coverage([
        Subclaim(id="s1", subject_id="org-a", text="org-a announces?"),   # covered.
        Subclaim(id="s2", subject_id="org-zzz", text="org-zzz announces?"),  # gap.
    ])
    assert res.coverage == pytest.approx(0.5)
    assert "s2" in res.gaps
    s2 = next(s for s in res.subclaims if s.id == "s2")
    assert s2.covered is False
    assert s2.gap_reason is not None


def test_no_subject_always_gap():
    """subject 없는 subclaim — 평가 불가, 항상 gap."""
    z = _zone()
    cov = InvestigationCoverage(z)
    res = cov.coverage([Subclaim(id="s1", text="무주제 질문")])
    assert res.coverage == pytest.approx(0.0)
    assert "s1" in res.gaps


def test_expected_info_gain():
    """미충족 subclaim → Δcoverage 휴리스틱 (> 0)."""
    z = _zone()
    cov = InvestigationCoverage(z)
    res = cov.coverage([
        Subclaim(id="s1", subject_id="org-a", text="a?"),      # covered.
        Subclaim(id="s2", subject_id="org-zzz", text="zzz?"),  # gap.
    ])
    gain = res.expected_info_gain
    assert "s2" in gain
    assert gain["s2"] > 0.0  # gap 채우면 coverage 0.5 → ? 상승.


def test_read_only_no_mutation():
    """coverage 평가는 read-only — 쓰기·영속·graph mutation 미노출."""
    cov = InvestigationCoverage(_zone())
    for bad in ("apply", "persist", "create_node", "create_edge", "insert"):
        assert not hasattr(cov, bad), f"read-only 위반: {bad} 노출"


def test_determinism():
    """동일 subclaims/zone → 동일 coverage."""
    z = _zone()
    subclaims = [Subclaim(id="s1", subject_id="org-a", text="a?"),
                 Subclaim(id="s2", subject_id="org-zzz", text="zzz?")]
    cov = InvestigationCoverage(z)
    a = cov.coverage(subclaims)
    b = cov.coverage(subclaims)
    assert a.coverage == b.coverage and a.gaps == b.gaps
