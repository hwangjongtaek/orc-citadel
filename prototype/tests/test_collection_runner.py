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
    promoted = []
    monkeypatch.setattr(collection_runner, "promote_zones", lambda summary: promoted.append(summary))

    collection_runner.main(["--state", str(state), "--source", "official-nvidia-news"])

    result = json.loads(state.read_text())
    assert result["status"] == "succeeded"
    assert result["summary"]["total_new"] == 2
    assert result["completed_at"].endswith("+00:00")
    assert promoted == [result["summary"]]


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
                        lambda spec, source_id, slo_log=None, known_urls=None:
                        calls.append((spec, source_id)) or
                        {"saved": 2, "skipped": 0, "errors": 0})

    summary = collect_selected(["gov-bulk-test"])

    assert calls == [("https://bulk/x.zip", "gov-bulk-test")]
    assert summary["total_new"] == 2
