"""hot/cold graph 분리 — 접근 온도 기반 계층 분리·조회 라우팅 (06 §8·ADR-603·Q4 게이트, Phase 5) TDD.

Phase 5 「hot/cold graph 분리」 — 10M Challenge 그래프 확장에서, **접근 온도(최근성)**로
그래프를 hot(빠른 상주)·cold(아카이브) 계층으로 분리해 hot 예산을 유지한다
(design 06 ADR-603 — 초기 논리 라벨 분리, 확장 시 물리 분리; Q4 게이트 — 노드 ≥ 1e6
시 교체/분리 트리거).

- `temperature` — 접근 최근성 → hot/cold. 미접근(None) → `None`(미측정, honest-gap §6.2 — 미접근 ≠ cold).
- `partition_tiers` — access_stats 를 hot/cold/unknown 으로 분할 (결정적 사전순).
- `tier_map` — unknown 을 보수적 기본(cold)으로 — **측정(unknown)과 할당(default) 구분**.
- `hot_resident_count` — hot 상주 수 (hot 예산).
- `cold_archive_decision` — Q4 노드 게이트 초과 시 cold 아카이브 (ADR-603 물리 분리).
- `route_query` — tier 별 조회 라우팅: hot → 빠른 상주, cold → 아카이브(느림, honest),
  None → not-measured. SLO 게이트(§1.4 slo-gate·CI 비차단).
- `mark_accessed` — read-only 스타일: 새 stats dict 반환(입력 불변), 승격은 호출자 몫(§3-3).

접근 stats 신호는 호출자(수집/조회 이벤트)가 주입 — 결정성은 순수 에뮬레이션 (mock/실측 격리).
"""
from __future__ import annotations

import pytest

from orc_citadel.graph_temperature import (
    NODE_GATE,
    cold_archive_decision,
    hot_resident_count,
    mark_accessed,
    partition_tiers,
    route_query,
    temperature,
    tier_map,
)


# --- temperature (접근 최근성 → hot/cold, 미접근 None) ------------------------


def test_temperature_recent_is_hot():
    """최근 접근(핫 윈도우 내) → hot."""
    assert temperature(last_access_ts=950, now_ts=1000, hot_window_sec=100) == "hot"


def test_temperature_stale_is_cold():
    """접근했으나 오래됨(윈도우 밖) → cold."""
    assert temperature(last_access_ts=800, now_ts=1000, hot_window_sec=100) == "cold"


def test_temperature_boundary_inclusive():
    """정확히 윈도우 경계(≤) → hot."""
    assert temperature(last_access_ts=900, now_ts=1000, hot_window_sec=100) == "hot"


def test_temperature_never_accessed_none():
    """미접근(None) → None (미측정 — honest-gap, 미접근을 cold 로 오판하지 않음)."""
    assert temperature(last_access_ts=None, now_ts=1000, hot_window_sec=100) is None


def test_temperature_deterministic():
    """동일 입력 → 동일 온도 (결정성)."""
    assert (temperature(950, 1000, 100) == temperature(950, 1000, 100))


# --- partition_tiers (stats → hot/cold/unknown 분할) ------------------------


def _stats(**kw):
    """편의 — access_stats dict 생성. 기본: {last_access_ts, access_count}."""
    return {k: {"last_access_ts": v.get("last_access_ts"),
                "access_count": v.get("access_count", 0)} for k, v in kw.items()}


def test_partition_separates_tiers():
    """hot/cold/unknown 이 각각 분할된다."""
    stats = _stats(
        a={"last_access_ts": 990},   # hot (1000-100 window 내)
        b={"last_access_ts": 800},   # cold
        c={"last_access_ts": None},  # unknown
    )
    part = partition_tiers(stats, now_ts=1000, hot_window_sec=100)
    assert part["hot"] == ["a"]
    assert part["cold"] == ["b"]
    assert part["unknown"] == ["c"]


def test_partition_empty():
    """빈 stats → 전 계층 빈 리스트."""
    part = partition_tiers({}, now_ts=1000, hot_window_sec=100)
    assert part == {"hot": [], "cold": [], "unknown": []}


def test_partition_deterministic_order():
    """동일 stats → 동일 분할·정렬 (결정성)."""
    stats = _stats(a={"last_access_ts": 990}, b={"last_access_ts": 980})
    assert partition_tiers(stats, 1000, 100) == partition_tiers(stats, 1000, 100)


# --- tier_map (unknown → 보수적 기본) ----------------------------------------


def test_tier_map_assigns_hot_cold():
    """hot/cold 는 그대로, unknown 은 기본(default cold)으로."""
    stats = _stats(a={"last_access_ts": 990}, b={"last_access_ts": 800},
                   c={"last_access_ts": None})
    tm = tier_map(stats, now_ts=1000, hot_window_sec=100)
    assert tm["a"] == "hot"
    assert tm["b"] == "cold"
    assert tm["c"] == "cold"  # unknown → 기본 cold (보수적 hot 예산)


def test_tier_map_default_can_be_overridden():
    """기본값 매개변수로 변경 가능 (기본 hot 예산 보수적 유지)."""
    stats = _stats(c={"last_access_ts": None})
    tm = tier_map(stats, 1000, 100, default="hot")
    assert tm["c"] == "hot"


def test_tier_map_empty():
    """빈 stats → 빈 map."""
    assert tier_map({}, 1000, 100) == {}


# --- hot_resident_count ------------------------------------------------------


def test_hot_resident_counts_hot():
    """hot 요소 수 = hot 상주 수."""
    stats = _stats(a={"last_access_ts": 990}, b={"last_access_ts": 800},
                   c={"last_access_ts": None})
    assert hot_resident_count(stats, 1000, 100) == 1


def test_hot_resident_empty():
    """빈 stats → 0."""
    assert hot_resident_count({}, 1000, 100) == 0


# --- cold_archive_decision (Q4 노드 게이트 → 아카이브) -----------------------


def test_archive_below_gate_not_needed():
    """노드 수 < 게이트 → 아카이브 불필요 (교체/분리 트리거 없음)."""
    d = cold_archive_decision(node_count=100_000, hot_resident=100_000)
    assert d["exceeds_gate"] is False
    assert d["archive_needed"] is False


def test_archive_at_gate_needed():
    """노드 수 ≥ 게이트(1e6) → cold 아카이브 필요 (Q4 게이트 정합, ADR-603 분리)."""
    d = cold_archive_decision(node_count=NODE_GATE, hot_resident=200_000)
    assert d["exceeds_gate"] is True
    assert d["archive_needed"] is True
    assert d["cold_archived"] == NODE_GATE - 200_000


def test_archive_preserves_hot_resident():
    """hot 상주 수는 보존, cold 만 아카이브."""
    d = cold_archive_decision(node_count=2_000_000, hot_resident=300_000)
    assert d["hot_resident"] == 300_000
    assert d["cold_archived"] == 2_000_000 - 300_000


def test_archive_cold_ratio():
    """cold 비율 = cold 아카이브 / 전체 (온도 효율 지표)."""
    d = cold_archive_decision(node_count=2_000_000, hot_resident=500_000)
    assert d["cold_ratio"] == pytest.approx(0.75)


def test_archive_never_negative_cold():
    """hot_resident 가 전체보다 크면 cold 아카이브 0 클램프 (가드)."""
    d = cold_archive_decision(node_count=100, hot_resident=500)
    assert d["cold_archived"] == 0
    assert d["cold_ratio"] == 0.0


def test_archive_deterministic():
    """동일 입력 → 동일 결정 (결정성)."""
    assert (cold_archive_decision(2_000_000, 300_000)
            == cold_archive_decision(2_000_000, 300_000))


# --- route_query (tier 별 조회 라우팅 + SLO 게이트) --------------------------


def test_route_hot_fast():
    """hot 경로 → 상주에서 빠르게, SLO ok."""
    r = route_query("hot", hot_latency_ms=2.0, cold_latency_ms=200.0, slo_ms=50.0)
    assert r["tier"] == "hot"
    assert r["served_from"] == "hot"
    assert r["latency_ms"] == 2.0
    assert r["classified"] == "ok"


def test_route_cold_archive_slower():
    """cold 경로 → 아카이브(느림) 정직 노출."""
    r = route_query("cold", hot_latency_ms=2.0, cold_latency_ms=200.0, slo_ms=50.0)
    assert r["served_from"] == "cold"
    assert r["latency_ms"] == 200.0


def test_route_unknown_not_measured():
    """unknown → not-measured (honest-gap — 미측정을 hot/cold 로 오판하지 않음)."""
    r = route_query(None, hot_latency_ms=2.0, cold_latency_ms=200.0, slo_ms=50.0)
    assert r["served_from"] == "unknown"
    assert r["classified"] == "not-measured"


def test_route_cold_slo_violated():
    """cold 지연이 SLO 초과 → slo-gate 위반 (비차단, §1.4)."""
    r = route_query("cold", hot_latency_ms=2.0, cold_latency_ms=400.0, slo_ms=50.0)
    assert r["classified"] == "slo-gate"
    assert r["violated"] is True


def test_route_deterministic():
    """동일 입력 → 동일 라우팅 (결정성)."""
    kw = dict(hot_latency_ms=2.0, cold_latency_ms=200.0, slo_ms=50.0)
    assert route_query("hot", **kw) == route_query("hot", **kw)


# --- mark_accessed (read-only 스타일 승격 — 새 dict 반환, 입력 불변) ----------


def test_mark_accessed_promotes_to_hot():
    """cold/unknown 요소 접근 → 새 stats 에서 hot 으로 (입력 불변, 승격)."""
    stats = _stats(a={"last_access_ts": 800})  # cold
    new = mark_accessed(stats, "a", now_ts=990)
    assert stats["a"]["last_access_ts"] == 800  # 입력 불변 (read-only)
    assert new["a"]["last_access_ts"] == 990
    assert temperature(new["a"]["last_access_ts"], now_ts=1000, hot_window_sec=100) == "hot"


def test_mark_accessed_returns_new_dict():
    """반환은 새 dict — 원본과 분리 (불변식, 승격은 호출자 적용)."""
    stats = _stats(a={"last_access_ts": 950})
    new = mark_accessed(stats, "a", now_ts=990)
    assert new is not stats
    assert new["a"]["access_count"] == stats["a"]["access_count"] + 1


def test_mark_accessed_unknown_element():
    """미등록 요소 접근 → 새 항목 생성 (최초 접근, access_count 1)."""
    new = mark_accessed({}, "x", now_ts=990)
    assert new["x"]["last_access_ts"] == 990
    assert new["x"]["access_count"] == 1


def test_read_only_no_mutation():
    """graph_temperature 모듈은 read-only — 쓰기·mutation 미노출 (불변식 §3-3)."""
    from orc_citadel import graph_temperature as gt

    for bad in ("apply", "persist", "create_node", "create_edge", "insert",
                "write", "upsert"):
        assert not hasattr(gt, bad), f"read-only 위반: {bad} 노출"
