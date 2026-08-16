"""SLO-01 측정 하니스 — 신규 문서 → graph 반영 지연 p95 (design 11 §2.3, 10 §1.4).

SLO-01 (11 §2.3): 신규 문서가 수집된 시점부터 graph 에 반영되는 시점까지 지연의 p95,
목표 `≤ 30 min` (deferred → 실측 후 확정). 측정 공식 (10 §1.4):
    `graph_commit_ts − fetched_ts` (p95)

**정직한 측정 모델 (honest-gap §6.2, 단일 프로세스 일괄 처리):**
  - `fetched_ts` = 원문 meta 의 `fetched_at` (collect_sample 에서 수집 시점 기록).
  - `graph_commit_ts` = 그래프 재구축(반영) 시점.
  - 단일 프로세스 일괄 처리에선 문서가 수집 직후 곧바로 그래프 반영되어 **"배치 내 반영
    지연"은 사실상 수집-처리 사이클 길이에 의존**한다. 실제 운영 반영 지연은 **배치
    간격(스케줄링)** 이 결정한다. 따라서 측정을 두 축으로 분리한다:
      (a) `measure_batch_reflection` — 배치 내 실제 벽시계
      (b) `measure_batch_interval_latency` — 배치 간격 시나리오 (운영 스케줄러 반영 지연)
    두 축을 구분해 과대 주장을 피한다 (단일 수치로 합치지 않음).

p95 결정법은 `neo4j_q4_harness.measure_query_latency` 와 동일한 **정렬 인덱스**
`int(0.95*(len-1))` 을 재사용한다. 판정 게이트는 `compute_graph_slo`(GRAPH_SLO_MS=60s,
10 §1.4 DoD ②) 와 **별개** — 이 하니스는 SLO-01 의 30 min 목표 판정을 전담한다.

시간 원천(clock)은 주입 가능 — 결정적·mock/실측 격리. read-only(불변식 §3-3).
"""
from __future__ import annotations

from datetime import datetime, timezone
import time as _time

# 11 §2.3 — SLO-01 목표 p95 반영 지연 30 분 (deferred → 실측 후 확정).
SLO01_TARGET_MS = 30 * 60 * 1000

# 10 §1.4 — 성능 SLO 판정 분류: slo-gate(nightly 비차단)·not-measured(honest-gap).
NOT_MEASURED = "not-measured"
SLO_GATE = "slo-gate"
OK = "ok"


def _epoch_ms(dt: datetime | None) -> float | None:
    """datetime → epoch ms. None → None (honest-gap §6.2)."""
    if dt is None:
        return None
    return dt.timestamp() * 1000.0


def compute_fetch_timestamps(metas: list[dict], parse=None) -> dict[str, float | None]:
    """각 문서의 `fetched_at` 를 epoch ms 로 정규화 ({doc_id: ms}).

    `parse` 는 ISO 문자열 → datetime 변환기(주입 가능, 결정성·테스트). 기본은
    `datetime.fromisoformat`. `fetched_at` 부재 또는 비파싱 → `None` (honest-gap
    §6.2 — 측정값이 없는 문서는 지연 분포에 포함하지 않되, 존재는 그래프에 노출).
    read-only·결정적.
    """
    if parse is None:
        def parse(s):  # type: ignore[misc]
            return datetime.fromisoformat(s)
    out: dict[str, float | None] = {}
    for meta in metas:
        doc_id = meta.get("doc_id")
        if doc_id is None:
            continue
        raw = meta.get("fetched_at")
        try:
            dt = parse(raw) if raw else None
        except Exception:
            dt = None
        out[doc_id] = _epoch_ms(dt)
    return out


def measure_batch_reflection(metas, commit_fn, clock=None, default_ts=None) -> dict:
    """(a) 배치 내 실제 벽시계 반영 지연 분포 (design 11 §2.3 측정 공식).

    각 문서의 `fetched_at`(epoch ms) 부터 `commit_fn(doc_id)` 가 그래프를 반영하는
    시각까지 지연(ms)을 **epoch ms 축**에서 측정한다. `clock()` 은 **epoch ms** 의
    현재 시각을 반환해야 한다 (기본 `time.time()*1000`). `commit_fn` 은 해당 문서의
    수집→반영 경로 단위 비용 (주입 — mock/실측 격리).

    `fetched_at` 가 없는 문서는 `clock()` 대신 `default_ts`(epoch) 를 수집 시각으로
    쓰고 `n_no_timestamp` 로 노출(honest-gap §6.2 — 측정값 부재를 숨기지 않음).

    반환: {latencies_ms, n, n_no_timestamp, p95_ms}. p95 는 정렬 인덱스 결정법
    (neo4j_q4_harness 와 동일). read-only·결정적(동일 clock/commit_fn).
    """
    if clock is None:
        clock = lambda: _time.time() * 1000.0
    lat = []
    no_ts = 0
    for meta in metas:
        doc_id = meta.get("doc_id")
        raw = meta.get("fetched_at")
        if doc_id is None:
            continue
        try:
            t0 = _epoch_ms(datetime.fromisoformat(raw)) if raw else None
        except Exception:
            t0 = None
        if t0 is None:
            if default_ts is None:
                no_ts += 1
                continue
            t0 = default_ts
        # 그래프 반영 시각(epoch ms) = 수집 직후 해당 문서 반영 완료 시각.
        commit_fn(doc_id)
        t1 = clock()
        lat.append(t1 - t0)
    return {"latencies_ms": lat, "n": len(lat), "n_no_timestamp": no_ts,
            "p95_ms": _p95(lat)}


def measure_batch_interval_latency(batch_times: list[float], interval_ms: float) -> dict:
    """(b) 배치 간격 시나리오 — 운영 스케줄러의 반영 지연 분포.

    `batch_times` = 각 문서의 `fetched_at`(epoch ms, 연속 운용 스케줄러 기준 상대
    시각). 운영 루프가 `interval_ms` 마다 그래프를 커밋·반영한다고 모델링 — 문서는
    그 다음 커밋 경계(`ceil(t/interval)*interval`)에 반영되므로 반영 지연은
    `ceil(t/interval_ms)*interval_ms − t`. 스케줄러가 이미 운용 중이라 항상 다음
    커밋이 존재하는 연속 모델 (간격이 클수록 지연이 커짐 — 운영 스케줄링의 지배 인자).

    반환: {latencies_ms, n, p95_ms}. 결정적(순수 함수 — 시간 원천 불요, epoch 는
    상대 배치 시각으로 모델링)·read-only.
    """
    if interval_ms <= 0:
        return {"latencies_ms": [], "n": 0, "p95_ms": None}
    lat = []
    for t in batch_times:
        n_commits = max(1, int(t / interval_ms) + (1 if t % interval_ms else 0))
        commit_ts = interval_ms * n_commits
        lat.append(commit_ts - t)
    return {"latencies_ms": lat, "n": len(lat), "p95_ms": _p95(lat)}


def slo01_p95(latencies: list[float]) -> float | None:
    """p95 정렬 인덱스 결정법 (neo4j_q4_harness.measure_query_latency 와 동일).

    순수 함수 — read-only·결정적. 빈/None 입력 → None (honest-gap §6.2).
    """
    return _p95(latencies)


def _p95(lat: list[float]) -> float | None:
    if not lat:
        return None
    s = sorted(lat)
    idx = int(0.95 * (len(s) - 1))
    return round(float(s[idx]), 3)


def evaluate_slo01(p95_ms: float | None) -> dict:
    """SLO-01 판정 게이트 (11 §2.3, 10 §1.4 slo-gate·CI 비차단).

    `p95_ms` < `SLO01_TARGET_MS`(30 min) → `classified="ok"`. 이상 → `classified=
    "slo-gate"` (CI 차단 없이 nightly 경보, 10 §1.4). None(미측정) →
    `classified="not-measured"` + `within_slo=False` — honest-gap (§6.2: 부재가
    OK 가 아니다). read-only·결정적.
    """
    if p95_ms is None:
        return {"within_slo": False, "classified": NOT_MEASURED,
                "target_ms": int(SLO01_TARGET_MS)}
    within = p95_ms < SLO01_TARGET_MS
    return {"within_slo": within,
            "classified": OK if within else SLO_GATE,
            "target_ms": int(SLO01_TARGET_MS), "p95_ms": p95_ms}
