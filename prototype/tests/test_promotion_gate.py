"""S38 Durable 승격 게이트 (설계 10 §3.1, ADR-1003) TDD.

S35 회귀의 last-promoted baseline을 **curated zone에 영속**해 실행 간 유지되는
승격 게이트로 완결한다 (design 10 §3.1: 게이트 통과 && 회귀 없음 → 승격 조).

- promotion_baselines 테이블 — version 기반 결정적 PK, active/superseded.
- PromotionGate.evaluate(snapshot): active baseline 대비 deltas·regressions·blocked.
- 회귀 없음+게이트 통과 → action=promote, align 가 active 갱신(superseded).
- 회귀 있음 → blocked, action=keep (baseline 유지).
- read-mostly: evaluate 는 조회만, align 만 영속 (불변식 §3-3 준수 — evaluate 시 상태 불변).

Atomic TDD: Red → Green → Refactor.
"""
from __future__ import annotations

import pytest

from orc_citadel.curated_zone import CuratedZone
from orc_citadel.regression import EvalSnapshot
from orc_citadel.pipeline_gate import PromotionGate


def _zone(snapshot=None) -> CuratedZone:
    z = CuratedZone(":memory:")
    z.initialize()
    if snapshot is not None:
        z.persist_promotion_baseline(version=snapshot.version,
                                     metrics=snapshot.metrics)
    return z


def _snap(version="g1", f1=1.0, p=1.0, cp=1.0, cr=1.0):
    return EvalSnapshot(version=version, metrics={
        "canonicalization_f1": f1, "canonicalization_precision": p,
        "contradiction_precision": cp, "contradiction_recall": cr})


# --- 영속 ---------------------------------------------------------------

def test_persist_baseline_roundtrip_active():
    """persist → active_baseline() 로드, 결정적 ID, active status."""
    z = _zone(_snap())
    rows = z.promotion_baselines()
    assert len(rows) == 1
    r = rows[0]
    assert r["status"] == "active"
    assert r["baseline_id"].startswith("base-")
    assert r["metrics"]["canonicalization_f1"] == 1.0
    active = z.active_baseline()
    assert active is not None
    assert active["version"] == "g1"


def test_persist_baseline_idempotent_same_version():
    """같은 version 재영속 → 1행 (결정적 ID, ON CONFLICT no-op)."""
    z = _zone()
    z.persist_promotion_baseline("g1", {"canonicalization_f1": 1.0})
    z.persist_promotion_baseline("g1", {"canonicalization_f1": 0.5})  # no-op (변경 무시).
    assert len(z.promotion_baselines()) == 1
    assert z.promotion_baselines()[0]["metrics"]["canonicalization_f1"] == 1.0


# --- evaluate --------------------------------------------------------------

def test_evaluate_against_active_baseline():
    """active baseline 대비 deltas·regressions·blocked."""
    z = _zone(_snap(version="g1", f1=1.0))
    g = PromotionGate(z)
    cur = _snap(version="g2", f1=0.90)
    res = g.evaluate(cur)
    assert res["baseline_version"] == "g1"
    assert res["deltas"]["canonicalization_f1"] == pytest.approx(-0.10)
    assert "canonicalization_f1" in res["regressions"]
    assert res["blocked"] is True
    assert res["action"] == "keep"


def test_evaluate_improvement_promote():
    """회귀 없음+게이트 통과 → passed, action=promote."""
    z = _zone(_snap(version="g1", f1=0.90))
    g = PromotionGate(z)
    cur = _snap(version="g2", f1=1.0)
    res = g.evaluate(cur)
    assert res["passed"] is True
    assert res["action"] == "promote"
    assert res["regressions"] == []


def test_align_promotes_baseline():
    """align(snapshot) — passed 시 active baseline 갱신, 기존 superseded."""
    z = _zone(_snap(version="g1", f1=0.9))
    g = PromotionGate(z)
    cur = _snap(version="g2", f1=1.0)
    assert g.evaluate(cur)["action"] == "promote"
    g.align(cur)
    baselines = z.promotion_baselines()
    assert len(baselines) == 2  # g1 superseded + g2 active.
    by_v = {b["version"]: b for b in baselines}
    assert by_v["g1"]["status"] == "superseded"
    assert by_v["g2"]["status"] == "active"
    assert z.active_baseline()["version"] == "g2"


def test_align_keep_when_blocked():
    """blocked 시 align은 baseline 유지 (갱신 안 함)."""
    z = _zone(_snap(version="g1", f1=1.0))
    g = PromotionGate(z)
    cur = _snap(version="g2", f1=0.85)
    assert g.evaluate(cur)["blocked"] is True
    assert g.align(cur) == False  # keep (영속 안 함).
    assert len(z.promotion_baselines()) == 1
    assert z.active_baseline()["version"] == "g1"


def test_no_active_baseline_first_run():
    """active baseline 없음(first) — 게이트만, blocked=False, action=init."""
    z = _zone()
    g = PromotionGate(z)
    res = g.evaluate(_snap(version="g1"))
    assert res["blocked"] is False
    assert res["action"] == "init"  # 최초 실행 — 기준선 생성 전.


# --- read-mostly -----------------------------------------------------------

def test_evaluate_read_only():
    """evaluate 는 영속 미노출 (read-mostly); align 만 영속."""
    z = _zone(_snap())
    g = PromotionGate(z)
    for bad in ("persist_promotion_baseline", "apply", "create_node"):
        assert not hasattr(g, bad), f"evaluate path read-only 위반: {bad}"

    # evaluate 호출 후 영속 미발생 (align 전까지 baseline 수 불변).
    before = len(z.promotion_baselines())
    g.evaluate(_snap(version="g2"))
    assert len(z.promotion_baselines()) == before


def test_determinism():
    """동일 상태 → 동일 판정."""
    z = _zone(_snap())
    g = PromotionGate(z)
    a = g.evaluate(_snap(version="g2", f1=0.9))
    b = g.evaluate(_snap(version="g2", f1=0.9))
    assert a["blocked"] == b["blocked"] and a["regressions"] == b["regressions"]
