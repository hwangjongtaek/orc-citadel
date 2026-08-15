"""signal source adaptive scheduling — 신호 수율 기반 수집 예산 배분 (04 §1·§5, 01 §6, Phase 5) TDD.

Phase 5 「signal source adaptive scheduling」 — 10M Challenge 수집 병목에서, 소스별
**신호 수율(문서당 claims+edges)**을 측정해 제한된 수집 예산을 **고수율 소스에 우선
배분**하되, 각 소스에 **freshness floor**(미배분/멸종 방지, 04 §5)를 보장한다.

- arXiv(신호 희소) vs 전용 반도체 언론(신호 고밀도) 대비를 **수율 지표**로 봉인
  (`signal_source_runner` 메모리 확증 재사용 — density = (claims+edges)/docs).
- `allocate_signal_budget` — density 비례 잉여 배분 + min_docs 피보장 (read-only·결정적).
  미측정 소스는 잉여 경쟁 제외(min 만 유지, honest-gap §6.2), 전 소스 미측정 → 균등(보수적).
- `freshness_lag` — 04 §5 freshness 지연(최신 수집 vs 기대 주기), overdue 판정.
- `cadence_priority` — density → 04 §1.1 schedule.priority (high/normal/low).
- `adaptive_schedule` — 히스토리 → trailing density → 배분 + lag 부착 결정적 오케스트레이션.

결정적·read-only·mock/실측 격리 원칙 (Phase 4/5 전 작업과 동일).
"""
from __future__ import annotations

import pytest

from orc_citadel.signal_scheduler import (
    adaptive_schedule,
    allocate_signal_budget,
    cadence_priority,
    freshness_lag,
    signal_density,
    trailing_signal_density,
)


# --- signal_density (신호 수율 = (claims+edges)/docs) -----------------------


def test_signal_density_positive():
    """10건 수집, claims 4 + edges 6 → density = (4+6)/10 = 1.0."""
    assert signal_density(docs=10, claims=4, edges=6) == 1.0


def test_signal_density_zero_signal():
    """수집은 있으나 신호 0 (arXiv abstract 메모리 확증) → 0.0."""
    assert signal_density(docs=10, claims=0, edges=0) == 0.0


def test_signal_density_fractional():
    """신호가 문서보다 적으면 1 미만 소수."""
    assert signal_density(docs=20, claims=3, edges=3) == pytest.approx(0.3)


def test_signal_density_no_docs_is_none():
    """docs=0 → None (측정 불가, honest-gap — 미측정이 0 이 아님)."""
    assert signal_density(docs=0, claims=0, edges=0) is None


def test_signal_density_high_density_source():
    """전용 반도체 언론 고신호 — density > 1."""
    d = signal_density(docs=4, claims=10, edges=8)
    assert d is not None and d > 1.0


def test_signal_density_deterministic():
    """동일 입력 → 동일 출력 (결정성)."""
    assert signal_density(10, 4, 6) == signal_density(10, 4, 6)


# --- trailing_signal_density (과거 run 누적) --------------------------------


def test_trailing_accumulates_docs_weighted():
    """여러 run 의 신호 총합 / 문서 총합 — 문서 수 가중."""
    runs = [
        {"docs": 10, "claims": 4, "edges": 6},   # signal 10
        {"docs": 10, "claims": 2, "edges": 0},   # signal 2
    ]
    assert trailing_signal_density(runs) == pytest.approx(12 / 20)  # 0.6


def test_trailing_zero_runs_is_none():
    """빈 이력 → None (미측정)."""
    assert trailing_signal_density([]) is None


def test_trailing_no_docs_is_none():
    """수집 문서 0 인 run 들 → None (박살 가드)."""
    assert trailing_signal_density([{"docs": 0, "claims": 1, "edges": 1}]) is None


def test_trailing_ignores_missing_keys():
    """key 누락(run dict 에 edges 없음 등)도 안전 — 없는 신호는 0 취급."""
    runs = [{"docs": 5, "claims": 2}]
    assert trailing_signal_density(runs) == pytest.approx(2 / 5)


# --- freshness_lag (04 §5 — 최신 수집 vs 기대 주기 지연) ---------------------


def test_freshness_lag_ok():
    """last_collect 90초 전, 기대 주기 300초 → lag 90, overdue False."""
    r = freshness_lag(now_ts=1000, last_collect_ts=910, expected_interval_sec=300)
    assert r["lag_sec"] == 90
    assert r["overdue"] is False


def test_freshness_lag_overdue():
    """지연이 기대 주기 초과 → overdue True."""
    r = freshness_lag(now_ts=1000, last_collect_ts=600, expected_interval_sec=300)
    assert r["lag_sec"] == 400
    assert r["overdue"] is True


def test_freshness_lag_missing_collect_unknown():
    """수집 이력 없음 → lag/overdue None (측정 불가, honest-gap)."""
    r = freshness_lag(now_ts=1000, last_collect_ts=None, expected_interval_sec=300)
    assert r["lag_sec"] is None
    assert r["overdue"] is None


def test_freshness_lag_no_expected_unknown():
    """기대 주기 미지정 → 지연만, overdue 판정 불가(None)."""
    r = freshness_lag(now_ts=1000, last_collect_ts=910, expected_interval_sec=None)
    assert r["lag_sec"] == 90
    assert r["overdue"] is None


def test_freshness_lag_clock_skew_clamped():
    """now < last_collect (시계 역행) → lag 0 클램프 (음수 방지)."""
    r = freshness_lag(now_ts=100, last_collect_ts=910, expected_interval_sec=300)
    assert r["lag_sec"] == 0
    assert r["overdue"] is False


# --- cadence_priority (density → 04 §1.1 schedule.priority) ------------------


def test_cadence_high_for_high_density():
    """고신호 소스 → high 주기 우선순위."""
    assert cadence_priority(3.0) == "high"


def test_cadence_low_for_low_density():
    """저(0)신호 소스 → low (arXiv — 희소, 수집 주기 축소)."""
    assert cadence_priority(0.0) == "low"


def test_cadence_normal_for_mid():
    """중간 density → normal."""
    assert cadence_priority(1.0) == "normal"


def test_cadence_none_is_normal():
    """미측정 → normal (상향도 하향도 하지 않음, 보수적)."""
    assert cadence_priority(None) == "normal"


def test_cadence_custom_thresholds():
    """임계 placeholder 조정 가능 — golden set 실측 튜닝."""
    assert cadence_priority(1.5, high_threshold=1.0) == "high"
    assert cadence_priority(0.5, low_threshold=0.6) == "low"


# --- allocate_signal_budget (주 알고리즘 — density 비례 + floor) -------------


def test_allocate_floor_guaranteed():
    """min_docs 피보장 — 어떤 소스도 floor 밑으로 내려가지 않음(freshness)."""
    sources = [
        {"source_id": "a", "signal_density": 3.0, "min_docs": 10},
        {"source_id": "b", "signal_density": 0.0, "min_docs": 20},
    ]
    alloc = allocate_signal_budget(sources, budget_docs=100)
    assert alloc["a"] >= 10
    assert alloc["b"] >= 20


def test_allocate_density_proportional_surplus():
    """잉여는 density 비례 — 고수율 소스가 더 많은 잉여 획득."""
    sources = [
        {"source_id": "hi", "signal_density": 3.0, "min_docs": 0},
        {"source_id": "lo", "signal_density": 1.0, "min_docs": 0},
    ]
    alloc = allocate_signal_budget(sources, budget_docs=40)
    # weight 비례 → hi : lo = 3:1 → hi 30, lo 10
    assert alloc["hi"] == pytest.approx(30.0, abs=0.01)
    assert alloc["lo"] == pytest.approx(10.0, abs=0.01)


def test_allocate_surplus_after_floors():
    """예산에서 floor 합 제외 후 잉여를 density 비례 배분."""
    sources = [
        {"source_id": "a", "signal_density": 2.0, "min_docs": 10},
        {"source_id": "b", "signal_density": 2.0, "min_docs": 10},
    ]
    alloc = allocate_signal_budget(sources, budget_docs=60)
    # total_floor 20, surplus 40, 1:1 → a = 10+20=30, b=30
    assert alloc["a"] == pytest.approx(30.0)
    assert alloc["b"] == pytest.approx(30.0)


def test_allocate_budget_shrinks_floors_when_scarce():
    """예산이 floor 합보다 작으면 density 무관 floor 비례 축소(전체 보존)."""
    sources = [
        {"source_id": "a", "signal_density": 3.0, "min_docs": 10},
        {"source_id": "b", "signal_density": 1.0, "min_docs": 30},
    ]
    alloc = allocate_signal_budget(sources, budget_docs=20)
    # scale = 20/40 = 0.5 → a=5, b=15
    assert alloc["a"] == pytest.approx(5.0)
    assert alloc["b"] == pytest.approx(15.0)


def test_allocate_measured_get_surplus_unmeasured_only_floor():
    """미측정 소스는 잉여 제외(min 만) — 근거 부재(§6.2)."""
    sources = [
        {"source_id": "measured", "signal_density": 2.0, "min_docs": 0},
        {"source_id": "new", "signal_density": None, "min_docs": 10},
    ]
    alloc = allocate_signal_budget(sources, budget_docs=30)
    assert alloc["new"] == pytest.approx(10.0)          # floor 만
    assert alloc["measured"] == pytest.approx(20.0)      # 잉여 전부


def test_allocate_all_unmeasured_uniform():
    """전 소스 미측정 → 잉여 균등(보수적) — 신호 근거 없으므로 차별 배분 불가."""
    sources = [
        {"source_id": "a", "signal_density": None, "min_docs": 0},
        {"source_id": "b", "signal_density": None, "min_docs": 0},
        {"source_id": "c", "signal_density": None, "min_docs": 0},
    ]
    alloc = allocate_signal_budget(sources, budget_docs=30)
    assert alloc["a"] == pytest.approx(10.0)
    assert alloc["b"] == pytest.approx(10.0)
    assert alloc["c"] == pytest.approx(10.0)


def test_allocate_empty_sources():
    """소스 없음 → {}."""
    assert allocate_signal_budget([], budget_docs=100) == {}


def test_allocate_zero_budget():
    """예산 0 → {} (배분 없음)."""
    sources = [{"source_id": "a", "signal_density": 3.0, "min_docs": 5}]
    assert allocate_signal_budget(sources, budget_docs=0) == {}


def test_allocate_preserves_budget_total():
    """배분 합은 예산을 초과하지 않음(불변식 — 방출 총량 보존)."""
    sources = [
        {"source_id": "a", "signal_density": None, "min_docs": 12},
        {"source_id": "b", "signal_density": None, "min_docs": 18},
    ]
    alloc = allocate_signal_budget(sources, budget_docs=100)
    assert sum(alloc.values()) <= 100.0


def test_allocate_negative_density_guarded():
    """음수 density → 가드(0 취급) — 잉여 미득점, floor 만."""
    sources = [
        {"source_id": "a", "signal_density": -5.0, "min_docs": 0},
        {"source_id": "b", "signal_density": 1.0, "min_docs": 0},
    ]
    alloc = allocate_signal_budget(sources, budget_docs=20)
    assert alloc["a"] == pytest.approx(0.0)
    assert alloc["b"] == pytest.approx(20.0)


def test_allocate_deterministic():
    """동일 입력 → 동일 배분 (결정성)."""
    sources = [
        {"source_id": "a", "signal_density": 3.0, "min_docs": 2},
        {"source_id": "b", "signal_density": 1.0, "min_docs": 0},
    ]
    assert allocate_signal_budget(sources, 50) == allocate_signal_budget(sources, 50)


# --- adaptive_schedule (오케스트레이션 — 히스토리 → 배분 + lag) ----------------
# --- (collected_at / expected_interval 기준 freshness 부착)                    # noqa: E266


def test_adaptive_schedule_high_density_gets_more():
    """히스토리 기반 — arXiv(press) 대비 고수율 소스가 더 큰 배분 + high 주기."""
    runs = {
        "press": [{"docs": 10, "claims": 8, "edges": 8, "collected_at": 900}],
        "arxiv": [{"docs": 100, "claims": 1, "edges": 0, "collected_at": 900}],
    }
    sched = adaptive_schedule(
        source_runs=runs,
        budget_docs=60,
        now_ts=1000,
        expected_intervals={"press": 300, "arxiv": 300},
        last_collect_ts={"press": 900, "arxiv": 900},
    )
    # press density 1.6, arxiv 0.01 → press 우세
    assert sched["press"]["allocated_docs"] > sched["arxiv"]["allocated_docs"]
    assert sched["press"]["signal_density"] == pytest.approx(1.6)
    assert sched["arxiv"]["signal_density"] == pytest.approx(0.01)


def test_adaptive_schedule_unknown_collect_is_none():
    """수집 이력 없는 소스 → lag/overdue None (측정 불가)."""
    runs = {"a": [{"docs": 5, "claims": 2, "edges": 0}]}
    sched = adaptive_schedule(
        source_runs=runs,
        budget_docs=10,
        now_ts=1000,
        expected_intervals={"a": 300},
        last_collect_ts={},  # 미수집
    )
    assert sched["a"]["lag_sec"] is None
    assert sched["a"]["overdue"] is None


def test_adaptive_schedule_overdue_source_flagged():
    """freshness 지연 소스는 overdue 표기 — floor 로도 멸종 방지됨."""
    runs = {"a": [{"docs": 5, "claims": 2, "edges": 0}]}
    sched = adaptive_schedule(
        source_runs=runs,
        budget_docs=10,
        now_ts=1000,
        expected_intervals={"a": 50},
        last_collect_ts={"a": 800},  # 200초 전 → 기대 50초 초과
    )
    assert sched["a"]["overdue"] is True


def test_adaptive_schedule_default_floor_liveness():
    """오케스트레이터 기본 floor=1.0 — 밀집도 0 소스도 1 문서 받아 liveness 유지."""
    runs = {"zero": [{"docs": 10, "claims": 0, "edges": 0}], "hi": [{"docs": 4, "claims": 8, "edges": 8}]}
    sched = adaptive_schedule(
        source_runs=runs,
        budget_docs=10,
        now_ts=1000,
        expected_intervals={},
        last_collect_ts={},
    )
    assert sched["zero"]["allocated_docs"] >= 1.0


def test_adaptive_schedule_all_unmeasured_uniform():
    """미측정 소스들 → 잉여 균등 (보수적), floor 기본 적용."""
    runs = {"a": [], "b": []}  # 이력 없음 → density None
    sched = adaptive_schedule(
        source_runs=runs,
        budget_docs=10,
        now_ts=1000,
        expected_intervals={},
        last_collect_ts={},
    )
    assert sched["a"]["allocated_docs"] == pytest.approx(sched["b"]["allocated_docs"])


def test_adaptive_schedule_deterministic():
    """동일 입력 → 동일 스케줄 (결정성)."""
    runs = {"a": [{"docs": 5, "claims": 2, "edges": 0}]}
    kwargs = dict(budget_docs=10, now_ts=1000, expected_intervals={"a": 300},
                  last_collect_ts={"a": 900})
    assert adaptive_schedule(runs, **kwargs) == adaptive_schedule(runs, **kwargs)


def test_read_only_no_mutation():
    """signal_scheduler 모듈은 read-only — 쓰기·mutation 미노출 (불변식 §3-3).

    스케줄은 산출물일 뿐 — 실제 수집 실행·큐 기록은 호출자 몫.
    """
    from orc_citadel import signal_scheduler as sched

    for bad in ("apply", "persist", "create_node", "create_edge", "insert",
                "write", "upsert"):
        assert not hasattr(sched, bad), f"read-only 위반: {bad} 노출"
