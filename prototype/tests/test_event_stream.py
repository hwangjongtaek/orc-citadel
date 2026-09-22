"""Versioned Kafka event envelopes, routing, and acknowledged delivery."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from orc_citadel.event_stream import (
    ALL_TOPIC_NAMES,
    EVENT_VERSION,
    EventEnvelope,
    InvalidEnvelope,
    KafkaEventProducer,
    STAGE_TOPICS,
    TransientBrokerError,
    bootstrap_topics,
)


def _envelope(**changes) -> EventEnvelope:
    fields = {
        "event_version": EVENT_VERSION,
        "event_id": "evt-1",
        "stage": "S2",
        "event_type": "raw_stored",
        "status": "succeeded",
        "input_ref": "https://source/doc",
        "output_ref": "raw://source/doc-a",
        "idempotency_key": "doc-a",
        "correlation_id": "corr-a",
        "attempt_count": 0,
        "occurred_at": datetime(2026, 9, 22, tzinfo=timezone.utc),
        "payload": {"source_id": "source"},
    }
    fields.update(changes)
    return EventEnvelope(**fields)


def test_envelope_json_roundtrip_is_canonical() -> None:
    encoded = _envelope().to_json()

    assert EventEnvelope.from_json(encoded) == _envelope()
    assert encoded == _envelope().to_json()
    assert b"content" not in encoded


@pytest.mark.parametrize("changes", [
    {"event_version": 2},
    {"stage": "S8"},
    {"payload": {"raw": b"document bytes"}},
    {"occurred_at": datetime(2026, 9, 22)},
])
def test_envelope_rejects_unsupported_or_non_json_contract(changes) -> None:
    with pytest.raises(InvalidEnvelope):
        _envelope(**changes)


def test_outbound_envelope_enforces_scalar_and_total_size_limits() -> None:
    with pytest.raises(InvalidEnvelope, match="scalar"):
        _envelope(input_ref="x" * 8193)
    with pytest.raises(InvalidEnvelope, match="size"):
        _envelope(payload={f"k{i}": "x" * 8000 for i in range(140)})
    mutable = _envelope()
    mutable.payload["padding"] = "x" * 8193
    with pytest.raises(InvalidEnvelope, match="scalar"):
        mutable.to_json()


def test_deserialization_rejects_invalid_stage_and_version() -> None:
    valid = _envelope().to_json().decode()

    with pytest.raises(InvalidEnvelope):
        EventEnvelope.from_json(valid.replace('"stage":"S2"', '"stage":"S9"'))
    with pytest.raises(InvalidEnvelope):
        EventEnvelope.from_json(valid.replace('"event_version":1', '"event_version":99'))


def test_stage_topics_cover_primary_retry_dlq_and_quarantine() -> None:
    assert tuple(STAGE_TOPICS) == tuple(f"S{i}" for i in range(1, 8))
    assert len(ALL_TOPIC_NAMES) == 28
    assert len(set(ALL_TOPIC_NAMES)) == 28
    assert STAGE_TOPICS["S1"].primary == "orc.events.s1.fetch.v1"
    assert STAGE_TOPICS["S7"].quarantine == "orc.events.s7.graph-mutation.v1.quarantine"


class _Future:
    def result(self):
        return None


class _Admin:
    def __init__(self):
        self.topics: set[str] = set()
        self.calls: list[tuple[str, ...]] = []

    def list_topics(self, timeout):
        metadata = type("Metadata", (), {})()
        metadata.topics = {name: object() for name in self.topics}
        return metadata

    def create_topics(self, declarations):
        names = tuple(item.topic for item in declarations)
        self.calls.append(names)
        self.topics.update(names)
        return {name: _Future() for name in names}


def test_topic_bootstrap_is_idempotent() -> None:
    admin = _Admin()

    assert bootstrap_topics(admin) == tuple(ALL_TOPIC_NAMES)
    assert bootstrap_topics(admin) == ()
    assert len(admin.calls) == 1


class _ProducerClient:
    def __init__(self, error=None, remaining=0):
        self.error = error
        self.remaining = remaining
        self.sent = []

    def produce(self, topic, *, key, value, on_delivery):
        self.sent.append((topic, key, value))
        on_delivery(self.error, object())

    def flush(self, timeout):
        return self.remaining


def test_producer_waits_for_broker_ack_and_routes_by_stage() -> None:
    client = _ProducerClient()
    producer = KafkaEventProducer(client, delivery_timeout=2.0)

    producer.publish(_envelope())

    assert client.sent == [(
        "orc.events.s2.store-raw.v1",
        b"doc-a",
        _envelope().to_json(),
    )]


def test_data_quarantine_is_an_explicit_route_not_a_broker_error() -> None:
    client = _ProducerClient()

    KafkaEventProducer(client).publish(
        _envelope(status="quarantined"), route="quarantine"
    )

    assert client.sent[0][0] == "orc.events.s2.store-raw.v1.quarantine"


class _RetriableError:
    def retriable(self):
        return True

    def __str__(self):
        return "broker unavailable"


def test_producer_classifies_retriable_delivery_failure() -> None:
    producer = KafkaEventProducer(_ProducerClient(error=_RetriableError()))

    with pytest.raises(TransientBrokerError, match="broker unavailable"):
        producer.publish(_envelope())
