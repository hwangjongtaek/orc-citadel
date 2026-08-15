"""hot/cold graph 분리 — 접근 온도 기반 계층 분리·조회 라우팅 (design 06 §8·ADR-603, Phase 5).

Phase 5 「hot/cold graph 분리」 — 10M Challenge 그래프 확장에서, **접근 온도(최근성)**로
그래프를 hot(빠른 상주)·cold(아카이브) 계층으로 분리해 hot 예산을 유지한다.

설계 근거:
- design 06 **ADR-603** — authoritative/quarantine 을 초기엔 논리 라벨 분리, 확장 시
  **물리 분리**. hot/cold 는 그 물리 분리 결정에 쓰는 접근 온도 축이다.
- **Q4 게이트** (06 §9 한계 측정) — 노드 수 ≥ `NODE_GATE`(=1e6, Community 실용 한계)
  시 교체/분리 트리거. cold 아카이브는 그 게이트를 넘는 그래프를 hot 예산 내로 유지한다.

원칙 (Phase 4/5 전 작업과 동일):
- **결정적** — 온도·분할·라우팅이 순수 입력 함수.
- **read-only** (불변식 §3-3) — 분리·승격 결정은 **산출물**일 뿐, 실제 아카이브
  이동·접근 기록 갱신은 호출자 몫. `mark_accessed` 는 새 stats dict 를 반환할 뿐
  입력을 변형하지 않는다.
- **mock/실측 격리** — 접근 stats·지연은 호출자(조회 이벤트)가 주입, 결정성은
  에뮬레이션으로 봉인.
- **honest-gap** (§6.2) — 미접근(unknown)·미측정(지연) 을 cold/위반 으로 오판하지
  않는다. unknown 은 보수적 기본(cold)으로 **할당**하되 측정과 구분.
"""
from __future__ import annotations

# design 06 §9 Q4 게이트 — Community 단일 인스턴스 실용 한계 (초과 시 분리/아카이브).
NODE_GATE = 1_000_000

# design 06 §8 hot/cold — hot 상주 예산 기본 (미지정 시 hot 예산 전체 유지 신호).
DEFAULT_HOT_WINDOW_SEC = 3_600.0  # 1시간 내 접근 = hot (placeholder — 사용자 정의 가능)
DEFAULT_SLO_MS = 50.0             # 조회 SLO p95 (11 §2 위임, slo-gate·CI 비차단)


def temperature(last_access_ts: float | None, now_ts: float,
                hot_window_sec: float = DEFAULT_HOT_WINDOW_SEC) -> str | None:
    """접근 최근성 → hot/cold.

    - `last_access_ts` None (미접근) → None (**미측정** — honest-gap §6.2,
      미접근을 cold 로 오판하지 않음).
    - `now - last_access_ts ≤ hot_window_sec` → "hot" (경계 포함), 초과 → "cold".
    - 음수(시계 역행) → 0 취급 → hot (가드).
    """
    if last_access_ts is None:
        return None
    lag = max(0.0, now_ts - last_access_ts)
    return "hot" if lag <= hot_window_sec else "cold"


def partition_tiers(access_stats: dict, now_ts: float,
                    hot_window_sec: float = DEFAULT_HOT_WINDOW_SEC) -> dict:
    """`access_stats` 를 hot/cold/unknown 으로 분할 (결정적, read-only).

    `access_stats[node_id]` = `{last_access_ts, access_count}` → 분할은 `last_access_ts`
    만으로. 각 리스트는 source 순서 보존(결정적 — 뒤 `mark_accessed` 순서와 정합).
    """
    hot, cold, unknown = [], [], []
    for node_id, stat in access_stats.items():
        t = temperature((stat or {}).get("last_access_ts"), now_ts, hot_window_sec)
        if t == "hot":
            hot.append(node_id)
        elif t == "cold":
            cold.append(node_id)
        else:
            unknown.append(node_id)
    return {"hot": hot, "cold": cold, "unknown": unknown}


def tier_map(access_stats: dict, now_ts: float,
             hot_window_sec: float = DEFAULT_HOT_WINDOW_SEC,
             default: str = "cold") -> dict:
    """요소별 tier 할당 — unknown 은 보수적 기본(`default`="cold") 으로.

    - hot/cold 은 실측 온도 유지.
    - unknown(미접근) 은 **할당**(default)만 — 측정(온도=None)과 구분, hot 예산 보수적 유지.
    """
    tm = {}
    for node_id, stat in access_stats.items():
        t = temperature((stat or {}).get("last_access_ts"), now_ts, hot_window_sec)
        tm[node_id] = t if t is not None else default
    return tm


def hot_resident_count(access_stats: dict, now_ts: float,
                       hot_window_sec: float = DEFAULT_HOT_WINDOW_SEC) -> int:
    """hot 상주 수 = hot 예산 소요 (온도에 따라 hot 이 아닌 건 제외)."""
    return len(partition_tiers(access_stats, now_ts, hot_window_sec)["hot"])


def cold_archive_decision(node_count: int, hot_resident: int) -> dict:
    """Q4 노드 게이트 → cold 아카이브 필요 판정 (ADR-603 물리 분리 트리거).

    - `node_count ≥ NODE_GATE` → `exceeds_gate=True` → `archive_needed=True`,
      cold 아카이브 = `max(0, node_count - hot_resident)` (hot 은 상주 보존).
    - `cold_ratio` = cold 아카이브 / node_count (온도 효율 지표).
    - 게이트 미만/아카이브 0 → `archive_needed=False`. read-only·결정적.
    """
    exceeds = node_count >= NODE_GATE
    cold_archived = max(0, node_count - hot_resident)
    cold_ratio = (cold_archived / node_count) if node_count > 0 else 0.0
    archive_needed = exceeds and cold_archived > 0
    return {
        "node_count": node_count,
        "hot_resident": hot_resident,
        "cold_archived": cold_archived,
        "cold_ratio": round(cold_ratio, 3),
        "exceeds_gate": exceeds,
        "archive_needed": archive_needed,
        "node_gate": NODE_GATE,
    }


def route_query(tier: str | None, hot_latency_ms: float, cold_latency_ms: float,
                slo_ms: float = DEFAULT_SLO_MS) -> dict:
    """tier 별 조회 라우팅 (read-only·결정적).

    - "hot" → 상주에서 빠르게 (`hot_latency_ms`), "cold" → 아카이브(`cold_latency_ms`).
    - tier **None**(미측정) → `served_from="unknown"`, `classified="not-measured"`
      (honest-gap §6.2).
    - 지연이 `slo_ms` 초과 → `classified="slo-gate"`, `violated=True` (비차단, §1.4).
    """
    if tier is None:
        return {"tier": None, "served_from": "unknown", "latency_ms": None,
                "classified": "not-measured", "violated": False, "slo_ms": slo_ms}
    served = "hot" if tier == "hot" else "cold"
    latency = hot_latency_ms if tier == "hot" else cold_latency_ms
    violated = (latency or 0.0) > slo_ms
    return {
        "tier": tier, "served_from": served, "latency_ms": latency,
        "classified": "slo-gate" if violated else "ok",
        "violated": violated, "slo_ms": slo_ms,
    }


def mark_accessed(access_stats: dict, node_id: str, now_ts: float,
                  access_count_increment: int = 1) -> dict:
    """read-only 승격 — 접근 기록 갱신 **새 dict** 반환 (입력 불변, 불변식 §3-3).

    실제 접근 기록 저장은 호출자 몫 — 본 함수는 결정적 산출물만 낸다. 미등록 요소는
    최초 접근(access_count=0 기준 +1)으로 생성.
    """
    new = {k: dict(v) if isinstance(v, dict) else v for k, v in access_stats.items()}
    existing = new.get(node_id, {})
    new[node_id] = {
        "last_access_ts": now_ts,
        "access_count": existing.get("access_count", 0) + access_count_increment,
    }
    return new
