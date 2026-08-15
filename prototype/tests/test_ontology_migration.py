"""온톨로지 migration 자동화 前단 계약 테스트 (설계 02 §6.1·§6.2·§6.3, 06 §7.3)."""
import pytest

from orc_citadel import ontology_migration as m


# ── migration_level (02 §6.1 semver 분류) ────────────────────────────────
def test_migration_level_same():
    assert m.migration_level("1.0.0", "1.0.0") == "none"


def test_migration_level_patch():
    assert m.migration_level("1.0.0", "1.0.1") == "patch"


def test_migration_level_minor():
    assert m.migration_level("1.0.0", "1.1.0") == "minor"


def test_migration_level_major():
    assert m.migration_level("1.0.0", "2.0.0") == "major"


def test_migration_level_major_ignores_minor_patch_difference():
    # minor/patch 차이는 major 보다 우선하지 않는다 — major 가 최상위 우선.
    assert m.migration_level("1.1.0", "2.9.1") == "major"


def test_migration_level_deterministic_typos():
    # 잘못된 구성요소 → 0 폴백 (결정적, 비정상 입력에 강건).
    assert m.migration_level("1.0.x", "1.1.0") == "minor"
    # 빈 버전 → (0,0,0) → cur 1.0.0 대비 major (비호환, 보수적).
    assert m.migration_level("", "1.0.0") == "major"


# ── compat_current (02 §6.3 호환성) ─────────────────────────────────────
def test_compat_same():
    assert m.compat_current("1.0.0", "1.0.0") == {"compatible": True, "reason": "same_version"}


def test_compat_minor_compatible():
    r = m.compat_current("1.0.0", "1.5.0")
    assert r["compatible"] is True and r["reason"] == "compatible_change"


def test_compat_patch_compatible():
    r = m.compat_current("1.0.0", "1.0.2")
    assert r["compatible"] is True and r["reason"] == "compatible_change"


def test_compat_major_incompatible():
    r = m.compat_current("1.0.0", "2.0.0")
    assert r["compatible"] is False and r["reason"] == "major_bump"


def test_compat_major_revalidate_required():
    # major → 타입 제거·의미 변경 → 전량 재평가 대상 (02 §6.3).
    assert m.compat_current("1.9.0", "2.0.0")["compatible"] is False


# ── plan_migration ───────────────────────────────────────────────────────
def _els(*predicates):
    """element 목록 생성 — id 는 순서, ontology_version 기본 1.0.0."""
    return [
        {"id": f"el-{i:02d}", "predicate": p, "ontology_version": "1.0.0"}
        for i, p in enumerate(predicates)
    ]


def _reg(*predicates):
    return set(predicates)


def test_plan_no_change_unchanged_honest_gap():
    # prev==cur → unchanged honest-gap (§6.2): "변경 없음"≠유의미 계획.
    plan = m.plan_migration(_els("depends_on"), "1.0.0", "1.0.0", _reg("depends_on"))
    assert plan.unchanged is True
    assert plan.revalidate_required is False
    assert plan.backfill_ids == ()
    assert plan.proposal_predicates == ()
    assert m.migration_actions(plan) == []


def test_plan_minor_compatible_no_backfill():
    plan = m.plan_migration(_els("depends_on"), "1.0.0", "1.2.0", _reg("depends_on"))
    assert plan.level == "minor"
    assert plan.revalidate_required is False       # minor 는 하위호환.
    assert plan.backfill_ids == ()                 # 저장 element 모두 호환.
    assert plan.unchanged is False
    assert "backfill" not in m.migration_actions(plan)


def test_plan_major_revalidate_and_backfill():
    plan = m.plan_migration(_els("depends_on"), "1.0.0", "2.0.0", _reg("depends_on"))
    assert plan.level == "major"
    assert plan.revalidate_required is True        # major → 전량 재평가.
    assert plan.backfill_ids == ("el-00",)         # 저장 1.0.0 element 는 비호환.
    assert "promotion" in m.migration_actions(plan)
    assert "backfill" in m.migration_actions(plan)


def test_plan_backfill_ids_sorted_deterministic():
    plan = m.plan_migration(
        _els("depends_on", "supplies", "depends_on"),
        "1.0.0", "2.0.0", _reg("depends_on", "supplies"))
    assert plan.backfill_ids == ("el-00", "el-01", "el-02")


def test_plan_unregistered_predicate_proposal():
    # 등록 안 된 predicate → proposal 트리거 (02 §4-2, quarantine 대상).
    plan = m.plan_migration(_els("dances_with"), "1.0.0", "1.0.0", _reg())
    assert plan.proposal_predicates == ("dances_with",)
    assert "proposal" in m.migration_actions(plan)


def test_plan_proposal_unique_sorted():
    plan = m.plan_migration(
        _els("dances_with", "depends_on", "dances_with", "sings"),
        "1.0.0", "1.0.0", _reg("depends_on"))
    assert plan.proposal_predicates == ("dances_with", "sings")


def test_plan_registered_only_no_proposal():
    plan = m.plan_migration(_els("depends_on", "supplies"), "1.0.0", "1.1.0",
                            _reg("depends_on", "supplies"))
    assert plan.proposal_predicates == ()


# ── quarantine_trigger (02 §4-2 predicate 폐쇄성) ──────────────────────
def test_trigger_registered_no_trigger():
    assert m.quarantine_trigger("depends_on", _reg("depends_on", "supplies")) == {"trigger": False}


def test_trigger_unregistered_triggers_proposal():
    assert m.quarantine_trigger("dances_with", _reg("depends_on")) == {
        "trigger": True, "predicate": "dances_with", "action": "quarantine_and_propose"}


def test_trigger_empty_registry_triggers():
    assert m.quarantine_trigger("depends_on", set())["trigger"] is True


# ── migration_actions (02 §6.2 절차 서열) ───────────────────────────────
def test_actions_full_sequence_for_major_with_unregistered():
    # proposal → review → promotion → backfill 순서 보존 (02 §6.2).
    plan = m.MigrationPlan(
        prev_version="1.0.0", cur_version="2.0.0", level="major",
        revalidate_required=True,
        backfill_ids=("el-00",),
        proposal_predicates=("dances_with",),
        unchanged=False,
    )
    assert m.migration_actions(plan) == ["proposal", "review", "promotion", "backfill"]


def test_actions_minor_promotion_only():
    plan = m.MigrationPlan("1.0.0", "1.1.0", "minor", False, unchanged=False)
    assert m.migration_actions(plan) == ["promotion"]


def test_actions_major_no_proposal_no_backfill():
    plan = m.MigrationPlan("1.0.0", "2.0.0", "major", True, unchanged=False)
    assert m.migration_actions(plan) == ["review", "promotion"]


def test_actions_none_unchanged():
    plan = m.MigrationPlan("1.0.0", "1.0.0", "none", False, unchanged=True)
    assert m.migration_actions(plan) == []


# ── backfill_events (06 §7.3 변환 이벤트 계획) ──────────────────────────
def test_backfill_events_reinterpret_target_version():
    plan = m.MigrationPlan("1.0.0", "2.0.0", "major", True,
                           backfill_ids=("el-01", "el-03"), unchanged=False)
    assert m.backfill_events(plan) == [
        {"op": "reinterpret", "element_id": "el-01", "target_version": "2.0.0"},
        {"op": "reinterpret", "element_id": "el-03", "target_version": "2.0.0"},
    ]


def test_backfill_events_empty_when_no_backfill():
    plan = m.MigrationPlan("1.0.0", "1.1.0", "minor", False, unchanged=False)
    assert m.backfill_events(plan) == []


def test_backfill_events_empty_when_minor_compatible():
    # 저장 element 가 현재 버전과 하위호환(minor) → backfill 대상 아님.
    els = [{"id": "el-00", "predicate": "depends_on", "ontology_version": "1.0.0"}]
    plan = m.plan_migration(els, "1.0.0", "1.1.0", _reg("depends_on"))
    assert plan.backfill_ids == ()


def test_empty_version_marked_incompatible_conservative():
    # 빈 ontology_version element 는 보수적으로 비호환 취급 → backfill 대상.
    # (unknown/stale version 은 자동 호환 오인 대신 재평가 대상 — §6.2 honest-gap.)
    els = [{"id": "el-00", "predicate": "depends_on", "ontology_version": ""}]
    plan = m.plan_migration(els, "1.0.0", "1.1.0", _reg("depends_on"))
    assert plan.backfill_ids == ("el-00",)
    assert "backfill" in m.migration_actions(plan)


# ── read-only (불변식 §3-3) ────────────────────────────────────────────
def test_read_only_no_mutation():
    for bad in ("apply", "persist", "create_node", "create_edge", "insert",
                "write", "upsert"):
        assert not hasattr(m, bad), f"read-only 위반: {bad} 노출"
