"""Redpanda event-stream deployment contract."""
from __future__ import annotations

import re
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def _compose(name: str) -> str:
    return (REPO / name).read_text(encoding="utf-8")


def _service_block(compose: str, name: str) -> str:
    match = re.search(rf"^  {name}:\n((?:    .*\n|\n)+)", compose, re.M)
    assert match, f"{name} service is missing"
    return match.group(1)


def test_base_redpanda_is_pinned_persistent_and_natively_healthy() -> None:
    block = _service_block(_compose("docker-compose.yml"), "redpanda")

    assert re.search(r"image: docker\.redpanda\.com/redpandadata/redpanda:v\d+\.\d+\.\d+", block)
    assert "127.0.0.1:19092:19092" in block
    assert "external://127.0.0.1:19092" in block
    assert "127.0.0.1:9644:9644" in block
    assert "redpanda-data:/var/lib/redpanda/data" in block
    assert "rpk cluster health" in block
    assert "restart: unless-stopped" in block
    assert re.search(r"^  redpanda-data:\s*$", _compose("docker-compose.yml"), re.M)




def test_topic_bootstrap_completes_before_prototype_starts() -> None:
    compose = _compose("docker-compose.yml")
    bootstrap = _service_block(compose, "redpanda-init")
    prototype = _service_block(compose, "prototype")

    assert 'command: ["python", "-m", "orc_citadel.event_stream", "bootstrap"]' in bootstrap
    assert "KAFKA_BOOTSTRAP_SERVERS: redpanda:9092" in bootstrap
    assert re.search(r"redpanda:\n\s+condition: service_healthy", bootstrap)
    assert re.search(r"redpanda-init:\n\s+condition: service_completed_successfully", prototype)


def test_promotion_consumer_waits_for_topics_and_durable_stores() -> None:
    block = _service_block(_compose("docker-compose.yml"), "promotion-consumer")

    assert 'command: ["python", "-m", "orc_citadel.promotion_consumer"]' in block
    assert "KAFKA_BOOTSTRAP_SERVERS: redpanda:9092" in block
    assert re.search(r"redpanda-init:\n\s+condition: service_completed_successfully", block)
    assert re.search(r"lakekeeper:\n\s+condition: service_healthy", block)
    assert re.search(r"minio:\n\s+condition: service_healthy", block)
    assert "./prototype/data:/app/data" in block
    assert "restart: unless-stopped" in block


def test_prod_promotion_consumer_is_always_on_and_uses_prod_data() -> None:
    block = _service_block(_compose("docker-compose.prod.yml"), "promotion-consumer")

    assert "profiles: !reset []" in block
    assert "proddata:/app/data" in block
    assert "restart: unless-stopped" in block


def test_prod_redpanda_has_no_published_ports_and_apps_use_broker_dns() -> None:
    prod = _compose("docker-compose.prod.yml")
    redpanda = _service_block(prod, "redpanda")
    assert "ports: !override []" in redpanda
    assert "restart: unless-stopped" in redpanda

    for service in ("prototype", "scheduler"):
        block = _service_block(prod, service)
        assert "KAFKA_BOOTSTRAP_SERVERS: redpanda:9092" in block
