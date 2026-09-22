"""수집 runner 상태 영속 계약."""
from __future__ import annotations

import json

from scripts import collection_runner


def test_runner_persists_success_summary(monkeypatch, tmp_path):
    state = tmp_path / "collection-run.json"
    state.write_text(json.dumps({"run_id": "collect-1", "status": "running"}))
    monkeypatch.setattr(collection_runner, "collect_selected", lambda source_ids: {
        "total_new": 2, "sources": {source_ids[0]: {"saved": 2, "skipped": 0, "errors": 0}},
    })

    collection_runner.main(["--state", str(state), "--source", "official-nvidia-news"])

    result = json.loads(state.read_text())
    assert result["status"] == "succeeded"
    assert result["summary"]["total_new"] == 2
    assert result["completed_at"].endswith("+00:00")
    assert not hasattr(collection_runner, "promote_zones")


def test_runner_dispatches_new_connector_kinds(monkeypatch, tmp_path):
    """새 kind 가 SOURCES 에 등록되면 러너가 바로 돌린다 — if/elif 세 벌 중복 제거의 계약."""
    import orc_citadel.collect_large as cl
    from scripts.collection_runner import collect_selected

    monkeypatch.setattr(cl, "RAW", tmp_path / "raw")
    monkeypatch.setattr(cl, "_SHARD_STORES", {})
    monkeypatch.setitem(cl.SOURCES, "gov-bulk-test",
                        ("bulk_archive", "https://bulk/x.zip"))

    calls = []
    monkeypatch.setitem(cl.COLLECTORS, "bulk_archive",
                        lambda spec, source_id, slo_log=None, known_urls=None,
                        event_producer=None:
                        calls.append((spec, source_id)) or
                        {"saved": 2, "skipped": 0, "errors": 0})

    summary = collect_selected(["gov-bulk-test"], event_producer=object())

    assert calls == [("https://bulk/x.zip", "gov-bulk-test")]
    assert summary["total_new"] == 2


def test_runner_uses_configured_producer_for_event_connectors(monkeypatch, tmp_path):
    import orc_citadel.collect_large as cl

    producer = object()
    monkeypatch.setattr(collection_runner.KafkaEventProducer, "from_env",
                        lambda: producer)
    monkeypatch.setattr(cl, "RAW", tmp_path / "raw")
    monkeypatch.setattr(cl, "_SHARD_STORES", {})
    monkeypatch.setitem(cl.SOURCES, "rss-test",
                        ("rss", "https://feed"))
    received = []
    monkeypatch.setitem(
        cl.COLLECTORS,
        "rss",
        lambda spec, source_id, *, known_urls, event_producer:
            received.append(event_producer)
            or {"saved": 0, "skipped": 0, "errors": 0},
    )

    collection_runner.collect_selected(["rss-test"])

    assert received == [producer]


def test_nightly_uses_configured_producer_for_scheduled_rss(monkeypatch, tmp_path):
    from scripts import nightly_collect
    import orc_citadel.collect_large as cl

    producer = object()
    monkeypatch.setattr(nightly_collect.KafkaEventProducer, "from_env",
                        lambda: producer)
    monkeypatch.setattr(cl, "SOURCES", {"rss-test": ("rss", "https://feed")})
    monkeypatch.setattr(nightly_collect, "SOURCES", cl.SOURCES)
    monkeypatch.setattr(cl, "RAW", tmp_path / "raw")
    monkeypatch.setattr(cl, "_SHARD_STORES", {})
    received = []
    monkeypatch.setitem(
        cl.COLLECTORS,
        "rss",
        lambda spec, source_id, *, slo_log, known_urls, event_producer:
            received.append(event_producer)
            or {"saved": 0, "skipped": 0, "errors": 0},
    )

    nightly_collect.main()

    assert received == [producer]
