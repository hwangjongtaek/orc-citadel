"""C1 조사 에이전트 트랙(S43–S47) edge case 보강 TDD.

빈 zone·미존재 subject·미존재 그래프 노드 등에서 각 계층이 크래시 없이
**결정적·read-only**로 동작하는지 고정한다. 빈 상태가 합리적 기본값(0/빈/None)을
돌려주고 그래프·존을 수정하지 않아야 한다.
"""
from __future__ import annotations

import pytest

from orc_citadel.curated_zone import CuratedZone


def _empty_zone() -> CuratedZone:
    z = CuratedZone(":memory:")
    z.initialize()
    return z


def _empty_graph():
    from orc_citadel.graph_service import GraphService as GS
    return GS()


def _zone_with_conflict():
    from orc_citadel.extract_claims import ClaimCandidate
    z = CuratedZone(":memory:"); z.initialize()
    def _claim(cid, pred):
        return ClaimCandidate(claim_candidate_id=cid, doc_id=f"doc-{cid}",
                              predicate=pred, subject_id="org-a", object_id="org-b",
                              object_literal=None, modality="asserted",
                              polarity="positive", confidence=0.8, seg_order=0,
                              char_start=0, char_end=4, surface_fragment="x",
                              event_type_hint=None, status="promoted")
    z.persist_claim(_claim("clm-a", "announces"))
    z.persist_claim(_claim("clm-c", "denies"))
    from orc_citadel.contradiction import ConflictCandidate
    z.persist_conflict(ConflictCandidate(claim_id_a="clm-a", claim_id_b="clm-c",
                                         conflict_type="value_conflict",
                                         rationale="deny", judged_by="pipeline"))
    return z


# --- S43 coverage: 빈 subclaim / 빈 zone -----------------------------------

def test_coverage_empty_subclaims():
    """subclaim 없음 → coverage 0, gaps 빈."""
    from orc_citadel.investigation import InvestigationCoverage
    res = InvestigationCoverage(_empty_zone()).coverage([])
    assert res.coverage == 0.0
    assert res.gaps == []
    assert res.expected_info_gain == {}


def test_coverage_empty_zone_subject():
    """빈 zone의 subject → covered False, gap (크래시 없음)."""
    from orc_citadel.investigation import InvestigationCoverage, Subclaim
    res = InvestigationCoverage(_empty_zone()).coverage(
        [Subclaim("s1", "q?", subject_id="org-x")])
    assert res.coverage == 0.0
    assert "s1" in res.gaps


# --- S44 Graph Explorer: 미존재 노드 ----------------------------------------

def test_explorer_missing_subject():
    """미존재 그래프 노드 → subgraph entity None, 빈 paths (크래시 없음)."""
    from orc_citadel.graph_explorer import GraphExplorer
    res = GraphExplorer(_empty_zone(), _empty_graph()).explore("s1", "org-missing")
    assert res["subgraph"]["entity"] is None
    assert res["relation_paths"] == []
    assert res["independence_summary"]["evidence_count"] == 0


# --- S45 counter-evidence: 모순 없음 부정 -----------------------------------

def test_counter_no_conflict_no_mutation():
    """모순 없는 subject → contradiction_candidates 빈, zone 수정 없음."""
    from orc_citadel.counter_evidence import CounterEvidenceAgent
    z = _empty_zone()
    agent = CounterEvidenceAgent(z)
    before = len(z.conflict_candidates())
    assert agent.contradiction_candidates("org-x") == []
    assert len(z.conflict_candidates()) == before  # read-only.


def test_counter_read_only_on_explore():
    """explore는 hypotheses/query만, 영속 없음."""
    from orc_citadel.counter_evidence import CounterEvidenceAgent
    z = _zone_with_conflict()
    agent = CounterEvidenceAgent(z)
    before_assertions = len(z.assertions())
    res = agent.explore("org-a", "announces")
    assert len(res["hypotheses"]) >= 1
    assert len(z.assertions()) == before_assertions


# --- S46 runner: gap만 / 빈 zone -------------------------------------------

def test_runner_empty_zone():
    """빈 zone + subclaim → coverage 0, no_new_evidence, zone 수정 없음."""
    from orc_citadel.investigation_runner import InvestigationRunner
    from orc_citadel.investigation import Subclaim
    z = _empty_zone()
    res = InvestigationRunner(z, _empty_graph()).run(
        [Subclaim("s1", "q?", subject_id="org-x")])
    assert res.coverage == 0.0
    assert res.terminated_by == "no_new_evidence" or res.terminated_by == "budget"
    assert len(z.assertions()) == 0  # read-only.


def test_runner_no_subject_subclaim():
    """subject 없는 subclaim — runner가 크래시 없이 gap 처리."""
    from orc_citadel.investigation_runner import InvestigationRunner
    from orc_citadel.investigation import Subclaim
    res = InvestigationRunner(_empty_zone(), _empty_graph()).run(
        [Subclaim("s1", "무주제 질문")])  # subject_id None.
    assert "s1" in res.gaps
    assert res.coverage == 0.0


# --- S47 Synthesis: 근거 없는 subject ---------------------------------------

def test_synthesis_no_evidence_subject():
    """근거 없는 subject → 결론 봉투 기본(0), audit은 무출처 없으면 passed."""
    from orc_citadel.synthesis import Synthesizer
    from orc_citadel.investigation_runner import InvestigationResult
    z = _empty_zone()
    inv = InvestigationResult(subject_id="org-x", coverage=0.0, subclaims=[],
                              gaps=["s1"], counter_evidence=[], retrieved=[],
                              iterations=1, terminated_by="no_new_evidence",
                              token_usage={"input_tokens":0,"output_tokens":0,"calls":0})
    rep = Synthesizer(z).synthesize(inv, "org-x")
    # 근거 없어 statements 비거나, 있는 경우에도 audit 위반 없음.
    assert rep.conclusion["value"] == 0.0
    assert all(s["claim_ref"] for s in rep.statements)  # evidence-first 유지.


def test_determinism_edge():
    """빈 상태에서도 결정성."""
    from orc_citadel.investigation import InvestigationCoverage, Subclaim
    a = InvestigationCoverage(_empty_zone()).coverage([Subclaim("s","q?",subject_id="x")])
    b = InvestigationCoverage(_empty_zone()).coverage([Subclaim("s","q?",subject_id="x")])
    assert a == b
