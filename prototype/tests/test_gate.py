"""S8 그래프 반영 게이트 (설계 05 §6, 03 §7) — TDD.

claim_candidates가 authoritative graph로 승격되기 전 거치는 4검증:
(1) schema (2) provenance (3) predicate 폐쇄성 (4) confidence 임계.
통과 → promoted(+ append-only create_node 이벤트), 실패 → quarantined(+ reason).
임계값은 05 §6이 10에 위임 — prototype은 placeholder 상수 (ADR).
"""
from __future__ import annotations

import pytest

from orc_citadel.extract_claims import ClaimCandidate, claim_id_for
from orc_citadel.gate import (
    CONTROLLED_PREDICATES,
    PROMOTION_CONFIDENCE,
    Gate,
    PromotionResult,
)


def _claim(conf: float = 0.8, predicate: str = "announces",
           subject: str | None = "org-abc", seg=0, start=0, end=12,
           frag="will host", provenance_ref: list | None = None) -> ClaimCandidate:
    return ClaimCandidate(
        claim_candidate_id=claim_id_for("doc-1", seg, start, end, predicate),
        doc_id="doc-1", predicate=predicate, subject_id=subject,
        object_id=None, object_literal=None, modality="asserted",
        polarity="positive", confidence=conf, seg_order=seg,
        char_start=start, char_end=end, surface_fragment=frag,
        event_type_hint="earnings", status="candidate",
        provenance_ref=provenance_ref or ["ext-1"],
    )


def test_promotes_valid_claim():
    """모든 검증 통과 → promote(create_node 이벤트) + 상태 promoted."""
    gate = Gate()
    c = _claim()
    result = gate.evaluate(c)
    assert result.promote
    assert result.reasons == []
    assert result.status == "promoted"
    # append-only 이벤트 발행 (재구축 가능).
    ms = gate.mutations()
    assert len(ms) == 1
    assert ms[0]["op"] == "create_node"
    assert ms[0]["element_ref"] == c.claim_candidate_id


def test_rejects_low_confidence():
    """confidence < 임계 → quarantine(+ reason)."""
    gate = Gate()
    c = _claim(conf=max(0.0, PROMOTION_CONFIDENCE - 0.1))
    result = gate.evaluate(c)
    assert not result.promote
    assert result.status == "quarantined"
    assert any("confidence" in r for r in result.reasons)
    assert gate.mutations() == []  # 실패는 승격 이벤트 발행 안 함


def test_rejects_unknown_predicate():
    """predicate ∉ controlled vocabulary → quarantine (+ 온톨로지 proposal hint)."""
    gate = Gate()
    c = _claim(predicate="eats_cookies")
    result = gate.evaluate(c)
    assert not result.promote
    assert any("predicate" in r for r in result.reasons)


def test_rejects_missing_subject():
    """subject 미해소(빈 스트링) → Reference 무결성 위반 quarantine."""
    gate = Gate()
    c = _claim(subject="")
    result = gate.evaluate(c)
    assert not result.promote
    assert any("subject" in r for r in result.reasons)


def test_rejects_bad_span():
    """span 비정상 (char_start>=char_end) → provenance/schema 실패."""
    gate = Gate()
    c = _claim(start=5, end=5)  # 0 길이 span
    result = gate.evaluate(c)
    assert not result.promote


def test_rejects_confidence_out_of_range():
    """confidence ∉ [0,1] → schema 실패 quarantine."""
    gate = Gate()
    c = _claim(conf=1.5)
    result = gate.evaluate(c)
    assert not result.promote


def test_controlled_predicates_include_announces():
    """02 §5.1 어휘 — announces/depends_on/supplies 등 포함."""
    assert "announces" in CONTROLLED_PREDICATES
    assert "depends_on" in CONTROLLED_PREDICATES
    assert "supplies" in CONTROLLED_PREDICATES


def test_controlled_predicate_partners_with_not_stale_partners():
    """02 §5.1 공식 `partners_with` 는 어휘 포함, 축약 `partners` 는 비포함.

    SLO-07 quarantine 원인(2026-08-12) — extractor 가 축약 `partners` 를 방출해
    §4-2 폐쇄성 게이트에서 71건 permanent quarantine 되었다. 어휘는 온톨로지
    표준 `partners_with` 를 담고 축약 `partners` 는 담지 않아야 정합 (폐쇄 유지).
    """
    assert "partners_with" in CONTROLLED_PREDICATES
    assert "partners" not in CONTROLLED_PREDICATES
    # partners_with claim 은 predicate 폐쇄성으로 quarantine 되지 않는다.
    gate = Gate()
    res = gate.evaluate(_claim(predicate="partners_with"))
    assert not any("predicate" in r for r in res.reasons)


def test_idempotent_event():
    """동일 claim 재평가 → 동일/추가 없는 이벤트 (03 §7 idempotency)."""
    gate = Gate()
    c = _claim()
    gate.evaluate(c)
    gate.evaluate(c)
    assert len(gate.mutations()) == 1


# --- Phase 6: SLO-07 quarantine 관측 배선 (design 11 §2.3, slo_observation_log) ---


def test_gate_quarantine_enter_plus_exit_feeds_slo07_dwell():
    """quarantined 진입 → promoted 재평가(해소) → SLO-07 체류 이벤트 + 중앙값."""
    from orc_citadel.slo_observation_log import SloObservationLog
    from orc_citadel.slo_metrics_harness import quarantine_dwell_median

    log = SloObservationLog()  # 실제 clock
    gate = Gate(slo_log=log)
    # 동일 element가 먼저 quarantined(저신뢰) → 나중에 promoted(해소).
    low = _claim(conf=0.1)  # low_confidence → quarantined
    gate.evaluate(low)
    assert gate.result(low.claim_candidate_id).status == "quarantined"

    ok = _claim(conf=0.9)  # promoted → 해소
    gate.evaluate(ok)
    assert gate.result(ok.claim_candidate_id).status == "promoted"

    # 동일 동치(element) — claim_candidate_id가 정확해야 함: 위 두 _claim은 id 동일.
    assert ok.claim_candidate_id == low.claim_candidate_id
    entries = log.dwell_entries()
    assert len(entries) == 1   # 진입+종료 짝 1건
    enter, exit_ = entries[0]
    assert exit_ >= enter
    assert quarantine_dwell_median(log.dwell_entries()) is not None


def test_gate_quarantine_only_not_measured():
    """진입만 있고 해소 없는 quarantine는 SLO-07 체류 미확정 (honest-gap)."""
    from orc_citadel.slo_observation_log import SloObservationLog
    from orc_citadel.slo_metrics_harness import quarantine_dwell_median

    log = SloObservationLog()
    gate = Gate(slo_log=log)
    gate.evaluate(_claim(conf=0.1))  # quarantined 진입만
    assert log.dwell_entries() == []          # 종료 없음 → 체류 미확정
    assert log.open_quarantine_count() == 1
    assert quarantine_dwell_median(log.dwell_entries()) is None


def test_gate_slo_log_truth_chain_e2e():
    """진입(저신뢰) → 해소(정상) 사이의 실제 경과 시간이 체류로 측정됨."""
    from orc_citadel.slo_observation_log import SloObservationLog
    from orc_citadel.slo_metrics_harness import quarantine_dwell_median_days

    log = SloObservationLog()
    gate = Gate(slo_log=log)
    gate.evaluate(_claim(conf=0.1))   # 진입
    # (실제 시간 일부 경과 — 해소 시점이 진입보다 늦음을 보장)
    gate.evaluate(_claim(conf=0.95))  # 해소
    med = quarantine_dwell_median_days(log.dwell_entries())
    assert med is not None and med >= 0


def test_gate_works_without_slo_log():
    """slo_log 기본 None — 기존 동작 무변경 (선택 주입, Spec 1.0.0)."""
    gate = Gate()
    r = gate.evaluate(_claim())
    assert r.promote
    assert len(gate.mutations()) == 1
