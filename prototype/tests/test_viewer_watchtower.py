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


# --- 동반 구성요소 접속 패널 (Watchtower — 사이드카 도달성 실측) --------------------

def test_watchtower_components_are_probed_not_hardcoded(monkeypatch):
    """components 는 프로브 실측 결과를 그대로 낸다 — 응답에서 상태를 가공하지 않음."""
    canned = [{"id": "grafana", "name": "Grafana", "layer": "관측", "port": 3000,
               "ui_port": 3000, "ui_path": "/d/citadel-pipeline",
               "requires_localhost": False, "note": None, "reachable": False}]
    monkeypatch.setattr(
        "orc_citadel.component_status.probe_components", lambda: canned)
    self = types.SimpleNamespace(raw_dir="")
    r = _watch(self)
    assert r["components"] == canned


def test_watchtower_components_default_catalog():
    """기본 카탈로그 6종이 응답에 나열된다 (도달성 값은 환경 종속 — 형태만 가드)."""
    self = types.SimpleNamespace(raw_dir="")
    r = _watch(self)
    ids = {c["id"] for c in r["components"]}
    assert ids == {"postgres", "minio", "neo4j", "opensearch",
                   "grafana", "duckdb-ui"}
    assert all(isinstance(c["reachable"], bool) for c in r["components"])


# --- run 메트릭 표시 필드 (specs/ui-overhaul-astryx Step 12 — TS-6) ----------------

def test_watchtower_run_metrics_honest_when_pg_down():
    """postgres 미가동 → run_metrics 는 정직 빈 (가짜 런 없음, §6.2)."""
    def broken():
        raise RuntimeError("pg down")
    self = types.SimpleNamespace(raw_dir="", metrics_connect=broken)
    r = _watch(self)
    rm = r["run_metrics"]
    assert rm["available"] is False and rm["runs"] == []
    assert "pipeline_run_metrics" in rm["source_tables"]
    assert rm["note"]


def test_watchtower_run_metrics_recent_runs_shape():
    """가동 시 최근 런 요약 — run_id·job_id·metrics 스칼라 분해 (표시용 read-only)."""
    class FakeCursor:
        def execute(self, sql, params=None):
            self._sql = sql
        def fetchall(self):
            if "GROUP BY" in self._sql:  # 최근 런 목록
                return [("run-1", "nightly_collect", "2026-09-08T07:07:00+00:00")]
            return [("run-1", "total_new", 3.0), ("run-1", "saved", 2.0)]
    class FakeConn:
        def cursor(self):
            return FakeCursor()
        def close(self):
            pass
    self = types.SimpleNamespace(raw_dir="", metrics_connect=lambda: FakeConn())
    r = _watch(self)
    rm = r["run_metrics"]
    assert rm["available"] is True
    (run,) = rm["runs"]
    assert run["run_id"] == "run-1" and run["job_id"] == "nightly_collect"
    assert run["metrics"] == {"total_new": 3.0, "saved": 2.0}
