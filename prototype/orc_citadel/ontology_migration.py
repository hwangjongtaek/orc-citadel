"""온톨로지 migration 자동화 前단 (설계 02 §6.1·§6.2·§6.3, 06 §7.3).

온톨로지 버저닝·거버넌스 절차(proposal → review → promotion → backfill)의 **계획·
판정 전단**을 봉인한다. 실제 이벤트 발행은 `graph_replay`·`GraphService`(Applier)
경로(불변식 §3-3)에 위임하며, 여기선 무엇을·어느 수준으로·누가 backfill/proposal
대상인지를 결정적으로 산출하는 **계획 산출물(read-only §3-3)**을 만든다.

- `migration_level` — 02 §6.1 semver 변경 분류(none/patch/minor/major). 버전 축
  추가(하위호환)=minor, 의미·필수성 변경/타입 제거=major.
- `compat_current` — 02 §6.3 호환성 판정. major(타입 제거·의미 변경)만 비호환 →
  **전량 재평가 대상**(`versioning.ontology_major_bump`와 별개 — 이 모듈은 저장된
  element 의 `ontology_version` 대비 현재 버전 호환을 판정).
- `plan_migration` — element 집합 대비 migration 계획 산출. prev==cur(변경 없음)은
  **honest-gap(§6.2)** — "no-op"≠유의미 계획(unchanged=True 에서 backfill·actions 공백).
- `migration_actions` — 계획에 따른 §6.2 절차 단계 서열(제안→검토→승격→백필).
- `quarantine_trigger` — 02 §4-2·§5 predicate 폐쇄성: 저장 element 의 미등록 predicate
  → quarantine + 온톨로지 proposal 트리거(자동 승격 금지, §6.2). 중복 회피: 신규
  수집의 게이트 판정은 `gate.py`(CONTROLLED_PREDICATES) 몫, 여기선 migration 계획
  관점에서 element 를 돌며 미등록 predicate 를 제안 대상으로 수집.
- `backfill_events` — 06 §7.3: 非호환 element 를 새 `ontology_version` target 으로
  재해석하는 **변환 이벤트 계획**(read-only 산출물 — 실제 발행은 Applier 경로).

결정적·read-only·mock/실측 격리. 스키마·계약 변경 없음 → Spec 그대로.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# §6.3 호환성 — major 는 전량 재평가(타입 제거·의미 변경), minor/patch 는 하위호환.
_REASON_MAJOR = "major_bump"
_REASON_COMPATIBLE = "compatible_change"
_REASON_SAME = "same_version"

# §6.2 절차 단계 서열 (제안→검토→승격→백필).
_ACTION_PROPOSAL = "proposal"
_ACTION_REVIEW = "review"
_ACTION_PROMOTION = "promotion"
_ACTION_BACKFILL = "backfill"


def _semver_tuple(v: str) -> tuple:
    """semver 문자열 → (major, minor, patch) 결정적 정규화.

    잘못된/빈 구성요소는 0 으로 폴백(결정적). 선행 zero·비어있음에 강건.
    """
    nums = []
    for part in str(v).split(".")[:3]:
        try:
            nums.append(int(part))
        except ValueError:
            nums.append(0)
    while len(nums) < 3:
        nums.append(0)
    return (nums[0], nums[1], nums[2])


def migration_level(prev: str, cur: str) -> str:
    """02 §6.1 semver 변경 분류. prev==cur → "none". 없으면 patch<minor<major."""
    if prev == cur:
        return "none"
    a, b = _semver_tuple(prev), _semver_tuple(cur)
    if a[0] != b[0]:
        return "major"
    if a[1] != b[1]:
        return "minor"
    return "patch"


def compat_current(stored: str, current: str) -> dict:
    """02 §6.3 호환성 판정 — 저장 element 의 버전이 현재 버전과 호환인가.

    - major 증가: **비호환**(타입 제거·의미 변경) → `incompatible`+reason=재평가 대상.
    - minor/patch: 하위호환 → `compatible`.
    - 동일: `compatible`.
    """
    level = migration_level(stored, current)
    if level == "major":
        return {"compatible": False, "reason": _REASON_MAJOR}
    if level == "minor" or level == "patch":
        return {"compatible": True, "reason": _REASON_COMPATIBLE}
    return {"compatible": True, "reason": _REASON_SAME}


@dataclass(frozen=True)
class MigrationPlan:
    """온톨로지 migration 계획 산출물 (read-only, 결정적).

    `unchanged`(prev==cur) 는 honest-gap 의 명시적 신호 — backfill·actions 가 비더라도
    "변경 없음"으로 구분되며 유의미 계획으로 오인하지 않는다(§6.2).
    """
    prev_version: str
    cur_version: str
    level: str
    revalidate_required: bool           # major → 전량 재평가 (02 §6.3)
    backfill_ids: tuple[str, ...] = ()  # 非호환 element → 재해석 대상 (06 §7.3)
    proposal_predicates: tuple[str, ...] = ()  # 미등록 predicate → proposal 트리거 (02 §4-2)
    unchanged: bool = False


def plan_migration(elements: list[dict], prev_version: str, cur_version: str,
                   registered_predicates: set[str]) -> MigrationPlan:
    """element 집합 대비 migration 계획 산출 (결정적).

    - `level`: prev→cur semver 분류.
    - `revalidate_required`: major 만 (전량 재평가).
    - `backfill_ids`: 저장 `ontology_version` 이 현재 버전과 非호환인 element id
      (정렬 — 결정적).
    - `proposal_predicates`: 미등록 predicate(unique, 정렬) → quarantine + proposal
      트리거 (자동 승격 금지, 02 §4-2).
    - `unchanged`: prev==cur 여부 (honest-gap).
    """
    level = migration_level(prev_version, cur_version)
    backfill = tuple(sorted(
        e["id"] for e in elements
        if not compat_current(e.get("ontology_version", ""), cur_version)["compatible"]
    ))
    propose = tuple(sorted({
        e.get("predicate") for e in elements
        if e.get("predicate") is not None and e.get("predicate") not in registered_predicates
    }))
    return MigrationPlan(
        prev_version=prev_version,
        cur_version=cur_version,
        level=level,
        revalidate_required=(level == "major"),
        backfill_ids=backfill,
        proposal_predicates=propose,
        unchanged=(prev_version == cur_version),
    )


def quarantine_trigger(predicate: str, registered_predicates: set[str]) -> dict:
    """02 §4-2·§5 predicate 폐쇄성 판정 — 미등록 → quarantine + proposal 트리거.

    신규 수집 게이트 판정은 `gate.py` 몫이므로 여기는 **proposal 트리거 신호**만
    반환한다(결정·read-only): 등록 predicate → `{"trigger": False}`, 미등록 →
    `{"trigger": True, "predicate": <p>, "action": "quarantine_and_propose"}`.
    """
    if predicate in registered_predicates:
        return {"trigger": False}
    return {"trigger": True, "predicate": predicate, "action": "quarantine_and_propose"}


def migration_actions(plan: MigrationPlan) -> list[str]:
    """계획 → §6.2 절차 단계 서열 (제안→검토→승격→백필).

    없을 단계는 제외. `unchanged` 이고 proposal 도 없으면 빈 단계(honest-gap —
    "아무 작업도 필요 없음").
    """
    if plan.unchanged and not plan.proposal_predicates:
        return []
    steps: list[str] = []
    if plan.proposal_predicates:
        steps.append(_ACTION_PROPOSAL)      # 미등록 predicate → 제안.
    if plan.revalidate_required:
        steps.append(_ACTION_REVIEW)        # major → 전량 재평가 검토.
    if not plan.unchanged:
        steps.append(_ACTION_PROMOTION)     # version bump → 승격.
    if plan.backfill_ids:
        steps.append(_ACTION_BACKFILL)      # 非호환 element → 백필(06 §7.3).
    return steps


def backfill_events(plan: MigrationPlan) -> list[dict]:
    """06 §7.3 — 非호환 element 를 새 version 으로 재해석하는 변환 이벤트 계획.

    read-only 산출물 — 각 항목은 `{"op":"reinterpret", "element_id":..., "target_version":...}`.
    실제 발행은 `graph_replay`·Applier 경로에 위임. backfill 대상 없으면 빈 목록.
    """
    return [
        {"op": "reinterpret",
         "element_id": eid,
         "target_version": plan.cur_version}
        for eid in plan.backfill_ids
    ]
