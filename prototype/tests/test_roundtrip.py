"""DoD ① 원문 offset → segment → claim → 원문 왕복 추적.

설계 03 §8.1 provenance 경로: Claim/Evidence → extraction_record → normalized
doc(segments, 양방향 offset) → raw(content.bin) → source URL.
"""
from orc_citadel.identity import doc_id_for, new_ulid
from orc_citadel.normalize import segment_document
from orc_citadel.raw_store import RawStore
from orc_citadel.pipeline import process_document


def test_doc_id_is_content_deterministic():
    """동일 bytes는 동일 doc_id (내용 기반 결정적, 03 §2.1)."""
    b1 = b"The camp works. The citadel remembers."
    b2 = b"The camp works. The citadel remembers."
    other = b"The camp works. The citadel forgets."
    assert doc_id_for(b1) == doc_id_for(b2)
    assert doc_id_for(b1) != doc_id_for(other)


def test_roundtrip_span_to_segment_to_raw():
    """원문 span → segment → extraction → raw bytes까지 재현 (DoD ①)."""
    raw_text = "NVIDIA announced a new chip. The chip ships in Q3."
    store = RawStore()
    doc_id = store.put(b"src-01J9...", "https://nvidianews.nvidia.com/rss.xml", raw_text.encode())

    segments = segment_document(doc_id, raw_text)
    # 문장 2개
    assert len(segments) >= 2

    # 두 번째 문장 segment를 claim의 source로 선택
    seg = segments[1]
    claim = process_document(store, segments, source_span=(seg.segment_id, seg.char_start, seg.char_end))

    # 왕복: claim의 provenance를 따라 raw bytes까지 도달
    resolved = store.resolve_claim(claim.claim_id)
    # ①-1 claim에서 원문 offset 복원
    assert resolved.segment_id == seg.segment_id
    assert resolved.char_start == seg.char_start
    assert resolved.char_end == seg.char_end
    # ①-2 offset으로 원문 텍스트 slice가 segment.text와 일치
    assert resolved.text == raw_text[resolved.char_start:resolved.char_end]
    # ①-3 raw bytes 복원 (설계 03 §2.1 content.bin)
    assert resolved.raw_bytes == raw_text.encode()
    # ①-4 왕복 보장: 정규화 text에서 offset이 원문 원본 위치를 가리킴
    assert resolved.content_hash == doc_id  # sha256(raw)[:24] == doc_id


def test_claim_carries_provenance_ref():
    """claim은 ≥1 extraction_record(provenance_ref)를 가진다 (불변식 §3-2)."""
    store = RawStore()
    doc_id = store.put(b"src-01J9...", "https://example.com/x", b"Oracle opens a new DC.")
    segments = segment_document(doc_id, "Oracle opens a new DC.")
    claim = process_document(store, segments, source_span=(segments[0].segment_id, segments[0].char_start, segments[0].char_end))
    resolved = store.resolve_claim(claim.claim_id)
    assert resolved.provenance_ref  # 비어 있지 않음


def test_new_ulid_unique():
    assert new_ulid() != new_ulid()
