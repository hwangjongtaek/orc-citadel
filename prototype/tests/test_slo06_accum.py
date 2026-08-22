"""SLO-06 7d rolling 누적 로그 (1번 시간 축 전환 — A26).

nightly 마다 SLO-06 실측의 개별 schema 검증 결과(`record_schema` 성격)를
`data/slo06_accum.json` 에 append하고, 최근 7일 누적분으로 `schema_pass_rate` →
`evaluate_slo06` 재확정 판정을 내린다 (11 §2.3, honest-gap §6.2 — 순시 스냅샷
아닌 운영 7d rolling 축적으로 확정(잠정)→확정 전환의 근거).

순수 함수·결정적 — 라이브 LLM·영속 쓰기는 드라이버(스크립트) 몫, 오프라인 테스트.
"""
from __future__ import annotations

import json

from orc_citadel.slo06_accum import accum_append, accum_recent, accum_slo06, SLO06_TARGET


def test_accum_append_writes_and_reads_entries(tmp_path):
    path = tmp_path / "slo06_accum.json"
    entries = [
        {"ts": "2026-08-20T00:00:00Z", "source_id": "claude_judge",
         "kind": "contradiction_verdict", "valid": True},
        {"ts": "2026-08-20T00:00:00Z", "source_id": "claude_judge",
         "kind": "canonical_verdict", "valid": True},
    ]
    accum_append(path, entries)
    data = json.loads(path.read_text())
    assert len(data) == 2
    assert data[0]["valid"] is True


def test_accum_append_is_append_not_overwrite(tmp_path):
    """재실행 시 기존 항목을 덮지 않고 append — 7일 축적의 핵심."""
    path = tmp_path / "slo06_accum.json"
    accum_append(path, [{"ts": "t1", "source_id": "s", "kind": "k", "valid": True}])
    accum_append(path, [{"ts": "t2", "source_id": "s", "kind": "k", "valid": False}])
    data = json.loads(path.read_text())
    assert len(data) == 2
    assert data[1]["valid"] is False


def test_accum_recent_filters_by_day_window(tmp_path):
    path = tmp_path / "slo06_accum.json"
    accum_append(path, [
        {"ts": "2026-08-01T00:00:00Z", "source_id": "s", "kind": "k", "valid": True},
        {"ts": "2026-08-20T00:00:00Z", "source_id": "s", "kind": "k", "valid": True},
        {"ts": "2026-08-21T00:00:00Z", "source_id": "s", "kind": "k", "valid": False},
    ])
    recent = accum_recent(path, days=3, now="2026-08-22T00:00:00Z")
    assert len(recent) == 2  # 8-19~8-22 창에 속하는 2건 (8-01 제외)


def test_accum_slo06_7d_roll_reevaluates_pass_rate(tmp_path):
    """7일 누적 전부 valid → pass_rate 1.0, within_slo True (확정(잠정)→확정 근거)."""
    path = tmp_path / "slo06_accum.json"
    entries = [
        {"ts": f"2026-08-{d:02d}T00:00:00Z", "source_id": "claude_judge",
         "kind": "contradiction_verdict", "valid": True}
        for d in range(16, 23)  # 8/16~8/22 — 7일분
    ]
    accum_append(path, entries)
    res = accum_slo06(path, days=7, now="2026-08-22T00:00:00Z")
    assert res["pass_rate"] == 1.0
    assert res["within_slo"] is True
    assert res["measured"] is True
    assert res["target"] == SLO06_TARGET


def test_accum_slo06_empty_log_is_not_measured(tmp_path):
    path = tmp_path / "slo06_accum.json"
    res = accum_slo06(path, days=7, now="2026-08-22T00:00:00Z")
    assert res["measured"] is False
    assert res["classified"] == "not-measured"
