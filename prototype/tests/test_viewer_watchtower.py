"""P1 viewer — Watchtower (`/watchtower`) 데이터 계약.

`/api/watchtower` 응답이 (a) source 수집 사실(실측 — source·type·doc 수)과
(b) SLO 판정표를 honest-gap(§6.2)으로 포함하는지 검증. SLO 관측은 in-memory
(런 간 미누적)이므로 전 SLO 가 `not-measured` — 가짜 데이터로 채우지 않음.
read-only 결정적.
"""
from __future__ import annotations

import json
import types

import pytest
from pathlib import Path

from orc_citadel.viewer import Handler


@pytest.fixture
def rawdir(tmp_path):
    """source_id 가 design 02 vocab prefix(official/press)를 갖는 raw 트리."""
    raw = tmp_path / "raw"
    for src, n in (("official-nvidia", 2), ("press-semi", 1)):
        for i in range(n):
            d = raw / src / "doc" / f"doc-{src}-{i}"
            d.mkdir(parents=True)
            (d / "content.bin").write_bytes(b"<h1>x</h1>")
            (d / "fetch.json").write_text('{"url": "https://e"}')
    return str(raw)


def _watch(self):
    return json.loads(Handler._api_watchtower(self, {}))


def test_watchtower_sources_from_raw_dir(rawdir):
    self = types.SimpleNamespace(raw_dir=rawdir)
    r = _watch(self)
    by_id = {s["source_id"]: s for s in r["sources"]}
    assert by_id["official-nvidia"]["doc_count"] == 2
    assert by_id["official-nvidia"]["source_type"] == "official"
    assert by_id["press-semi"]["doc_count"] == 1
    assert by_id["press-semi"]["source_type"] == "press"


def test_watchtower_slo_is_honest_not_measured():
    """관측 없음(런 간 미누적) → 전 nightly SLO not-measured, 위반 0, ratio None."""
    self = types.SimpleNamespace(raw_dir="")
    r = _watch(self)
    slo = r["slo"]
    # 5 nightly SLO 전부 나열 + measured=false (honest-gap 흉내 아님).
    assert len(slo["nightly_slos"]) == 5
    assert all(not s["measured"] for s in slo["nightly_slos"])
    assert all(s["classified"] == "not-measured" for s in slo["nightly_slos"])
    # error budget — 측정된 SLO 가 없어 ratio None (분모 제외, §6.2).
    eb = slo["error_budget"]
    assert eb["violations"] == 0
    assert eb["measured_count"] == 0
    assert eb["violation_ratio"] is None
