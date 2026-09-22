"""Canonical Redpanda topics and small, versioned pipeline event envelopes."""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol


EVENT_VERSION = 1
MAX_ENVELOPE_BYTES = 1024 * 1024
MAX_JSON_DEPTH = 32
MAX_SCALAR_CHARS = 8_192


def _validate_json_tree(root: object, *, start_depth: int = 1) -> None:
    stack = [(root, start_depth)]
    while stack:
        node, depth = stack.pop()
        if depth > MAX_JSON_DEPTH:
            raise InvalidEnvelope("event envelope exceeds nesting depth limit")
        if isinstance(node, str):
            if len(node) > MAX_SCALAR_CHARS:
                raise InvalidEnvelope("event envelope scalar exceeds length limit")
        elif isinstance(node, dict):
            for key, child in node.items():
                if not isinstance(key, str) or len(key) > MAX_SCALAR_CHARS:
                    raise InvalidEnvelope("event envelope scalar exceeds length limit")
                stack.append((child, depth + 1))
        elif isinstance(node, list):
            stack.extend((child, depth + 1) for child in node)
STAGES = tuple(f"S{i}" for i in range(1, 8))
_STAGE_SLUGS = {
    "S1": "fetch",
    "S2": "store-raw",
    "S3": "parse-normalize",
    "S4": "dedup",
    "S5": "extract",
    "S6": "resolve",
    "S7": "graph-mutation",
}


class EventStreamError(RuntimeError):
    """Base error for the event-stream boundary."""


class InvalidEnvelope(ValueError):
    """The event does not satisfy the supported JSON contract."""


class TransientBrokerError(EventStreamError):
    """A broker failure that a caller may retry without quarantining data."""


class BrokerDeliveryError(EventStreamError):
    """A non-retriable broker rejection, distinct from a data defect."""


@dataclass(frozen=True, slots=True)
class StageTopics:
    primary: str
    retry: str
    dlq: str
    quarantine: str


STAGE_TOPICS = {
    stage: StageTopics(
        primary=(base := f"orc.events.{stage.lower()}.{_STAGE_SLUGS[stage]}.v{EVENT_VERSION}"),
        retry=f"{base}.retry",
        dlq=f"{base}.dlq",
        quarantine=f"{base}.quarantine",
    )
    for stage in STAGES
}
ALL_TOPIC_NAMES = tuple(
    name
    for topics in STAGE_TOPICS.values()
    for name in (topics.primary, topics.retry, topics.dlq, topics.quarantine)
)


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    event_version: int
    event_id: str
    stage: str
    event_type: str
    status: str
    input_ref: str | None
    output_ref: str | None
    idempotency_key: str
    correlation_id: str
    attempt_count: int
    occurred_at: datetime
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if type(self.event_version) is not int or self.event_version != EVENT_VERSION:
            raise InvalidEnvelope(f"unsupported event_version: {self.event_version!r}")
        if self.stage not in STAGE_TOPICS:
            raise InvalidEnvelope(f"invalid stage: {self.stage!r}")
        for field_name in ("event_id", "event_type", "status", "idempotency_key", "correlation_id"):
            if not isinstance(getattr(self, field_name), str) or not getattr(self, field_name):
                raise InvalidEnvelope(f"{field_name} must be a non-empty string")
        for field_name in ("input_ref", "output_ref"):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, str):
                raise InvalidEnvelope(f"{field_name} must be a string or null")
        if type(self.attempt_count) is not int or self.attempt_count < 0:
            raise InvalidEnvelope("attempt_count must be a non-negative integer")
        if not isinstance(self.occurred_at, datetime) or self.occurred_at.tzinfo is None:
            raise InvalidEnvelope("occurred_at must be timezone-aware")
        if not isinstance(self.payload, Mapping):
            raise InvalidEnvelope("payload must be a JSON object")
        try:
            _validate_json_tree(self.payload, start_depth=2)
            data = self._json_dict()
            _validate_json_tree(data)
            encoded = json.dumps(
                data, allow_nan=False, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        except InvalidEnvelope:
            raise
        except (TypeError, ValueError, RecursionError) as exc:
            raise InvalidEnvelope("envelope must contain JSON values and no bytes") from exc
        if len(encoded) > MAX_ENVELOPE_BYTES:
            raise InvalidEnvelope("event envelope exceeds size limit")

    def _json_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["occurred_at"] = self.occurred_at.isoformat()
        return data

    def to_json(self) -> bytes:
        try:
            data = self._json_dict()
            _validate_json_tree(data)
            encoded = json.dumps(
                data, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"), allow_nan=False,
            ).encode("utf-8")
        except InvalidEnvelope:
            raise
        except (TypeError, ValueError, RecursionError) as exc:
            raise InvalidEnvelope(
                "envelope must contain JSON values and no bytes") from exc
        if len(encoded) > MAX_ENVELOPE_BYTES:
            raise InvalidEnvelope("event envelope exceeds size limit")
        return encoded

    @classmethod
    def from_json(cls, value: bytes | str) -> "EventEnvelope":
        try:
            encoded_size = len(value) if isinstance(value, bytes) else len(
                value.encode("utf-8"))
            if encoded_size > MAX_ENVELOPE_BYTES:
                raise InvalidEnvelope("event envelope exceeds size limit")
            data = json.loads(value)
            if not isinstance(data, dict):
                raise TypeError("envelope root must be an object")
            _validate_json_tree(data)
            data["occurred_at"] = datetime.fromisoformat(data["occurred_at"])
            return cls(**data)
        except InvalidEnvelope:
            raise
        except (KeyError, TypeError, ValueError, json.JSONDecodeError,
                RecursionError) as exc:
            raise InvalidEnvelope("invalid event envelope JSON") from exc


class EventProducer(Protocol):
    def publish(self, envelope: EventEnvelope, *, route: str = "primary") -> None: ...


def _retriable(error: object) -> bool:
    retriable = getattr(error, "retriable", None)
    if callable(retriable):
        return bool(retriable())
    args = getattr(error, "args", ())
    return bool(args) and args[0] is not error and _retriable(args[0])


def _delivery_error(error: object) -> EventStreamError:
    error_type = TransientBrokerError if _retriable(error) else BrokerDeliveryError
    return error_type(str(error))


class KafkaEventProducer:
    """Synchronous boundary producer: return only after the broker callback acks."""

    def __init__(self, client, *, delivery_timeout: float = 10.0):
        self._client = client
        self._delivery_timeout = delivery_timeout

    @classmethod
    def from_env(cls) -> "KafkaEventProducer":
        from confluent_kafka import Producer

        brokers = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:19092")
        client = Producer({
            "bootstrap.servers": brokers,
            "acks": "all",
            "enable.idempotence": True,
        })
        return cls(client)

    def publish(self, envelope: EventEnvelope, *, route: str = "primary") -> None:
        topics = STAGE_TOPICS[envelope.stage]
        if route not in ("primary", "retry", "dlq", "quarantine"):
            raise ValueError(f"invalid event route: {route}")
        errors: list[object] = []

        def delivered(error, _message) -> None:
            if error is not None:
                errors.append(error)

        try:
            self._client.produce(
                getattr(topics, route),
                key=envelope.idempotency_key.encode("utf-8"),
                value=envelope.to_json(),
                on_delivery=delivered,
            )
            remaining = self._client.flush(self._delivery_timeout)
        except Exception as exc:
            raise _delivery_error(exc) from exc
        if errors:
            raise _delivery_error(errors[0])
        if remaining:
            raise TransientBrokerError(
                f"broker acknowledgement timed out with {remaining} event(s) pending"
            )


def bootstrap_topics(admin_client, *, partitions: int = 3,
                     replication_factor: int = 1) -> tuple[str, ...]:
    """Create every stage route once; a second call is a no-op."""
    from confluent_kafka import KafkaError
    from confluent_kafka.admin import NewTopic

    existing = set(admin_client.list_topics(timeout=10).topics)
    missing = tuple(name for name in ALL_TOPIC_NAMES if name not in existing)
    if not missing:
        return ()
    declarations = [NewTopic(name, num_partitions=partitions,
                             replication_factor=replication_factor)
                    for name in missing]
    for name, future in admin_client.create_topics(declarations).items():
        try:
            future.result()
        except Exception as exc:
            kafka_error = exc.args[0] if exc.args else None
            if getattr(kafka_error, "code", lambda: None)() != KafkaError.TOPIC_ALREADY_EXISTS:
                raise BrokerDeliveryError(f"failed to create topic {name}: {exc}") from exc
    return missing


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Bootstrap Orc Citadel event topics")
    parser.add_argument("command", choices=("bootstrap",), nargs="?", default="bootstrap")
    args = parser.parse_args(argv)
    if args.command == "bootstrap":
        from confluent_kafka.admin import AdminClient

        brokers = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:19092")
        bootstrap_topics(AdminClient({"bootstrap.servers": brokers}))


if __name__ == "__main__":
    main()
