"""SLO-01 측정 하니스 — 신규 문서 → graph 반영 지연 p95 (design 11 §2.3, 10 §1.4) TDD.

Phase 6(Stable 운용) 첫 실측 작업 — deferred SLO-01 의 **측정 계약·하니스 봉인**.
단일 프로세스 일괄 처리의 정직한 한계를 반영한 두 축 측정 모델:

- (a) `measure_batch_reflection` — 배치 내 **실제 벽시계** 반영 지연 (fetched_at →
  그래프 반영 완료; 주입 clock·commit_fn 으로 결정적).
- (b) `measure_batch_interval_latency` — **배치 간격 시나리오** (운영 스케줄러가
  interval 마다 커밋 → `ceil(t/inter)*inter − t`).

p95 는 `neo4j_q4_harness` 와 동일한 정렬 인덱스 결정법. 판정은 SLO-01 30 min 목표
(`SLO01_TARGET_MS`)로 — `compute_graph_slo`(60s, DoD②)와 별개 게이트.

read-only(불변식 §3-3)·결정성·honest-gap(§6.2) 원칙 (Phase 6 전 작업과 동일).
"""
from __future__ import annotations

from orc_citadel.reflection_slo_harness import (
    NOT_MEASURED,
    OK,
    SLO01_TARGET_MS,
    SLO_GATE,
    compute_fetch_timestamps,
    evaluate_slo01,
    measure_batch_interval_latency,
    measure_batch_reflection,
    slo01_p95,
)

# --- compute_fetch_timestamps: fetched_at 정규화 (read-only) -----------------------


def _meta(doc_id: str, fetched_at: str | None = "2026-08-11T00:00:00+00:00") -> dict:
    return {"doc_id": doc_id, "fetched_at": fetched_at}


def test_fetch_timestamps_parses_iso():
    """ISO fetched_at → epoch ms 정규화 (collect_sample 기록 형식)."""
    out = compute_fetch_timestamps([_meta("d1")])
    assert "d1" in out and out["d1"] is not None and out["d1"] > 0


def test_fetch_timestamps_missing_is_none():
    """fetched_at 부재/비파싱 → None (honest-gap: 측정값 없는 문서는 분포 제외 대상)."""
    out = compute_fetch_timestamps([_meta("d1", None), _meta("bad", "not-a-date")])
    assert out["d1"] is None and out["bad"] is None


def test_fetch_timestamps_no_doc_id_skipped():
    """doc_id 부재 문서는 결과에서 제외 (식별 불가 — 분포 오염 방지)."""
    out = compute_fetch_timestamps([{"fetched_at": "2026-08-11T00:00:00+00:00"}])
    assert out == {}


def test_fetch_timestamps_deterministic():
    """동일 입력 → 동일 epoch (결정적)."""
    metas = [_meta("d1"), _meta("d2")]
    assert compute_fetch_timestamps(metas) == compute_fetch_timestamps(metas)


# --- measure_batch_reflection: (a) 배치 내 실제 벽시계 -----------------------------


def test_batch_reflection_latency_computed():
    """반영 지연 = 그래프 반영 시각 − fetched_at (epoch 축, 주입 clock)."""
    metas = [_meta("d1", "2026-08-11T00:00:00+00:00")]
    # fetched_at epoch + 5s 가 현재 시각 → 지연 5000ms.
    base = compute_fetch_timestamps(metas)["d1"]

    def clock():
        return base + 5000.0  # epoch ms

    res = measure_batch_reflection(metas, commit_fn=lambda _id: None,
                                   clock=clock)
    assert res["n"] == 1
    assert abs(res["latencies_ms"][0] - 5000.0) < 1e-3


def test_batch_reflection_commit_fn_called():
    """commit_fn 이 각 문서에 대해 호출 (수집→반영 경로 단위 비용 주입 지점)."""
    calls = []

    def commit(doc_id):
        calls.append(doc_id)

    metas = [_meta("d1"), _meta("d2")]
    base = compute_fetch_timestamps(metas)["d1"]

    def clock():  # 시각 흐름 — 각 문서 반영 완료 시각이 수집 시각보다 큼
        return base + 1000.0 + len(calls) * 1.0

    measure_batch_reflection(metas, commit_fn=commit, clock=clock)
    assert calls == ["d1", "d2"]


def test_batch_reflection_no_timestamp_reported():
    """fetched_at 부재 문서 → n_no_timestamp 로 노출 (honest-gap, 숨기지 않음)."""
    metas = [_meta("d1", None), _meta("d2")]
    base = compute_fetch_timestamps([_meta("d2")])["d2"]
    commit_fn = lambda _id: None
    clock = lambda: base + 1000.0
    res = measure_batch_reflection(metas, commit_fn=commit_fn, clock=clock)
    assert res["n_no_timestamp"] == 1
    assert res["n"] == 1  # 식별·측정 가능 문서만 분포에


def test_batch_reflection_read_only():
    """입력 metas 를 변경하지 않음 (read-only 불변식 §3-3)."""
    metas = [_meta("d1"), _meta("d2")]
    snapshot = [dict(m) for m in metas]
    base = compute_fetch_timestamps(metas)["d1"]
    clock = lambda: base + 1000.0
    measure_batch_reflection(metas, commit_fn=lambda _id: None, clock=clock)
    assert metas == snapshot


def test_batch_reflection_deterministic():
    """동일 clock·commit_fn → 동일 분포 (결정적)."""
    metas = [_meta("d1"), _meta("d2")]
    base = compute_fetch_timestamps(metas)["d1"]

    def clock():
        return base + 2000.0

    a = measure_batch_reflection(metas, commit_fn=lambda _id: None, clock=clock)
    b = measure_batch_reflection(metas, commit_fn=lambda _id: None, clock=clock)
    assert a["latencies_ms"] == b["latencies_ms"]
    assert a["p95_ms"] == b["p95_ms"]


# --- measure_batch_interval_latency: (b) 배치 간격 시나리오 ------------------------


def test_interval_latency_next_commit_boundary():
    """반영 지연 = 다음 커밋 경계 − 수집 시각 (interval 10000ms)."""
    # t=1s → 다음 커밋 10s → 지연 9000ms; t=9.5s → 10s → 500ms.
    res = measure_batch_interval_latency([1000.0, 9500.0], interval_ms=10000.0)
    assert res["n"] == 2
    assert res["latencies_ms"] == [9000.0, 500.0]


def test_interval_latency_exact_boundary():
    """수집이 정확히 커밋 경계 → 지연 0 (지연 없이 즉시 반영)."""
    res = measure_batch_interval_latency([10000.0], interval_ms=10000.0)
    assert res["latencies_ms"] == [0.0]


def test_interval_latency_larger_interval_bigger_lag():
    """간격이 클수록 지연 증가 (운영 스케줄링의 지배 인자)."""
    t = [5000.0]
    small = measure_batch_interval_latency(t, interval_ms=10000.0)
    big = measure_batch_interval_latency(t, interval_ms=60000.0)
    assert big["latencies_ms"][0] > small["latencies_ms"][0]


def test_interval_latency_empty():
    """빈 입력 → n=0·p95=None (honest-gap §6.2)."""
    res = measure_batch_interval_latency([], interval_ms=10000.0)
    assert res["n"] == 0 and res["p95_ms"] is None


def test_interval_latency_nonpositive_interval():
    """비정상 interval(≤0) → 빈 분포 (측정 불가 명시)."""
    res = measure_batch_interval_latency([1000.0], interval_ms=0.0)
    assert res["n"] == 0 and res["p95_ms"] is None


# --- slo01_p95: p95 정렬 인덱스 결정법 (neo4j_q4_harness 와 동일) -------------------


def test_p95_uses_sorted_index():
    """p95 = 0.95 정렬 인덱스 (기존 결정법 재사용)."""
    # len=5 → idx=int(0.95*4)=3 → sorted[3]=4.0 (neo4j_q4_harness 결정법).
    assert slo01_p95([1.0, 2.0, 3.0, 4.0, 5.0]) == 4.0


def test_p95_empty_is_none():
    """빈 분포 → None (honest-gap)."""
    assert slo01_p95([]) is None


def test_p95_deterministic():
    """동일 입력 → 동일 p95 (결정적)."""
    lat = [10.0, 20.0, 30.0, 40.0]
    assert slo01_p95(lat) == slo01_p95(lat)


# --- evaluate_slo01: 판정 게이트 (11 §2.3, 10 §1.4 slo-gate 비차단) -----------------


def test_evaluate_slo01_ok():
    """p95 < 30 min → within_slo + classified=ok."""
    res = evaluate_slo01(p95_ms=SLO01_TARGET_MS - 1)
    assert res["within_slo"] is True and res["classified"] == OK
    assert res["target_ms"] == SLO01_TARGET_MS


def test_evaluate_slo01_violated_slo_gate():
    """p95 ≥ 30 min → slo-gate (CI 차단 없이 nightly 경보, 10 §1.4)."""
    res = evaluate_slo01(p95_ms=SLO01_TARGET_MS + 1)
    assert res["within_slo"] is False and res["classified"] == SLO_GATE


def test_evaluate_slo01_not_measured():
    """p95=None → not-measured + within_slo=False (honest-gap: 부재가 OK 아님)."""
    res = evaluate_slo01(p95_ms=None)
    assert res["within_slo"] is False and res["classified"] == NOT_MEASURED


def test_evaluate_slo01_deterministic():
    """동일 p95 → 동일 판정 (결정적)."""
    assert evaluate_slo01(SLO01_TARGET_MS - 1) == evaluate_slo01(SLO01_TARGET_MS - 1)
