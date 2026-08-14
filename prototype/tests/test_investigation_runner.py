"""S46 Investigation Runner (설계 07 §4 조사 루프) TDD.

S43 coverage→S44 Graph Explorer→S45 counter-evidence를 하나의 루프로 묶어 read-only로
종료까지 진행. 종료: coverage ≥ 0.80(10 §1.3) || gap에서 no_new_evidence || 반복 예산.

- run(subclaims): subclaim별 coverage·gap·counter_evidence, iterations, terminated_by.
- read-only (불변식 §3-3): 반복이 그래프·존을 수정하지 않음 (같은 state 평가).
- 결정성.

Atomic TDD: Red → Green.
"""
from __future__ import annotations

import pytest

from orc_citadel.investigation_runner import InvestigationRunner
from orc_citadel.investigation import Subclaim
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


def _graph():
    from orc_citadel.graph_service import GraphService as GS
    g = GS()
    g.apply([
        {"mutation_id": "m1", "idempotency_key": "k1", "op": "create_node",
         "payload": {"id": "org-a", "props": {}, "labels": []}},
        {"mutation_id": "m2", "idempotency_key": "k2", "op": "create_node",
         "payload": {"id": "clm-a", "props": {}, "labels": []}},
        {"mutation_id": "m3", "idempotency_key": "k3", "op": "create_edge",
         "payload": {"type": "ABOUT", "from": "org-a", "to": "clm-a", "props": {}}},
    ])
    return g


def _run(subclaims, **kw):
    return InvestigationRunner(_zone(), _graph(), **kw).run(subclaims)


def test_terminated_by_coverage():
    """전부 covered → terminated_by=coverage, iterations 1."""
    res = _run([Subclaim("s1", "a?", subject_id="org-a")])
    assert res.coverage == pytest.approx(1.0)
    assert res.terminated_by == "coverage"
    assert res.iterations == 1


def test_gap_no_new_evidence():
    """gap 있어도 반복에서 새 evidence 없음 → no_new_evidence terminate."""
    res = _run([Subclaim("s1", "gap?", subject_id="org-zzz")])
    assert res.coverage == 0.0
    assert res.terminated_by == "no_new_evidence"
    assert "s1" in res.gaps


def test_budget_over():
    """반복 예산 1회(미충족) → budget terminate."""
    res = _run([Subclaim("s1", "gap?", subject_id="org-zzz")], max_iters=1)
    assert res.terminated_by == "budget"
    assert res.iterations == 1


def test_counter_evidence_present():
    """gap subclaim에 counter-evidence 포함."""
    res = _run([Subclaim("s1", "zzz?", subject_id="org-zzz")])
    # counter_evidence는 explore 호출 포함.
    assert isinstance(res.counter_evidence, list)
    assert any(c.get("subject_id") == "org-zzz" for c in res.counter_evidence)


def test_budget_hard_stop_d():
    """§4.3 D(budget 소진) → hard stop — coverage와 무관하게 budget terminate."""
    from orc_citadel.investigation_budget import InvestigationBudget
    # max_steps=0 → 단일 iteration에서 이미 소진 → hard stop.
    b = InvestigationBudget(max_steps=0, max_tokens=0)
    res = _run([Subclaim("s1", "a?", subject_id="org-a")], budget=b)
    assert res.terminated_by == "budget"


def test_token_usage_zero():
    """LLM 미실행 prototype → token_usage 0 (S42 placeholder)."""
    res = _run([Subclaim("s1", "a?", subject_id="org-a")])
    assert res.token_usage["input_tokens"] == 0
    assert res.token_usage["calls"] == 0


def test_read_only_no_mutation():
    """runner는 read-only — 반복이 그래프·존 수정 없음."""
    z, g = _zone(), _graph()
    before_z = len(z.assertions())
    before_edges = len(g.edges())
    InvestigationRunner(z, g).run([Subclaim("s1", "a?", subject_id="org-a")])
    assert len(z.assertions()) == before_z
    assert len(g.edges()) == before_edges


def test_search_stage_returns_candidates_for_gap():
    """gap subclaim의 SEARCH 스테이지 — 그래프 공백을 채울 후보 span 반환 (07 §4)."""
    from orc_citadel.extract import Mention

    z = _zone()
    # 검색 corpus에 매칭될 멘션 문장 추가 (context_window = 문장 텍스트).
    z.persist_mention(Mention(mention_id="men-search", doc_id="doc-search",
                              segment_id="doc-search#s0", surface_text="org-a",
                              mention_type="ORG", char_start=0, char_end=4,
                              context_window="org-a announces superconductors"))
    g = _graph()
    res = InvestigationRunner(z, g).run(
        [Subclaim("s1", "superconductors?", subject_id="org-zzz")])
    # SEARCH 스테이지가 gap에 대해 retrieved 후보를 노출.
    assert res.retrieved
    assert res.retrieved[0]["doc_id"] == "doc-search"
    assert "span" in res.retrieved[0]
    assert res.retrieved[0]["retrieval_path"].startswith("bm25")


def test_determinism():
    """동일 입력 → 동일 결과."""
    a = _run([Subclaim("s1", "a?", subject_id="org-a")])
    b = _run([Subclaim("s1", "a?", subject_id="org-a")])
    assert a.coverage == b.coverage and a.terminated_by == b.terminated_by
