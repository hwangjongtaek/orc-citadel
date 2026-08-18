"""SLO nightly 게이트 — 운용 루프 통합 오케스트레이션 (10 §1.4·11 §2.3).

Phase 6 DoD ② — "지속 수집이 자동 신호·SLO 에 반영되는 운용 루프 가동". 각 SLO
하니스의 **측정 → 판정(evaluate_slo0*) → Watchtower 운영 경보 라우팅** 을 하나의
기계적 nightly 게이트로 연결한다. 게이트는 **CI 비차단**(10 §1.4 — slo-gate 는
차단 없이 nightly 경보)으로, 분류·알림은 산출물일 뿐이며 read-only·결정적이다.

측정값은 **주입**(mock/실측 격리)한다 — nightly 드라이버가 하니스에서 실측값을
얻어 여기에 넘긴다. 게이트 자체는 계산에만 책임 (저장·발송·스케줄은 호출자 몫).
"""
from __future__ import annotations

import pytest

from orc_citadel.slo_nightly_gate import (
    NIGHTLY_SLOS,
    classify_slo,
    run_nightly_gate,
)


# --- classify_slo --------------------------------------------------------------


def test_classify_slo_measures_measurements():
    """측정값 → evaluate_slo0* 판정 → {slo_id, classified, evaluation}."""
    out = classify_slo("SLO-01", 2000000)  # > 30min → slo-gate
    assert out["slo_id"] == "SLO-01"
    assert out["classified"] == "slo-gate"
    assert out["evaluation"]["within_slo"] is False


def test_classify_slo_ok_within_target():
    assert classify_slo("SLO-05", 0.995)["classified"] == "ok"


def test_classify_slo_not_measured_on_none():
    """미측정(None) → not-measured (부재가 OK 가 아님, §6.2)."""
    assert classify_slo("SLO-07", None)["classified"] == "not-measured"


def test_classify_slo_unknown_slo_id():
    """미지정 SLO id 는 조용히 ok 로 퉁치지 않고 명시적 예외/퉁치기 금지."""
    with pytest.raises(ValueError):
        classify_slo("SLO-999", 1.0)


# --- run_nightly_gate ----------------------------------------------------------


def test_nightly_gate_routes_violations_to_watchtower():
    """slo-gate 판정은 Watchtower 운영 경보로 라우팅된다 (11 §2.3)."""
    out = run_nightly_gate({"SLO-01": 2000000, "SLO-05": 0.995})
    assert [v["slo_id"] for v in out["violations"]] == ["SLO-01"]


def test_nightly_gate_reports_per_slo_classification():
    out = run_nightly_gate({"SLO-01": 2000000, "SLO-05": 0.995})
    assert out["per_slo"]["SLO-01"]["classified"] == "slo-gate"
    assert out["per_slo"]["SLO-05"]["classified"] == "ok"


def test_nightly_gate_error_budget():
    """error budget = 위반 SLO 수 / 측정된(SLO-08 게이트 제외) SLO 수 (honest §6.2)."""
    out = run_nightly_gate({"SLO-01": 2000000, "SLO-05": 0.995, "SLO-07": 1.0})
    assert out["error_budget"]["violations"] == 1
    assert out["error_budget"]["measured_count"] == 3
    assert out["error_budget"]["violation_ratio"] == 0.3333  # 4자리 반올림(결정적)


def test_nightly_gate_not_measured_not_burned_in_error_budget():
    """미측정은 위반도 아니고 error budget 분모에도 포함되지 않는다 (§6.2)."""
    out = run_nightly_gate({"SLO-01": None, "SLO-05": 0.995})
    assert out["not_measured"] == ["SLO-01"]
    assert out["error_budget"]["measured_count"] == 1
    assert out["error_budget"]["violations"] == 0


def test_nightly_gate_empty():
    out = run_nightly_gate({})
    assert out["violations"] == []
    assert out["per_slo"] == {}
    assert out["error_budget"]["measured_count"] == 0


def test_nightly_gate_none_input():
    assert run_nightly_gate(None)["violations"] == []


def test_nightly_gate_fire_once_across_runs():
    """동일 nightly 라우터에서 SLO 는 한 번만 점화 (ADR-1104 과잉 알림 금지)."""
    g = run_nightly_gate({"SLO-01": 2000000})
    g2 = run_nightly_gate({"SLO-01": 2000000}, router=g["router"])
    assert len(g["violations"]) == 1
    assert g2["violations"] == []  # 재점화 금지


# --- read-only · 결정성 ---------------------------------------------------------


def test_nightly_gate_is_read_only():
    """입력 측정 dict 를 변경하지 않는다 (불변식 §3-3)."""
    m = {"SLO-01": 2000000, "SLO-05": 0.995}
    snapshot = dict(m)
    run_nightly_gate(m)
    assert m == snapshot


def test_nightly_gate_is_deterministic():
    """동일 입력 → 동일 출력 (결정적)."""
    m = {"SLO-01": 2000000, "SLO-05": 0.995}
    assert run_nightly_gate(m)["per_slo"] == run_nightly_gate(m)["per_slo"]


# --- NIGHTLY_SLOS --------------------------------------------------------------


def test_nightly_slos_are_deferred_phase6_slos():
    """nightly 루프 대상은 Phase 6 deferred SLO(01/05/06/07/08)."""
    assert "SLO-01" in NIGHTLY_SLOS
    assert "SLO-05" in NIGHTLY_SLOS
    assert "SLO-06" in NIGHTLY_SLOS
    assert "SLO-07" in NIGHTLY_SLOS
    assert "SLO-08" in NIGHTLY_SLOS
