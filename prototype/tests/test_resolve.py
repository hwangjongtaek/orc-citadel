"""S6 Entity Resolution — 결정적 stage-1만 (설계 05 §2.2 rule 1, ADR-507).

공유 외부식별자(ticker) exact match만 자동 병합(SAME_AS). lexical/embedding/LLM·점수
고신뢰는 비결정적 자동 병합 금지 (ADR-507) → 이 scope에서 구현·검증하지 않는다.
canonical 대표 1개 (02 §4-5·§3.1 SAME_AS 동치류). 결정적·idempotent (03 §5).
"""
from __future__ import annotations

import pytest

from orc_citadel.extract import extract_mentions
from orc_citadel.parse import ParsedDoc, parse_document
from orc_citadel.identity import doc_id_for
from orc_citadel.resolve import EntityResolver


def _mentions(text: str):
    doc_id = doc_id_for(text.encode())
    doc = ParsedDoc(text=text, title="")
    return doc_id, extract_mentions(doc_id, doc, parse_document(doc_id, doc))


def test_shared_identifier_same_entity():
    """NVIDIA(gazetteer, ticker NVDA) + NVDA(ticker mention) → 한 entity (SAME_AS)."""
    doc_id, ms = _mentions("NVIDIA (NASDAQ: NVDA) leads the market.")
    res = EntityResolver()
    entities, resolved = res.resolve(doc_id, ms)
    # 둘 다 해소돼야 하고 같은 entity여야 한다 (shared ticker).
    ents = {m.resolved_entity_id for m in resolved if m.resolved}
    assert len(ents) == 1
    assert {e.entity_id for e in entities} == ents
    # canonical_name은 NVDA/NVIDIA 동치류의 대표 — 같은 클래스인 것만 확인.
    nv = [m for m in resolved if "NVIDIA" in m.surface_text or m.surface_text == "NVDA"]
    assert len({m.resolved_entity_id for m in nv}) == 1


def test_distinct_identifier_distinct_entity():
    """서로 다른 ticker는 다른 entity (오병합 방지)."""
    doc_id, ms = _mentions("NVIDIA (NASDAQ: NVDA) and TSMC (NYSE: TSM) compete.")
    res = EntityResolver()
    entities, resolved = res.resolve(doc_id, ms)
    ids = {m.resolved.entity_id for m in resolved if m.resolved}
    assert len(ids) == 2  # NVDA·TSM 서로 다름
    assert len(entities) == 2


def test_no_identifier_no_merge():
    """식별자 없는 mention은 병합하지 않고 개별 엔터티 (결정적 보존)."""
    doc_id, ms = _mentions("SEMI leads the industry.")
    res = EntityResolver()
    entities, resolved = res.resolve(doc_id, ms)
    # SEMI는 표면형 그대로 개별 entity, resolved 부여.
    sem = [m for m in resolved if m.surface_text == "SEMI"]
    assert len(sem) == 1
    assert sem[0].resolved is not None


def test_entity_id_deterministic():
    """동일 mention → 동일 entity_id (재실행 idempotency, 03 §5)."""
    doc_id, ms = _mentions("NVIDIA leads AI. NVIDIA grows fast.")
    a = EntityResolver().resolve(doc_id, ms)
    b = EntityResolver().resolve(doc_id, ms)
    assert [e.entity_id for e in a[0]] == [e.entity_id for e in b[0]]


def test_entity_id_reuses_identifier_key():
    """entity_id는 (type, canonical, identifiers) 기반 결정적 — org- 접두."""
    doc_id, ms = _mentions("NVIDIA (NASDAQ: NVDA).")
    entity, _ = EntityResolver().resolve(doc_id, ms)
    e0 = entity[0]
    assert e0.entity_id.startswith("org-")
    assert e0.identifiers.get("ticker") == "NVDA"


def test_canonical_name_most_common():
    """canonical_name은 동치류 최빈 표면형 (결정적 사전순 동률)."""
    # NVIDIA가 더 많이 등장하는 본문 → canonical NVIDIA가 돼야 한다.
    doc_id, ms = _mentions(
        "NVIDIA is strong. NVIDIA wins. TSMC trails. NVDA is the ticker."
    )
    entity, resolved = EntityResolver().resolve(doc_id, ms)
    by_id = {e.entity_id: e for e in entity}
    nv_ids = {m.resolved.entity_id for m in resolved
              if m.resolved and (m.surface_text == "NVIDIA" or m.surface_text == "NVDA")}
    nv_ent = by_id[list(nv_ids)[0]]
    assert nv_ent.canonical_name == "NVIDIA"  # NVIDIA 2회 > NVDA 1회


def test_mention_resolved_filled():
    """mention.resolved가 entity를 가리키면 curated에 resolved_entity_id 기록 가능."""
    doc_id, ms = _mentions("TSMC is the foundry leader.")
    entity, resolved = EntityResolver().resolve(doc_id, ms)
    tsm = [m for m in resolved if m.surface_text == "TSMC"][0]
    assert tsm.resolved.entity_id == entity[0].entity_id
    assert tsm.resolved.canonical_name == "TSMC"
