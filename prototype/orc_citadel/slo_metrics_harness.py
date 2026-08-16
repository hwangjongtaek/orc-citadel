"""SLO-05/06/07/08 측정 하니스 — 지표 실측 계약 봉인 (design 11 §2.3, 10 §1.4).

Phase 6(Stable 운용) deferred SLO 실측 — SLO-01(`reflection_slo_harness`)과 동일한
**측정 계약·하니스 봉인** 패턴. 목표치 확정은 실데이터 축적 후 (측정 없는 목표는
신뢰하지 않는다, blueprint §20). 각 SLO 는 서로 다른 측정 공식(10 §1.4·11 §2.3)과
데이터 원천을 가진다:

- **SLO-05** source 수집 성공률 `≥ 99%`      — 성공 수 / 총 시도
- **SLO-06** schema validation 통과율 `≥ 95%` — 통과 / 총 검증
- **SLO-07** quarantine 체류 시간(중앙값) `≤ 3d` — 종료 − 진입 (중앙값)
- **SLO-08** 100만 문서 전체 재처리 시간       — full rebuild wall-clock 벤치 공개

**정직한 모델 (honest-gap §6.2):** 각 지표의 빈/미측정 입력 → `None`(부재가 OK 가
아니며, 측정값 없이 목표 충족을 주장하지 않음). 판정은 SLO-01 과 동일한
`ok` / `slo-gate`(10 §1.4 — CI 비차단 nightly 경보) / `not-measured`(부재) 분류.
SLO-08 은 목표가 "벤치마크 공개"라 임계 게이트 없이 **공개 + measured 여부** 만 명시.

시간·집계 원천은 주입 가능 — 결정적·mock/실측 격리. read-only(불변식 §3-3).
"""
from __future__ import annotations

import statistics

# 11 §2.3 — SLO-05/06/07 목표 (deferred → 실측 후 확정).
SLO05_TARGET = 0.99      # 수집 성공률 ≥ 99%
SLO06_TARGET = 0.95      # schema 통과율 ≥ 95%
SLO07_TARGET_DAYS = 3.0  # quarantine 체류 중앙값 ≤ 3일

# 10 §1.4 — 성능 SLO 판정 분류 (slo-gate nightly 비차단·not-measured honest-gap).
NOT_MEASURED = "not-measured"
SLO_GATE = "slo-gate"
OK = "ok"

# 일 ↔ ms (입력이 epoch ms 인 경우). SLO-07 체류 시간 입력 단위는 ms 로 가정.
_DAY_MS = 24 * 60 * 60 * 1000


# --- SLO-05: source 수집 성공률 --------------------------------------------------


def collect_success_rate(results: list[bool | None]) -> dict:
    """수집 성공률 = 성공 / 총 시도 (11 §2.3 SLO-05, 10 §1.4).

    `results` = 문서/요청별 성공 여부(bool). None(측정되지 않은 시도) → `n_unknown`
    로 노출하고 분모에서 제외(honest-gap §6.2 — 실패/성공 판정 없는 것은 세지 않음).
    빈 입력(성공+실패 0) → `success_rate=None` + `measured=False`.

    반환: {success_rate, n_success, n_attempt, n_unknown, measured}.
    """
    known = [r for r in results if r is not None]
    n_unknown = len(results) - len(known)
    if not known:
        return {"success_rate": None, "n_success": 0, "n_attempt": 0,
                "n_unknown": n_unknown, "measured": False}
    n_success = sum(1 for r in known if r)
    return {"success_rate": round(n_success / len(known), 4),
            "n_success": n_success, "n_attempt": len(known),
            "n_unknown": n_unknown, "measured": True}


def evaluate_slo05(success_rate: float | None) -> dict:
    """SLO-05 판정 (11 §2.3, 10 §1.4 slo-gate·CI 비차단)."""
    if success_rate is None:
        return {"within_slo": False, "classified": NOT_MEASURED,
                "target": SLO05_TARGET}
    within = success_rate >= SLO05_TARGET
    return {"within_slo": within,
            "classified": OK if within else SLO_GATE,
            "target": SLO05_TARGET, "success_rate": success_rate}


# --- SLO-06: schema validation 통과율 -------------------------------------------


def schema_pass_rate(passes: list[bool | None]) -> dict:
    """schema 검증 통과율 = 통과 / 총 검증 (11 §2.3 SLO-06, 10 §1.4).

    `passes` = schema 검증 통과 여부(bool). None(검증 미실행) → `n_unknown` 노출·
    분모 제외 (honest-gap §6.2). 빈 입력 → `pass_rate=None` + `measured=False`.
    """
    known = [p for p in passes if p is not None]
    n_unknown = len(passes) - len(known)
    if not known:
        return {"pass_rate": None, "n_pass": 0, "n_total": 0,
                "n_unknown": n_unknown, "measured": False}
    n_pass = sum(1 for p in known if p)
    return {"pass_rate": round(n_pass / len(known), 4),
            "n_pass": n_pass, "n_total": len(known),
            "n_unknown": n_unknown, "measured": True}


def evaluate_slo06(pass_rate: float | None) -> dict:
    """SLO-06 판정 (11 §2.3, 10 §1.4 slo-gate·CI 비차단)."""
    if pass_rate is None:
        return {"within_slo": False, "classified": NOT_MEASURED,
                "target": SLO06_TARGET}
    within = pass_rate >= SLO06_TARGET
    return {"within_slo": within,
            "classified": OK if within else SLO_GATE,
            "target": SLO06_TARGET, "pass_rate": pass_rate}


# --- SLO-07: quarantine 체류 시간(중앙값) ---------------------------------------


def quarantine_dwell_times(entries: list[tuple[float, float]]) -> list[float]:
    """각 quarantine 이력의 체류 시간(ms) = 종료 − 진입 (11 §2.3 SLO-07, 10 §1.4).

    `entries` = [(enter_ts_ms, exit_ts_ms), ...]. 아직 진행 중(exit=None)인 이력은
    측정 불가 → 제외하되 호출자 집계에서 노출 (honest-gap §6.2). read-only·결정적.
    """
    out = []
    for enter, exit_ in entries:
        if enter is None or exit_ is None:
            continue
        if exit_ < enter:
            continue  # 비정상 — 정방향만
        out.append(exit_ - enter)
    return out


def quarantine_dwell_median(entries: list[tuple[float, float]]) -> float | None:
    """체류 시간 중앙값 (ms). 빈 입력 → None (honest-gap §6.2)."""
    d = quarantine_dwell_times(entries)
    if not d:
        return None
    return round(float(statistics.median(d)), 3)


def quarantine_dwell_median_days(entries: list[tuple[float, float]]) -> float | None:
    """체류 중앙값을 일 단위로 (SLO-07 목표 ≤3d 비교용). None → not-measured."""
    ms = quarantine_dwell_median(entries)
    if ms is None:
        return None
    return round(ms / _DAY_MS, 4)


def evaluate_slo07(median_days: float | None) -> dict:
    """SLO-07 판정 (11 §2.3, 10 §1.4 slo-gate·CI 비차단)."""
    if median_days is None:
        return {"within_slo": False, "classified": NOT_MEASURED,
                "target_days": SLO07_TARGET_DAYS}
    within = median_days <= SLO07_TARGET_DAYS
    return {"within_slo": within,
            "classified": OK if within else SLO_GATE,
            "target_days": SLO07_TARGET_DAYS, "median_days": median_days}


# --- SLO-08: 100만 재처리 시간 (벤치마크 공개) ----------------------------------


def reprocess_benchmark(bench: dict) -> dict:
    """전체 재처리(full rebuild) 벽시계 공개 (11 §2.3 SLO-08, 10 §1.4).

    `bench` = recompute_bench/neo4j_q4_harness 의 full rebuild 결과 (full_ms 등).
    SLO-08 목표는 "벤치마크 공개" 이므로 임계 게이트는 없다 — 공개 값과 실측 여부를
    명시한다. `full_ms` 미제공 → `measured=False` (honest-gap §6.2).
    read-only·결정적.
    """
    full_ms = bench.get("full_ms")
    return {
        "full_ms": full_ms,
        "incremental_ms": bench.get("incremental_ms"),
        "measured": full_ms is not None,
        "source": "recompute_bench" if full_ms is not None else NOT_MEASURED,
    }
