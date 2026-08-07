"""S45 Counter-Evidence Agent (설계 07 §3.6) — read-only 반증 탐색.

현재 결론(subject·predicate)에 대한 반증 탐색 — hypotheses·negative_queries·
contradiction_candidates를 read-only로 산출 (07 §3.6, tier L5).

- hypotheses: subject에 대한 부정적·반대 가설 (결정적 규칙).
- negative_queries: 결론을 반박하는 용어 조합 (un-·취소·반대·부정).
- contradiction_candidates: S10 기존 모순 (같은 subject 다른 주장, conflict_type·
  rationale → 반박을 binary가 아닌 근거·판정 이유 포함, 07 §3.6 불변식).
- **read-only** (불변식 §3-3): 조회만, 쓰기·그래프 mutation 미노출.
"""
from __future__ import annotations


class CounterEvidenceAgent:
    """현재 결론에 대한 반증 탐색 (07 §3.6, read-only)."""

    # 결정적 반대 용어 (부정·취소·반대).
    _NEGATORS = ("not", "no", "never", "반대", "부정", "취소", "거부", "무효")

    def __init__(self, zone) -> None:
        self._zone = zone

    def contradiction_candidates(self, subject_id: str) -> list[dict]:
        """subject 기존 모순 (S10 conflict_candidates) — 이중 추적 검출."""
        # subject의 claims 기준 모순을 반환. prototype은 zone conflict_candidates에서
        # (같은 subject claim 포함 쌍)을 재현 — 여기선 모든 모순 리턴 + subject 관계.
        conflicts = self._zone.conflict_candidates()
        # subject와 연관된 쌍 식별: 같은 subject의 claim 쌍 여부는 zone claims로.
        claims_by_id = {c["claim_candidate_id"]: c for c in self._zone.claims()}
        out = []
        for cf in conflicts:
            a, b = cf["claim_id_a"], cf["claim_id_b"]
            ca, cb = claims_by_id.get(a), claims_by_id.get(b)
            # 둘 중 하나라도 이 subject면 후보 (subject 내/교차 모순).
            if (ca and ca["subject_id"] == subject_id) or \
               (cb and cb["subject_id"] == subject_id):
                out.append({
                    "claim_a": a, "claim_b": b,
                    "conflict_type": cf["conflict_type"],
                    "rationale": cf["rationale"],
                    "judged_by": cf["judged_by"],
                })
        return out

    def hypotheses(self, subject_id: str, predicate: str,
                   object_literal: str | None = None) -> list[str]:
        """반대 가설 (결정적 규칙 생성)."""
        target = object_literal or predicate
        return [
            f"{subject_id}는 {target}를 {predicate}(하지) 않았다 / 그 반대다",
            f"{subject_id}의 {predicate} 주장은 철회·취소되었다",
            f"{subject_id}의 {predicate}은 유효하지 않다 (범위·시점 한정)",
        ]

    def negative_queries(self, subject_id: str, predicate: str) -> list[str]:
        """부정 검색 쿼리 (결론 반박 용어)."""
        return [
            f"{subject_id} denied {predicate}",
            f"{subject_id} cancels {predicate}",
            f"{subject_id} reassesses {predicate}",
            f"{subject_id} 반대 {predicate}",
        ]

    def explore(self, subject_id: str, predicate: str,
                object_literal: str | None = None) -> dict:
        return {
            "conclusion": f"{subject_id} {predicate}",
            "hypotheses": self.hypotheses(subject_id, predicate, object_literal),
            "negative_queries": self.negative_queries(subject_id, predicate),
            "contradiction_candidates": self.contradiction_candidates(subject_id),
        }
