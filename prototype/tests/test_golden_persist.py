"""S34 골든셋 영속화 + 평가 파이프라인 통합 (설계 10 §2.3) TDD.

design 10 §2.3 골든셋 저장·버저닝 — curated zone에 `golden_pairs` 테이블.
- 결정적 golden_id (재실행 idempotent, 03 §5).
- split ∈ {dev, test} (ADR-1007), gold_version, labeled_by/at, rationale
  (human review as data, 불변식 §3-7: 원 출력·정답·이유 3자 보존).
- EvalHarness zone 모드 — 골든 자동 로드로 파이프라인 산출(캐노니컬·모순) 대조.
- promotion_blocked — 골든 gate 미달 시 신호 (design 10 §3.1).

Atomic TDD: Red → Green → Refactor.
"""
from __future__ import annotations

import pytest

from orc_citadel.curated_zone import CuratedZone
from orc_citadel.eval_harness import EvalHarness, GoldenPair


def _zone() -> CuratedZone:
    z = CuratedZone(":memory:")
    z.initialize()
    return z


# --- persist_golden_pair ----------------------------------------------------

def test_persist_golden_pair_idempotent():
    """결정적 golden_id — 동일 claim pair 2회 upsert 시 1행 (idempotent, 03 §5)."""
    z = _zone()
    z.persist_golden_pair(claim_a="clm-a", claim_b="clm-b", label="equivalent",
                          split="dev", gold_version="g1", labeled_by="human:test",
                          labeled_at="2026-08-01T00:00:00Z", rationale="같은 표면형",
                          original_prediction="equivalent")
    z.persist_golden_pair(claim_a="clm-a", claim_b="clm-b", label="equivalent",
                          split="dev", gold_version="g1", labeled_by="human:test",
                          labeled_at="2026-08-01T00:00:00Z", rationale="같은 표면형",
                          original_prediction="equivalent")
    assert len(z.golden_pairs()) == 1


def test_golden_pairs_roundtrip():
    """golden_pairs() — 저장 필드 왕복."""
    z = _zone()
    z.persist_golden_pair(claim_a="clm-a", claim_b="clm-b", label="contradicts",
                          split="test", gold_version="g1", labeled_by="human:kim",
                          labeled_at="2026-08-02T00:00:00Z", rationale="반대 주장",
                          original_prediction="unrelated")
    rows = z.golden_pairs()
    assert len(rows) == 1
    r = rows[0]
    assert r["claim_a"] == "clm-a" and r["claim_b"] == "clm-b"
    assert r["label"] == "contradicts"
    assert r["split"] == "test"
    assert r["gold_version"] == "g1"
    assert r["labeled_by"] == "human:kim"
    assert r["rationale"] == "반대 주장"
    assert r["original_prediction"] == "unrelated"
    assert r["golden_id"].startswith("gold-")


def test_golden_pair_deterministic_id():
    """같은 (a,b,label,split,version) → 같은 golden_id."""
    z = _zone()
    z.persist_golden_pair("clm-a", "clm-b", "equivalent", split="dev",
                          gold_version="g1", labeled_by="human:x", labeled_at="t",
                          original_prediction=None)
    z.persist_golden_pair("clm-a", "clm-b", "equivalent", split="dev",
                          gold_version="g1", labeled_by="human:x", labeled_at="t",
                          original_prediction=None)
    ids = {r["golden_id"] for r in z.golden_pairs()}
    assert len(ids) == 1


# --- EvalHarness zone 자동 로드 ---------------------------------------------

def test_harness_loads_golden_from_zone():
    """EvalHarness(zone=...) — 골든 자동 로드, 캐노니컬 대조."""
    z = _zone()
    # 캐노니컬 병합 상태.
    z.persist_canonical(_cc("ccl-1", ["clm-a", "clm-b"]))
    for cid in ("clm-a", "clm-b"):
        z.set_claim_canonical(cid, "ccl-1")
    # 골든: clm-a~clm-b equivalent.
    z.persist_golden_pair("clm-a", "clm-b", "equivalent", split="dev",
                          gold_version="g1", labeled_by="human:x", labeled_at="t",
                          original_prediction=None)
    h = EvalHarness(zone=z)  # golden 미주입 → zone에서 로드.
    m = h.canonicalization_metrics()
    assert (m.tp, m.fp, m.fn) == (1, 0, 0)


def test_promotion_blocked_when_gate_missed():
    """골든 gate 미달 → report promotion_blocked=True (design 10 §3.1)."""
    z = _zone()
    # clm-a~clm-b는 분리되어 있음 (캐노니컬 없음) — 골든 equivalent → FN.
    z.persist_golden_pair("clm-a", "clm-b", "equivalent", split="dev",
                          gold_version="g1", labeled_by="human:x", labeled_at="t",
                          original_prediction=None)
    h = EvalHarness(zone=z)
    rep = h.report()
    assert rep["promotion_blocked"] is True  # FN → F1 0 < 0.85.


def test_promotion_passed_when_perfect():
    """골든 gate 충족 → promotion_blocked=False."""
    z = _zone()
    z.persist_canonical(_cc("ccl-1", ["clm-a", "clm-b"]))
    for cid in ("clm-a", "clm-b"):
        z.set_claim_canonical(cid, "ccl-1")
    z.persist_golden_pair("clm-a", "clm-b", "equivalent", split="dev",
                          gold_version="g1", labeled_by="human:x", labeled_at="t",
                          original_prediction=None)
    h = EvalHarness(zone=z)
    rep = h.report()
    assert rep["promotion_blocked"] is False


def test_harness_injected_golden_still_works():
    """기존 주입 방식 유지 (뒤쪽 호환)."""
    h = EvalHarness(
        canonical_claims=[{"canonical_claim_id": "ccl-1", "member_claim_ids": ["clm-a", "clm-b"]}],
        member_of=[{"claim_id": "clm-a", "canonical_claim_id": "ccl-1"},
                   {"claim_id": "clm-b", "canonical_claim_id": "ccl-1"}],
        golden=[GoldenPair("clm-a", "clm-b", "equivalent")])
    assert h.canonicalization_metrics().tp == 1


# --- parquet export ---------------------------------------------------------

def test_golden_export_parquet():
    """parquet export에 golden_pairs 포함."""
    z = _zone()
    z.persist_golden_pair("clm-a", "clm-b", "equivalent", split="dev",
                          gold_version="g1", labeled_by="human:x", labeled_at="t",
                          original_prediction=None)
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as d:
        z.export_parquet(d)
        assert pathlib.Path(d, "golden_pairs.parquet").exists()


# read-only (harness가 쓰기 미노출 유지) -------------------------------------

def test_harness_read_only_persist_blocked():
    """EvalHarness는 골든 쓰기 미노출 (read-only, 불변식 §3-3)."""
    h = EvalHarness(zone=_zone())
    for bad in ("persist_golden_pair", "apply", "create_node", "insert", "update"):
        assert not hasattr(h, bad), f"read-only 위반: {bad} 노출"


def _cc(cid, members):
    from orc_citadel.canonicalize import CanonicalClaim
    return CanonicalClaim(
        canonical_claim_id=cid, subject_id="org-a", predicate="announces",
        object_id="org-b", canonical_text="x", member_claim_ids=members)
