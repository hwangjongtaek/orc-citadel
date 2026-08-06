"""S30 조사 결론·신뢰도 종합 (설계 09 §3 conclusion, blueprint §5.2) TDD.

S29 어세션 근거 프로젝터(AssertionEvidence)를 소비해 **subject-level 결론 신뢰도
봉투**를 생성한다 (09 §3 conclusion.confidence, 09 §4 — `value` 단일 게이지 금지).

- value        : subject 어세션 평균 support × (1 − 반박 위험).
- evidence_count: subject 전체 지지 근거 합.
- independent_source_count: 어세션별 독립 출처 통합 (dup_cluster 보정 유지).
- dimensions   : support(평균)/contradiction(반박 위험)/coverage(근거 있는 비율).
- by_predicate : predicate별 {count, independent_source_count, max_value} — 보고서 섹션 재료.
- open_questions: 지지 근거 0(coverage 부족) or 저신뢰(value<임계) 어세션 신호 (09 §3).

confidence는 **증거 구조** 기반 (blueprint §11, ADR-202 추출 confidence와 별개 축).
**read-only** (불변식 §3-3) — 쓰기·영속·그래프 mutation 미노출.

Atomic TDD: Red → Green → Refactor.
"""
from __future__ import annotations

import pytest

from orc_citadel.conclusion import ConclusionProjector
from orc_citadel.curated_zone import CuratedZone


def _populate_zone() -> CuratedZone:
    z = CuratedZone(":memory:")
    z.initialize()
    return z


def _seed_claims(z: CuratedZone, claims: list[dict]) -> None:
    """claims: {cid, subj, pred, obj, doc} → claim + mention + assertion."""
    from orc_citadel.assertions import materialize
    from orc_citadel.extract import Mention
    from orc_citadel.extract_claims import ClaimCandidate

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
        from datetime import datetime, timezone

        a = materialize(cc, observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                        mutation=f"mut-{c['cid']}")
        z.persist_assertion(a)


# --- value / evidence_count ------------------------------------------------

def test_conclusion_value_uncontradicted():
    """반박 없음 → value = subject 어세션 평균 support."""
    z = _populate_zone()
    _seed_claims(z, [
        {"cid": "clm-a", "doc": "doc-1", "subj": "org-nvda", "pred": "announces", "obj": "org-cowos"},
        {"cid": "clm-b", "doc": "doc-2", "subj": "org-nvda", "pred": "announces", "obj": "org-cowos"},
    ])
    p = ConclusionProjector(z)
    c = p.for_subject("org-nvda")
    assert c is not None
    # 어세션 2건(같은 주장) — 각각 support 2/3. 평균 2/3.
    assert c.confidence["dimensions"]["support"] == pytest.approx(2 / 3)
    # 반박 없음 → contradiction 0 → value = support.
    assert c.confidence["value"] == pytest.approx(2 / 3)
    assert c.confidence["dimensions"]["contradiction"] == 0


def test_conclusion_evidence_count_sum():
    """evidence_count = subject 전체 지지 근거 합."""
    z = _populate_zone()
    _seed_claims(z, [
        {"cid": "clm-a", "doc": "doc-1", "subj": "org-nvda", "pred": "announces", "obj": "org-cowos"},
        {"cid": "clm-b", "doc": "doc-2", "subj": "org-nvda", "pred": "announces", "obj": "org-cowos"},
    ])
    p = ConclusionProjector(z)
    c = p.for_subject("org-nvda")
    assert c.confidence["evidence_count"] == 2  # 2개 어세션 × 1 근거 = 2.


def test_conclusion_independent_sources_dedup():
    """independent_source_count — dup_cluster로 묶인 근거는 1로 보정 (09 §3 note)."""
    z = _populate_zone()
    _seed_claims(z, [
        {"cid": "clm-a", "doc": "doc-1", "subj": "org-a", "pred": "announces", "obj": "org-b"},
        {"cid": "clm-b", "doc": "doc-2", "subj": "org-a", "pred": "announces", "obj": "org-b"},
    ])
    z.persist_cluster("clu-1", root_doc_id="doc-1", member_doc_ids=["doc-1", "doc-2"],
                      independent_addition_doc_ids=[], dedup_method="exact")
    p = ConclusionProjector(z)
    c = p.for_subject("org-a")
    assert c.confidence["independent_source_count"] == 1  # doc-2는 복제 → 독립 1.


# --- contradiction / value 감쇄 -------------------------------------------

def test_conclusion_contradiction_reduces_value():
    """반박 신호 있으면 contradiction>0, value가 평균 support 대비 감쇄."""
    z = _populate_zone()
    _seed_claims(z, [
        {"cid": "clm-a", "doc": "doc-1", "subj": "org-a", "pred": "announces", "obj": "org-b"},
        {"cid": "clm-b", "doc": "doc-2", "subj": "org-a", "pred": "announces", "obj": "org-b"},
        {"cid": "clm-c", "doc": "doc-3", "subj": "org-a", "pred": "denies", "obj": "org-b"},
    ])
    from orc_citadel.contradiction import ConflictCandidate

    z.persist_conflict(ConflictCandidate(
        claim_id_a="clm-a", claim_id_b="clm-c", conflict_type="value_conflict",
        rationale="denies announces", judged_by="pipeline"))
    p = ConclusionProjector(z)
    c = p.for_subject("org-a")
    con = c.confidence["dimensions"]["contradiction"]
    assert con > 0
    # value = 평균 support × (1 − con).
    assert c.confidence["value"] == pytest.approx((2 / 3) * (1 - con))


# --- by_predicate ----------------------------------------------------------

def test_by_predicate_distribution():
    """predicate별 {count, independent_source_count, max_value} — 보고서 섹션 재료."""
    z = _populate_zone()
    _seed_claims(z, [
        {"cid": "clm-a", "doc": "doc-1", "subj": "org-a", "pred": "announces", "obj": "org-b"},
        {"cid": "clm-b", "doc": "doc-2", "subj": "org-a", "pred": "announces", "obj": "org-b"},
        {"cid": "clm-c", "doc": "doc-3", "subj": "org-a", "pred": "powers", "obj": "org-dc"},
    ])
    p = ConclusionProjector(z)
    c = p.for_subject("org-a")
    assert set(c.by_predicate) == {"announces", "powers"}
    assert c.by_predicate["announces"]["count"] == 2
    assert c.by_predicate["announces"]["independent_source_count"] == 2
    assert c.by_predicate["powers"]["count"] == 1


# --- open_questions (09 §3) ------------------------------------------------

def test_open_questions_low_confidence_no_evidence():
    """지지 근거 0(coverage 부족) or 저신뢰 → open_questions 신호."""
    z = _populate_zone()
    _seed_claims(z, [
        # org-a: announces 근거 2건 → 신뢰.
        {"cid": "clm-a", "doc": "doc-1", "subj": "org-a", "pred": "announces", "obj": "org-b"},
        {"cid": "clm-b", "doc": "doc-2", "subj": "org-a", "pred": "announces", "obj": "org-b"},
    ])
    p = ConclusionProjector(z)
    c = p.for_subject("org-a")
    assert c.open_questions == []  # 증거 충분 → 미결 없음.


def test_open_questions_low_confidence_flagged():
    """독립 근거 1건(support 0.5) → open_questions 노출 (reason 포함)."""
    z = _populate_zone()
    # org-a의 'powers' 어세션은 근거 1건 → 저신뢰(0.5 >= 0.4 아님) → coverage는 1.0이므로
    # 신뢰 임계(0.4) 기준 저신뢰로 미결 플래그.
    _seed_claims(z, [
        {"cid": "clm-a", "doc": "doc-1", "subj": "org-a", "pred": "announces", "obj": "org-b"},
        {"cid": "clm-p", "doc": "doc-1", "subj": "org-a", "pred": "powers", "obj": "org-dc"},
    ])
    p = ConclusionProjector(z, low_confidence=0.6)  # 낮은 임계로 저신뢰 검출.
    c = p.for_subject("org-a")
    # powers 어세션 support 0.5 < 0.6 → 저신뢰 미결.
    oq = [o for o in c.open_questions if o["predicate"] == "powers"]
    assert len(oq) == 1
    assert "저신뢰" in oq[0]["reason"]


def test_open_questions_no_evidence_coverage():
    """지지 근거 없는 어세션(지원 없음) — coverage<1로 미결 (증거 부족)."""
    from orc_citadel.assertions import materialize
    from orc_citadel.extract_claims import ClaimCandidate
    from datetime import datetime, timezone

    z = _populate_zone()
    # claim/mention 없이 어세션만 직접 삽입 → 지지 근거 0.
    cc = ClaimCandidate(
        claim_candidate_id="clm-x", doc_id="doc-9", predicate="predicts",
        subject_id="org-a", object_id=None, object_literal="growth",
        modality="prediction", polarity="positive", confidence=0.5,
        seg_order=0, char_start=0, char_end=4, surface_fragment="x",
        event_type_hint=None, status="promoted",
    )
    z.persist_assertion(materialize(cc, observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                                    mutation="mut-x"))
    p = ConclusionProjector(z)
    c = p.for_subject("org-a")
    assert c.confidence["dimensions"]["coverage"] == 0.0
    oq = [o for o in c.open_questions if o["predicate"] == "predicts"]
    assert len(oq) == 1
    assert "증거 부족" in oq[0]["reason"]


# --- 봉투 필수 / read-only / no-subject ------------------------------------

def test_envelope_fields_complete():
    """결론 봉투 필수: value/evidence_count/independent_source_count/basis/dimensions."""
    z = _populate_zone()
    _seed_claims(z, [
        {"cid": "clm-a", "doc": "doc-1", "subj": "org-a", "pred": "announces", "obj": "org-b"},
    ])
    p = ConclusionProjector(z)
    env = p.for_subject("org-a").confidence
    for k in ("value", "evidence_count", "independent_source_count", "basis", "dimensions"):
        assert k in env, f"결론 봉투 필드 부재: {k}"
    assert 0.0 <= env["value"] <= 1.0
    assert {"support", "contradiction", "coverage"} <= set(env["dimensions"])
    assert isinstance(env["basis"], str) and len(env["basis"]) > 0


def test_read_only_no_mutation():
    """projector는 read-only — 쓰기·영속·그래프 mutation 미노출."""
    z = _populate_zone()
    _seed_claims(z, [
        {"cid": "clm-a", "doc": "doc-1", "subj": "org-a", "pred": "announces", "obj": "org-b"},
    ])
    p = ConclusionProjector(z)
    for bad in ("apply", "persist", "create_node", "create_edge", "insert"):
        assert not hasattr(p, bad), f"read-only 위반: {bad} 노출"


def test_no_subject_returns_none():
    """미존재 subject → None."""
    z = _populate_zone()
    _seed_claims(z, [
        {"cid": "clm-a", "doc": "doc-1", "subj": "org-a", "pred": "announces", "obj": "org-b"},
    ])
    p = ConclusionProjector(z)
    assert p.for_subject("org-zzz") is None
