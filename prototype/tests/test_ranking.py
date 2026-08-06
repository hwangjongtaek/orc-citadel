"""S31 Subject 신뢰도 랭킹 (설계 09 §2.1 조사 목록·War Table 우선순위 재료) TDD.

S30 결론 프로젝터(`ConclusionProjector.for_subject`)를 소비해 전체 subject를 신뢰도
기준으로 **정렬된 read-only 랭킹**으로 노출한다.

- rank   : value DESC 정렬. tie-breaker: independent_source_count DESC → subject_id ASC
           (완전 결정적 — 동률 순서 고정).
- signal : 주목 신호 — `contradicted`(반박 존재) / `low_evidence`(근거 미확립) /
           `high_confidence`(value ≥ 상위신뢰 임계) / `normal` (조회 우선순위 언어).
- 09 §4 원칙: value 단일 게이지 금지 — 항목마다 결론 봉투(value/evidence_count/
  independent_source_count/basis/dimensions)를 함께 노출.

confidence는 **증거 구조** 기반 (blueprint §11). **read-only** (불변식 §3-3) —
쓰기·영속·그래프 mutation 미노출.

Atomic TDD: Red → Green → Refactor.
"""
from __future__ import annotations

import pytest

from orc_citadel.ranking import ConclusionRanking
from orc_citadel.curated_zone import CuratedZone


def _populate_zone() -> CuratedZone:
    z = CuratedZone(":memory:")
    z.initialize()
    return z


def _seed_claims(z: CuratedZone, claims: list[dict]) -> None:
    from orc_citadel.assertions import materialize
    from orc_citadel.extract import Mention
    from orc_citadel.extract_claims import ClaimCandidate
    from datetime import datetime, timezone

    for i, c in enumerate(claims):
        cc = ClaimCandidate(
            claim_candidate_id=c["cid"], doc_id=c["doc"], predicate=c["pred"],
            subject_id=c["subj"], object_id=c.get("obj"), object_literal=None,
            modality="asserted", polarity="positive", confidence=0.8,
            seg_order=i, char_start=0, char_end=4, surface_fragment="x",
            event_type_hint=None, status="promoted",
        )
        z.persist_claim(cc)
        m = Mention(
            mention_id=f"men-{c['cid']}", doc_id=c["doc"], segment_id=f"{c['doc']}#s0",
            surface_text=c["subj"], mention_type="ORG",
            char_start=0, char_end=4, context_window=None,
        )
        z.persist_mention(m)
        z.set_mention_authoritative(m.mention_id)
        a = materialize(cc, observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                        mutation=f"mut-{c['cid']}")
        z.persist_assertion(a)


# --- 정렬 / rank -----------------------------------------------------------

def test_ranked_value_desc():
    """value DESC 정렬, 1-based rank."""
    z = _populate_zone()
    _seed_claims(z, [
        # org-strong: 3근거 → support 0.75.
        {"cid": "c1", "doc": "d1", "subj": "org-strong", "pred": "announces", "obj": "org-b"},
        {"cid": "c2", "doc": "d2", "subj": "org-strong", "pred": "announces", "obj": "org-b"},
        {"cid": "c3", "doc": "d3", "subj": "org-strong", "pred": "announces", "obj": "org-b"},
        # org-weak: 1근거 → support 0.5.
        {"cid": "c4", "doc": "d4", "subj": "org-weak", "pred": "announces", "obj": "org-c"},
    ])
    r = ConclusionRanking(z)
    ranked = r.ranked()
    assert [x.subject_id for x in ranked] == ["org-strong", "org-weak"]
    assert ranked[0].rank == 1
    assert ranked[1].rank == 2
    assert ranked[0].confidence["value"] > ranked[1].confidence["value"]


def test_ranked_tiebreak_independent_sources():
    """동률 value → 독립 출처 DESC."""
    z = _populate_zone()
    _seed_claims(z, [
        # org-a: 1근거.
        {"cid": "c1", "doc": "d1", "subj": "org-a", "pred": "announces", "obj": "org-b"},
        # org-b: 1근거 — 같은 support 0.5, value 동률.
        {"cid": "c2", "doc": "d2", "subj": "org-b", "pred": "announces", "obj": "org-b"},
    ])
    # org-a에 복제 근거 추가 → 독립 출처 1, 근거 2? 아니 — 어세션 1건(1문서)을 유지하려면
    # 여기서는 같은 subject의 근거 문서를 늘리지 않고, dup_cluster로 독립 보정만 확인.
    # 동률 유지: 두 subject 모두 독립 1 → tie-break은 subject_id ASC.
    r = ConclusionRanking(z)
    ranked = r.ranked()
    # 동률 value + 동률 indep → subject_id ASC.
    assert {x.subject_id for x in ranked} == {"org-a", "org-b"}
    assert ranked[0].subject_id == "org-a"


def test_ranked_tiebreak_subject_alpha():
    """값·독립 동률 → subject_id ASC (결정적 순서)."""
    z = _populate_zone()
    _seed_claims(z, [
        {"cid": "c1", "doc": "d1", "subj": "org-zed", "pred": "announces", "obj": "org-b"},
        {"cid": "c2", "doc": "d2", "subj": "org-abc", "pred": "announces", "obj": "org-b"},
    ])
    r = ConclusionRanking(z)
    ranked = r.ranked()
    assert ranked[0].subject_id == "org-abc"
    assert ranked[1].subject_id == "org-zed"


# --- signal ----------------------------------------------------------------

def test_signal_high_confidence():
    """value ≥ 0.8 → high_confidence."""
    z = _populate_zone()
    _seed_claims(z, [
        # 4근거(4문서) → support 0.8.
        {"cid": "c1", "doc": "d1", "subj": "org-a", "pred": "announces", "obj": "org-b"},
        {"cid": "c2", "doc": "d2", "subj": "org-a", "pred": "announces", "obj": "org-b"},
        {"cid": "c3", "doc": "d3", "subj": "org-a", "pred": "announces", "obj": "org-b"},
        {"cid": "c4", "doc": "d4", "subj": "org-a", "pred": "announces", "obj": "org-b"},
    ])
    r = ConclusionRanking(z)
    assert r.ranked()[0].signal == "high_confidence"


def test_signal_contradicted():
    """반박 존재(contradiction>0) → contradicted."""
    z = _populate_zone()
    _seed_claims(z, [
        {"cid": "c1", "doc": "d1", "subj": "org-a", "pred": "announces", "obj": "org-b"},
        {"cid": "c2", "doc": "d2", "subj": "org-a", "pred": "announces", "obj": "org-b"},
        {"cid": "c3", "doc": "d3", "subj": "org-a", "pred": "denies", "obj": "org-b"},
    ])
    from orc_citadel.contradiction import ConflictCandidate

    z.persist_conflict(ConflictCandidate(
        claim_id_a="c1", claim_id_b="c3", conflict_type="value_conflict",
        rationale="denies announces", judged_by="pipeline"))
    r = ConclusionRanking(z)
    assert r.ranked()[0].signal == "contradicted"


def test_signal_low_evidence():
    """근거 0 → low_evidence."""
    z = _populate_zone()
    # 어세션만 (지지 근거 없는 predicts) → evidence_count 0.
    from orc_citadel.assertions import materialize
    from orc_citadel.extract_claims import ClaimCandidate
    from datetime import datetime, timezone

    cc = ClaimCandidate(
        claim_candidate_id="clm-x", doc_id="doc-9", predicate="predicts",
        subject_id="org-a", object_id=None, object_literal="growth",
        modality="prediction", polarity="positive", confidence=0.5,
        seg_order=0, char_start=0, char_end=4, surface_fragment="x",
        event_type_hint=None, status="promoted",
    )
    z.persist_assertion(materialize(cc, observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                                    mutation="mut-x"))
    r = ConclusionRanking(z)
    assert r.ranked()[0].signal == "low_evidence"


# --- 필터 / limit / by_signal ----------------------------------------------

def test_ranked_signal_filter():
    """signal= 필터 — 해당 신호만."""
    from orc_citadel.assertions import materialize
    from orc_citadel.extract_claims import ClaimCandidate
    from datetime import datetime, timezone

    z = _populate_zone()
    _seed_claims(z, [
        # org-b: 근거 4 → high_confidence.
        {"cid": "c2", "doc": "d2", "subj": "org-b", "pred": "announces", "obj": "org-c"},
        {"cid": "c3", "doc": "d3", "subj": "org-b", "pred": "announces", "obj": "org-c"},
        {"cid": "c4", "doc": "d4", "subj": "org-b", "pred": "announces", "obj": "org-c"},
        {"cid": "c5", "doc": "d5", "subj": "org-b", "pred": "announces", "obj": "org-c"},
    ])
    # org-a: 지지 근거 없는 어세션만 → low_evidence.
    cc = ClaimCandidate(
        claim_candidate_id="clm-ax", doc_id="doc-9", predicate="predicts",
        subject_id="org-a", object_id=None, object_literal="growth",
        modality="prediction", polarity="positive", confidence=0.5,
        seg_order=0, char_start=0, char_end=4, surface_fragment="x",
        event_type_hint=None, status="promoted",
    )
    z.persist_assertion(materialize(cc, observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                                    mutation="mut-ax"))
    r = ConclusionRanking(z)
    hi = r.ranked(signal="high_confidence")
    assert [x.subject_id for x in hi] == ["org-b"]
    lo = r.ranked(signal="low_evidence")
    assert [x.subject_id for x in lo] == ["org-a"]


def test_ranked_limit():
    """limit= 상위 N만."""
    z = _populate_zone()
    _seed_claims(z, [
        {"cid": "c1", "doc": "d1", "subj": "org-a", "pred": "announces", "obj": "org-b"},
        {"cid": "c2", "doc": "d2", "subj": "org-b", "pred": "announces", "obj": "org-b"},
        {"cid": "c3", "doc": "d3", "subj": "org-c", "pred": "announces", "obj": "org-b"},
    ])
    r = ConclusionRanking(z)
    assert len(r.ranked(limit=2)) == 2


def test_by_signal_groups():
    """by_signal — signal별 묶음."""
    z = _populate_zone()
    _seed_claims(z, [
        {"cid": "c1", "doc": "d1", "subj": "org-a", "pred": "announces", "obj": "org-b"},
    ])
    # org-a 근거 1 → normal. org-b는 지지 근거 없는 어세션만 → low_evidence.
    from orc_citadel.assertions import materialize
    from orc_citadel.extract_claims import ClaimCandidate
    from datetime import datetime, timezone

    cc = ClaimCandidate(
        claim_candidate_id="clm-bx", doc_id="doc-9", predicate="predicts",
        subject_id="org-b", object_id=None, object_literal="growth",
        modality="prediction", polarity="positive", confidence=0.5,
        seg_order=0, char_start=0, char_end=4, surface_fragment="x",
        event_type_hint=None, status="promoted",
    )
    z.persist_assertion(materialize(cc, observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                                    mutation="mut-bx"))
    r = ConclusionRanking(z)
    groups = r.by_signal()
    assert "normal" in groups and "org-a" in groups["normal"]
    assert "low_evidence" in groups and "org-b" in groups["low_evidence"]


# --- 봉투 / read-only / empty ----------------------------------------------

def test_ranking_envelope_complete():
    """랭킹 항목마다 결론 봉투(09 §4) 노출 — 단일 value 게이지 금지."""
    z = _populate_zone()
    _seed_claims(z, [
        {"cid": "c1", "doc": "d1", "subj": "org-a", "pred": "announces", "obj": "org-b"},
    ])
    r = ConclusionRanking(z)
    item = r.ranked()[0]
    for k in ("value", "evidence_count", "independent_source_count", "basis", "dimensions"):
        assert k in item.confidence


def test_read_only_no_mutation():
    """랭킹은 read-only — 쓰기·영속·그래프 mutation 미노출."""
    z = _populate_zone()
    _seed_claims(z, [
        {"cid": "c1", "doc": "d1", "subj": "org-a", "pred": "announces", "obj": "org-b"},
    ])
    r = ConclusionRanking(z)
    for bad in ("apply", "persist", "create_node", "create_edge", "insert"):
        assert not hasattr(r, bad), f"read-only 위반: {bad} 노출"


def test_empty_zone():
    """빈 zone → [] (종합 없음)."""
    r = ConclusionRanking(_populate_zone())
    assert r.ranked() == []
    assert r.by_signal() == {}
