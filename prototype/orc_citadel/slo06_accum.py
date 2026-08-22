"""SLO-06 7d rolling 누적 로그 (1번 시간 축 전환 — A26).

nightly 마다 SLO-06 실측의 개별 schema 검증 결과를 `data/slo06_accum.json` 에
append한다. 운영 7일치가 쌓이면 `accum_slo06` 이 최근 N일 항목을 모아
`schema_pass_rate` → `evaluate_slo06` 로 **재확정 판정**을 내린다 — 순시 스냅샷
(A24 n=30)을 운영 7d rolling 축적으로 승격해 확정(잠정)→확정 전환의 근거를 준다
(11 §2.3, honest-gap §6.2).

순수 함수·결정적 — 라이브 LLM 호출·영속 파일 생명주기는 드라이버(스크립트) 몫.
오프라인 테스트 대상 (test_slo06_accum).
"""
from __future__ import annotations

import json
from datetime import date, timedelta

from orc_citadel.slo_metrics_harness import (  # noqa: F401  (테스트가 직접 import)
    SLO06_TARGET,
    evaluate_slo06,
    schema_pass_rate,
)

_DAY = timedelta(days=1)


def accum_append(path, entries: list[dict], now: str | None = None) -> None:
    """`entries` 를 누적 로그(path)에 append — 재실행 시 덮지 않고 추가.

    각 `entry` 는 `{"ts", "source_id", "kind", "valid"}` 형태. `ts` 누락 시
    드라이버가 `now`(ISO8601)를 채운다. 기존 파일이 있으면 읽어 뒤에 붙인다.
    """
    items = list(entries)
    if now is not None:
        for it in items:
            it.setdefault("ts", now)
    existing = []
    if path.exists():
        try:
            existing = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            existing = []
    path.write_text(json.dumps(existing + items, ensure_ascii=False, indent=2))


def accum_recent(path, days: int = 7, now: str | None = None) -> list[dict]:
    """누적 로그에서 최근 `days` 일 윈도우 항목만 반환 (날짜 필터, ISO ts).

    `now`(ISO8601) 기준 과거 `days` 일(포함) 창에 `ts` 가 속한 항목. 결정적 —
    테스트가 `now` 를 고정해 재현.
    """
    if not path.exists():
        return []
    try:
        items = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    if now is None:
        return items  # now 미지정 시 전체 (순수 필터는 스크립트가 now 주입)
    boundary = now[:10]  # YYYY-MM-DD
    recent = set()
    current = _parse_date(boundary)
    for i in range(days):
        recent.add(_fmt_date(current))
        current -= _DAY
    return [it for it in items if it.get("ts", "")[:10] in recent]


def accum_slo06(path, days: int = 7, now: str | None = None) -> dict:
    """최근 `days` 일 누적 schema 검증 → pass_rate·SLO-06 판정.

    `valid: bool` 항목만 분모에 (None 은 n_unknown, honest-gap §6.2). 빈 로그 →
    `schema_pass_rate` 가 measured=False 를 반환하고 `evaluate_slo06` 이
    not-measured 를 준다. 반환: {pass_rate, n_pass, n_total, n_unknown, within_slo,
    classified, target, measured, days, window}.
    """
    recent = accum_recent(path, days=days, now=now)
    passes = [it.get("valid") for it in recent]
    rate = schema_pass_rate(passes)
    verdict = evaluate_slo06(rate["pass_rate"])
    return {**rate, **verdict, "days": days, "window": now}


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def _fmt_date(d: date) -> str:
    return d.isoformat()
