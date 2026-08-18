"""S7 Claim 추출 — 결정적 규칙 기반 (설계 05 §3, 02 §2.4·§5.1) TDD.

source span(clean text 축)에 근거한 구조화 claim 후보(`claim_candidates`, status=candidate)
를 결정적 predicate 규칙으로 추출한다 (05 §5 deterministic-first). LLM(§3)·canonicalization
(§4)·contradiction(§5)은 후속 — 여기선 규칙만.
"""
from __future__ import annotations

import pytest

from orc_citadel.extract import extract_mentions
from orc_citadel.parse import ParsedDoc, parse_document
from orc_citadel.identity import doc_id_for
from orc_citadel.resolve import EntityResolver
from orc_citadel.extract_claims import extract_claims


def _doc(text: str):
    doc_id = doc_id_for(text.encode())
    doc = ParsedDoc(text=text, title="")
    segs = parse_document(doc_id, doc)
    # 해소된 mention index (subject 바인딩용).
    ms = extract_mentions(doc_id, doc, segs)
    entities, resolved = EntityResolver().resolve(doc_id, ms)
    by_id = {e.entity_id: e for e in entities}
    return doc_id, doc, segs, resolved, by_id


def test_conference_call_announces():
    """NVIDIA conference call → announces(earnings) claim."""
    doc_id, doc, segs, resolved, by_id = _doc(
        "NVIDIA will host a conference call to discuss its financial results."
    )
    claims = extract_claims(doc_id, segs, resolved, by_id)
    ann = [c for c in claims if c.predicate == "announces"]
    assert ann
    c = ann[0]
    # subject = 해소된 NVIDIA entity (by_id가 정확히 1개)
    assert c.subject_id and c.subject_id in by_id
    assert c.event_type_hint == "earnings"
    # provenance span — segment.text slice 재현
    seg = segs[c.seg_order]
    assert seg.text[c.char_start:c.char_end] == c.surface_fragment


def test_claim_uses_resolved_subject():
    """subject_id는 NVIDIA 해소 entity (Reference 무결성, 02 §4-3)."""
    doc_id, doc, segs, resolved, by_id = _doc(
        "NVIDIA will host a conference call for Q2 results."
    )
    claims = extract_claims(doc_id, segs, resolved, by_id)
    ann = [c for c in claims if c.predicate == "announces"][0]
    nv = by_id[list(by_id)[0]]  # 유일 NVIDIA entity
    assert ann.subject_id == nv.entity_id
    assert ann.subject_id.startswith("org-")


def test_source_span_offsets():
    """source_span은 clean text 축 char offset + seg_order (ADR-302, provenance)."""
    doc_id, doc, segs, resolved, by_id = _doc(
        "NVIDIA will host a conference call to discuss results."
    )
    claims = extract_claims(doc_id, segs, resolved, by_id)
    c = extract_claims(doc_id, segs, resolved, by_id)[0]
    seg = segs[c.seg_order]
    assert seg.text[c.char_start:c.char_end] == c.surface_fragment
    assert 0 <= c.char_start < c.char_end <= len(seg.text)


def test_claim_fields_schema():
    """designed schema: predicate/modality/polarity/confidence status 등 (02 §2.4·03 §4.2)."""
    doc_id, doc, segs, resolved, by_id = _doc(
        "NVIDIA will host a conference call."
    )
    claims = extract_claims(doc_id, segs, resolved, by_id)
    c = claims[0]
    assert c.modality in {"fact", "asserted", "opinion", "prediction"}
    assert c.polarity in {"positive", "negative"}
    assert 0.0 <= c.confidence <= 1.0
    assert c.status == "candidate"


def test_no_predicate_text_no_claim():
    """규칙이 안 맞는 본문은 claim 0건 (precision 우선, 05 §5)."""
    doc_id, doc, segs, resolved, by_id = _doc(
        "The quick brown fox jumps over the lazy dog."
    )
    claims = extract_claims(doc_id, segs, resolved, by_id)
    assert claims == []


def test_subject_required_no_dropped():
    """해소 mention 없는 segment는 claim을 내지 않음 (Reference 무결성, 02 §4-3)."""
    doc_id, doc, segs, resolved, by_id = _doc(
        "The conference call will be webcast live on the investor site."
    )
    claims = extract_claims(doc_id, segs, resolved, by_id)
    # "conference call"/"webcast" 매칭되지만 segment에 NVIDIA mention 없음 → 폐기.
    assert claims == []


def test_no_redundant_per_segment():
    """동일 segment에서 predicate당 첫 매칭만 (중복 방지, precision)."""
    doc_id, doc, segs, resolved, by_id = _doc(
        "NVIDIA will host a conference call; the call will also be webcast."
    )
    claims = extract_claims(doc_id, segs, resolved, by_id)
    ann = [c for c in claims if c.predicate == "announces"]
    # 같은 segment에서 announces는 1개만 (conference call/webcast 모두 매칭돼도).
    assert len(ann) <= 1


def test_deterministic():
    """동일 입력 → 동일 claim (idempotency, 03 §5)."""
    doc_id, doc, segs, resolved, by_id = _doc(
        "NVIDIA will host a conference call to discuss results."
    )
    a = extract_claims(doc_id, segs, resolved, by_id)
    b = extract_claims(doc_id, segs, resolved, by_id)
    assert [c.claim_candidate_id for c in a] == [c.claim_candidate_id for c in b]


# --- 공급망 도메인 신호 규칙 (arXiv abstract 신호 밀도 ↑, 04 §5.1 확장) -------

def test_supply_to_claim():
    """'{E} supplies/manufactures/produces ...' → supplies(predicate) claim.

    arXiv abstract 의 반도체 공급망 신호(타이완이 TSMC 생산 등)를 결정적으로 잡는다.
    subject 는 해소 entity (Reference 무결성).
    """
    doc_id, doc, segs, resolved, by_id = _doc(
        "Taiwan Semiconductor Manufacturing Company produces chips for NVIDIA and Apple."
    )
    claims = extract_claims(doc_id, segs, resolved, by_id)
    sup = [c for c in claims if c.predicate == "supplies"]
    assert sup, f"no supplies claim from: {[c.predicate for c in claims]}"
    c = sup[0]
    assert c.subject_id in by_id  # TSMC 해소 entity
    assert c.event_type_hint == "manufacturing"
    seg = segs[c.seg_order]
    assert seg.text[c.char_start:c.char_end] == c.surface_fragment


def test_partnership_claim():
    """'{E} partnership/agreement with {E2}' → partners_with(predicate) claim.

    predicate 는 02 §5.1 controlled vocabulary 의 공식 `partners_with` 여야 한다 —
    extractor 가 과거 축약 `partners` 를 방출하면 §4-2 폐쇄성 게이트(2026-08-12 SLO-07
    quarantine 원인 71건) 를 떨어뜨려 permanent quarantine 된다 (추출·온톨로지 정합화).
    """
    doc_id, doc, segs, resolved, by_id = _doc(
        "TSMC announced a partnership with NVIDIA to develop advanced chips."
    )
    claims = extract_claims(doc_id, segs, resolved, by_id)
    part = [c for c in claims if c.predicate == "partners_with"]
    # partnership 규칙(partners_with) 이 잡아야 함.
    assert part, f"no partners_with claim from: {[c.predicate for c in claims]}"
    c = part[0]
    assert c.event_type_hint == "partnership"
    seg = segs[c.seg_order]
    assert seg.text[c.char_start:c.char_end] == c.surface_fragment
    # 미등록 축약 `partners` 는 폐쇄성 게이트에 실패해야 정합 (방출 금지).
    assert all(c.predicate != "partners" for c in claims)


# --- object 바인딩: 정규 삼항 완성 (공급망 엣지) ------------------------------

def test_object_bound_to_second_entity_after_predicate():
    """'TSMC supplies NVIDIA' → subject=TSMC, object=NVIDIA (엣지용 정규 삼항).

    supply-chain predicate 뒤에 오는 두 번째 해소 엔티티를 object 로 묶는다.
    """
    doc_id, doc, segs, resolved, by_id = _doc(
        "TSMC supplies NVIDIA with advanced silicon."
    )
    claims = extract_claims(doc_id, segs, resolved, by_id)
    sup = [c for c in claims if c.predicate == "supplies"]
    assert sup
    c = sup[0]
    # object 는 subject(TSMC)와 다른 해소 엔티티(NVIDIA).
    assert c.object_id is not None
    assert c.object_id != c.subject_id
    assert c.object_id in by_id


def test_object_literal_when_no_second_entity():
    """'NVIDIA powers the data center' → 두 번째 해소 엔티티 없으면 object 미상(엣지 없음)."""
    doc_id, doc, segs, resolved, by_id = _doc(
        "NVIDIA powers the data center."
    )
    claims = extract_claims(doc_id, segs, resolved, by_id)
    ann = [c for c in claims if c.predicate == "announces"]
    assert ann
    # 'data center' 는 해소 엔티티가 아니라면 object 는 None (object_literal 로 남김).
    c = ann[0]
    assert all(c.object_id is None for c in ann)
