"""Signal Spire — 결론·confidence 의 중요한 변화 한정 알림 (design 11 §4, Phase 5).

Signal Spire 는 **결론과 confidence 의 중요한 변화**만 알린다(운영 경보와 구분,
11 §4.1). Watchtower 운영 경보(SLO 위반)와 채널을 분리한다(11 §2.3·§4).

- **5 종 트리거 (§4.1):** `contradicting_evidence`(신규 CONTRADICTS)·`claim_changed`
  (SUPERSEDES)·`plan_to_execution`(Event.status planned→confirmed)·
  `new_independent_source`(독립 증거 수 증가, §1.4)·`confidence_threshold`(confidence Δ).
- **1 회 점화 fire-once (§4.2):** 동일 `(investigation_id, trigger_type, target)` 는
  `dedup_key` 로 묶어 재알림 금지. 이미 점화된 조합은 다시 점화하지 않는다
  (ADR-1104 — 과잉 알림 방지). 상태가 재차 유의미하게 변할 때만 새 알림.
- **Alert 스키마 (§4.3):** alert_id·investigation_id·trigger_type·severity·
  dedup_key(=`inv:trigger:target`)·target·delta·cause(mutation_ids·correlation_id·
  new_document_ids·independent_evidence_count)·fired_at·fire_count·acknowledged.
  대상 식별 필드는 `investigation_id`(technical-first, campaign_id 미사용 — ADR-903).

트리거 평가는 **mutation event 스트림**을 입력으로 (7 §4, 03 §7.2 shape) —
실제 graph_mutations 은 주입, 결정성은 순수 이벤트 평가로 봉인 (mock/실측 격리).

read-only(불변식 §3-3)·결정적 — 알림은 산출물일 뿐, 저장·발송은 호출자 몫.
Phase 4 전 작업과 동일한 결정적·read-only 원칙.
"""
from __future__ import annotations

# design 11 §4.1 — 5 종 트리거 (Blueprint §5.3 확정).
TRIGGER_TYPES = (
    "contradicting_evidence", "claim_changed", "plan_to_execution",
    "new_independent_source", "confidence_threshold",
)

# 설계 §4.3 — severity (결론 변화 크기).
SEVERITY_MATERIAL = "material"
SEVERITY_MINOR = "minor"

# Confidence 변화 임계 (placeholder, 10 실측으로 조정 — 11 §2.3 정책).
CONFIDENCE_DELTA_TRIGGER = 0.10


def _events_with_op(events: list[dict], op: str) -> list[dict]:
    """지정 op 의 이벤트만 (read-only 필터, 결정적)."""
    return [e for e in events if e.get("op") == op]


def trigger_contradicting_evidence(events: list[dict],
                                   target_claim: str) -> bool:
    """`contradicting_evidence` — 기존 결론을 뒤집는 신규 CONTRADICTS 발견 (11 §4.1).

    대상 claim 을 `to` 로 하는 CONTRADICTS `create_edge` 이벤트가 새로 들어오면 True.
    """
    for e in _events_with_op(events, "create_edge"):
        p = e.get("payload") or {}
        if p.get("type") == "CONTRADICTS" and p.get("to") == target_claim:
            return True
    return False


def trigger_claim_changed(events: list[dict], target_claim: str) -> bool:
    """`claim_changed` — 기업·인물의 기존 주장이 변경됨 (SUPERSEDES, 11 §4.1).

    대상 claim 을 새 버전(`from`) 또는 구 버전(`to`) 으로 하는 SUPERSEDES 이벤트 시 True.
    """
    for e in _events_with_op(events, "create_edge"):
        p = e.get("payload") or {}
        if p.get("type") == "SUPERSEDES" and (p.get("from") == target_claim
                                              or p.get("to") == target_claim):
            return True
    return False


def trigger_plan_to_execution(events: list[dict], status_field: str = "status") -> bool:
    """`plan_to_execution` — 계획으로만 발표된 내용의 실행 증거 발견 (11 §4.1).

    Event.status(02 ontology: planned/confirmed/cancelled) 가 planned→confirmed 로
    바뀌는 `create_node`/`update` 이벤트(새 props.status=confirmed) 시 True.
    결정적 — events 의 현재 확정 상태만 본다.
    """
    for e in _events_with_op(events, "create_node"):
        p = e.get("payload") or {}
        props = p.get("props") or {}
        if props.get(status_field) == "confirmed":
            return True
    return False


def trigger_new_independent_source(events: list[dict],
                                   prev_count: int, new_count: int) -> bool:
    """`new_independent_source` — 서로 독립적인 새 출처 추가 (11 §4.1·§1.4).

    독립 증거 수(`§1.4 independent_source_count`)가 증가하면 True. `prev_count` 는
    변화 **전** 기준선 — 반복 증가를 피하려면 최근 점화 시점 수를 넘겨야 한다(fire-once).
    """
    return new_count > prev_count


def trigger_confidence_threshold(events: list[dict], before: float,
                                 after: float,
                                 threshold: float = CONFIDENCE_DELTA_TRIGGER) -> bool:
    """`confidence_threshold` — confidence 가 임계값 이상 변함 (11 §4.1).

    `|after - before| >= threshold` 시 True. ADR-706(δ=0.02 수렴 보조) 과 별개 —
    이 트리거는 결론 confidence 의 **중요 변화**만 알리는 운영 계약이다.
    """
    return abs(after - before) >= threshold


def dedup_key(investigation_id: str, trigger_type: str, target: str) -> str:
    """fire-once dedup key = `investigation:trigger:target` (11 §4.2·§4.3)."""
    return f"{investigation_id}:{trigger_type}:{target}"


def make_alert(investigation_id: str, trigger_type: str, target: str,
               severity: str = SEVERITY_MATERIAL, delta: dict | None = None,
               cause: dict | None = None, fire_count: int = 1) -> dict:
    """Alert dict 생성 (§4.3 스키마) — 결정·read-only.

    `dedup_key` 는 §4.2 규칙으로 자동 산출. `delta`·`cause` 는 (§4.3 예시대로)
    선택이며, cause 는 provenance 를 통과한 근거만 담는다(감사 가능, §4.3).
    """
    return {
        "investigation_id": investigation_id,
        "trigger_type": trigger_type,
        "severity": severity,
        "dedup_key": dedup_key(investigation_id, trigger_type, target),
        "target": {"claim_id": target},
        "delta": delta or {},
        "cause": cause or {},
        "fire_count": fire_count,
        "acknowledged": False,
    }


class SignalSpire:
    """fire-once 상태를 추적하며 트리거를 평가·알림 생성 (11 §4.2).

    점화된 `dedup_key` 를 기억해 **재알림 금지** (ADR-1104 — 과잉 알림 방지).
    read-only: 알림 산출만, 저장·발송은 호출자. 결정적.
    """

    def __init__(self):
        self._fired: set = set()

    def fired(self, key: str) -> bool:
        """이 dedup_key 가 이미 점화되었는가 (fire-once 조회)."""
        return key in self._fired

    def fire_once(self, alert: dict) -> dict | None:
        """alert 를 한 번 점화 — dedup_key 이미 점화 시 None (재알림 없음).

        fire_count 는 시퀀스(1, 2, …) — 상태가 재차 유의미하게 변해 새 dedup_key
        (다른 target/delta) 로 새 alert 를 만들면 이전과 다른 점화가 된다.
        """
        key = alert["dedup_key"]
        if key in self._fired:
            return None
        self._fired.add(key)
        return alert


def evaluate_and_fire(spire: SignalSpire, investigation_id: str,
                      trigger_type: str, target: str, events: list[dict],
                      severity: str = SEVERITY_MATERIAL, delta: dict | None = None,
                      cause: dict | None = None,
                      context: dict | None = None) -> dict | None:
    """트리거 평가 → fire-once → alert (일괄 래퍼).

    `trigger_type` 별 평가 함수에 `context`(새 출처 수·confidence before/after 등)
    를 넘겨 점화 여부를 결정하고, fire-once 를 지나면 §4.3 alert 를 반환한다.
    이미 점화(then) 여부와 무관하게 이번이 안 됐으면 None.
    """
    events = list(events or [])
    if trigger_type == "contradicting_evidence":
        ok = trigger_contradicting_evidence(events, target)
    elif trigger_type == "claim_changed":
        ok = trigger_claim_changed(events, target)
    elif trigger_type == "plan_to_execution":
        ok = trigger_plan_to_execution(events)
    elif trigger_type == "new_independent_source":
        ok = trigger_new_independent_source(events, (context or {}).get("prev_count", 0),
                                            (context or {}).get("new_count", 0))
    elif trigger_type == "confidence_threshold":
        ok = trigger_confidence_threshold(events, (context or {}).get("before", 0.0),
                                          (context or {}).get("after", 0.0))
    else:
        return None
    if not ok:
        return None
    alert = make_alert(investigation_id, trigger_type, target, severity,
                       delta=delta, cause=cause)
    return spire.fire_once(alert)
