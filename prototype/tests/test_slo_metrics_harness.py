"""SLO-05/06/07/08 측정 하니스 — 지표 실측 계약 봉인 (design 11 §2.3, 10 §1.4) TDD.

Phase 6(Stable 운용) deferred SLO 실측 — SLO-01과 동일한 측정 계약·하니스 봉인
패턴을 4개 SLO에 적용. 각각 독립 게이트 + not-measured/slo-gate 판정 (CI 비차단
nightly, 10 §1.4). SLO-08은 "벤치마크 공개"가 목표라 게이트 없이 공개 + measured 여부.

read-only(불변식 §3-3)·결정적·honest-gap(§6.2) 원칙 (Phase 6 전 작업과 동일).
"""
from __future__ import annotations

from orc_citadel.slo_metrics_harness import (
    NOT_MEASURED,
    OK,
    SLO05_TARGET,
    SLO06_TARGET,
    SLO07_TARGET_DAYS,
    SLO_GATE,
    collect_success_rate,
    evaluate_slo05,
    evaluate_slo06,
    evaluate_slo07,
    quarantine_dwell_median,
    quarantine_dwell_median_days,
    quarantine_dwell_times,
    reprocess_benchmark,
    schema_pass_rate,
)

# --- SLO-05: 수집 성공률 --------------------------------------------------------


def test_success_rate_basic():
    """성공/실패 → 성공률 = 성공/총 시도."""
    res = collect_success_rate([True, True, False, True])
    assert res["success_rate"] == 0.75
    assert res["n_success"] == 3 and res["n_attempt"] == 4
    assert res["measured"] is True


def test_success_rate_unknown_excluded():
    """None(미측정 시도)은 분모에서 제외·n_unknown 으로 노출 (honest-gap)."""
    res = collect_success_rate([True, None, False])
    assert res["success_rate"] == 0.5  # known 2건 (True, False)
    assert res["n_unknown"] == 1


def test_success_rate_empty_not_measured():
    """빈 입력 → success_rate=None + measured=False (부재가 OK 아님)."""
    res = collect_success_rate([])
    assert res["success_rate"] is None and res["measured"] is False


def test_evaluate_slo05_ok():
    """성공률 ≥ 99% → within_slo + ok."""
    res = evaluate_slo05(SLO05_TARGET)
    assert res["within_slo"] is True and res["classified"] == OK


def test_evaluate_slo05_violated():
    """성공률 < 99% → slo-gate (CI 차단 없이 nightly, 10 §1.4)."""
    res = evaluate_slo05(SLO05_TARGET - 0.01)
    assert res["within_slo"] is False and res["classified"] == SLO_GATE


def test_evaluate_slo05_not_measured():
    """None → not-measured + within_slo=False."""
    res = evaluate_slo05(None)
    assert res["within_slo"] is False and res["classified"] == NOT_MEASURED


# --- SLO-06: schema 통과율 ------------------------------------------------------


def test_schema_pass_rate_basic():
    """통과/실패 → 통과율 = 통과/총 검증."""
    res = schema_pass_rate([True, True, False, True, True])
    assert res["pass_rate"] == 0.8
    assert res["n_pass"] == 4 and res["n_total"] == 5


def test_schema_pass_rate_unknown_excluded():
    """None(검증 미실행)은 분모 제외·n_unknown 노출 (honest-gap)."""
    res = schema_pass_rate([True, None, False])
    assert res["pass_rate"] == 0.5 and res["n_unknown"] == 1


def test_schema_pass_rate_empty_not_measured():
    """빈 입력 → pass_rate=None + measured=False."""
    res = schema_pass_rate([])
    assert res["pass_rate"] is None and res["measured"] is False


def test_evaluate_slo06_ok():
    """통과율 ≥ 95% → ok."""
    res = evaluate_slo06(SLO06_TARGET)
    assert res["within_slo"] is True and res["classified"] == OK


def test_evaluate_slo06_violated():
    """통과율 < 95% → slo-gate."""
    res = evaluate_slo06(SLO06_TARGET - 0.01)
    assert res["classified"] == SLO_GATE


def test_evaluate_slo06_not_measured():
    """None → not-measured."""
    res = evaluate_slo06(None)
    assert res["classified"] == NOT_MEASURED


# --- SLO-07: quarantine 체류 시간(중앙값) --------------------------------------


def test_quarantine_dwell_times():
    """체류 시간 = 종료 − 진입 (ms)."""
    d = quarantine_dwell_times([(1000.0, 4000.0), (5000.0, 10000.0)])
    assert d == [3000.0, 5000.0]


def test_quarantine_dwell_open_excluded():
    """진행 중(exit=None)/비정상(exit<enter)은 제외 (측정 불가, honest-gap)."""
    d = quarantine_dwell_times([(1000.0, 4000.0), (1000.0, None)])
    assert d == [3000.0]


def test_quarantine_dwell_median():
    """중앙값 (체류 [2000,4000] → 짝수 개 → 평균 3000)."""
    assert quarantine_dwell_median([(1000.0, 3000.0), (1000.0, 5000.0)]) == 3000.0


def test_quarantine_dwell_median_odd():
    """중앙값 (홀수 개 → 중앙 원소). 체류 [2000,4000,6000] → 4000."""
    vals = [(1000.0, 3000.0), (1000.0, 5000.0), (1000.0, 7000.0)]
    assert quarantine_dwell_median(vals) == 4000.0


def test_quarantine_dwell_median_empty_none():
    """빈 입력 → None (honest-gap)."""
    assert quarantine_dwell_median([]) is None


def test_quarantine_dwell_median_days():
    """ms → 일 단위 변환 (SLO-07 목표 ≤3d 비교용). 2일 = 172800000ms."""
    days = quarantine_dwell_median_days([(0.0, 2 * 24 * 60 * 60 * 1000.0)])
    assert abs(days - 2.0) < 0.001


def test_evaluate_slo07_ok():
    """체류 중앙값 ≤ 3d → ok."""
    res = evaluate_slo07(SLO07_TARGET_DAYS)
    assert res["within_slo"] is True and res["classified"] == OK


def test_evaluate_slo07_violated():
    """체류 중앙값 > 3d → slo-gate."""
    res = evaluate_slo07(SLO07_TARGET_DAYS + 0.5)
    assert res["classified"] == SLO_GATE


def test_evaluate_slo07_not_measured():
    """None → not-measured."""
    res = evaluate_slo07(None)
    assert res["classified"] == NOT_MEASURED


# --- SLO-08: 100만 재처리 벤치마크 공개 -----------------------------------------


def test_reprocess_benchmark_publication():
    """벤치 full_ms 가 있으면 공개 + measured (게이트 없음 — 공개가 목표)."""
    res = reprocess_benchmark({"full_ms": 1234.5, "incremental_ms": 50.0})
    assert res["full_ms"] == 1234.5
    assert res["measured"] is True


def test_reprocess_benchmark_not_measured():
    """full_ms 미제공 → measured=False (honest-gap: 부재가 공개 근거 아님)."""
    res = reprocess_benchmark({})
    assert res["full_ms"] is None and res["measured"] is False


# --- read-only·결정성 -----------------------------------------------------------


def test_slo_metrics_read_only():
    """입력 리스트를 변경하지 않음 (read-only 불변식 §3-3)."""
    sr = [True, False, True]
    sp = [True, True, False]
    qe = [(1.0, 3.0), (2.0, 5.0)]
    sr0, sp0, qe0 = list(sr), list(sp), list(qe)
    collect_success_rate(sr)
    schema_pass_rate(sp)
    quarantine_dwell_times(qe)
    assert sr == sr0 and sp == sp0 and qe == qe0


def test_slo_metrics_deterministic():
    """동일 입력 → 동일 결과 (결정적)."""
    sr = [True, False, True, None]
    qe = [(1.0, 3.0), (2.0, 4.0)]
    assert collect_success_rate(sr) == collect_success_rate(sr)
    assert quarantine_dwell_median(qe) == quarantine_dwell_median(qe)
    assert evaluate_slo05(0.99) == evaluate_slo05(0.99)
