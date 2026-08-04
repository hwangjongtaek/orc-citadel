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


def find_conflict_candidates(claims: list[ClaimCandidate]) -> list[ConflictCandidate]:
    """same subject ∧ (동일|호환) predicate 그룹에서 상충 쌍 후보를 생성."""
    # blocking: (subject, predicate) — 호환 predicate는 여기선 정확 동일만 (최소).
    groups: dict[tuple, list[ClaimCandidate]] = defaultdict(list)
    for c in claims:
        if not c.subject_id:
            continue
        groups[(c.subject_id, c.predicate)].append(c)

    candidates: list[ConflictCandidate] = []
    for _, members in groups.items():
        members = sorted(members, key=lambda c: c.claim_candidate_id)
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = members[i], members[j]
                # 1) polarity 상충.
                if a.polarity != b.polarity:
                    candidates.append(ConflictCandidate(
                        claim_id_a=a.claim_candidate_id,
                        claim_id_b=b.claim_candidate_id,
                        conflict_type="polarity",
                        rationale=f"동일 subject·predicate에서 polarity 상충 "
                                  f"({a.polarity} vs {b.polarity})",
                    ))
                    continue
                # 2) object 상충 (동일 predicate, 다른 대상).
                if a.object_id is not None and b.object_id is not None \
                        and a.object_id != b.object_id:
                    candidates.append(ConflictCandidate(
                        claim_id_a=a.claim_candidate_id,
                        claim_id_b=b.claim_candidate_id,
                        conflict_type="value_conflict",
                        rationale=f"동일 subject·predicate가 서로 다른 object "
                                  f"({a.object_id} vs {b.object_id})",
                    ))

    # 결정적 정렬 (순서 일정).
    candidates.sort(key=lambda c: (c.claim_id_a, c.claim_id_b))
    return candidates
