"""S12 mention/edge 게이트 확장 (설계 05 §6 전체) — TDD.

claim 게이트를 mention·POSSIBLY_SAME_AS edge 후보까지 확장해 authoritative graph를
완성한다. mention: provenance(span)·해소 entity 참조·type. edge: resolution_ref +
score ∈ [0,1] → promote(create_edge). SAME_AS 자동 병합은 결정적 식별자만
(ADR-507 유지 — edge는 후보/승격만).
"""
from __future__ import annotations

import pytest

from orc_citadel.edges import PossiblySameAsEdge
from orc_citadel.extract import Mention
from orc_citadel.gate import Gate


def _edge(score: float = 0.9, blocking_key: str = "norm_name",
          entity_a: str = "org-a", entity_b: str = "org-b",
          resolution_ref: str = "res-1") -> PossiblySameAsEdge:
    return PossiblySameAsEdge(
        edge_id="psa-edge-1",
        entity_a_id=entity_a,
        entity_b_id=entity_b,
        score=score,
        blocking_key=blocking_key,
        resolution_ref=resolution_ref,
        judged_by="pipeline",
    )


def test_promotes_valid_edge():
    """POSSIBLY_SAME_AS edge: score∈[0,1]·resolution_ref → promote(create_edge)."""
    gate = Gate()
    e = _edge(score=0.9)
    result = gate.evaluate_edge(e)
    assert result.promote
    assert result.status == "promoted"
    ev = [m for m in gate.mutations() if m["op"] == "create_edge"]
    assert len(ev) == 1
    assert ev[0]["element_ref"] == e.edge_id


def test_rejects_score_out_of_range():
    """score ∉ [0,1] → quarantine (02 §3.1 weight 범위, 불변식4-7)."""
    gate = Gate()
    e = _edge(score=1.5)
    result = gate.evaluate_edge(e)
    assert not result.promote
    assert result.status == "quarantined"
    assert any("score" in r for r in result.reasons)


def test_rejects_missing_resolution_ref():
    """resolution_ref 없음 → quarantine (02 §3.1 판정 근거 필수)."""
    gate = Gate()
    e = _edge(resolution_ref="")
    result = gate.evaluate_edge(e)
    assert not result.promote


def test_rejects_same_entity_self_loop():
    """자기 루프(같은 entity 쌍) → quarantine (02 §4-5 무순환, 결정적)."""
    gate = Gate()
    e = _edge(entity_a="org-x", entity_b="org-x")
    result = gate.evaluate_edge(e)
    assert not result.promote


def test_promotes_valid_mention():
    """해소된 mention(span 유효·entity 참조·type 유효) → promote(create_node)."""
    gate = Gate()
    m = Mention(
        mention_id="men-1", doc_id="doc-1", segment_id="doc-1#p0.s0",
        surface_text="NVIDIA", mention_type="Organization",
        char_start=0, char_end=6, context_window="...", identifiers={"ticker": "NVDA"},
        resolved_entity_id="org-1",
    )
    result = gate.evaluate_mention(m)
    assert result.promote
    assert result.status == "promoted"
    ev = [x for x in gate.mutations() if x["op"] == "create_node"]
    assert ev and ev[0]["element_ref"] == "men-1"


def test_mention_without_span_quarantine():
    """span 없는 mention(잘못된 span) → quarantine (05 §1.1 폐기 원칙)."""
    gate = Gate()
    m = Mention(
        mention_id="men-2", doc_id="doc-1", segment_id="", surface_text="X",
        mention_type="Organization", char_start=5, char_end=5,
        context_window="", identifiers={}, resolved_entity_id="org-1",
    )
    result = gate.evaluate_mention(m)
    assert not result.promote
    assert any("span" in r for r in result.reasons)


def test_mention_promotes_with_explicit_resolved():
    """해소 결과(ResolvedMention)의 entity id를 명시 전달 → promote (실제 파이프라인 경로)."""
    gate = Gate()
    # raw mention은 resolved_entity_id=None (prototype 해소는 별도 레코드).
    m = Mention(
        mention_id="men-r", doc_id="doc-1", segment_id="s",
        surface_text="NVIDIA", mention_type="Organization",
        char_start=0, char_end=6, context_window="", identifiers={"ticker": "NVDA"},
        resolved_entity_id=None,
    )
    result = gate.evaluate_mention(m, resolved_entity_id="org-1")
    assert result.promote
    assert result.status == "promoted"


def test_mention_unresolved_quarantine():
    """미해소 mention(resolved_entity_id 없음) → Reference 무결성 quarantine."""
    gate = Gate()
    m = Mention(
        mention_id="men-3", doc_id="doc-1", segment_id="s", surface_text="TSMC",
        mention_type="Organization", char_start=0, char_end=4,
        context_window="", identifiers={}, resolved_entity_id=None,
    )
    result = gate.evaluate_mention(m)
    assert not result.promote


def test_deterministic_and_no_auto_merge():
    """edge 게이트는 승격만 — 자동 SAME_AS 병합은 하지 않음 (ADR-507 유지)."""
    gate = Gate()
    e = _edge()
    # 승격은 되지만 병합(노드 collapse) 이벤트는 없다 (create_edge만).
    result = gate.evaluate_edge(e)
    assert result.promote
    ops = {m["op"] for m in gate.mutations()}
    assert "merge_entity" not in ops
