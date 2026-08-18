"""SLO 실측 관측 로그 — sealed 하니스 입력 생산 (design 11 §2.3) TDD.

Phase 6 인스트루먼테이션: SLO-05/06/07 가 `slo_metrics_harness` 판정의 *입력*을
생산하는 관측 계층. 로그가 sealed 하니스(수정 없음)와 이어져 "다음 수집·처리 런부터
측정 가능"하게 함을 통합 검증한다. read-only(불변식 §3-3)·결정적(clock 주입)·
honest-gap(§6.2 — 로그 부재 → 하니스 measured=False) 원칙.
"""
from __future__ import annotations

from orc_citadel.slo_metrics_harness import (
    collect_success_rate,
    quarantine_dwell_median,
    schema_pass_rate,
)
from orc_citadel.slo_observation_log import SloObservationLog


# --- SLO-05: 수집 시도/성공 → 성공률 --------------------------------------------


def test_collect_records_and_feeds_success_rate():
    """시도/성공 로그가 하니스 collect_success_rate 입력을 생산·연결."""
    log = SloObservationLog()
    log.record_collect("src", "http://a", ok=True)
    log.record_collect("src", "http://b", ok=True)
    log.record_collect("src", "http://c", ok=False)
    assert log.success_results() == [True, True, False]
    res = collect_success_rate(log.success_results())
    assert res["success_rate"] == round(2 / 3, 4)
    assert res["measured"] is True


def test_collect_log_readonly_and_empty_not_measured():
    """빈 로그 → 하니스 measured=False (honest-gap). 조회는 비파괴."""
    log = SloObservationLog()
    assert log.success_results() == []
    res = collect_success_rate(log.success_results())
    assert res["measured"] is False and res["success_rate"] is None
    # collect_log 은 원본 리스트 복사본 — 외부 변경이 내부에 영향 없음.
    log.record_collect("s", "u", True)
    raw = log.collect_log()
    raw.clear()
    assert log.success_results() == [True]


# --- SLO-06: schema 검증 통과 → 통과율 -------------------------------------------


def test_schema_records_and_feeds_pass_rate():
    """검증 통과 로그가 하니스 schema_pass_rate 입력을 생산·연결."""
    log = SloObservationLog()
    log.record_schema("src", "canonical", valid=True)
    log.record_schema("src", "contradiction", valid=True)
    log.record_schema("src", "canonical", valid=False)
    assert log.schema_results() == [True, True, False]
    res = schema_pass_rate(log.schema_results())
    assert res["pass_rate"] == round(2 / 3, 4)
    assert res["measured"] is True


def test_schema_log_readonly():
    log = SloObservationLog()
    log.record_schema("s", "k", True)
    raw = log.schema_log()
    raw.clear()
    assert log.schema_results() == [True]


# --- SLO-07: quarantine 진입/종료 → 체류 중앙값 ----------------------------------


def test_quarantine_dwell_fed_to_harness_median():
    """진입+종료 짝지어 체류 이벤트 → 하니스 quarantine_dwell_median 연결."""
    clock = iter([1000.0, 4000.0])  # enter 1회·exit 1회 clock 소모
    log = SloObservationLog(now_ms=lambda: next(clock))
    log.record_quarantine_enter("e1", reason="dangling_ref")
    log.record_quarantine_exit("e1")   # 4000 - 1000 = 3000ms
    assert log.dwell_entries() == [(1000.0, 4000.0)]
    assert quarantine_dwell_median(log.dwell_entries()) == 3000.0


def test_quarantine_open_entries_not_measured():
    """진입만 있고 종료 없는(진행 중) quarantine 는 체류 입력에서 제외 (honest-gap)."""
    log = SloObservationLog(now_ms=lambda: 1000.0)
    log.record_quarantine_enter("open1")
    assert log.dwell_entries() == []
    assert log.open_quarantine_count() == 1
    # 진행 중만으로는 measured 불가 (빈 입력 → 하니스 None).
    assert quarantine_dwell_median(log.dwell_entries()) is None


def test_quarantine_exit_without_enter_ignored():
    """진입 기록 없는 종료는 무시 (체류 부재를 측정으로 오인 금지)."""
    log = SloObservationLog(now_ms=lambda: 5000.0)
    log.record_quarantine_exit("phantom")  # 진입 없음
    assert log.dwell_entries() == []


def test_quarantine_reenter_idempotent():
    """동일 키 재진입 무시 — 첫 진입 시각 유지 (재진입은 clock 미소모)."""
    clock = iter([1000.0, 5000.0])  # enter 1회·exit 1회만 clock 소모
    log = SloObservationLog(now_ms=lambda: next(clock))
    log.record_quarantine_enter("e1")
    log.record_quarantine_enter("e1")  # 재진입 무시 — clock 안 씀
    log.record_quarantine_exit("e1")   # 5000 - 1000 = 4000
    assert log.dwell_entries() == [(1000.0, 5000.0)]


# --- 결정성 · clock 주입 --------------------------------------------------------


def test_clock_injection_deterministic():
    """now_ms 주입으로 측정 시각 결정 — 동일 입력 동일 출력."""
    def make():
        clock = iter([1000.0, 2000.0])
        log = SloObservationLog(now_ms=lambda: next(clock))
        log.record_quarantine_enter("e")
        log.record_quarantine_exit("e")
        return quarantine_dwell_median(log.dwell_entries())
    assert make() == make() == 1000.0
