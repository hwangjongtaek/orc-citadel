"""S9 Claim Canonicalization — 결정적 최소 (설계 05 §4, 02 §2.4·§3.1).

의미가 같은 claim을 하나의 CanonicalClaim(`ccl-`)으로 묶는다. LLM 관계 판정(§4.2
7-labels)은 후속 스텁 — prototype은 **결정적 규칙으로 `equivalent`만** 판정한다.

- 후보 축소(§4.1 blocking): same subject ∧ same predicate 그룹만 비교.
- `equivalent` 판정: 그룹 내 claim이 **겹치는 source_span**(같은 문장 표현) → 결정적.
- CanonicalClaim(02 §2.4): canonical_text + member_claim_ids + 정규 삼항.
- 소속의 정본은 `MEMBER_OF` 엣지(02 §3.1) — prototype은 canonical_claims 테이블 +
  member_of 엣지로 materialize (curated_zone에서).
- 결정적·idempotent (03 §5).
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field

from .extract_claims import ClaimCandidate

# 캐노니컬화 규칙 식별 — 변경 시 bump (03 §5, 재생성).
CANONICALIZATION_VERSION = "c1"


@dataclass(frozen=True)
class CanonicalClaim:
    canonical_claim_id: str
    subject_id: str
    predicate: str
    object_id: str | None
    canonical_text: str
    member_claim_ids: tuple = field(default_factory=tuple)

    def to_row(self) -> dict:
        return {
            "canonical_claim_id": self.canonical_claim_id,
            "subject_id": self.subject_id,
            "predicate": self.predicate,
            "object_id": self.object_id,
            "canonical_text": self.canonical_text,
            "member_claim_ids": list(self.member_claim_ids),
        }


def canonical_claim_id_for(subject_id: str, predicate: str, members: set[str]) -> str:
    """결정적 ccl- ID — (subject, predicate, member set) hash (03 §5)."""
    key = json.dumps(
        {"s": subject_id, "p": predicate, "m": sorted(members)},
        ensure_ascii=False, sort_keys=True,
    )
    return "ccl-" + hashlib.sha256(key.encode()).hexdigest()[:24]


def _claims_equivalent(a: ClaimCandidate, b: ClaimCandidate) -> bool:
    """같은 blocking 그룹(subject·predicate)에서 claim이 동일 표현인지.

    - 같은 문장(seg)에서 겹치는 source span → 동일 (추출 중복).
    - 다른 문장이지만 **동일 surface_fragment**(같은 토큰이 반복) — "의미가 같지만
      표현이 다르다(같은 표면형)"의 결정적 신호 (05 §4 equivalent, precision-first).
      예: 같은 subject·announces의 `power`/`powered`가 여러 segment에 반복.
    """
    if a.surface_fragment.strip().lower() == b.surface_fragment.strip().lower():
        return True
    # 같은 문장 내 겹치는 span도 동일 (추출 중복).
    if a.seg_order == b.seg_order:
        return a.char_start < b.char_end and b.char_start < a.char_end
    return False


def canonicalize_claims(claims: list[ClaimCandidate]) -> list[CanonicalClaim]:
    """claim 리스트를 동일 (subject, predicate) blocking 그룹으로 묶어 CanonicalClaim 생성.

    그룹 내 겹치는 span claim들을 union-find로 연결해 동치류를 만들고, 각 동치류를
    하나의 CanonicalClaim으로. 결정적 정렬.
    """
    # blocking (subject, predicate) ↔ 연결 컴포넌트.
    parents: dict[str, str] = {}
    groups: dict[tuple, list[ClaimCandidate]] = defaultdict(list)

    def find(x: str) -> str:
        while parents[x] != x:
            parents[x] = parents[parents[x]]
            x = parents[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parents[rb] = ra

    for c in claims:
        if not c.subject_id:
            continue  # 미해소 제외
        groups[(c.subject_id, c.predicate)].append(c)

    canonicals: list[CanonicalClaim] = []
    for (subj, pred), members in groups.items():
        # union-find: 같은 그룹 내 겹치는 span claim 연결.
        ids = [c.claim_candidate_id for c in members]
        for cid in ids:
            parents[cid] = cid
        members_by_id = {c.claim_candidate_id: c for c in members}
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                if _claims_equivalent(members[i], members[j]):
                    union(members[i].claim_candidate_id, members[j].claim_candidate_id)

        comps: dict[str, list[str]] = defaultdict(list)
        for cid in ids:
            comps[find(cid)].append(cid)
        for comp_members in comps.values():
            member_set = set(comp_members)
            # canonical text: member 중 가장 긴 surface (결정적 — stable sort).
            rep = sorted(members_by_id[cid].surface_fragment
                         for cid in comp_members)[0]
            canonicals.append(CanonicalClaim(
                canonical_claim_id=canonical_claim_id_for(subj, pred, member_set),
                subject_id=subj,
                predicate=pred,
                object_id=members_by_id[comp_members[0]].object_id,
                canonical_text=rep,
                member_claim_ids=tuple(sorted(member_set)),
            ))

    canonicals.sort(key=lambda c: c.subject_id)
    return canonicals
