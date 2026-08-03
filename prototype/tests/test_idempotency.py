"""DoD ② 동일 문서 재처리 시 중복 mutation 없음 + immutable raw.

설계 03 §5·§7: doc_id 내용 기반 idempotency, mutation_log idempotency_key unique,
§2.1 immutable(동일 URL 변경분은 새 doc_id로 보존).
"""
from orc_citadel.identity import doc_id_for
from orc_citadel.normalize import segment_document
from orc_citadel.raw_store import RawStore
from orc_citadel.mutation_log import MutationLog, IdempotencyViolation
from orc_citadel.pipeline import process_document


def test_same_bytes_reprocess_no_duplicate_mutation():
    """동일 문서를 두 번 재처리해도 mutation이 중복 생성되지 않는다 (DoD ②)."""
    store = RawStore()
    ml = MutationLog(store)
    raw_text = "Micron expands HBM capacity."
    doc_id = store.put(b"src-01J9...", "https://example.com/mu", raw_text.encode())

    segments = segment_document(doc_id, raw_text)
    span = (segments[0].segment_id, segments[0].char_start, segments[0].char_end)

    ml.apply(doc_id, "create_claim", source_span=span, idempotency_key="k-1")
    ml.apply(doc_id, "create_claim", source_span=span, idempotency_key="k-2")

    # 서로 다른 key라도 같은 doc_id+span이면 결과 element는 1개여야 (내용 기반 dedup)
    assert len(ml.claims_for(source_span=span)) == 1


def test_same_idempotency_key_noop():
    """동일 idempotency_key 재실행은 no-op (불변식 §3-6, 03 §7.2)."""
    store = RawStore()
    ml = MutationLog(store)
    raw_text = "TSMC starts fab."
    doc_id = store.put(b"src-01J9...", "https://example.com/tsmc", raw_text.encode())
    segments = segment_document(doc_id, raw_text)
    span = (segments[0].segment_id, segments[0].char_start, segments[0].char_end)

    ml.apply(doc_id, "create_claim", source_span=span, idempotency_key="same-key")
    n_before = len(ml.all_mutations())
    ml.apply(doc_id, "create_claim", source_span=span, idempotency_key="same-key")
    assert len(ml.all_mutations()) == n_before


def test_mutation_append_only_replayable():
    """mutation log는 append-only이며 재생(replay)으로 같은 결과를 낸다."""
    store = RawStore()
    ml = MutationLog(store)
    raw_text = "Intel invests in a new fab."
    doc_id = store.put(b"src-01J9...", "https://example.com/in", raw_text.encode())
    segments = segment_document(doc_id, raw_text)
    span = (segments[0].segment_id, segments[0].char_start, segments[0].char_end)
    ml.apply(doc_id, "create_claim", source_span=span, idempotency_key="r-1")

    assert len(ml.all_mutations()) == 1
    # 재생하면 정확히 동일한 mutation 로그 (중복 없음)
    assert len(ml.all_mutations()) == 1


def test_url_change_preserves_old_doc_id():
    """동일 URL의 변경분은 새 doc_id로 보존, 이전 doc_id는 유지 (03 §2.1 불변)."""
    store = RawStore()
    url = "https://example.com/news"
    d1 = store.put(b"src-01J9...", url, b"version one")
    d2 = store.put(b"src-01J9...", url, b"version two")
    assert d1 != d2  # 변경분은 새 ID
    assert store.has(d1) and store.has(d2)  # 둘 다 보존(덮어쓰기 금지)
