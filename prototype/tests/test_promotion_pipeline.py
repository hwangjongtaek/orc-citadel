"""S39 종단 간 승격 파이프라인 (설계 10 §3.1) TDD.

S36 EvalSuite 평가 → S38 PromotionGate 승격/차단을 자동 결합. 골든 영속 → P/R/F1 →
회귀 → durable baseline 승격/차단의 종단 간 흐름.

- run(version): 평가+판정+align(승격 시 영속).
- dry_run(version): 평가+판정만, align 없음 (read-only, 불변식 §3-3).
- action: PROMOTED / BLOCKED / INITIALIZED (baseline 없음 first run).
- realized: baseline 반영(promotion/초기화) 여부.

Atomic TDD: Red → Green → Refactor.
"""
from __future__ import annotations

import pytest

from orc_citadel.curated_zone import CuratedZone
from orc_citadel.regression import EvalSnapshot
from orc_citadel.promotion_pipeline import PromotionPipeline


def _zone(goldens=(), canonical_claims=(), member_of=(), baseline=None) -> CuratedZone:
    z = CuratedZone(":memory:")
    z.initialize()
    for g in goldens:
        z.persist_golden_pair(g["a"], g["b"], g["label"], split=g.get("split", "dev"),
                              gold_version="g1", labeled_by="human:test",
                              labeled_at="2026-08-01T00:00:00Z", rationale="x")
    for c in canonical_claims:
        z.persist_canonical(_cc(c["cid"], c["members"]))
    for m in member_of:
        z.set_claim_canonical(m["claim"], m["cc"])
    if baseline is not None:
        z.persist_promotion_baseline(version=baseline["version"],
                                     metrics=baseline["metrics"])
    return z


def _cc(cid, members):
    from orc_citadel.canonicalize import CanonicalClaim
    return CanonicalClaim(canonical_claim_id=cid, subject_id="org-a",
                          predicate="announces", object_id="org-b",
                          canonical_text="x", member_claim_ids=members)


def _perfect_zone():
    """골든 equivalent 1쌍 + 캐노니컬 병합 → F1=1.0."""
    return _zone(
        goldens=[{"a": "clm-a", "b": "clm-b", "label": "equivalent"}],
        canonical_claims=[{"cid": "ccl-1", "members": ["clm-a", "clm-b"]}],
        member_of=[{"claim": "clm-a", "cc": "ccl-1"},
                   {"claim": "clm-b", "cc": "ccl-1"}])


M100 = {"canonicalization_f1": 1.0, "canonicalization_precision": 1.0,
        "contradiction_precision": 0.0, "contradiction_recall": 0.0}  # 모순 골든 없음 = vacuous.


# --- INITALIZED (baseline 없음) ----------------------------------------

def test_run_initialized_first():
    """baseline 없음 → INITIALIZED, align로 active 생성 (realized)."""
    z = _perfect_zone()
    res = PromotionPipeline(z).run(version="v1")
    assert res.action == "INITIALIZED"
    assert res.passed is True
    assert res.realized is True
    assert z.active_baseline()["version"] == "v1"


# --- PROMOTED (회귀 없음, gate 통과) -----------------------------------

def test_run_promoted_identical():
    """baseline과 동일 → PROMOTED, active 갱신."""
    z = _perfect_zone()
    z.persist_promotion_baseline(version="v1", metrics=M100)
    res = PromotionPipeline(z).run(version="v2")
    assert res.action == "PROMOTED"
    assert res.regressions == []
    assert res.realized is True
    assert z.active_baseline()["version"] == "v2"


def test_run_promoted_gate_pass():
    """gate 통과+회귀 없음 → PROMOTED."""
    z = _perfect_zone()
    z.persist_promotion_baseline(version="v1", metrics=M100)
    res = PromotionPipeline(z).run(version="v2")
    assert res.gates["canonicalization"]["pass"] is True
    assert res.action == "PROMOTED"


# --- BLOCKED --------------------------------------------------------------

def test_run_blocked_regression():
    """baseline 대비 회귀 → BLOCKED, baseline 유지."""
    z = _perfect_zone()
    # baseline을 현재보다 높은 F1로 강제 → 현재 F1=1.0 이어도 회귀는 아님.
    # 회귀를 위해 baseline F1이 현재보다 높아야 — 현재는 골든 equivalent가 F1=1.0.
    # 간단히: baseline을 이상치(모순 P/R=1.0)로 주어 현재 모순 vacuous(0.0) 대비 하락.
    base = dict(M100, contradiction_precision=1.0, contradiction_recall=1.0)
    z = _perfect_zone()
    z.persist_promotion_baseline(version="v1", metrics=base)
    res = PromotionPipeline(z).run(version="v2")
    assert res.action == "BLOCKED"
    assert res.passed is False
    assert res.realized is False
    assert z.active_baseline()["version"] == "v1"  # 유지.


def test_run_blocked_gate_missed():
    """gate 미달(캐노니컬 분리) → BLOCKED."""
    z = _zone(goldens=[{"a": "clm-a", "b": "clm-b", "label": "equivalent"}])  # 캐노니컬 없음.
    z.persist_promotion_baseline(version="v1", metrics=M100)
    res = PromotionPipeline(z).run(version="v2")
    assert res.action == "BLOCKED"
    assert z.active_baseline()["version"] == "v1"


# --- dry_run (read-only) ---------------------------------------------------

def test_dry_run_no_persist():
    """dry_run — 평가·판정만, align 없음 (baseline 수 불변)."""
    z = _perfect_zone()
    p = PromotionPipeline(z)
    res = p.dry_run(version="v1")
    assert res.action == "INITIALIZED"  # 판정은 동일.
    assert res.realized is False        # 영속 안 함.
    assert z.active_baseline() is None  # baseline 생성 안 됨. read-only.


def test_dry_run_after_baseline():
    """baseline 존재 시 dry_run → PROMOTED 판정 but realized=False."""
    z = _perfect_zone()
    z.persist_promotion_baseline(version="v1", metrics=M100)
    res = PromotionPipeline(z).dry_run(version="v2")
    assert res.action == "PROMOTED"
    assert res.realized is False
    assert z.active_baseline()["version"] == "v1"  # 미반영.


# --- read-only surface / determinism ---------------------------------------

def test_dry_run_no_mutation_surface():
    """dry_run 경로는 영속 미노출, run은 align만 (프로파일·게이트 내부)."""
    z = _perfect_zone()
    p = PromotionPipeline(z)
    # dry_run 후 baseline 없음 (영속 안 함).
    p.dry_run("v1")
    assert z.active_baseline() is None


def test_determinism():
    """동일 상태 → 동일 판정·realized."""
    def run_twice():
        z = _perfect_zone()
        z.persist_promotion_baseline(version="v1", metrics=M100)
        return PromotionPipeline(z).run(version="v2")
    a, b = run_twice(), run_twice()
    assert a.action == b.action and a.realized == b.realized


# --- 5축 version-aware (S40) ---------------------------------------------

def _perfect_zone_vt(ontology="1.0.0"):
    from orc_citadel.versioning import fingerprint
    z = _perfect_zone()
    vt = {"ontology_version": ontology, "schema_version": "0.1.0",
          "prompt_template_hash": "sha256:abc", "model_id": "claude-opus-4-8",
          "extraction_code_version": "p1"}
    z.persist_promotion_baseline(version=fingerprint(vt), metrics=M100,
                                 ontology=ontology)
    return z, vt


def test_run_vt_initialized():
    """5축 dict로 run → fingerprint baseline, INITALIZED."""
    from orc_citadel.promotion_pipeline import PromotionPipeline
    z = _perfect_zone()  # baseline 없음.
    res = PromotionPipeline(z).run(version_tuple=VT)
    assert res.action == "INITIALIZED"
    assert res.version.startswith("vt-")


def test_run_vt_promoted_identical_ontology():
    """동일 5축 baseline → PROMOTED, major 없음."""
    from orc_citadel.promotion_pipeline import PromotionPipeline
    z, vt = _perfect_zone_vt()
    res = PromotionPipeline(z).run(version_tuple=vt)
    assert res.action == "PROMOTED"
    assert res.ontology_major_bump is False


def test_run_vt_ontology_major_bump():
    """온톨로지 major bump → revalidate_required 신호."""
    from orc_citadel.promotion_pipeline import PromotionPipeline
    z, _ = _perfect_zone_vt(ontology="1.0.0")
    vt2 = dict(VT, ontology_version="2.0.0")
    res = PromotionPipeline(z).run(version_tuple=vt2)
    assert res.revalidate_required is True


def test_run_vt_ontology_minor_no_bump():
    """온톨로지 minor → 재평가 불필요, 정상 판정."""
    from orc_citadel.promotion_pipeline import PromotionPipeline
    z, _ = _perfect_zone_vt(ontology="1.0.0")
    vt2 = dict(VT, ontology_version="1.1.0")
    res = PromotionPipeline(z).run(version_tuple=vt2)
    assert res.revalidate_required is False


def test_run_string_version_still_works():
    """뒤쪽 호환 — 기존 문자열 version 그대로 동작."""
    from orc_citadel.promotion_pipeline import PromotionPipeline
    z = _perfect_zone()
    z.persist_promotion_baseline(version="v1", metrics=M100)
    res = PromotionPipeline(z).run(version="v2")
    assert res.action == "PROMOTED"


def test_dry_run_vt_read_only():
    """5축 dry_run — 영속 없음."""
    from orc_citadel.promotion_pipeline import PromotionPipeline
    z, _ = _perfect_zone_vt()
    before = len(z.promotion_baselines())
    res = PromotionPipeline(z).dry_run(version_tuple=VT)
    assert res.realized is False
    assert len(z.promotion_baselines()) == before


VT = {
    "ontology_version": "1.0.0", "schema_version": "0.1.0",
    "prompt_template_hash": "sha256:abc", "model_id": "claude-opus-4-8",
    "extraction_code_version": "p1",
}
