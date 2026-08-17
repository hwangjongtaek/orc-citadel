"""Watchtower — SLO 위반 운영 경보 라우팅 (design 11 §2.3, ADR-1104).

SLO 위반은 Signal Spire 결론 알림이 아니라 **Watchtower 운영 경보**로 라우팅된다
(11 §2.3 — "SLO 위반은 자동으로 Signal Spire 운영 알림이 아니라 Watchtower 운영
경보로 라우팅한다", ADR-1104 채널 분리). 본 테스트는 그 라우팅 계약을 봉인한다:

- 운영 경보 = `classified == "slo-gate"` 루트만 (10 §1.4 CI 비차단 nightly).
- `not-measured` 는 위반이 아니라 honest-gap(§6.2) — 알림 대신 별도 관찰 버킷으로
  노출해 조용히 떨어뜨리지 않는다.
- fire-once: 각 SLO 는 `slo:{slo_id}` dedup_key 로 한 번만 점화 (ADR-1104).
- read-only(불변식 §3-3)·결정적 — 알림은 산출물일 뿐 저장·발송은 호출자 몫.

mock/실측 격리: 판정 결과(`evaluate_slo01/05/06/07` 산출 shape)를 주입.
"""
from __future__ import annotations

import pytest

from orc_citadel.watchtower_slo_alert import (
    WatchtowerSloAlert,
    is_slo_violation,
    make_operational_alert,
)

# --- 대표 SLO 판정 결과 (slo_metrics_harness / reflection_slo_harness 산출 shape) -----


def _slo_gate(slo_id: str) -> dict:
    """slo-gate (위반) — nightly 경보 대상."""
    if slo_id == "SLO-01":
        return {"within_slo": False, "classified": "slo-gate",
                "target_ms": 1800000, "p95_ms": 2000000}
    if slo_id == "SLO-05":
        return {"within_slo": False, "classified": "slo-gate",
                "target": 0.99, "success_rate": 0.95}
    if slo_id == "SLO-07":
        return {"within_slo": False, "classified": "slo-gate",
                "target_days": 3.0, "median_days": 6.0}
    raise ValueError(slo_id)


def _ok(slo_id: str) -> dict:
    if slo_id == "SLO-02":
        return {"within_slo": True, "classified": "ok", "target_ms": 10, "p50_ms": 1.0}
    raise ValueError(slo_id)


def _not_measured(slo_id: str) -> dict:
    """deferred SLO — 실데이터 부재 (부재가 OK 가 아니다, §6.2)."""
    return {"within_slo": False, "classified": "not-measured",
            "target_ms": 1800000}


# --- is_slo_violation -----------------------------------------------------------


def test_is_slo_violation_true_for_slo_gate():
    assert is_slo_violation(_slo_gate("SLO-01")) is True


def test_is_slo_violation_false_for_ok():
    assert is_slo_violation(_ok("SLO-02")) is False


def test_is_slo_violation_false_for_not_measured():
    assert is_slo_violation(_not_measured("SLO-01")) is False


def test_is_slo_violation_false_for_none():
    assert is_slo_violation(None) is False


# --- make_operational_alert -----------------------------------------------------


def test_make_operational_alert_channel_is_watchtower():
    """운영 경보 채널은 watchtower-operational (Signal Spire 와 분리, ADR-1104)."""
    alert = make_operational_alert("SLO-01", _slo_gate("SLO-01"))
    assert alert["channel"] == "watchtower-operational"
    assert alert["slo_id"] == "SLO-01"
    assert alert["classification"] == "slo-gate"


def test_make_operational_alert_dedup_key():
    """fire-once dedup key = `slo:{slo_id}` (ADR-1104 과잉 알림 금지)."""
    alert = make_operational_alert("SLO-01", _slo_gate("SLO-01"))
    assert alert["dedup_key"] == "slo:SLO-01"


def test_make_operational_alert_carries_evaluation_snapshot():
    """위반 알림은 측정 스냅샷(값·목표·within)을 담아 온콜이 판단 근거를 봐야 한다."""
    alert = make_operational_alert("SLO-01", _slo_gate("SLO-01"))
    assert alert["evaluation"]["p95_ms"] == 2000000
    assert alert["evaluation"]["target_ms"] == 1800000
    assert alert["evaluation"]["within_slo"] is False
    assert alert["acknowledged"] is False


def test_make_operational_alert_carries_rolling_window():
    """§2.3 측정 창 — 7d/1d/30d rolling, SLO 별 메타로 부착."""
    assert make_operational_alert("SLO-01", _slo_gate("SLO-01"))["window"] == "7d"
    assert make_operational_alert("SLO-05", _slo_gate("SLO-05"))["window"] == "7d"
    assert make_operational_alert("SLO-07", _slo_gate("SLO-07"))["window"] == "30d"


# --- WatchtowerSloAlert.route ---------------------------------------------------


def test_route_only_slo_gate_becomes_operational_alert():
    """위반(slo-gate)만 운영 경보로 — ok 는 알리지 않는다."""
    wt = WatchtowerSloAlert()
    out = wt.route({"SLO-01": _slo_gate("SLO-01"), "SLO-02": _ok("SLO-02")})
    assert [a["slo_id"] for a in out["violations"]] == ["SLO-01"]
    assert out["ok"] == ["SLO-02"]


def test_route_not_measured_is_surfaced_not_alerted():
    """`not-measured` 는 알림이 아니지만 조용히 떨어뜨리지 않는다 (§6.2 honest-gap)."""
    wt = WatchtowerSloAlert()
    out = wt.route({"SLO-01": _not_measured("SLO-01")})
    assert out["violations"] == []
    assert out["not_measured"] == ["SLO-01"]


def test_route_fire_once_dedup():
    """동일 SLO 는 한 번만 점화 (ADR-1104 과잉 알림 금지)."""
    wt = WatchtowerSloAlert()
    first = wt.route({"SLO-01": _slo_gate("SLO-01")})
    second = wt.route({"SLO-01": _slo_gate("SLO-01")})
    assert len(first["violations"]) == 1
    assert second["violations"] == []  # 재점화 금지


def test_route_multiple_violations_all_alerted():
    """여러 SLO 위반은 각각 운영 경보로."""
    wt = WatchtowerSloAlert()
    out = wt.route({"SLO-01": _slo_gate("SLO-01"),
                    "SLO-05": _slo_gate("SLO-05"),
                    "SLO-07": _slo_gate("SLO-07")})
    assert sorted(a["slo_id"] for a in out["violations"]) == ["SLO-01", "SLO-05", "SLO-07"]


def test_route_unclassified_is_surfaced():
    """classified 미지정(비정상 입력)은 ok 로 퉁치지 않고 별도 버킷으로 노출."""
    wt = WatchtowerSloAlert()
    out = wt.route({"SLO-99": {"within_slo": False}})
    assert out["violations"] == []
    assert out["unclassified"] == ["SLO-99"]


def test_route_empty_results():
    """빈 입력 → 빈 버킷 (부재가 OK 가 아니다 — 버킷은 모두 빈 채 반환)."""
    wt = WatchtowerSloAlert()
    out = wt.route({})
    assert out == {"violations": [], "not_measured": [], "ok": [], "unclassified": []}


def test_route_none_input():
    assert WatchtowerSloAlert().route(None)["violations"] == []


# --- read-only · 결정성 ---------------------------------------------------------


def test_route_is_read_only():
    """입력 판정 결과 dict 를 변경하지 않는다 (불변식 §3-3)."""
    results = {"SLO-01": _slo_gate("SLO-01")}
    snapshot = {"SLO-01": dict(results["SLO-01"])}
    WatchtowerSloAlert().route(results)
    assert results == snapshot


def test_route_is_deterministic():
    """동일 입력 → 동일 출력·동일 alert (결정적)."""
    results = {"SLO-01": _slo_gate("SLO-01"), "SLO-05": _slo_gate("SLO-05")}
    a = WatchtowerSloAlert().route(results)
    b = WatchtowerSloAlert().route(results)
    assert a == b
