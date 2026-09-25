"""Consume durable S2 raw references and promote them into Iceberg zones."""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .event_stream import (
    EventEnvelope,
    InvalidEnvelope,
    KafkaEventProducer,
    STAGE_TOPICS,
)
from .incremental_promote import (
    BATCH_SIZE,
    PromotionInputError,
    promote_raw_refs,
)
from .raw_shard import SOURCE_ID_PATTERN

GROUP_ID = "orc-citadel-s2-promotion-v1"

# Offsets commit only after a whole batch is promoted, so the batch is also the
# unit the broker measures us by. 2026-09-23 prod: 237 documents in one batch
# blew past the librdkafka default 300_000ms, the client left the group, the
# follow-up commit raised UNKNOWN_MEMBER_ID and the process exited — restarting
# straight into the same uncommitted batch, forever.
#
# Measured the same day on prod (25 unpromoted documents, 183-document corpus):
# 150.3s, i.e. 6.01s per document — one 237-document batch needs ~24 minutes.
# 25 documents leaves roughly 6x headroom inside the declared interval. Per-
# document cost grows with corpus size (dedup and block reconcile both read the
# corpus), so this pair is a measured ceiling for today's corpus, not a constant.
POLL_BATCH_SIZE = 25
MAX_POLL_INTERVAL_MS = 900_000

# 배치를 채우려고 기다리는 시간. 커밋 상각의 단위는 배치인데 **배치는 저절로
# 커지지 않는다** — 수집은 문서를 하나씩 발행하고(HTTP 레이트리밋으로 분 단위에
# 흩뿌려진다) 1초 폴에 잡히는 건 보통 1건이라, 유효 배치 크기가 1이 된다.
#
# 2026-09-25 prod 실측: 신규 49문서에 curated 스냅샷 **+383**(문서당 약 7.8).
# 같은 25문서를 로컬에서 1배치로 승격하면 11스냅샷·1.2s, 5배치면 51·2.2s,
# 25배치면 **251스냅샷·13.8s** — 배치화의 이득은 전적으로 배치 크기에 비례한다.
#
# 대가는 승격 지연이다. 승격은 비동기이고 소비자가 없으므로 분 단위 지연은
# 값을 치를 만하다. 상한은 폴 간격 예산 — linger + 처리가 MAX_POLL_INTERVAL_MS
# 안에 끝나야 그룹에서 축출되지 않는다(테스트가 절반 이하로 고정한다).
LINGER_SECONDS = 60.0

# 스트림이 조용해지면 더 기다리지 않는다. 폴 1회는 `timeout` 만큼(기본 1s) 블록
# 하므로 연속 빈 폴 수는 곧 침묵의 길이다 — 수집이 끝났는데 linger 끝까지 굳어
# 있으면 승격만 늦어진다. arXiv 는 1 req/3s 라 문서 사이 빈 폴 몇 번은 정상이다.
QUIET_POLLS = 30

_DOC_ID = re.compile(r"^doc-[0-9a-f]{24}$")


def consumer_config(brokers: str) -> dict:
    """Return the stable manual-offset consumer configuration."""
    return {
        "bootstrap.servers": brokers,
        "group.id": GROUP_ID,
        "enable.auto.commit": False,
        "enable.auto.offset.store": False,
        "auto.offset.reset": "earliest",
        "max.poll.interval.ms": MAX_POLL_INTERVAL_MS,
    }


def _event_id(event_type: str, idempotency_key: str) -> str:
    digest = hashlib.sha256(f"{event_type}:{idempotency_key}".encode()).hexdigest()[:24]
    return f"evt-{digest}"


def _doc_id(envelope: EventEnvelope, message_key=None) -> tuple[str, str]:
    source_id = envelope.payload.get("source_id")
    expected_ref = (
        f"raw://{source_id}/{envelope.idempotency_key}"
        if (
            isinstance(source_id, str)
            and SOURCE_ID_PATTERN.fullmatch(source_id) is not None
        )
        else None
    )
    if isinstance(message_key, bytes):
        try:
            message_key = message_key.decode("utf-8")
        except UnicodeDecodeError:
            message_key = object()
    if (
        envelope.stage != "S2"
        or envelope.event_type != "raw_stored"
        or envelope.status not in {"succeeded", "retrying"}
        or not _DOC_ID.fullmatch(envelope.idempotency_key)
        or envelope.output_ref != expected_ref
        or (message_key is not None and message_key != envelope.idempotency_key)
    ):
        raise InvalidEnvelope("invalid S2 raw document reference")
    return source_id, envelope.idempotency_key


def _completion(envelope: EventEnvelope, summary: dict) -> EventEnvelope:
    doc_id = envelope.idempotency_key
    return EventEnvelope(
        event_version=1,
        event_id=_event_id("normalization_completed", doc_id),
        stage="S3",
        event_type="normalization_completed",
        status="succeeded",
        input_ref=envelope.output_ref,
        output_ref=f"iceberg://normalized/documents/{doc_id}",
        idempotency_key=doc_id,
        correlation_id=envelope.correlation_id,
        attempt_count=0,
        occurred_at=datetime.now(timezone.utc),
        payload={"doc_id": doc_id, "promotion": dict(summary)},
    )


def _message_key(message) -> str:
    key = message.key()
    if isinstance(key, bytes):
        try:
            decoded = key.decode("utf-8")
        except UnicodeDecodeError:
            decoded = None
        raw_key = key
    elif isinstance(key, str):
        decoded = key
        raw_key = key.encode("utf-8")
    else:
        decoded = None
        raw_key = b""
    if isinstance(decoded, str) and _DOC_ID.fullmatch(decoded):
        return decoded
    material = raw_key or message.value() or b""
    return "invalid-" + hashlib.sha256(material).hexdigest()[:24]


def _error_text(error: Exception) -> str:
    text = str(error)
    return text if len(text) <= 2_048 else text[:2_045] + "..."

def _quarantine(message, envelope: EventEnvelope | None, error: Exception) -> EventEnvelope:
    key = envelope.idempotency_key if envelope is not None else _message_key(message)
    return EventEnvelope(
        event_version=1,
        event_id=_event_id("raw_event_quarantined", key),
        stage="S2",
        event_type="raw_event_quarantined",
        status="quarantined",
        input_ref=envelope.input_ref if envelope is not None else None,
        output_ref=envelope.output_ref if envelope is not None else None,
        idempotency_key=key,
        correlation_id=(
            envelope.correlation_id if envelope is not None
            else f"corr-{hashlib.sha256(key.encode()).hexdigest()[:24]}"
        ),
        attempt_count=envelope.attempt_count if envelope is not None else 0,
        occurred_at=datetime.now(timezone.utc),
        payload={"error": _error_text(error)},
    )


def _failure(envelope: EventEnvelope, error: Exception,
             max_retries: int) -> tuple[EventEnvelope, str]:
    attempt = envelope.attempt_count + 1
    route = "retry" if attempt < max_retries else "dlq"
    status = "retrying" if route == "retry" else "failed"
    payload = {
        "source_id": envelope.payload.get("source_id"),
        "error": _error_text(error),
    }
    return EventEnvelope(
        event_version=envelope.event_version,
        event_id=_event_id(f"raw_stored_{route}_{attempt}", envelope.idempotency_key),
        stage="S2",
        event_type="raw_stored",
        status=status,
        input_ref=envelope.input_ref,
        output_ref=envelope.output_ref,
        idempotency_key=envelope.idempotency_key,
        correlation_id=envelope.correlation_id,
        attempt_count=attempt,
        occurred_at=datetime.now(timezone.utc),
        payload=payload,
    ), route


class PromotionConsumer:
    """One process-level S2 consumer; Kafka partitions provide parallelism."""

    def __init__(
        self,
        consumer,
        producer,
        *,
        raw_dir: str | Path,
        data_dir: str | Path,
        promote: Callable = promote_raw_refs,
        max_retries: int = 3,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._consumer = consumer
        self._producer = producer
        self._raw_dir = Path(raw_dir)
        self._data_dir = Path(data_dir)
        self._promote = promote
        self._max_retries = max_retries
        self._clock = clock
        topics = STAGE_TOPICS["S2"]
        consumer.subscribe([topics.primary, topics.retry])

    @classmethod
    def from_env(cls, *, raw_dir: str | Path | None = None,
                 data_dir: str | Path | None = None) -> "PromotionConsumer":
        from confluent_kafka import Consumer

        brokers = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:19092")
        root = Path(data_dir or os.environ.get("ORC_DATA_DIR", "data"))
        return cls(
            Consumer(consumer_config(brokers)),
            KafkaEventProducer.from_env(),
            raw_dir=raw_dir or root / "raw",
            data_dir=root,
            max_retries=int(os.environ.get("PROMOTION_MAX_RETRIES", "3")),
        )

    def _fill_batch(self, timeout: float) -> list:
        """Poll until the batch is full or the linger deadline passes.

        `consume` 자체가 poll 이므로 여기서 도는 동안에도 그룹 하트비트는 살아
        있다 — 잠들지 않고 계속 폴한다. 메시지가 하나도 없으면 기다리지 않는다
        (유휴 루프가 linger 만큼 굳으면 안 된다).
        """
        messages = self._consumer.consume(num_messages=POLL_BATCH_SIZE, timeout=timeout)
        if not messages:
            return []
        deadline = self._clock() + LINGER_SECONDS
        quiet = 0
        while (len(messages) < POLL_BATCH_SIZE and quiet < QUIET_POLLS
               and self._clock() < deadline):
            more = self._consumer.consume(
                num_messages=POLL_BATCH_SIZE - len(messages), timeout=timeout)
            messages.extend(more)
            quiet = 0 if more else quiet + 1
        return messages

    def run_once(self, *, timeout: float = 1.0) -> int:
        messages = self._fill_batch(timeout)
        if not messages:
            return 0
        started = self._clock()
        valid = []
        for message in messages:
            if message.error() is not None:
                raise RuntimeError(str(message.error()))
            envelope = None
            try:
                envelope = EventEnvelope.from_json(message.value())
                _doc_id(envelope, message.key())
                valid.append((message, envelope))
            except InvalidEnvelope as exc:
                self._producer.publish(_quarantine(message, envelope, exc),
                                       route="quarantine")

        pending = valid
        while pending:
            try:
                summary = self._promote(
                    self._raw_dir, self._data_dir,
                    [_doc_id(envelope) for _, envelope in pending],
                )
            except PromotionInputError as exc:
                defects = [
                    item for item in pending
                    if item[1].idempotency_key == exc.doc_id
                    and (
                        exc.source_id is None
                        or item[1].payload.get("source_id") == exc.source_id
                    )
                ]
                if not defects:
                    raise
                for message, envelope in defects:
                    self._producer.publish(_quarantine(message, envelope, exc),
                                           route="quarantine")
                pending = [item for item in pending if item not in defects]
                continue
            except Exception as exc:
                for _, envelope in pending:
                    outbound, route = _failure(envelope, exc, self._max_retries)
                    self._producer.publish(outbound, route=route)
                break
            for _, envelope in pending:
                self._producer.publish(_completion(envelope, summary))
            # 문서당 비용은 이 파이프라인의 스케일 한계를 정하는 수치다
            # (2026-09-23 prod 실측 6.01s/doc → 1,000만 단순 투영 약 694일).
            # 배치마다 로그에 남겨 다음 측정이 사람 손을 타지 않게 한다.
            elapsed = self._clock() - started
            per_doc = elapsed / len(pending) if pending else 0.0
            print(f"[promote] batch={len(messages)} promoted={len(pending)} "
                  f"elapsed={elapsed:.1f}s s/doc={per_doc:.2f} {summary}", flush=True)
            break
        for message in messages:
            try:
                self._consumer.commit(message=message, asynchronous=False)
            except Exception as exc:
                # Eviction invalidates every commit in this batch, not just one.
                # Redelivery is safe: promotion is idempotent, so let the group
                # rebalance and hand the batch back rather than dying on it.
                print(f"[promote] commit failed, batch will be redelivered: {exc}",
                      flush=True)
                break
        return len(messages)

    def run_forever(self, *, timeout: float = 1.0) -> None:
        try:
            while True:
                self.run_once(timeout=timeout)
        finally:
            self._consumer.close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Consume S2 raw_stored events and promote referenced documents",
    )
    parser.add_argument("--data-dir", default=os.environ.get("ORC_DATA_DIR", "data"))
    args = parser.parse_args(argv)
    PromotionConsumer.from_env(data_dir=args.data_dir).run_forever()


if __name__ == "__main__":
    main()