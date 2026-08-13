"""S29 어세션별 근거·다차원 신뢰도 집계 (설계 09 §4) TDD.

09 §4 Confidence 표현 계약 — `value` 단일 게이지 금지, 봉투 필수
(value/evidence_count/independent_source_count/basis/dimensions).
`value`는 source reputation이 아니라 **claim별 증거 구조**로 계산한다 (blueprint §11).

- support   : 서로 다른 문서(doc)에서 동일 (subject,predicate) 주장을 입증하는 지지 근거 수로
              정규화 — `1 - 1/(n_support+1)` (문서 1건만으론 확정 불가, 미관측 한계).
- contradiction: 반박 증거(conflict) 수로 위험 노출 — `1 - 1/(n_conflict+1)`.
- value     : `support * (1 - contradiction)`.
- independent_source_count: dup_cluster 뿌리(root) 보정 후 독립 출처 수 (09 §3 note).
- read-only : 쓰기·영속·그래프 mutation 미노출 (불변식 §3-3).

Atomic TDD: Red(모듈 미존재) → Green(최소 구현) → Refactor.
"""
from __future__ import annotations

import pytest

from orc_citadel.assertion_evidence import AssertionEvidenceProjector
from orc_citadel.curated_zone import CuratedZone


def _populate_zone() -> CuratedZone:
    """assertions + claims + mentions + dup_clusters + conflicts 배치."""
    z = CuratedZone(":memory:")
    z.initialize()
    return z


def _seed_claims(z: CuratedZone, claims: list[dict]) -> None:
    """claims: list of {cid, subj, pred, obj, doc, status} → claim_candidates + mentions."""
    from orc_citadel.extract_claims import ClaimCandidate

    for i, c in enumerate(claims):
        cc = ClaimCandidate(
            claim_candidate_id=c["cid"], doc_id=c["doc"], predicate=c["pred"],
            subject_id=c["subj"], object_id=c.get("obj"), object_literal=None,
            modality="asserted", polarity="positive", confidence=c.get("conf", 0.8),
            seg_order=i, char_start=0, char_end=4, surface_fragment="x",
            event_type_hint=None, status=c.get("status", "promoted"),
        )
        z.persist_claim(cc)
        from orc_citadel.extract import Mention

        m = Mention(
            mention_id=f"men-{c['cid']}", doc_id=c["doc"], segment_id=f"{c['doc']}#s0",
            surface_text=c["subj"], mention_type=c.get("mtype", "ORG"),
            char_start=0, char_end=4, context_window=None,
        )
        z.persist_mention(m)
        z.set_mention_authoritative(m.mention_id)

    # assertions — asr- id는 claim_id 기반 결정적 (assertion_id_for).
    from orc_citadel.assertions import materialize
    from datetime import datetime, timezone

    for c in claims:
        cc = ClaimCandidate(
            claim_candidate_id=c["cid"], doc_id=c["doc"], predicate=c["pred"],
            subject_id=c["subj"], object_id=c.get("obj"), object_literal=None,
            modality="asserted", polarity="positive", confidence=c.get("conf", 0.8),
            seg_order=0, char_start=0, char_end=4, surface_fragment="x",
            event_type_hint=None, status="promoted",
        )
        a = materialize(cc, observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                        mutation=f"mut-{c['cid']}")
        z.persist_assertion(a)


# --- support / evidence_count ---------------------------------------------

def test_support_from_distinct_docs():
    """서로 다른 문서 2건이 동일 (subj, pred) 주장 → evidence_count=2, support≈0.667."""
    z = _populate_zone()
    _seed_claims(z, [
        {"cid": "clm-a", "doc": "doc-1", "subj": "org-nvda", "pred": "announces", "obj": "org-cowos"},
        {"cid": "clm-b", "doc": "doc-2", "subj": "org-nvda", "pred": "announces", "obj": "org-cowos"},
    ])
    p = AssertionEvidenceProjector(z)
    # subject+predicate+object 기준으로 동일 주장.
    evs = p.all()
    assert len(evs) == 2  # {clm-a, clm-b} 각각 1 assert, 같은 주장으로 집계.
    assert evs[0].evidence_count == 2
    assert abs(evs[0].confidence["dimensions"]["support"] - (1 - 1 / 3)) < 1e-9


def test_support_single_doc_not_certain():
    """문서 1건만 → support=0.5 (미관측 한계, 확정 불가)."""
    z = _populate_zone()
    _seed_claims(z, [
        {"cid": "clm-a", "doc": "doc-1", "subj": "org-a", "pred": "announces", "obj": "org-b"},
    ])
    p = AssertionEvidenceProjector(z)
    ev = p.all()[0]
    assert ev.evidence_count == 1
    assert ev.confidence["evidence_count"] == 1
    assert abs(ev.confidence["dimensions"]["support"] - 0.5) < 1e-9


# --- independent_source_count / dup_cluster 보정 --------------------------

def test_independent_source_count_dedup():
    """dup_cluster로 묶인 2문서(같은 root) → independent_source_count=1 (중복 보정)."""
    z = _populate_zone()
    _seed_claims(z, [
        {"cid": "clm-a", "doc": "doc-1", "subj": "org-a", "pred": "announces", "obj": "org-b"},
        {"cid": "clm-b", "doc": "doc-2", "subj": "org-a", "pred": "announces", "obj": "org-b"},
    ])
    z.persist_cluster("clu-1", root_doc_id="doc-1",
                      member_doc_ids=["doc-1", "doc-2"],
                      independent_addition_doc_ids=[], dedup_method="exact")
    p = AssertionEvidenceProjector(z)
    ev = p.all()[0]
    assert ev.evidence_count == 2
    assert ev.independent_source_count == 1  # doc-2는 doc-1의 복제.
    assert ev.confidence["independent_source_count"] == 1


def test_independent_source_count_distinct_root():
    """서로 다른 클러스터(또는 무클러스터) → 독립 출처 2건."""
    z = _populate_zone()
    _seed_claims(z, [
        {"cid": "clm-a", "doc": "doc-1", "subj": "org-a", "pred": "announces", "obj": "org-b"},
        {"cid": "clm-b", "doc": "doc-2", "subj": "org-a", "pred": "announces", "obj": "org-b"},
    ])
    # 2문서 각각 별개 root의 서로 다른 클러스터 → 독립 2.
    z.persist_cluster("clu-1", root_doc_id="doc-1", member_doc_ids=["doc-1"],
                      independent_addition_doc_ids=[], dedup_method="exact")
    z.persist_cluster("clu-2", root_doc_id="doc-2", member_doc_ids=["doc-2"],
                      independent_addition_doc_ids=[], dedup_method="exact")
    p = AssertionEvidenceProjector(z)
    ev = p.all()[0]
    assert ev.independent_source_count == 2


# --- contradiction ---------------------------------------------------------

def test_contradiction_reduces_value():
    """conflict_candidates 존재 → contradiction>0, value가 support 대비 감쇄."""
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
    p = AssertionEvidenceProjector(z)
    ev_a = next(e for e in p.all() if e.claim_id == "clm-a")
    sup = ev_a.confidence["dimensions"]["support"]
    con = ev_a.confidence["dimensions"]["contradiction"]
    assert con > 0
    assert ev_a.confidence["value"] == pytest.approx(sup * (1 - con))


def test_contradiction_absent_zero():
    """conflict 없음 → contradiction=0, value=support."""
    z = _populate_zone()
    _seed_claims(z, [
        {"cid": "clm-a", "doc": "doc-1", "subj": "org-a", "pred": "announces", "obj": "org-b"},
    ])
    p = AssertionEvidenceProjector(z)
    ev = p.all()[0]
    assert ev.confidence["dimensions"]["contradiction"] == 0
    assert ev.confidence["value"] == pytest.approx(ev.confidence["dimensions"]["support"])


# --- basis -----------------------------------------------------------------

def test_basis_human_readable():
    """basis — 독립성 보정·반박 존재·성분을 사람 읽는 문장으로."""
    z = _populate_zone()
    _seed_claims(z, [
        {"cid": "clm-a", "doc": "doc-1", "subj": "org-a", "pred": "announces", "obj": "org-b"},
        {"cid": "clm-b", "doc": "doc-2", "subj": "org-a", "pred": "announces", "obj": "org-b"},
    ])
    p = AssertionEvidenceProjector(z)
    ev = p.all()[0]
    b = ev.confidence["basis"]
    assert "지지 근거" in b
    assert "독립 출처" in b
    assert "반박 근거" in b


# --- 봉투 필수 (09 §4: value 단일 게이지 금지) ------------------------------

def test_envelope_fields_complete():
    """봉투 필수: value/evidence_count/independent_source_count/basis/dimensions."""
    z = _populate_zone()
    _seed_claims(z, [
        {"cid": "clm-a", "doc": "doc-1", "subj": "org-a", "pred": "announces", "obj": "org-b"},
    ])
    p = AssertionEvidenceProjector(z)
    env = p.all()[0].confidence
    for k in ("value", "evidence_count", "independent_source_count", "basis", "dimensions"):
        assert k in env, f"봉투 필드 부재: {k}"
    assert 0.0 <= env["value"] <= 1.0
    assert {"support", "contradiction", "coverage"} <= set(env["dimensions"])


# --- read-only (불변식 §3-3) ------------------------------------------------

def test_read_only_no_mutation():
    """projector는 read-only — 쓰기·영속·그래프 mutation 미노출."""
    z = _populate_zone()
    _seed_claims(z, [
        {"cid": "clm-a", "doc": "doc-1", "subj": "org-a", "pred": "announces", "obj": "org-b"},
    ])
    p = AssertionEvidenceProjector(z)
    for bad in ("apply", "persist", "create_node", "create_edge", "insert"):
        assert not hasattr(p, bad), f"read-only 위반: {bad} 노출"


def test_value_zero_when_no_support():
    """지지 근거 0 → support=0, value=0."""
    z = _populate_zone()
    p = AssertionEvidenceProjector(z)
    assert p.all() == []


# --- independent_source_count: independent_addition 보정 (11 §1.4) --------

def test_independent_addition_counts_extra_source():
    """같은 root 클러스터 내 파생 문서가 독립 추가 정보를 담고 해당 claim을
    지지 → §1.4 둘째 항: 독립 추가 1건 가산 (root 1 + independent 1 = 2)."""
    z = _populate_zone()
    _seed_claims(z, [
        {"cid": "clm-a", "doc": "doc-1", "subj": "org-a", "pred": "announces", "obj": "org-b"},
        {"cid": "clm-b", "doc": "doc-2", "subj": "org-a", "pred": "announces", "obj": "org-b"},
    ])
    # doc-2 는 doc-1 의 파생(member)이지만 독립 추가 정보를 담고, 같은 claim 지지.
    z.persist_cluster("clu-1", root_doc_id="doc-1",
                      member_doc_ids=["doc-1", "doc-2"],
                      independent_addition_doc_ids=["doc-2"], dedup_method="minhash")
    p = AssertionEvidenceProjector(z)
    ev = p.all()[0]
    assert ev.evidence_count == 2
    # §1.4: distinct root(1) + 독립 추가 중 "adds new evidence"(1) = 2.
    assert ev.independent_source_count == 2
    assert ev.confidence["independent_source_count"] == 2


def test_independent_addition_not_claiming_does_not_add():
    """독립 추가 파생 문서가 해당 claim 을 지지하지 않으면 가산되지 않는다."""
    z = _populate_zone()
    # doc-3 이 독립 추가이지만 이 claim(clm-a)을 지지하지 않음.
    _seed_claims(z, [
        {"cid": "clm-a", "doc": "doc-1", "subj": "org-a", "pred": "announces", "obj": "org-b"},
        {"cid": "clm-b", "doc": "doc-2", "subj": "org-a", "pred": "announces", "obj": "org-b"},
    ])
    # doc-3 은 root doc-1 의 파생·독립 추가이로 등록되나, 이 claim 을 주장하지 않음.
    z.persist_cluster("clu-1", root_doc_id="doc-1",
                      member_doc_ids=["doc-1", "doc-2", "doc-3"],
                      independent_addition_doc_ids=["doc-3"], dedup_method="minhash")
    p = AssertionEvidenceProjector(z)
    ev = p.all()[0]
    # root(doc-1) + 지지하는 독립 추가(doc-2 는 평범한 파생) = 1.
    assert ev.independent_source_count == 1


def test_independent_addition_and_distinct_member():
    """독립 추가가 아닌 파생만 지지 → root 1 (가산 없음, 기존 계약 유지)."""
    z = _populate_zone()
    _seed_claims(z, [
        {"cid": "clm-a", "doc": "doc-1", "subj": "org-a", "pred": "announces", "obj": "org-b"},
        {"cid": "clm-b", "doc": "doc-2", "subj": "org-a", "pred": "announces", "obj": "org-b"},
    ])
    z.persist_cluster("clu-1", root_doc_id="doc-1",
                      member_doc_ids=["doc-1", "doc-2"],
                      independent_addition_doc_ids=[], dedup_method="exact")
    p = AssertionEvidenceProjector(z)
    assert p.all()[0].independent_source_count == 1
