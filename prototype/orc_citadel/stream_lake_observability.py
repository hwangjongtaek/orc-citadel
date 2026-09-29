"""Kafka consumer와 Iceberg catalog metadata를 run metric snapshot으로 내린다.

이 모듈은 broker log나 Iceberg table body를 읽지 않는다. Kafka Admin offset과
Iceberg snapshot metadata만 조회하고 기존 append-only ``pipeline_run_metrics``에
flush한다. 관측 실패는 0으로 바꾸지 않고 component probe 상태로 남긴다.
"""
from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from typing import Any

from .run_metrics import safe_flush

LOGGER = logging.getLogger(__name__)
DEFAULT_GROUP_ID = "orc-citadel-s2-promotion-v1"
DEFAULT_INTERVAL_S = 60.0


def _metric(name: str, value: float, labels: dict[str, str]) -> dict[str, Any]:
    return {"metric": name, "value": float(value), "labels": labels}


def _state_name(state: object) -> str:
    """confluent enum과 테스트용 문자열을 모두 안정적인 소문자 state로 만든다."""
    return str(getattr(state, "name", state)).rsplit(".", 1)[-1].lower()


def collect_kafka_metrics(admin: Any, group_id: str) -> list[dict[str, Any]]:
    """Kafka consumer group state, assigned partition 수와 topic 합계 lag를 읽는다."""
    from confluent_kafka import ConsumerGroupTopicPartitions, TopicPartition
    from confluent_kafka.admin import OffsetSpec

    group = admin.describe_consumer_groups([group_id])[group_id].result()
    state = _state_name(group.state)
    committed = admin.list_consumer_group_offsets(
        [ConsumerGroupTopicPartitions(group_id)]
    )[group_id].result().topic_partitions
    metrics = [
        _metric("kafka_consumer_group_healthy", state == "stable",
                {"group": group_id, "state": state}),
        _metric("kafka_consumer_group_partitions", len(committed), {"group": group_id}),
    ]
    if not committed:
        return metrics

    committed_by_partition = {
        (partition.topic, partition.partition): partition.offset for partition in committed
    }
    requested = {
        TopicPartition(topic, partition): OffsetSpec.latest()
        for topic, partition in committed_by_partition
    }
    end_offsets = admin.list_offsets(requested)
    lag_by_topic: dict[str, int] = {}
    for partition, end_future in end_offsets.items():
        end_offset = end_future.result().offset
        committed_offset = committed_by_partition[(partition.topic, partition.partition)]
        lag_by_topic[partition.topic] = lag_by_topic.get(partition.topic, 0) + max(
            0, end_offset - max(0, committed_offset)
        )
    metrics.extend(
        _metric("kafka_consumer_lag", lag, {"group": group_id, "topic": topic})
        for topic, lag in sorted(lag_by_topic.items())
    )
    return metrics


def _identifier_labels(identifier: object) -> dict[str, str]:
    parts = tuple(identifier) if isinstance(identifier, (tuple, list)) else str(identifier).split(".")
    if len(parts) < 2:
        raise ValueError(f"Iceberg table identifier requires namespace and table: {identifier!r}")
    return {"namespace": ".".join(str(part) for part in parts[:-1]), "table": str(parts[-1])}


def _summary_int(summary: dict[str, object], key: str) -> int | None:
    value = summary.get(key)
    if value is None:
        return None
    return int(value)


def collect_iceberg_metrics(catalog: Any, *, now_s: float | None = None) -> list[dict[str, Any]]:
    """Iceberg metadata만 조회해 table별 snapshot 상태를 만든다 (scan 금지)."""
    now_ms = int((time.time() if now_s is None else now_s) * 1000)
    metrics: list[dict[str, Any]] = []
    for namespace in catalog.list_namespaces():
        for identifier in catalog.list_tables(namespace):
            labels = _identifier_labels(identifier)
            try:
                table = catalog.load_table(identifier)
                snapshots = table.snapshots()
                metrics.append(_metric("iceberg_table_probe_ok", 1, labels))
                metrics.append(_metric("iceberg_snapshot_count", len(snapshots), labels))
                snapshot = table.current_snapshot()
                if snapshot is None:
                    continue
                metrics.append(_metric(
                    "iceberg_current_snapshot_age_s",
                    max(0, (now_ms - snapshot.timestamp_ms) / 1000), labels,
                ))
                for summary_key, metric_name in (
                    ("total-records", "iceberg_current_snapshot_records"),
                    ("total-data-files", "iceberg_current_snapshot_data_files"),
                ):
                    value = _summary_int(snapshot.summary, summary_key)
                    if value is not None:
                        metrics.append(_metric(metric_name, value, labels))
            except Exception:
                LOGGER.exception("Iceberg table metadata probe failed: %s", ".".join(labels.values()))
                metrics.append(_metric("iceberg_table_probe_ok", 0, labels))
    return metrics


def collect_observability_metrics(
    kafka_collector: Callable[[], list[dict[str, Any]]],
    iceberg_collector: Callable[[], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """두 저장 계층을 독립적으로 관측하고 실패 component만 0으로 남긴다."""
    metrics: list[dict[str, Any]] = []
    for probe_name, collector in (("kafka", kafka_collector), ("iceberg", iceberg_collector)):
        try:
            metrics.extend(collector())
        except Exception:
            LOGGER.exception("%s probe failed", probe_name)
            metrics.append(_metric(f"{probe_name}_probe_ok", 0, {}))
        else:
            metrics.append(_metric(f"{probe_name}_probe_ok", 1, {}))
    return metrics


def _collect_kafka_from_environment() -> list[dict[str, Any]]:
    from confluent_kafka.admin import AdminClient

    bootstrap_servers = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    group_id = os.environ.get("STREAM_STORAGE_KAFKA_GROUP", DEFAULT_GROUP_ID)
    return collect_kafka_metrics(AdminClient({"bootstrap.servers": bootstrap_servers}), group_id)


def _collect_iceberg_from_environment() -> list[dict[str, Any]]:
    from .iceberg_catalog import open_catalog

    handle = open_catalog(os.environ.get("ICEBERG_LOCAL_ROOT", "/app/data/iceberg"))
    try:
        return collect_iceberg_metrics(handle.catalog)
    finally:
        handle.close()


def collect_once() -> dict[str, Any]:
    """현재 Kafka/Iceberg snapshot을 기존 metric store로 비차단 flush한다."""
    metrics = collect_observability_metrics(
        _collect_kafka_from_environment, _collect_iceberg_from_environment,
    )
    return safe_flush(job_id="stream_storage_observer", metrics=metrics)


def main() -> None:
    """상주 probe 진입점 — polling 간격은 환경에서만 조정한다."""
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    interval_s = float(os.environ.get("STREAM_STORAGE_OBSERVE_INTERVAL_S", DEFAULT_INTERVAL_S))
    if interval_s <= 0:
        raise ValueError("STREAM_STORAGE_OBSERVE_INTERVAL_S must be positive")
    while True:
        result = collect_once()
        if result["flushed"]:
            LOGGER.info("stream storage metrics flushed: %s", result["metrics"])
        else:
            LOGGER.error("stream storage metric flush failed: %s", result["error"])
        time.sleep(interval_s)


if __name__ == "__main__":
    main()
