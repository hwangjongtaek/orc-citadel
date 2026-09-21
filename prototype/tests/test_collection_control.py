"""등록 source 즉시 수집 제어 계약."""
from __future__ import annotations

import json

import pytest

from orc_citadel.collection_control import CollectionControl


class _Process:
    pid = 731


def test_trigger_starts_only_registered_sources_and_persists_running_state(tmp_path):
    calls = []
    control = CollectionControl(tmp_path, popen=lambda args: calls.append(args) or _Process())

    result = control.trigger(["official-nvidia-news"])

    assert result["status"] == "running"
    assert result["source_ids"] == ["official-nvidia-news"]
    assert result["pid"] == 731
    assert calls[0][1].endswith("scripts/collection_runner.py")
    assert calls[0][-2:] == ["--source", "official-nvidia-news"]
    assert json.loads((tmp_path / "collection-run.json").read_text())["run_id"] == result["run_id"]


def test_trigger_rejects_unknown_or_empty_source_ids(tmp_path):
    control = CollectionControl(tmp_path, popen=lambda _: _Process())

    with pytest.raises(ValueError, match="등록된 source"):
        control.trigger(["official-blizzard-news"])
    with pytest.raises(ValueError, match="최소 한 개"):
        control.trigger([])


def test_trigger_does_not_start_second_collection_while_running(tmp_path):
    calls = []
    control = CollectionControl(tmp_path, popen=lambda args: calls.append(args) or _Process())
    control.trigger(["official-nvidia-news"])

    with pytest.raises(RuntimeError, match="이미 실행 중"):
        control.trigger(["official-amd-ir"])

    assert len(calls) == 1
