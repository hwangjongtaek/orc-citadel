"""Watchtower — SLO 위반 운영 경보 라우팅 (design 11 §2.3, ADR-1104).

SLO 위반은 자동으로 Signal Spire 결론 알림이 아니라 **Watchtower 운영 경보**로
라우팅한다 (11 §2.3 — Signal Spire `signal_spire.py` 의 결론 알림과 채널 분리,
ADR-1104). 본 모듈은 그 운영 경보 **라우팅 계약**을 봉인한다:

- **위반 = `classified == "slo-gate"` 루트만.** `evaluate_slo01/05/06/07`(각
  SLO 하니스)가 반환한 판정 결과를 입력으로 받아, `slo-gate` 인 것만 운영
  경보로 만든다 (10 §1.4 — CI 비차단 nightly 경보).
- **`not-measured` 는 위반이 아니다** — honest-gap(§6.2, 부재가 OK 가 아님).
  조용히 떨어뜨리지 않고 별도 버킷으로 노출해 관측 창을 채운다.
- **fire-once:** 각 SLO 는 `slo:{slo_id}` dedup_key 로 한 번만 점화 (ADR-1104
  과잉 알림 금지). 상태가 재차 변해(새 측정 주기 값) 새로 점화되는 건 호출자가
  새 라우터/주기로 구분한다.
- **read-only(불변식 §3-3)·결정적** — alert 는 산출물일 뿐 저장·발송은 호출자
  몫 (Signal Spire 와 동일 원칙).
- 알림 채널 `watchtower-operational` 은 Signal Spire 와 분리된 운영 채널이다.
"""
from __future__ import annotations

# design 11 §2.3 측정 창 (rolling window) — SLO 별 메타.
_SLO_WINDOW = {
    "SLO-01": "7d", "SLO-02": "1d", "SLO-03": "1d", "SLO-04": "1d",
    "SLO-05": "7d", "SLO-06": "7d", "SLO-07": "30d", "SLO-08": "release",
}

# 운영 경보 채널 — Signal Spire(결론 알림)와 분리 (ADR-1104).
CHANNEL_OPERATIONAL = "watchtower-operational"


def _window(slo_id: str) -> str:
    """SLO 측정 창(§2.3 rolling). 미지정 SLO 는 조용히 생략하지 않고 None."""
    return _SLO_WINDOW.get(slo_id, "")


def is_slo_violation(evaluation: dict | None) -> bool:
    """운영 경보 대상 여부 — `classified == "slo-gate"` 만 (10 §1.4).

    `ok`·`not-measured`·None 은 위반이 아니다.
    """
    return bool(evaluation and evaluation.get("classified") == "slo-gate")


def make_operational_alert(slo_id: str,
                           evaluation: dict | None) -> dict | None:
    """SLO 위반 → Watchtower 운영 경보 alert dict (§2.3·ADR-1104).

    `evaluation`(evaluate_slo0* 산출 shape) 이 `slo-gate` 가 아니면 None.
    반환: {channel, slo_id, dedup_key, classification, window, evaluation,
    acknowledged}. 측정 스냅샷(`evaluation`)을 그대로 담아 온콜이 값·목표·within 을
    판단 근거로 본다. read-only·결정적.
    """
    if not is_slo_violation(evaluation):
        return None
    return {
        "channel": CHANNEL_OPERATIONAL,
        "slo_id": slo_id,
        "dedup_key": f"slo:{slo_id}",
        "classification": "slo-gate",
        "window": _window(slo_id),
        "evaluation": dict(evaluation),
        "acknowledged": False,
    }


class WatchtowerSloAlert:
    """SLO 판정 결과를 운영 경보로 라우팅하는 fire-once 라우터 (11 §2.3).

    `route(results)` — `{slo_id: evaluation}` 를 입력으로:
      - `slo-gate`    → 운영 경보 (violations, fire-once)
      - `not-measured`→ 조용히 떨어뜨리지 않고 not_measured 버킷으로 노출(§6.2)
      - `ok`          → ok 버킷
      - classified 미지정(비정상) → unclassified 버킷 (ok 로 퉁치지 않음)

    read-only(불변식 §3-3)·결정적. 반환은 결코 None 이 아닌 4-버킷 구조.
    """

    def __init__(self):
        self._fired: set = set()

    def fired(self, slo_id: str) -> bool:
        """이 SLO 가 이미 점화되었는가 (fire-once 조회)."""
        return f"slo:{slo_id}" in self._fired

    def route(self, results: dict | None) -> dict:
        """판정 결과를 라우팅 — 최신 측정 주기로 SLO 위반만 운영 경보로."""
        results = dict(results or {})
        return {
            "violations": self._collect_violations(results),
            "not_measured": self._collect(results, "not-measured"),
            "ok": self._collect_ok(results),
            "unclassified": self._collect_unclassified(results),
        }

    def _collect_violations(self, results: dict) -> list:
        out = []
        for slo_id, evaluation in results.items():
            alert = make_operational_alert(slo_id, evaluation)
            if alert is None:
                continue
            key = alert["dedup_key"]
            if key in self._fired:
                continue  # fire-once — 재알림 금지 (ADR-1104)
            self._fired.add(key)
            out.append(alert)
        return out

    def _collect(self, results: dict, classified: str) -> list:
        return [slo_id for slo_id, ev in results.items()
                if ev and ev.get("classified") == classified]

    def _collect_ok(self, results: dict) -> list:
        return [slo_id for slo_id, ev in results.items()
                if ev and ev.get("classified") == "ok"]

    def _collect_unclassified(self, results: dict) -> list:
        return [slo_id for slo_id, ev in results.items()
                if ev is None or ev.get("classified") not in ("slo-gate", "ok",
                                                              "not-measured")]
