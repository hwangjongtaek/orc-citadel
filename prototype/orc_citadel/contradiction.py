"""S10 Contradiction — 결정적 충돌 후보 규칙 (설계 05 §5.1, 02 §3.1·ADR-504).

claim 쌍의 모순 **후보**를 결정적 그래프 규칙으로 생성한다 (§5.1). LLM 판정(§5.2
verdict/conflict_type)·SUPPORTS/CONTRADICTS edge는 후속 — 여기선 후보 생성까지
(precision-first, 규칙으로 확정하지 않고 후보로만).

- blocking: same subject ∧ (동일|호환) predicate 그룹.
- 상충 신호 (mutually exclusive, §5.1):
  - `polarity` positive vs negative → `polarity` 후보
  - object(동일 predicate) 서로 다른 값 → `value_conflict`
- §5.3 저장 계약: rationale + judged_by(규칙 판정 `pipeline`) 강제.
- verdict는 후보화로만 — 실제 모순 여부는 후속 LLM.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .extract_claims import ClaimCandidate

# 충돌 규칙 식별 — 변경 시 bump (03 §5, 재생성).
CONTRADICTION_VERSION = "c1"


@dataclass(frozen=True)
class ConflictCandidate:
    claim_id_a: str
    claim_id_b: str
    conflict_type: str  # value_conflict | polarity
    rationale: str
    judged_by: str = "pipeline"

    def to_row(self) -> dict:
        return {
            "claim_id_a": self.claim_id_a,
            "claim_id_b": self.claim_id_b,
            "conflict_type": self.conflict_type,
            "rationale": self.rationale,
            "judged_by": self.judged_by,
        }


def _ask_judge(a: ClaimCandidate, b: ClaimCandidate, judge) -> str | None:
    """LLM 실제 모순 판정(05 §5.2) — 계약-유효 verdict만 신뢰, 실패/무효는 None.

    `real_conflict`만 유지, `not_conflict`/`temporal`/`scope`는 전달받아 후보에서 제거
    할 용도로 returning. None이면 호출 측이 결정적 후보를 그대로 유지(후보 유지, ADR-507).
    """
    d = judge.judge_contradiction((a.claim_candidate_id, b.claim_candidate_id))
    if not isinstance(d, dict) or d.get("verdict") not in {
        "real_conflict", "temporal", "scope", "not_conflict",
    }:
        return None
    return d["verdict"]


def find_conflict_candidates(claims: list[ClaimCandidate], judge=None) -> list[ConflictCandidate]:
    """same subject ∧ (동일|호환) predicate 그룹에서 상충 쌍 후보를 생성.

    **결정적-우선**(05 §5): 규칙으로 상충 후보를 생성하고, 선택적 `judge`가 실제 모순
    여부를 판정한다. `real_conflict`만 남기고 `not_conflict`/`temporal`/`scope`는 제거
    (허위 모순 감소). 판정 주체를 `judged_by`에 기록 (rule=`pipeline`, LLM=`llm`).
    judge 미주입 시 순수 결정적 (기존 동작, 재생성 안전 — 03 §5).
    """
    # blocking: (subject, predicate) — 호환 predicate는 여기선 정확 동일만 (최소).
    groups: dict[tuple, list[ClaimCandidate]] = defaultdict(list)
    for c in claims:
        if not c.subject_id:
            continue
        groups[(c.subject_id, c.predicate)].append(c)

    candidates: list[ConflictCandidate] = []
    for _, members in groups.items():
        # 후보 생성 — 전쌍 O(n²) 계산을 **후보-최적 blocking** 으로 대체 (P1 병목).
        # 후보는 (A) polarity 상충(전 polarity 쌍) 또는 (B) 같은 polarity ∧ object 다름.
        #  (A) polarity 별 버킷 → 반대 polarity 와 cross (이는 출력 자체 — 출력-최적).
        by_pol: dict[str, list[ClaimCandidate]] = defaultdict(list)
        for m in members:
            by_pol[m.polarity].append(m)
        pol_keys = list(by_pol)
        for pi in range(len(pol_keys)):
            for pj in range(pi + 1, len(pol_keys)):
                for a in by_pol[pol_keys[pi]]:
                    for b in by_pol[pol_keys[pj]]:
                        candidates.append(ConflictCandidate(
                            claim_id_a=a.claim_candidate_id,
                            claim_id_b=b.claim_candidate_id,
                            conflict_type="polarity",
                            rationale=f"동일 subject·predicate에서 polarity 상충 "
                                      f"({a.polarity} vs {b.polarity})",
                        ))
        #  (B) 같은 polarity 에서 object 다른 쌍 — (polarity, object) 별 버킷 간 cross.
        #       polarity 상충 쌍(A)은 continue 되므로 value_conflict 는 같은 polarity 만.
        by_obj: dict[tuple, list[ClaimCandidate]] = defaultdict(list)
        for m in members:
            if m.object_id is not None:  # object 없는(논리) claim 은 value 후보 없음.
                by_obj[(m.polarity, m.object_id)].append(m)
        obj_keys = list(by_obj)
        for oi in range(len(obj_keys)):
            for oj in range(oi + 1, len(obj_keys)):
                kp, _o1 = obj_keys[oi]
                kp2, _o2 = obj_keys[oj]
                if kp != kp2:
                    continue  # polarity 다르면 (A)에서 이미 polarity 로 처리됨.
                for a in by_obj[obj_keys[oi]]:
                    for b in by_obj[obj_keys[oj]]:
                        candidates.append(ConflictCandidate(
                            claim_id_a=a.claim_candidate_id,
                            claim_id_b=b.claim_candidate_id,
                            conflict_type="value_conflict",
                            rationale=f"동일 subject·predicate가 서로 다른 object "
                                      f"({a.object_id} vs {b.object_id})",
                        ))

    # 결정적 출력 순서 — 생성 순서(버킷)와 무관하게 항상 정렬 (재생성 안전 03 §5).
    candidates.sort(key=lambda c: (c.claim_id_a, c.claim_id_b))

    if judge is not None:
        # 결정적 후보에 대해 LLM이 실제 모순 여부 확정 (05 §5.2).
        kept = []
        for c in candidates:
            a = next((x for x in claims if x.claim_candidate_id == c.claim_id_a), None)
            b = next((x for x in claims if x.claim_candidate_id == c.claim_id_b), None)
            verdict = _ask_judge(a, b, judge) if (a and b) else None
            if verdict == "real_conflict":
                kept.append(ConflictCandidate(
                    claim_id_a=c.claim_id_a, claim_id_b=c.claim_id_b,
                    conflict_type=c.conflict_type,
                    rationale=f"[LLM] 실제 모순 확정: {c.rationale}",
                    judged_by="llm",
                ))
            # else: None(유지) / not_conflict·temporal·scope(제거).
            elif verdict is None:
                kept.append(c)  # LLM 판정 불가 → 결정적 후보 유지.
        candidates = kept

    # 결정적 정렬 (순서 일정).
    candidates.sort(key=lambda c: (c.claim_id_a, c.claim_id_b))
    return candidates
