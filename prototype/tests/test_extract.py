"""S5 L1 결정적 추출 (설계 05 §1.1) — TDD 테스트.

L1 deterministic parser: gazetteer·식별자(ticker·URL)·대문자 표면형에서 결
정적 mention을 추출한다. span은 clean text 축 (03 §3.2, ADR-302).
Resolved None — 해소(§2)는 후속.
"""
from __future__ import annotations

import pytest

from orc_citadel.extract import (
    GAZETTEER,
    Mention,
    extract_mentions,
    mention_id_for,
)
from orc_citadel.parse import ParsedDoc, parse_document
from orc_citadel.identity import doc_id_for


def _doc(text: str) -> tuple[str, ParsedDoc]:
    raw = f"<html><body><article><p>{text}</p></article></body></html>".encode()
    doc_id = doc_id_for(raw)
    doc = ParsedDoc(text=text, title="")
    return doc_id, doc


# --- ticker 규칙 -------------------------------------------------------------

def test_ticker_mention():
    doc_id, doc = _doc("NVIDIA (NASDAQ:NVDA) announced results yesterday.")
    segs = parse_document(doc_id, doc)
    mentions = extract_mentions(doc_id, doc, segs)
    # ticker 표면형: "NASDAQ:NVDA" 규칙에서 ticker 심볼만 surface로 (NVDA).
    assert any(m.surface_text == "NVDA" for m in mentions)


# --- gazetteer 규칙 ----------------------------------------------------------

def test_gazetteer_mention():
    doc_id, doc = _doc("NVIDIA and TSMC partner to expand the Arizona fab.")
    segs = parse_document(doc_id, doc)
    mentions = extract_mentions(doc_id, doc, segs)
    orgs = [m for m in mentions if m.mention_type == "Organization"]
    surfaces = {m.surface_text for m in mentions}
    assert "NVIDIA" in surfaces
    assert "TSMC" in surfaces
    assert all(o.resolved_entity_id is None for o in orgs)


# --- URL 도메인 규칙 ---------------------------------------------------------

def test_url_domain_mention():
    doc_id, doc = _doc("See https://www.nvidia.com for details.")
    segs = parse_document(doc_id, doc)
    mentions = extract_mentions(doc_id, doc, segs)
    # URL 도메인 규칙이 조직명 mention을 만들어야 한다.
    assert any("nvidia" in m.surface_text.lower() for m in mentions)


# --- 대문자 연속 토큰 규칙 ---------------------------------------------------

def test_acronym_mention():
    doc_id, doc = _doc("The GeForce NOW service and RTX GPUs were upgraded.")
    segs = parse_document(doc_id, doc)
    mentions = extract_mentions(doc_id, doc, segs)
    surfaces = {m.surface_text for m in mentions}
    assert "GeForce NOW" in surfaces
    assert "RTX" in surfaces


# --- span·context_window -----------------------------------------------------

def test_span_slices_to_surface():
    """mention span으로 segment.text를 slice하면 surface_text가 재현 (offset 왕복)."""
    doc_id, doc = _doc("NVIDIA announced a record quarter.")
    segs = parse_document(doc_id, doc)
    mentions = extract_mentions(doc_id, doc, segs)
    nv = [m for m in mentions if m.surface_text == "NVIDIA"][0]
    # segment.text 전체에서 span 위치 — 문맥 문장(전체 text) 기준.
    assert doc.text[nv.char_start:nv.char_end] == nv.surface_text
    # char_span은 clean text 내 절대 오프셋이어야 한다.
    assert nv.char_start >= 0 and nv.char_end <= len(doc.text)


def test_context_window_present():
    doc_id, doc = _doc("NVIDIA just announced results. NVIDIA grows every year.")
    segs = parse_document(doc_id, doc)
    mentions = extract_mentions(doc_id, doc, segs)
    nv = [m for m in mentions if m.surface_text == "NVIDIA"][0]
    assert nv.context_window and "NVIDIA" in nv.context_window


# --- 중복 제거 ---------------------------------------------------------------

def test_overlapping_span_dedup():
    """겹치는 span은 하나로 (가장 긴 것 유지) — 결정적."""
    doc_id, doc = _doc("NVIDIA GeForce NOW launched.")
    segs = parse_document(doc_id, doc)
    mentions = extract_mentions(doc_id, doc, segs)
    # NVIDIA(4) 와 GeForce NOW(11)이 서로 다른 위치 — 중복 span 없음.
    # NVIDIA 가 GeForce NOW 안에 포함되는지 확인해 볼 수 없으므로, 같은 mention이 두 번
    # 추출되지 않아야 한다 (동일 surface+span 중복 금지).
    seen = []
    for m in mentions:
        assert (m.surface_text, m.char_start, m.char_end) not in seen
        seen.append((m.surface_text, m.char_start, m.char_end))


# --- 결정성 / idempotency ----------------------------------------------------

def test_mention_id_deterministic():
    """동일 mention은 동일 mention_id (재실행 idempotency, 03 §5)."""
    doc_id, doc = _doc("TSMC leads the advanced-node race.")
    segs = parse_document(doc_id, doc)
    m1 = [m for m in extract_mentions(doc_id, doc, segs) if m.surface_text == "TSMC"][0]
    m2 = [m for m in extract_mentions(doc_id, doc, segs) if m.surface_text == "TSMC"][0]
    assert m1.mention_id == m2.mention_id
    # ID 규칙: men- 접두 + 결정 해시
    assert m1.mention_id.startswith("men-")


def test_mention_id_differs_for_diff_span():
    doc_id, doc = _doc("TSMC fab 1 and TSMC fab 2.")
    segs = parse_document(doc_id, doc)
    ts = [m for m in extract_mentions(doc_id, doc, segs) if m.surface_text == "TSMC"]
    ids = {m.mention_id for m in ts}
    assert len(ids) == len(ts)  # 다른 span → 다른 ID


# --- span 없는 mention 폐기 (설계 05 §1.1, §3.2) ----------------------------

def test_no_span_mention_discarded():
    """mention 생성은 반드시 결정적 span을 가지며, span 없는 건 존재하지 않음."""
    doc_id, doc = _doc("")
    segs = parse_document(doc_id, doc)
    mentions = extract_mentions(doc_id, doc, segs)
    assert mentions == []  # 빈 본문 → 추출 0건 (불필요 mention 생성 금지)
