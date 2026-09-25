from __future__ import annotations

from datetime import datetime, timezone
import json

import pytest

from orc_citadel.event_stream import EventEnvelope, InvalidEnvelope, STAGE_TOPICS
from orc_citadel.incremental_promote import PromotionDataError
from orc_citadel.promotion_consumer import (
    BATCH_SIZE,
    GROUP_ID,
    LINGER_SECONDS,
    MAX_POLL_INTERVAL_MS,
    POLL_BATCH_SIZE,
    PromotionConsumer,
    consumer_config,
)


def test_consumer_config_is_stable_manual_and_bounded() -> None:
    config = consumer_config("redpanda:9092")

    assert GROUP_ID == "orc-citadel-s2-promotion-v1"
    assert config["bootstrap.servers"] == "redpanda:9092"
    assert config["group.id"] == GROUP_ID
    assert config["enable.auto.commit"] is False
    assert config["enable.auto.offset.store"] is False
    assert BATCH_SIZE == 1_000


def test_poll_batch_fits_the_declared_poll_interval() -> None:
    """A batch must finish well inside the poll interval or the broker evicts us.

    2026-09-23 prod: one 237-document batch exceeded the librdkafka default
    300_000ms, the client left the group, the follow-up commit raised
    UNKNOWN_MEMBER_ID and the process died into a non-progressing restart loop.
    """
    config = consumer_config("redpanda:9092")

    assert config["max.poll.interval.ms"] == MAX_POLL_INTERVAL_MS
    assert POLL_BATCH_SIZE < BATCH_SIZE
    # Budget per document at a full batch. Prod measured 6.01s/doc on 2026-09-23,
    # so a 30s budget keeps ~5x margin as the corpus — and the cost — grows.
    assert MAX_POLL_INTERVAL_MS / POLL_BATCH_SIZE >= 30_000



def _raw_event(doc_id: str = "doc-" + "a" * 24, **changes) -> EventEnvelope:
    fields = {
        "event_version": 1,
        "event_id": f"evt-{doc_id}",
        "stage": "S2",
        "event_type": "raw_stored",
        "status": "succeeded",
        "input_ref": "https://example.test/a",
        "output_ref": f"raw://official-news/{doc_id}",
        "idempotency_key": doc_id,
        "correlation_id": f"corr-{doc_id}",
        "attempt_count": 0,
        "occurred_at": datetime(2026, 9, 22, tzinfo=timezone.utc),
        "payload": {"source_id": "official-news"},
    }
    fields.update(changes)
    return EventEnvelope(**fields)


class _Message:
    def __init__(self, value: bytes, *, offset: int = 0, key: bytes | None = None):
        self._value = value
        self._offset = offset
        self._key = key

    def value(self):
        return self._value

    def key(self):
        return self._key

    def topic(self):
        return STAGE_TOPICS["S2"].primary

    def partition(self):
        return 0

    def offset(self):
        return self._offset

    def error(self):
        return None


class _ConsumerClient:
    def __init__(self, messages, order=None, per_poll=None):
        self.messages = messages
        self.order = order if order is not None else []
        self.subscriptions = []
        self.commits = []
        self.consume_args = None
        self.first_consume_args = None
        self.consume_calls = 0
        # None = 한 번에 전부 (기존 동작). 정수면 폴 1회당 그만큼만 낸다 —
        # prod 에서 수집이 문서를 하나씩 발행하는 실제 형태.
        self.per_poll = per_poll

    def subscribe(self, topics):
        self.subscriptions.append(topics)

    def consume(self, *, num_messages, timeout):
        self.consume_args = (num_messages, timeout)
        if self.first_consume_args is None:
            self.first_consume_args = self.consume_args
        self.consume_calls += 1
        take = len(self.messages) if self.per_poll is None else self.per_poll
        messages, self.messages = self.messages[:take], self.messages[take:]
        return messages

    def commit(self, *, message, asynchronous):
        self.order.append(("commit", message.offset()))
        self.commits.append((message, asynchronous))


class _Producer:
    def __init__(self, order=None):
        self.order = order if order is not None else []
        self.published = []

    def publish(self, envelope, *, route="primary"):
        self.order.append(("publish", envelope.stage, route))
        self.published.append((envelope, route))


def test_successful_batch_promotes_referenced_ids_then_acks_s3_before_commit(tmp_path) -> None:
    event = _raw_event()
    messages = [
        _Message(event.to_json(), offset=4),
        _Message(event.to_json(), offset=5),
    ]
    order = []
    client = _ConsumerClient(messages, order)
    producer = _Producer(order)
    promotions = []

    def promote(raw_dir, data_dir, refs):
        order.append(("promote", tuple(refs)))
        promotions.append((raw_dir, data_dir, refs))
        return {"new_docs": 1, "mentions": 1, "claims": 1,
                "promoted_claims": 1, "clusters": 0}

    worker = PromotionConsumer(
        client, producer, raw_dir=tmp_path / "raw", data_dir=tmp_path / "data",
        promote=promote,
    )
    processed = worker.run_once(timeout=0.25)

    assert client.subscriptions == [[STAGE_TOPICS["S2"].primary,
                                     STAGE_TOPICS["S2"].retry]]
    # 첫 폴은 배치 상한만큼 요청한다 — 이후 폴은 남은 자리만 채운다(linger).
    assert client.first_consume_args == (POLL_BATCH_SIZE, 0.25)
    assert processed == 2
    assert promotions == [(tmp_path / "raw", tmp_path / "data",
                           [("official-news", event.idempotency_key)] * 2)]
    assert [(out.stage, out.event_type, route)
            for out, route in producer.published] == [
                ("S3", "normalization_completed", "primary"),
                ("S3", "normalization_completed", "primary"),
            ]
    assert order.index(("promote", (("official-news", event.idempotency_key),) * 2)) < \
        order.index(("publish", "S3", "primary")) < order.index(("commit", 4))
    assert [async_ for _, async_ in client.commits] == [False, False]


def test_invalid_envelope_and_reference_are_acked_to_quarantine_then_committed(tmp_path) -> None:
    doc_id = "doc-" + "b" * 24
    bad_reference = _raw_event(doc_id, output_ref=f"raw://wrong/{doc_id}")
    path_source = _raw_event(
        doc_id,
        output_ref=f"raw://../../outside/{doc_id}",
        payload={"source_id": "../../outside"},
    )
    messages = [
        _Message(b"not-json", offset=1, key=doc_id.encode()),
        _Message(bad_reference.to_json(), offset=2, key=doc_id.encode()),
        _Message(path_source.to_json(), offset=3, key=doc_id.encode()),
    ]
    order = []
    client = _ConsumerClient(messages, order)
    producer = _Producer(order)

    def should_not_promote(*args):
        raise AssertionError("invalid input reached promotion")

    processed = PromotionConsumer(
        client, producer, raw_dir=tmp_path / "raw", data_dir=tmp_path / "data",
        promote=should_not_promote,
    ).run_once()

    assert processed == 3
    assert [(event.stage, event.status, route)
            for event, route in producer.published] == [
                ("S2", "quarantined", "quarantine"),
                ("S2", "quarantined", "quarantine"),
                ("S2", "quarantined", "quarantine"),
            ]
    assert [event.idempotency_key for event, _ in producer.published] == [
        doc_id, doc_id, doc_id]
    assert max(i for i, item in enumerate(order) if item[0] == "publish") < \
        min(i for i, item in enumerate(order) if item[0] == "commit")


def test_data_defect_is_quarantined_and_committed(tmp_path) -> None:
    event = _raw_event("doc-" + "c" * 24)
    client = _ConsumerClient([_Message(event.to_json(), key=event.idempotency_key.encode())])
    producer = _Producer()

    def reject_data(raw_dir, data_dir, refs):
        raise PromotionDataError(refs[0][1], "unparseable document")

    processed = PromotionConsumer(
        client, producer, raw_dir=tmp_path / "raw", data_dir=tmp_path / "data",
        promote=reject_data,
    ).run_once()

    assert processed == 1
    assert [(out.status, route) for out, route in producer.published] == [
        ("quarantined", "quarantine"),
    ]
    assert len(client.commits) == 1


def test_data_defect_quarantines_only_the_exact_source_reference(tmp_path) -> None:
    doc_id = "doc-" + "f" * 24
    good = _raw_event(
        doc_id,
        output_ref=f"raw://good-source/{doc_id}",
        payload={"source_id": "good-source"},
    )
    bad = _raw_event(
        doc_id,
        output_ref=f"raw://bad-source/{doc_id}",
        payload={"source_id": "bad-source"},
    )
    client = _ConsumerClient([
        _Message(good.to_json(), offset=1),
        _Message(bad.to_json(), offset=2),
    ])
    producer = _Producer()
    calls = []

    def reject_one_source(raw_dir, data_dir, refs):
        calls.append(refs)
        if ("bad-source", doc_id) in refs:
            raise PromotionDataError(
                doc_id, "unparseable document", source_id="bad-source")
        return {"new_docs": 1, "mentions": 0, "claims": 0,
                "promoted_claims": 0, "clusters": 0}

    processed = PromotionConsumer(
        client, producer, raw_dir=tmp_path / "raw", data_dir=tmp_path / "data",
        promote=reject_one_source,
    ).run_once()

    assert processed == 2
    assert calls == [
        [("good-source", doc_id), ("bad-source", doc_id)],
        [("good-source", doc_id)],
    ]
    assert [(out.status, out.output_ref, route)
            for out, route in producer.published] == [
                ("quarantined", f"raw://bad-source/{doc_id}", "quarantine"),
                ("succeeded", f"iceberg://normalized/documents/{doc_id}", "primary"),
            ]
    assert len(client.commits) == 2


@pytest.mark.parametrize(
    ("attempt_count", "route", "status"),
    [(0, "retry", "retrying"), (1, "dlq", "failed"), (2, "dlq", "failed")],
)
def test_unexpected_failure_routes_incremented_retry_or_dlq_before_commit(
        tmp_path, attempt_count, route, status) -> None:
    event = _raw_event("doc-" + "d" * 24, attempt_count=attempt_count)
    order = []
    client = _ConsumerClient([_Message(event.to_json())], order)
    producer = _Producer(order)

    def fail(*args):
        raise RuntimeError("catalog temporarily unavailable")

    processed = PromotionConsumer(
        client, producer, raw_dir=tmp_path / "raw", data_dir=tmp_path / "data",
        promote=fail, max_retries=2,
    ).run_once()

    assert processed == 1
    [(out, actual_route)] = producer.published
    assert actual_route == route
    assert out.stage == "S2"
    assert out.status == status
    assert out.attempt_count == attempt_count + 1
    assert order.index(("publish", "S2", route)) < order.index(("commit", 0))


def test_retry_drops_untrusted_payload_padding_and_still_commits(tmp_path) -> None:
    payload = {"source_id": "official-news", "padding": []}
    while True:
        candidate = {
            "source_id": "official-news",
            "padding": [*payload["padding"], "x" * 8192],
        }
        try:
            _raw_event(payload=candidate)
        except InvalidEnvelope:
            break
        payload = candidate
    low, high = 0, 8192
    event = _raw_event(payload=payload)
    while low <= high:
        middle = (low + high) // 2
        candidate = {**payload, "tail": "x" * middle}
        try:
            event = _raw_event(payload=candidate)
        except InvalidEnvelope:
            high = middle - 1
        else:
            low = middle + 1
    client = _ConsumerClient([
        _Message(event.to_json(), key=event.idempotency_key.encode())
    ])
    producer = _Producer()

    def fail(*_args):
        raise RuntimeError("e" * 2048)

    processed = PromotionConsumer(
        client, producer, raw_dir=tmp_path / "raw", data_dir=tmp_path / "data",
        promote=fail, max_retries=2,
    ).run_once()

    assert processed == 1
    [(retry, route)] = producer.published
    assert route == "retry"
    assert retry.attempt_count == 1
    assert set(retry.payload) == {"source_id", "error"}
    assert len(retry.to_json()) < 4096
    assert len(client.commits) == 1


def test_broker_publish_failure_leaves_offsets_uncommitted(tmp_path) -> None:
    event = _raw_event("doc-" + "e" * 24)
    client = _ConsumerClient([_Message(event.to_json())])

    class RejectingProducer:
        def publish(self, envelope, *, route="primary"):
            raise RuntimeError("broker did not acknowledge")

    def promote(*args):
        return {"new_docs": 1, "mentions": 0, "claims": 0,
                "promoted_claims": 0, "clusters": 0}

    worker = PromotionConsumer(
        client, RejectingProducer(), raw_dir=tmp_path / "raw",
        data_dir=tmp_path / "data", promote=promote,
    )
    with pytest.raises(RuntimeError, match="acknowledge"):
        worker.run_once()

    assert client.commits == []


def test_oversized_and_deep_events_are_quarantined_small_then_committed(tmp_path) -> None:
    base = json.loads(_raw_event().to_json())
    oversized = dict(base)
    oversized["payload"] = {
        "source_id": "official-news",
        "padding": "x" * (1024 * 1024),
    }
    nested: object = "leaf"
    for _ in range(40):
        nested = {"next": nested}
    deep = dict(base)
    deep["payload"] = {"source_id": "official-news", "nested": nested}
    messages = [
        _Message(json.dumps(oversized).encode(), offset=1),
        _Message(json.dumps(deep).encode(), offset=2),
        _Message(b"not-json", offset=3, key=b"k" * (600 * 1024)),
    ]
    client = _ConsumerClient(messages)
    producer = _Producer()

    processed = PromotionConsumer(
        client, producer, raw_dir=tmp_path / "raw", data_dir=tmp_path / "data",
        promote=lambda *_args: (_ for _ in ()).throw(
            AssertionError("poison record reached promotion")),
    ).run_once()

    assert processed == 3
    assert len(client.commits) == 3
    assert [(event.status, route) for event, route in producer.published] == [
        ("quarantined", "quarantine"),
        ("quarantined", "quarantine"),
        ("quarantined", "quarantine"),
    ]
    assert all(len(event.idempotency_key) < 64
               for event, _ in producer.published)
    assert all(len(event.to_json()) < 1_024 for event, _ in producer.published)

def test_commit_failure_is_survivable_and_the_batch_is_redelivered(tmp_path) -> None:
    """A rebalance-time commit failure must not kill the worker.

    At-least-once delivery plus idempotent promotion makes redelivery safe, so
    the worker keeps polling and the uncommitted batch simply arrives again.
    """
    event = _raw_event("doc-" + "0" * 24)

    class _EvictingClient(_ConsumerClient):
        def __init__(self, messages):
            super().__init__(messages)
            self.commit_attempts = 0

        def commit(self, *, message, asynchronous):
            self.commit_attempts += 1
            raise RuntimeError("Commit failed: Broker: Unknown member")

    client = _EvictingClient([
        _Message(event.to_json(), offset=7),
        _Message(event.to_json(), offset=8),
    ])
    producer = _Producer()

    def promote(raw_dir, data_dir, refs):
        return {"new_docs": 1, "mentions": 0, "claims": 0,
                "promoted_claims": 0, "clusters": 0}

    worker = PromotionConsumer(
        client, producer, raw_dir=tmp_path / "raw", data_dir=tmp_path / "data",
        promote=promote,
    )

    assert worker.run_once() == 2
    # The first failure ends the batch: every later commit fails the same way.
    assert client.commit_attempts == 1
    assert client.commits == []

    client.messages = [_Message(event.to_json(), offset=7)]
    assert worker.run_once() == 1


def test_batch_progress_is_logged_for_diagnosis(tmp_path, capsys) -> None:
    """The 2026-09-23 incident ran 20 minutes with an empty container log."""
    event = _raw_event("doc-" + "1" * 24)
    client = _ConsumerClient([_Message(event.to_json())])

    def promote(raw_dir, data_dir, refs):
        return {"new_docs": 1, "mentions": 2, "claims": 3,
                "promoted_claims": 4, "clusters": 5}

    PromotionConsumer(
        client, _Producer(), raw_dir=tmp_path / "raw", data_dir=tmp_path / "data",
        promote=promote,
    ).run_once()

    out = capsys.readouterr().out
    assert "1" in out and "new_docs" in out
    # 배치 소요는 승격 비용(2026-09-23 실측 6.01s/doc)의 유일한 상시 관측점이다 —
    # 다음 nightly 의 문서당 비용을 사람이 따로 재러 가지 않아도 로그에 남는다.
    assert "elapsed=" in out and "s/doc=" in out


# ---- 배치 적재(linger) — 커밋 상각의 단위는 배치이고, 배치는 저절로 크지 않는다 ----

def test_batch_accumulates_across_polls_instead_of_promoting_one_document(
        tmp_path, monkeypatch) -> None:
    """수집은 문서를 하나씩 발행한다 — 1초 폴에 잡히는 것만 묶으면 배치가 1이다.

    2026-09-25 prod 실측: 신규 49문서에 curated 스냅샷 **+383**(문서당 약 7.8).
    같은 25문서를 로컬에서 1배치로 승격하면 11스냅샷·1.2s, 25배치로 쪼개면
    **251스냅샷·13.8s** — 배치화의 이득은 전적으로 배치 크기에 비례하고, prod 의
    유효 배치 크기는 1이었다. 그래서 폴을 여러 번 걸쳐 모은다.
    """
    events = [_Message(_raw_event(f"doc-{i:024d}").to_json(), offset=i)
              for i in range(5)]
    client = _ConsumerClient(events, per_poll=1)
    promotions = []

    def promote(raw_dir, data_dir, refs):
        promotions.append(len(refs))
        return {"new_docs": len(refs)}

    consumer = PromotionConsumer(
        client, _Producer(), raw_dir=tmp_path / "raw", data_dir=tmp_path / "data",
        promote=promote)

    processed = consumer.run_once()

    # 5번의 폴이 5개의 승격이 아니라 1개의 승격으로 합쳐져야 한다.
    assert processed == 5
    assert promotions == [5]
    assert client.consume_calls >= 5


def test_idle_poll_returns_without_lingering(tmp_path) -> None:
    """메시지가 없으면 기다리지 않는다 — 유휴 루프가 linger 만큼 굳으면 안 된다."""
    client = _ConsumerClient([], per_poll=1)

    consumer = PromotionConsumer(
        client, _Producer(), raw_dir=tmp_path / "raw", data_dir=tmp_path / "data",
        promote=lambda *_a: {})

    assert consumer.run_once() == 0
    assert client.consume_calls == 1


def test_linger_gives_up_at_the_deadline(tmp_path) -> None:
    """적재는 무한정이 아니다 — 폴 간격 예산 안에서 끝나야 한다."""
    import itertools
    ticks = itertools.chain([0.0, 0.0, 1.0], itertools.repeat(LINGER_SECONDS + 1.0))
    client = _ConsumerClient(
        [_Message(_raw_event(f"doc-{i:024d}").to_json(), offset=i) for i in range(5)],
        per_poll=1)
    promotions = []

    consumer = PromotionConsumer(
        client, _Producer(), raw_dir=tmp_path / "raw", data_dir=tmp_path / "data",
        promote=lambda raw, data, refs: promotions.append(len(refs)) or {},
        clock=lambda: next(ticks))

    processed = consumer.run_once()

    assert processed < 5, "deadline 을 넘겼는데도 배치를 계속 채웠다"
    assert promotions == [processed]
    # 남은 메시지는 다음 폴에서 이어받는다 — 버려지지 않는다.
    assert len(client.messages) == 5 - processed


def test_linger_fits_inside_the_declared_poll_interval() -> None:
    """linger + 처리 시간이 poll 간격을 넘으면 그룹에서 축출된다."""
    assert LINGER_SECONDS * 1000 < MAX_POLL_INTERVAL_MS / 2
