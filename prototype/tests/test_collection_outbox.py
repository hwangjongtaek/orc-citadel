from __future__ import annotations

import hashlib

import pytest

from orc_citadel.collection_outbox import CollectionEventOutbox, s1_idempotency_key
from orc_citadel.raw_shard import RawShardStore


class RecordingProducer:
    def __init__(self):
        self.events = []

    def publish(self, envelope, *, route="primary"):
        self.events.append(envelope)


def _seed(raw_dir, source_id="source-a", url="https://example.test/a", content=b"body"):
    store = RawShardStore(raw_dir)
    doc_id, _ = store.append(source_id, url, content, {
        "fetched_at": "2026-09-22T01:02:03+00:00",
        "fetch_window": "2026-09-22",
        "fetch_correlation_id": "corr-fixed",
    })
    store.flush()
    return store, doc_id


def test_reconcile_recovers_durable_raw_row_and_acks_both_events(tmp_path):
    raw_dir = tmp_path / "data" / "raw"
    store, doc_id = _seed(raw_dir)
    producer = RecordingProducer()

    outbox = CollectionEventOutbox(tmp_path / "data")
    assert outbox.reconcile(store.iter_records()) == 1
    assert outbox.drain(producer) == 1

    assert [(event.stage, event.event_type) for event in producer.events] == [
        ("S1", "document_fetched"), ("S2", "raw_stored")]
    s1, s2 = producer.events
    assert s1.idempotency_key == s1_idempotency_key(
        "source-a", "https://example.test/a", "2026-09-22")
    assert s1.idempotency_key != f"fetch:{doc_id}"
    assert s1.event_id == "evt-" + hashlib.sha256(
        f"document_fetched:{s1.idempotency_key}".encode()).hexdigest()[:24]
    assert s2.idempotency_key == doc_id
    assert s2.output_ref == f"raw://source-a/{doc_id}"
    assert s1.correlation_id == s2.correlation_id == "corr-fixed"
    assert outbox.pending_count() == 0

    replay = RecordingProducer()
    assert outbox.drain(replay) == 0
    assert replay.events == []


def test_long_raw_url_uses_bounded_event_reference_without_blocking_outbox(tmp_path):
    raw_dir = tmp_path / "data" / "raw"
    store, doc_id = _seed(raw_dir, url="https://example.test/" + "x" * 9000)
    outbox = CollectionEventOutbox(tmp_path / "data")
    outbox.reconcile(store.iter_records())
    producer = RecordingProducer()

    assert outbox.drain(producer) == 1
    assert outbox.pending_count() == 0
    assert len(producer.events) == 2
    assert all(event.input_ref.startswith("url-sha256:")
               for event in producer.events)
    assert producer.events[1].output_ref == f"raw://source-a/{doc_id}"


def test_publish_without_ack_is_retried_and_duplicate_is_logical_same_event(tmp_path):
    raw_dir = tmp_path / "data" / "raw"
    store, _doc_id = _seed(raw_dir)
    outbox = CollectionEventOutbox(tmp_path / "data")
    outbox.reconcile(store.iter_records())

    class LoseSecondAck(RecordingProducer):
        def publish(self, envelope, *, route="primary"):
            super().publish(envelope, route=route)
            if envelope.stage == "S2":
                raise RuntimeError("ack lost")

    first = LoseSecondAck()
    with pytest.raises(RuntimeError, match="ack lost"):
        outbox.drain(first)

    second = RecordingProducer()
    assert CollectionEventOutbox(tmp_path / "data").drain(second) == 1
    assert [event.stage for event in second.events] == ["S2"]
    assert second.events[0].event_id == first.events[-1].event_id


def test_reconcile_keeps_identical_bytes_source_specific(tmp_path):
    raw_dir = tmp_path / "data" / "raw"
    store, doc_id = _seed(raw_dir, "source-a", "https://a.test/doc")
    store.append("source-b", "https://b.test/doc", b"body", {
        "fetched_at": "2026-09-22T01:02:03+00:00",
        "fetch_window": "full",
        "fetch_correlation_id": "corr-b",
    })
    store.flush()
    producer = RecordingProducer()
    outbox = CollectionEventOutbox(tmp_path / "data")

    assert outbox.reconcile(store.iter_records()) == 2
    assert outbox.drain(producer) == 2

    s2_refs = {event.output_ref for event in producer.events if event.stage == "S2"}
    assert s2_refs == {
        f"raw://source-a/{doc_id}",
        f"raw://source-b/{doc_id}",
    }
