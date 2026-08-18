"""SLO 실측 관측 로그 — sealed 하니스(`slo_metrics_harness`) 입력 생산 (design 11 §2.3).

Phase 6(Stable 운용) 인스트루먼테이션: deferred SLO-05/06/07 를 **다음 수집·처리 런
부터 실제로 측정 가능**하게 하는 비침투적 관측 계층. 기존 `slo_metrics_harness.py`
의 판정 함수(**수정 없음**)가 소비하는 입력 셰이프를 이 로그가 생산해 재사용한다.

- **SLO-05** 수집 성공률  — `record_collect(source_id, url, ok)` 시도/성공 로그 →
  `success_results()` → `collect_success_rate` 의 `results: list[bool|None]`
- **SLO-06** schema 통과율  — `record_schema(source_id, kind, valid)` 검증 로그 →
  `schema_results()` → `schema_pass_rate` 의 `passes: list[bool|None]`
- **SLO-07** quarantine 체류 — `record_quarantine_enter(edge_key, reason)` +
  `record_quarantine_exit(edge_key)` 진입/종료 로그 → `dwell_entries()` →
  `quarantine_dwell_*` 의 `entries: list[(enter_ts_ms, exit_ts_ms)]`

측정 경계에서 **어댑터가 원시 이벤트만 기록**하고, 집계·판정은 sealed 하니스에
위임 — 중복 구현 없음. honest-gap(§6.2): 로그가 비면 하니스가
`measured=False`/`not-measured` 로 자동 판정 (부재가 OK 가 아님).

read-only(불변식 §3-3)·결정적 — clock 주입으로 측정 시각을 결정한다.
mock/실측 격리 — 실제 영속·발송(flush)은 운영 드라이버 몫, 여기선 메모리 로그만.
**스키마·계약 변경 없음 → Spec 그대로(1.0.0).**
"""
from __future__ import annotations

import time


class SloObservationLog:
    """SLO-05/06/07 실측을 위한 이벤트 로그 (clock 주입, read-only 외부 노출).

    `now_ms` 주입 (기본 time.time()*1000) — 결정적·테스트에서 시간 고정 가능.
    내부 축적은 저장·발송 행위가 아니므로 불변식 §3-3(read-only 조회)에 위배되지
    않는다 — 산출 메서드(`success_results` 등)는 모조리 비파괴 조회다.
    """

    def __init__(self, now_ms=None) -> None:
        self._now = now_ms if now_ms is not None else (lambda: time.time() * 1000)
        self._collect: list[dict] = []     # {source_id, url, ok}
        self._schema: list[dict] = []      # {kind, valid}
        # quarantine 진입을 edge_key 로 색인 — 종료 시 매칭해 체류 이벤트 확정.
        self._q_enter: dict[str, float] = {}   # edge_key -> enter_ts_ms
        self._q_dwell: list[tuple[float, float]] = []  # (enter, exit) 확정분

    # --- SLO-05: 수집 시도/성공 -------------------------------------------------

    def record_collect(self, source_id: str, url: str, ok: bool) -> None:
        """수집 시도 기록 — `ok` 는 fetch 성공 여부 (SLO-05 denominator 의 시도)."""
        self._collect.append({"source_id": source_id, "url": url, "ok": bool(ok)})

    def success_results(self) -> list[bool | None]:
        """SLO-05 하니스 입력: 시도별 성공여부 (None=판정 없는 시도는 기록 안 함)."""
        return [c["ok"] for c in self._collect]

    def collect_log(self) -> list[dict]:
        """원시 수집 로그 조회 (read-only)."""
        return list(self._collect)

    # --- SLO-06: schema 검증 통과 ----------------------------------------------

    def record_schema(self, source_id: str, kind: str, valid: bool) -> None:
        """schema 검증 결과 기록 — `valid` 는 validate_* 통과 여부 (SLO-06)."""
        self._schema.append({"source_id": source_id, "kind": kind, "valid": bool(valid)})

    def schema_results(self) -> list[bool | None]:
        """SLO-06 하니스 입력: 검증별 통과 여부."""
        return [s["valid"] for s in self._schema]

    def schema_log(self) -> list[dict]:
        """원시 schema 검증 로그 조회 (read-only)."""
        return list(self._schema)

    # --- SLO-07: quarantine 진입/종료 → 체류 ------------------------------------

    def record_quarantine_enter(self, edge_key: str, reason: str | None = None) -> None:
        """quarantine 진입 이벤트 기록 (진입 시각 확정)."""
        if edge_key in self._q_enter:
            return  # 동일 키 재진입 무시 (멱등)
        self._q_enter[edge_key] = self._now()

    def record_quarantine_exit(self, edge_key: str) -> None:
        """quarantine 종료(해소) 이벤트 — 진입 기록과 짝지어 체류 이벤트 확정.

        진입 기록이 없는 종료는 무시 (honest-gap — 체류 부재를 측정으로 오인 금지).
        """
        enter = self._q_enter.pop(edge_key, None)
        if enter is None:
            return
        exit_ = self._now()
        if exit_ >= enter:  # 정방향만 (비정방향은 하니스에서도 재차 걸러짐)
            self._q_dwell.append((enter, exit_))

    def dwell_entries(self) -> list[tuple[float, float]]:
        """SLO-07 하니스 입력: 확정된 (enter_ts_ms, exit_ts_ms) 체류 이력.

        아직 종료되지 않은(진입만 있는) quarantine 은 체류 미확정 → 제외.
        단, 하니스의 `quarantine_dwell_times` 가 (enter=None, exit=None) 진행중을
        다시 걸러주므로 이 계약은 진입-종료가 **모두 기록된 것만** 넘긴다(honest-gap).
        """
        return list(self._q_dwell)

    def open_quarantine_count(self) -> int:
        """아직 종료되지 않은 quarantine 수 (진입만 존재) — honest-gap 노출용."""
        return len(self._q_enter)
