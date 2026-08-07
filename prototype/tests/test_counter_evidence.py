"""S45 Counter-Evidence Agent (설계 07 §3.6) TDD.

현재 결론(subject·predicate)에 대한 반증 탐색 — hypotheses·negative_queries·
contradiction_candidates를 read-only로 산출. 반박을 binary가 아닌 근거·판정 이유 포함.

- hypotheses: subject에 대한 부정적·반대 가설 (결정적 규칙 생성).
- negative_queries: 결론을 반박하는 용어 조합 (부정·무효화·취소).
- contradiction_candidates: S10 기존 모순 (같은 subject 다른 주장, conflict_type 구분).
- **read-only** (불변식 §3-3) — 쓰기·그래프 mutation 미노출.

Atomic TDD: Red → Green.
"""
from __future__ import annotations

import pytest

from orc_citadel.counter_evidence import CounterEvidenceAgent
from orc_citadel.curated_zone import CuratedZone


def _zone_with_conflict() -> CuratedZone:
    from orc_citadel.extract_claims import ClaimCandidate

    z = CuratedZone(":memory:")
    z.initialize()
    # 같은 subject org-a: announces(clm-a) vs denies(clm-c) — 모순.
    def _claim(cid, pred):
        return ClaimCandidate(
            claim_candidate_id=cid, doc_id=f"doc-{cid}", predicate=pred,
            subject_id="org-a", object_id="org-b", object_literal=None,
            modality="asserted", polarity="positive", confidence=0.8,
            seg_order=0, char_start=0, char_end=4, surface_fragment="x",
            event_type_hint=None, status="promoted")
    z.persist_claim(_claim("clm-a", "announces"))
    z.persist_claim(_claim("clm-c", "denies"))
    from orc_citadel.contradiction import ConflictCandidate
    z.persist_conflict(ConflictCandidate(
        claim_id_a="clm-a", claim_id_b="clm-c", conflict_type="value_conflict",
        rationale="denies contradicts announces", judged_by="pipeline"))
    return z


def test_hypotheses_negative():
    """hypotheses — subject에 대한 부정적 반대 가설 (결정적)."""
    agent = CounterEvidenceAgent(_zone_with_conflict())
    hyps = agent.hypotheses("org-a", "announces")
    assert isinstance(hyps, list) and hyps
    assert any("not" in h.lower() or "반대" in h or "부정" in h for h in hyps)


def test_negative_queries():
    """negative_queries — 결론 반박 용어 조합."""
    agent = CounterEvidenceAgent(_zone_with_conflict())
    qs = agent.negative_queries("org-a", "announces")
    assert isinstance(qs, list) and qs
    # 반박·취소 용어 포함.
    assert any("den" in q.lower() or "cancel" in q.lower() or "반대" in q for q in qs)


def test_contradiction_candidates():
    """contradiction_candidates — subject 기존 모순 (이유 포함)."""
    agent = CounterEvidenceAgent(_zone_with_conflict())
    cands = agent.contradiction_candidates("org-a")
    assert len(cands) == 1
    c = cands[0]
    assert c["conflict_type"] == "value_conflict"
    assert c["rationale"]  # 근거·이유 필수 (07 §3.6 불변식).
    # 반박이 binary가 아닌 이유 포함.
    assert {"claim_a", "claim_b", "conflict_type", "rationale"} <= set(c)


def test_explore_structure():
    """explore — 3개 출력 포함."""
    agent = CounterEvidenceAgent(_zone_with_conflict())
    res = agent.explore("org-a", "announces", "org-b")
    assert "conclusion" in res and "hypotheses" in res
    assert "negative_queries" in res and "contradiction_candidates" in res


def test_no_conflict_empty():
    """모순 없는 subject — contradiction_candidates 빈 목록."""
    z = CuratedZone(":memory:")
    z.initialize()
    agent = CounterEvidenceAgent(z)
    assert agent.contradiction_candidates("org-x") == []


def test_read_only_no_mutation():
    """agent는 read-only — 쓰기·그래프 mutation 미노출."""
    agent = CounterEvidenceAgent(_zone_with_conflict())
    for bad in ("apply", "persist", "create_node", "create_edge", "insert"):
        assert not hasattr(agent, bad), f"read-only 위반: {bad} 노출"


def test_determinism():
    """동일 입력 → 동일 출력."""
    agent = CounterEvidenceAgent(_zone_with_conflict())
    a = agent.explore("org-a", "announces")
    b = agent.explore("org-a", "announces")
    assert a == b
