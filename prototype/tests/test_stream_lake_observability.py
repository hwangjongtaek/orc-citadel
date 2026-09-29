from __future__ import annotations

from dataclasses import dataclass

from orc_citadel.stream_lake_observability import (
    collect_iceberg_metrics,
    collect_kafka_metrics,
    collect_observability_metrics,
)


class Future:
    def __init__(self, value):
        self.value = value

    def result(self):
        return self.value


@dataclass
class Offset:
    topic: str
    partition: int
    offset: int


class KafkaAdmin:
    def describe_consumer_groups(self, group_ids):
        return {group_ids[0]: Future(type("Group", (), {"state": "STABLE"})())}

    def list_consumer_group_offsets(self, requests):
        group_id = requests[0].group_id
        offsets = [Offset("orc.events.s2.store-raw.v1", 0, 12),
                   Offset("orc.events.s2.store-raw.v1", 1, 7)]
        return {group_id: Future(type("GroupOffsets", (), {
            "topic_partitions": offsets,
        })())}

    def list_offsets(self, requests):
        values = {("orc.events.s2.store-raw.v1", 0): 15,
                  ("orc.events.s2.store-raw.v1", 1): 7}
        return {partition: Future(Offset(partition.topic, partition.partition,
                                         values[(partition.topic, partition.partition)]))
                for partition in requests}


def test_collect_kafka_metrics_reports_group_state_and_topic_lag() -> None:
    metrics = collect_kafka_metrics(KafkaAdmin(), "orc-citadel-s2-promotion-v1")

    assert {m["metric"] for m in metrics} == {
        "kafka_consumer_group_healthy", "kafka_consumer_group_partitions",
        "kafka_consumer_lag",
    }
    assert [m["value"] for m in metrics if m["metric"] == "kafka_consumer_lag"] == [3.0]
    assert next(m for m in metrics if m["metric"] == "kafka_consumer_group_healthy") == {
        "metric": "kafka_consumer_group_healthy", "value": 1.0,
        "labels": {"group": "orc-citadel-s2-promotion-v1", "state": "stable"},
    }


@dataclass
class Snapshot:
    timestamp_ms: int
    summary: dict[str, str]


class IcebergTable:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def snapshots(self):
        return [self.snapshot]

    def current_snapshot(self):
        return self.snapshot


class IcebergCatalog:
    def list_namespaces(self):
        return [("normalized",)]

    def list_tables(self, namespace):
        assert namespace == ("normalized",)
        return [("normalized", "documents")]

    def load_table(self, identifier):
        assert identifier == ("normalized", "documents")
        return IcebergTable(Snapshot(1_000, {
            "total-records": "359",
            "total-data-files": "2",
        }))


def test_collect_iceberg_metrics_reads_snapshot_metadata_without_a_table_scan() -> None:
    metrics = collect_iceberg_metrics(IcebergCatalog(), now_s=4)

    values = {metric["metric"]: metric["value"] for metric in metrics}
    assert values == {
        "iceberg_table_probe_ok": 1.0,
        "iceberg_snapshot_count": 1.0,
        "iceberg_current_snapshot_age_s": 3.0,
        "iceberg_current_snapshot_records": 359.0,
        "iceberg_current_snapshot_data_files": 2.0,
    }


def test_component_failure_becomes_probe_state_not_zero_measurement() -> None:
    metrics = collect_observability_metrics(
        lambda: (_ for _ in ()).throw(RuntimeError("Kafka unavailable")),
        lambda: [{"metric": "iceberg_snapshot_count", "value": 1.0, "labels": {}}],
    )

    assert {"metric": "kafka_probe_ok", "value": 0.0, "labels": {}} in metrics
    assert {"metric": "iceberg_probe_ok", "value": 1.0, "labels": {}} in metrics
