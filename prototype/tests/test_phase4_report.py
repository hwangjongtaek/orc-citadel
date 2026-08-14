"""Phase 4 DoD ①② 통합 공개 리포트 (design 10 §4.5·§1.4 → 01·06) TDD.

#14–#17 이 봉인한 계약을 DoD ①② 측에서 통합 공개한다 (중복 구현 없음 — 재사용).

- DoD ①: `project_time_to_scale`·`project_cost_to_scale` — 100만 스케일 처리 시간·비용
  **투영(projection)**. 결정적 모델 값이 실측이 아니므로 `measured=False` 명시
  (honest-gap §6.2). batch_cost 는 Message Batches 50% 절감(#17) 재사용.
- DoD ②: `graph_reflect_slo`·`compute_graph_slo`(#15) — 신규 문서 SLO 내 graph 반영 +
  증분 완료조건(ratio > 10×) 통합 판정.
- `phase4_dod_report` — DoD ①② 종합 리포트, `all_measured` 로 부분 미측정 노출.

read-only·결정적·mock/실측 격리 원칙 (Phase 4 전 작업과 동일).
"""
from __future__ import annotations

import pytest

from orc_citadel.phase4_report import (
    PHASE4_TARGET_DOCS,
    graph_reflect_slo,
    phase4_dod_report,
    project_cost_to_scale,
    project_time_to_scale,
)
from orc_citadel.batch_inference import MESSAGE_BATCHES_DISCOUNT


# --- project_time_to_scale (DoD ① 처리 시간 투영) ---------------------------


def test_time_projection_linear_scaling():
    """per-doc × target = 시간 투영 (결정적 선형 모델, 10 §4.5)."""
    r = project_time_to_scale(per_doc_ms=10.0, docs_processed=100,
                              target_docs=1_000_000)
    assert r["measured"] is True
    assert r["projected_ms"] == 10.0 * 1_000_000


def test_time_projection_parallel_speedup():
    """병렬 speedup 시 나누기 — 분산 batch(#14) 이득 반영."""
    r = project_time_to_scale(per_doc_ms=10.0, docs_processed=100,
                              target_docs=1_000_000, parallel_speedup=4.0)
    assert r["projected_ms"] == (10.0 * 1_000_000) / 4.0


def test_time_projection_speedup_floor():
    """speedup < 1 은 1 로 플로어 — 투영이 비현실적으로 빨라지지 않게 (보호)."""
    r = project_time_to_scale(per_doc_ms=10.0, docs_processed=100,
                              target_docs=1_000_000, parallel_speedup=0.2)
    assert abs(r["projected_ms"] - 10.0 * 1_000_000) < 1e-6


def test_time_projection_unmeasured_honest():
    """per_doc 미측정(None) → measured False · projected None — honest-gap (§6.2)."""
    r = project_time_to_scale(None, docs_processed=100, target_docs=1_000_000)
    assert r["measured"] is False
    assert r["projected_ms"] is None


def test_time_projection_zero_docs_is_unmeasured():
    """docs_processed ≤ 0 → measured False (분모·근거 부재)."""
    r = project_time_to_scale(per_doc_ms=10.0, docs_processed=0)
    assert r["measured"] is False
    assert r["projected_ms"] is None


def test_time_projection_uses_passed_target():
    """target_docs 파라미터 준수 (기본 100만)."""
    r = project_time_to_scale(per_doc_ms=5.0, docs_processed=100,
                              target_docs=500_000)
    assert r["target_docs"] == 500_000
    assert r["projected_ms"] == 5.0 * 500_000


# --- project_cost_to_scale (DoD ① 비용 투영) ---------------------------------


def test_cost_projection_sequential():
    """cost_per_doc × target = 순차 비용 투영 (10 §1.4 문서당 총비용)."""
    r = project_cost_to_scale(cost_per_doc=0.01, docs_processed=100,
                              target_docs=1_000_000, use_batch=False)
    assert r["measured"] is True
    assert r["sequential_cost"] == 0.01 * 1_000_000
    assert r["projected_cost"] == 0.01 * 1_000_000


def test_cost_projection_batch_discount():
    """use_batch → Message Batches 50% 절감 적용 (#17 재사용)."""
    r = project_cost_to_scale(cost_per_doc=0.01, docs_processed=100,
                              target_docs=1_000_000, use_batch=True)
    seq = 0.01 * 1_000_000
    assert r["sequential_cost"] == seq
    assert r["batch_cost"] == round(seq * MESSAGE_BATCHES_DISCOUNT, 6)
    assert r["projected_cost"] == r["batch_cost"]
    assert r["batch_discount"] == MESSAGE_BATCHES_DISCOUNT


def test_cost_projection_unmeasured_honest():
    """cost_per_doc 미측정(None) → measured False · 값 None — honest-gap (§6.2)."""
    r = project_cost_to_scale(None, docs_processed=100, target_docs=1_000_000)
    assert r["measured"] is False
    assert r["projected_cost"] is None
    assert r["sequential_cost"] is None


def test_cost_projection_zero_calls_discount_zero():
    """target ≤ 0 → measured False (투영 근거 없음 — batch 할인도 무시)."""
    r = project_cost_to_scale(0.01, docs_processed=100, target_docs=0,
                              use_batch=True)
    assert r["measured"] is False
    assert "batch_cost" not in r


# --- graph_reflect_slo / DoD ② ----------------------------------------------


def test_graph_reflect_passes_through():
    """graph_slo 결과를 재노출 — 중복 계산 없음 (#15 재사용)."""
    g = {"classified": "ok", "within_slo": True}
    r = graph_reflect_slo(graph=g)
    assert r["graph_slo"] == g
    assert "node_slo" not in r and "incremental_gate" not in r


def test_graph_reflect_includes_optional_slos():
    """latency·incremental 게이트 포함 시 재노출 (DoD ② 종합)."""
    r = graph_reflect_slo(
        graph={"classified": "ok"},
        latency={"classified": "ok", "violated": False},
        incremental={"saving_meaningful": True,
                     "gate": {"threshold": 10.0, "pass": True},
                     "slo_gate": True},
    )
    assert r["node_slo"]["violated"] is False
    assert r["incremental_gate"]["gate"]["pass"] is True


# --- phase4_dod_report (DoD ①② 종합) ----------------------------------------


def test_report_all_measured():
    """전 구성요소 실측 → all_measured True (DoD ①·② 공개)."""
    time_ = project_time_to_scale(10.0, 100, target_docs=1_000_000)
    cost_ = project_cost_to_scale(0.01, 100, target_docs=1_000_000)
    gs = {"classified": "ok", "within_slo": True}
    rep = phase4_dod_report(dod1_time=time_, dod1_cost=cost_, graph_slo=gs)
    assert rep["all_measured"] is True
    assert rep["dod1"]["target_docs"] == PHASE4_TARGET_DOCS
    assert rep["dod1"]["processing_time"]["projected_ms"] == 10.0 * 1_000_000


def test_report_marks_partial_unmeasured_honest():
    """시간·비용 투영(measured=True)이라도 graph_slo 미측정이면 all_measured False."""
    time_ = project_time_to_scale(10.0, 100)
    cost_ = project_cost_to_scale(0.01, 100)
    gs = {"classified": "not-measured", "within_slo": False}  # honest-gap §6.2.
    rep = phase4_dod_report(dod1_time=time_, dod1_cost=cost_, graph_slo=gs)
    assert rep["all_measured"] is False


def test_report_marks_time_projection_as_honest():
    """DoD ① 시간·비용은 투영이므로 cost 미측정 입력 → all_measured False."""
    time_ = project_time_to_scale(10.0, 100)
    cost_ = project_cost_to_scale(None, 100)  # 미측정.
    gs = {"classified": "ok"}
    rep = phase4_dod_report(dod1_time=time_, dod1_cost=cost_, graph_slo=gs)
    assert rep["all_measured"] is False


def test_report_includes_optional_slos():
    """latency·incremental 게이트 포함 → DoD ② 종합 노출 (partial)."""
    time_ = project_time_to_scale(10.0, 100)
    cost_ = project_cost_to_scale(0.01, 100)
    gs = {"classified": "ok"}
    lat = {"classified": "ok", "violated": False}
    inc = {"gate": {"pass": True}, "slo_gate": True}
    rep = phase4_dod_report(time_, cost_, gs, latency_slo=lat,
                            incremental_gate=inc)
    assert rep["all_measured"] is True
    assert rep["dod2"]["node_slo"]["violated"] is False
    assert rep["dod2"]["incremental_gate"]["gate"]["pass"] is True


# --- 불변식 (read-only·결정성) -----------------------------------------------


def test_read_only_no_mutation():
    """phase4_report 모듈은 read-only — 쓰기·mutation 미노출 (불변식 §3-3)."""
    from orc_citadel import phase4_report as pr

    for bad in ("apply", "persist", "create_node", "create_edge", "insert",
                "write", "upsert"):
        assert not hasattr(pr, bad), f"read-only 위반: {bad} 노출"


def test_report_is_deterministic():
    """동일 입력 → 동일 투영·리포트 (결정성 — 재현성)."""
    a = phase4_dod_report(
        project_time_to_scale(10.0, 100),
        project_cost_to_scale(0.01, 100),
        {"classified": "ok"},
    )
    b = phase4_dod_report(
        project_time_to_scale(10.0, 100),
        project_cost_to_scale(0.01, 100),
        {"classified": "ok"},
    )
    assert a == b
