"""Signal Spire — 결론·confidence 중요 변화 알림 (design 11 §4, Phase 5) TDD.

5 종 트리거(§4.1)·fire-once dedup(§4.2)·alert 스키마(§4.3) 를 봉인한다.

- 트리거: contradicting_evidence(CONTRADICTS)·claim_changed(SUPERSEDES)·
  plan_to_execution(planned→confirmed)·new_independent_source(독립 수 증가)·
  confidence_threshold(Δ ≥ 임계).
- **1 회 점화** — (investigation_id, trigger_type, target) dedup_key 로 재알림 금지
  (ADR-1104 과잉 알림 방지). 상태가 재차 변해 새 key 로만 새 알림.
- Alert 스키마 — investigation_id(technical-first)·severity·dedup_key·delta·cause.
- read-only(불변식 §3-3) — 알림은 산출물, 저장·발송은 호출자 몫. 결정적.
"""
from __future__ import annotations

import pytest

from orc_citadel.signal_spire import (
    CONFIDENCE_DELTA_TRIGGER,
    TRIGGER_TYPES,
    SignalSpire,
    dedup_key,
    evaluate_and_fire,
    make_alert,
    trigger_claim_changed,
    trigger_confidence_threshold,
    trigger_contradicting_evidence,
    trigger_new_independent_source,
    trigger_plan_to_execution,
)


def _node_events(status_value=None, event_ids=("evt-1",)):
    """create_node 이벤트 (plan_to_execution 평가용)."""
    evs = []
    for n, eid in enumerate(event_ids):
        props = {"id": eid}
        if status_value is not None:
            props["status"] = status_value
        evs.append({"op": "create_node",
                    "payload": {"id": eid, "props": props}})
    return evs


def _edge_events(etype, target, source="evd-x"):
    """CONTRADICTS/SUPERSEDES create_edge 이벤트."""
    return [{"op": "create_edge",
             "payload": {"type": etype, "from": source, "to": target}}]


# --- 트리거 (11 §4.1) --------------------------------------------------------


def test_contradicting_evidence_trigger_fires():
    """기존 결론에 신규 CONTRADICTS → contradicting_evidence 트리거 (11 §4.1)."""
    assert trigger_contradicting_evidence(
        _edge_events("CONTRADICTS", "clm-1"), target_claim="clm-1") is True


def test_contradicting_evidence_no_false_positive():
    """CONTRADICTS 가 대상 claim 에 없으면 트리거 안 함 (정밀성)."""
    assert trigger_contradicting_evidence(
        _edge_events("CONTRADICTS", "clm-2"), target_claim="clm-1") is False


def test_contradicting_evidence_supports_is_not_trigger():
    """SUPPORTS 는 반대 증거가 아니므로 트리거 안 함 (오알림 방지)."""
    assert trigger_contradicting_evidence(
        _edge_events("SUPPORTS", "clm-1"), target_claim="clm-1") is False


def test_claim_changed_trigger_fires():
    """SUPERSEDES → 기존 주장 변경 트리거 (11 §4.1)."""
    assert trigger_claim_changed(
        _edge_events("SUPERSEDES", "clm-1"), target_claim="clm-1") is True


def test_claim_changed_no_false_positive():
    """대상 claim 과 무관한 SUPERSEDES → 트리거 안 함."""
    assert trigger_claim_changed(
        _edge_events("SUPERSEDES", "other"), target_claim="clm-1") is False


def test_plan_to_execution_trigger_fires_on_confirmed():
    """Event.status planned→confirmed → plan_to_execution 트리거 (02 ontology)."""
    assert trigger_plan_to_execution(_node_events(status_value="confirmed")) is True


def test_plan_to_execution_planned_does_not_fire():
    """status=planned 만이면 아직 실행 증거 없음 → 트리거 안 함."""
    assert trigger_plan_to_execution(_node_events(status_value="planned")) is False


def test_plan_to_execution_empty_no_fire():
    """이벤트 없음 → 트리거 안 함 (가드)."""
    assert trigger_plan_to_execution([]) is False


def test_new_independent_source_fires_on_increase():
    """독립 증거 수 증가 → new_independent_source 트리거 (11 §1.4)."""
    assert trigger_new_independent_source([], prev_count=1, new_count=2) is True


def test_new_independent_source_no_increase_no_fire():
    """독립 수 유지/감소 → 트리거 안 함."""
    assert trigger_new_independent_source([], prev_count=2, new_count=2) is False
    assert trigger_new_independent_source([], prev_count=2, new_count=1) is False


def test_confidence_threshold_fires_on_delta():
    """confidence Δ ≥ 임계 → confidence_threshold 트리거 (11 §4.1)."""
    assert trigger_confidence_threshold([], before=0.8, after=0.5) is True


def test_confidence_threshold_small_delta_no_fire():
    """Δ < 임계 → 트리거 안 함 (과잉 알림 방지)."""
    assert trigger_confidence_threshold([], before=0.8, after=0.79,
                                        threshold=0.10) is False


def test_trigger_types_exactly_five():
    """11 §4.1 의 5 종 트리거 고정."""
    assert set(TRIGGER_TYPES) == {"contradicting_evidence", "claim_changed",
                                  "plan_to_execution", "new_independent_source",
                                  "confidence_threshold"}


# --- fire-once dedup (11 §4.2) ----------------------------------------------


def test_dedup_key_format():
    """dedup key = investigation:trigger:target (11 §4.2·§4.3)."""
    assert dedup_key("inv-1", "contradicting_evidence", "clm-1") == \
        "inv-1:contradicting_evidence:clm-1"


def test_fire_once_first_time():
    """첫 점화는 alert 반환 (fire-once 신규)."""
    s = SignalSpire()
    a = make_alert("inv-1", "contradicting_evidence", "clm-1")
    assert s.fire_once(a) == a


def test_fire_once_blocks_duplicate():
    """동일 dedup_key 재점화 → None (재알림 금지 — ADR-1104 과잉 알림 방지)."""
    s = SignalSpire()
    a = make_alert("inv-1", "contradicting_evidence", "clm-1")
    assert s.fire_once(a) == a
    assert s.fire_once(a) is None


def test_fire_once_distinct_key_fires():
    """다른 target(다른 dedup_key) → 새 점화 (상태 재변화 시 새 알림)."""
    s = SignalSpire()
    a1 = make_alert("inv-1", "contradicting_evidence", "clm-1")
    a2 = make_alert("inv-1", "contradicting_evidence", "clm-2")
    assert s.fire_once(a1) == a1
    assert s.fire_once(a2) == a2


def test_fire_once_fired_query():
    """fired() 조회는 점화 여부만 반환 (read-only)."""
    s = SignalSpire()
    s.fire_once(make_alert("inv-1", "claim_changed", "clm-1"))
    assert s.fired("inv-1:claim_changed:clm-1") is True
    assert s.fired("inv-1:claim_changed:clm-9") is False


# --- alert 스키마 (11 §4.3) -------------------------------------------------


def test_alert_schema_investigation_id_technical_first():
    """대상 식별은 campaign_id 가 아닌 investigation_id (11 §4.3, ADR-903)."""
    a = make_alert("inv-1", "contradicting_evidence", "clm-1")
    assert a["investigation_id"] == "inv-1"
    assert "campaign_id" not in a


def test_alert_schema_has_core_fields():
    """§4.3 핵심 필드 — severity·dedup_key·target·delta·cause·fire_count·acknowledged."""
    a = make_alert("inv-1", "claim_changed", "clm-1", severity="material",
                   delta={"before": {"confidence": 0.8}, "after": {"confidence": 0.5}},
                   cause={"mutation_ids": ["mut-1"], "correlation_id": "corr-1"})
    assert a["severity"] == "material"
    assert a["dedup_key"] == "inv-1:claim_changed:clm-1"
    assert a["target"]["claim_id"] == "clm-1"
    assert a["delta"]["before"]["confidence"] == 0.8
    assert a["cause"]["correlation_id"] == "corr-1"  # provenance gate 통과 근거.
    assert a["fire_count"] == 1
    assert a["acknowledged"] is False


def test_alert_dedup_key_always_present():
    """dedup_key 는 항상 자동 산출 — 조합별 재알림 방지의 근거."""
    a = make_alert("inv-9", "confidence_threshold", "clm-3")
    assert a["dedup_key"] == "inv-9:confidence_threshold:clm-3"


# --- 일괄 evaluate_and_fire -------------------------------------------------


def test_evaluate_and_fire_contradicting():
    """일괄 — CONTRADICTS 대상 claim → alert 생성."""
    s = SignalSpire()
    a = evaluate_and_fire(s, "inv-1", "contradicting_evidence", "clm-1",
                          events=_edge_events("CONTRADICTS", "clm-1"))
    assert a is not None
    assert a["trigger_type"] == "contradicting_evidence"


def test_evaluate_and_fire_fire_once_blocks_second():
    """일괄 — 동일 조합 두 번째는 None (fire-once)."""
    s = SignalSpire()
    evs = _edge_events("CONTRADICTS", "clm-1")
    assert evaluate_and_fire(s, "inv-1", "contradicting_evidence", "clm-1",
                             events=evs) is not None
    assert evaluate_and_fire(s, "inv-1", "contradicting_evidence", "clm-1",
                             events=evs) is None


def test_evaluate_and_fire_no_trigger_no_alert():
    """트리거 조건 미충족 → None (결정, 알림 없음)."""
    s = SignalSpire()
    assert evaluate_and_fire(s, "inv-1", "contradicting_evidence", "clm-1",
                             events=_edge_events("SUPPORTS", "clm-1")) is None


def test_evaluate_and_fire_new_source_context():
    """new_independent_source 는 context prev/new 수로 평가."""
    s = SignalSpire()
    a = evaluate_and_fire(s, "inv-1", "new_independent_source", "clm-1",
                          events=[], context={"prev_count": 1, "new_count": 3})
    assert a is not None


def test_evaluate_and_fire_unknown_trigger_returns_none():
    """미지원 trigger_type → None (가드)."""
    s = SignalSpire()
    assert evaluate_and_fire(s, "inv-1", "bogus", "clm-1", events=[]) is None


# --- 불변식 (read-only·결정성) -----------------------------------------------


def test_read_only_no_mutation():
    """signal_spire 모듈은 read-only — 쓰기·mutation 미노출 (불변식 §3-3)."""
    from orc_citadel import signal_spire as ss

    for bad in ("apply", "persist", "create_node", "create_edge", "insert",
                "write", "upsert"):
        assert not hasattr(ss, bad), f"read-only 위반: {bad} 노출"


def test_evaluate_is_deterministic():
    """동일 입력 → 동일 트리거·알림 (결정성 — 재현성)."""
    s1, s2 = SignalSpire(), SignalSpire()
    a = evaluate_and_fire(s1, "inv-1", "contradicting_evidence", "clm-1",
                          events=_edge_events("CONTRADICTS", "clm-1"))
    assert a == evaluate_and_fire(s2, "inv-1", "contradicting_evidence", "clm-1",
                                  events=_edge_events("CONTRADICTS", "clm-1"))
