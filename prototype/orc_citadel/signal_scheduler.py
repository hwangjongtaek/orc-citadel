"""signal source adaptive scheduling — 신호 수율 기반 수집 예산 배분 (design 04 §1·§5, 01 §6, Phase 5).

Phase 5 「signal source adaptive scheduling」 — 10M Challenge 수집 병목에서, 소스별
**신호 수율(문서당 claims+edges)** 을 측정해 제한된 수집 예산(budget_docs) 을
**고수율 소스에 우선 배분**하되, 각 소스에 **freshness floor(min_docs)** 를 보장한다
(04 §5 freshness — 어느 소스도 멸종하지 않음).

수율 근거: `signal_source_runner` 메모리 확증 — arXiv abstract 는 신호 희소(edges=0) 인
반면 전용 반도체/공급망 언론 본문은 신호 고밀도. adaptive scheduling 은 이 **신호 수율
차이를 정량화**해 수집 주기(04 §1.1 `schedule.priority`)·예산 배분에 반영한다.

원칙 (Phase 4/5 전 작업과 동일):
- **결정적** — 수율·배분이 순수 입력 함수 (동일 입력 → 동일 산출).
- **read-only** (불변식 §3-3) — 스케줄은 산출물일 뿐, 실제 수집 실행·큐 기록은 호출자 몫.
- **mock/실측 격리** — 신호 counts 는 호출자(수집 이력)가 주입, 결정성은 에뮬레이션으로 봉인.
- **honest-gap** (§6.2) — 미측정 소스는 잉여 경쟁 제외(min 만 유지), 전 소스 미측정은
  균등 배분(보수적) — 신호 근거 부재를 "0 신호" 로 오판하지 않는다.
"""
from __future__ import annotations

# design 04 §5 — freshness 근거 없는 소스까지 지탱하는 기본 배분 (없으면 liveness 붕괴).
DEFAULT_MIN_DOCS = 1.0

# design 04 §1.1 schedule.priority — 수율에 따른 수집 주기 우선순위 placeholder.
HIGH_DENSITY_THRESHOLD = 2.0   # density ≥ 2 → high (고신호, 빈번 수집)
LOW_DENSITY_THRESHOLD = 0.2    # density < 0.2 → low (희소, 수집 주기 축소)


def signal_density(docs: int, claims: int, edges: int) -> float | None:
    """소스 신호 수율 = (claims+edges) / docs (문서당 신호 생성량).

    `docs == 0` → None (측정 불가 — honest-gap §6.2: 미측정을 0 신호로 오판하지 않음).
    """
    if docs <= 0:
        return None
    return (claims + edges) / docs


def trailing_signal_density(runs: list[dict]) -> float | None:
    """과거 수집 run 들의 누적 신호 수율 = Σ(신호) / Σ(docs) (문서 수 가중).

    - `runs`: `[{docs, claims, edges}, ...]` (역순·무관 — 합산/총합만 사용).
    - key 누락은 0 취급 (없는 신호). **분자 0 vs 미측정** 구분: 총 docs > 0 이면
      실제 신호 0 (반환 0.0), 총 docs == 0 이면 None (측정 불가).
    """
    total_docs = sum(r.get("docs", 0) for r in runs)
    if total_docs <= 0:
        return None
    signal = sum(r.get("claims", 0) + r.get("edges", 0) for r in runs)
    return signal / total_docs


def freshness_lag(now_ts: float, last_collect_ts: float | None,
                  expected_interval_sec: float | None) -> dict:
    """04 §5 freshness 지연 = `now - last_collect` vs 기대 주기.

    반환 `{lag_sec, overdue}`:
    - `last_collect_ts` None (수집 이력 없음) → 둘 다 None (측정 불가, honest-gap).
    - `expected_interval_sec` None → `lag_sec` 만, `overdue` None (기대 주기 미지정).
    - `lag_sec` = `now - last_collect`, 음수(시계 역행) → 0 클램프.
    - `overdue` = `lag_sec > expected_interval_sec`.
    """
    if last_collect_ts is None:
        return {"lag_sec": None, "overdue": None}
    lag = max(0.0, now_ts - last_collect_ts)
    if expected_interval_sec is None:
        return {"lag_sec": round(lag, 3), "overdue": None}
    return {"lag_sec": round(lag, 3), "overdue": lag > expected_interval_sec}


def cadence_priority(density: float | None,
                     high_threshold: float = HIGH_DENSITY_THRESHOLD,
                     low_threshold: float = LOW_DENSITY_THRESHOLD) -> str:
    """수율 density → 04 §1.1 `schedule.priority` (high/normal/low).

    - density ≥ high → "high" (빈번 수집), density < low → "low" (주기 축소).
    - `None` (미측정) → "normal" (상향도 하향도 하지 않음, 보수적).

    임계는 placeholder — golden set 실측으로 조정(04 §1.1 정합).
    """
    if density is None:
        return "normal"
    if density >= high_threshold:
        return "high"
    if density < low_threshold:
        return "low"
    return "normal"


def allocate_signal_budget(sources: list[dict], budget_docs: float) -> dict:
    """`budget_docs` 를 소스별로 배분 (read-only·결정적).

    `sources[i]` = `{source_id, signal_density, min_docs}`:
    - **floor 피보장** — 각 소스는 `min_docs` (기본 `DEFAULT_MIN_DOCS`) 를 받고,
      그 위 잉여만 수율 비례 배분 (어느 소스도 멸종 방지, 04 §5).
    - 예산이 floor 합보다 작으면 floor 비례 축소(비율 일관, 전체 보존).
    - **미측정**(`signal_density` None) 소스는 잉여 경쟁 제외 — floor 만 (honest-gap).
    - 전 소스 미측정이면 잉여 균등 — 차별 근거 부재 (보수적, 결정).
    - 음수 density → 0 취급 (가드).

    반환 `{source_id: allocated_docs}` (합 ≤ budget — 불변식).
    """
    if not sources or budget_docs <= 0:
        return {}

    floors = {}
    for s in sources:
        s_id = s["source_id"]
        floors[s_id] = max(0.0, s.get("min_docs", DEFAULT_MIN_DOCS))

    total_floor = sum(floors.values())
    if total_floor >= budget_docs:
        # 예산 희소 — floor 비례 축소 (비율 일관, 합 = 예산).
        scale = budget_docs / total_floor if total_floor > 0 else 0.0
        return {s_id: round(f * scale, 3) for s_id, f in floors.items()}

    # 잉여 = 예산 - floor 합 → 수율 비례 배분.
    surplus = budget_docs - total_floor
    alloc = {s_id: f for s_id, f in floors.items()}

    # measured 만 잉여 경쟁.
    measured = [(s, max(0.0, s.get("signal_density") or 0.0))
                for s in sources if s.get("signal_density") is not None]
    if measured:
        total_w = sum(w for _, w in measured)
        if total_w > 0:
            for s, w in measured:
                alloc[s["source_id"]] += surplus * (w / total_w)
        else:
            _uniform_surplus(alloc, measured, surplus)
    else:
        _uniform_surplus(alloc, sources, surplus)

    return {s_id: round(v, 3) for s_id, v in alloc.items()}


def _uniform_surplus(alloc: dict, source_specs: list, surplus: float) -> None:
    """잉여를 참여 소스에 균등 배분 (결정적 — 차별 근거 없을 때 보수적)."""
    n = len(source_specs)
    if n == 0:
        return
    each = surplus / n
    for s in source_specs:
        alloc[s["source_id"]] += each


def adaptive_schedule(source_runs: dict, budget_docs: float, now_ts: float,
                      expected_intervals: dict | None = None,
                      last_collect_ts: dict | None = None,
                      min_docs: float = DEFAULT_MIN_DOCS) -> dict:
    """히스토리 기반 오케스트레이션 — 수율·freshness·배분을 한 번에 산출.

    - `source_runs`: `{source_id: [{docs, claims, edges, ...}, ...]}` — trailing 수율.
    - `expected_intervals`/`last_collect_ts`: `{source_id: seconds/ts}` — freshness 부착.
    - 반환 `{source_id: {signal_density, priority, lag_sec, overdue, allocated_docs}}`.

    read-only 산출물 — 실제 수집 실행·큐 기록은 호출자 몫 (불변식 §3-3).
    """
    sources = []
    for s_id in source_runs:
        density = trailing_signal_density(source_runs[s_id])
        sources.append({
            "source_id": s_id,
            "signal_density": density,
            "min_docs": min_docs,
        })
    alloc = allocate_signal_budget(sources, budget_docs)

    expected = expected_intervals or {}
    last = last_collect_ts or {}
    sched = {}
    for s in sources:
        s_id = s["source_id"]
        lag = freshness_lag(now_ts, last.get(s_id), expected.get(s_id))
        sched[s_id] = {
            "signal_density": s["signal_density"],
            "priority": cadence_priority(s["signal_density"]),
            "lag_sec": lag["lag_sec"],
            "overdue": lag["overdue"],
            "allocated_docs": alloc.get(s_id, 0.0),
        }
    return sched
