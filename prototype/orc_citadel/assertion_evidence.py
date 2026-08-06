"""S29 어세션별 근거·다차원 신뢰도 집계 프로젝션 (설계 09 §4).

09 §4 Confidence 표현 계약 — `value` 단일 게이지 금지, 봉투 필수
(`value/evidence_count/independent_source_count/basis/dimensions`).
`value`는 source reputation이 아니라 **claim별 증거 구조**로 계산한다 (blueprint §11,
ADR-202 confidence·certainty와 별개 축).

- support   : 서로 다른 문서(doc)에서 동일 (subject, predicate, object) 주장을 입증하는
              지지 근거 수로 정규화 — `1 - 1/(n_support+1)` (문서 1건만으론 확정 불가,
              미관측 한계).
- contradiction: 반박 증거(conflict) 수로 위험 노출 — `1 - 1/(n_conflict+1)`.
- coverage  : 증거 공백 축 — n_support>0 이면 1.0, 없으면 0.0 (prototype은 미관측
              subclaim 추정 없음).
- value     : `support * (1 - contradiction)`.
- independent_source_count: dup_cluster 뿌리(root) 보정 후 독립 출처 수 (09 §3 note
  "복제 500건 = 독립 증거 2건"). 무클러스터 문서는 자기 자신을 root로 간주.
- **read-only** (불변식 §3-3): zone 행 읽기만 — 쓰기·영속·그래프 mutation 미노출.
  조사 UX(09 §2.3 claims/evidence, §3 conclusion)가 바로 소비하는 근거 집계.
"""
from __future__ import annotations

from dataclasses import dataclass


def _obj_key(row: dict) -> tuple:
    """object_id vs object_literal 통일 식별 (assertion·claim 공용)."""
    if row.get("object_id"):
        return ("id", row["object_id"])
    return ("lit", row.get("object_literal"))


@dataclass(frozen=True)
class AssertionEvidence:
    """어세션 1건의 근거·다차원 신뢰도 봉투 (09 §4)."""
    assertion_id: str
    claim_id: str
    subject_id: str
    predicate: str
    confidence: dict           # 09 §4 봉투.
    supporting_docs: tuple     # 지지 근거 문서 (distinct doc_id, 정렬).
    supporting_claims: tuple   # 지지 근거 claim 목록.
    contradicting_claims: tuple  # 반박 근거 claim 목록.
    evidence_count: int
    independent_source_count: int


class AssertionEvidenceProjector:
    """curated zone 부산물에 대한 read-only 근거·신뢰도 투사."""

    def __init__(self, zone) -> None:
        self._zone = zone
        self._claims = zone.claims()
        self._conflicts = zone.conflict_candidates()
        self._assertions = zone.assertions()
        self._doc_root = self._build_doc_root()

    def _build_doc_root(self) -> dict:
        """doc_id → dup_cluster root (복제 보정). 무클러스터는 미등록(자기=root)."""
        root = {}
        for cl in self._zone.clusters():
            r = cl["root_doc_id"]
            for member in cl.get("member_doc_ids", []):
                root[member] = r
        return root

    def _supporting_claims(self, subj: str, pred: str, obj: tuple) -> list[dict]:
        """같은 (subject, predicate, object) 주장을 입증하는 claim 후보 전체."""
        return [c for c in self._claims
                if c["subject_id"] == subj and c["predicate"] == pred
                and _obj_key(c) == obj]

    def _root_of(self, doc_id: str) -> str:
        return self._doc_root.get(doc_id, doc_id)

    def _compute(self, a: dict) -> AssertionEvidence:
        claim_id = a["claim_id"]
        subj, pred = a["subject_id"], a["predicate"]
        obj = _obj_key(a)

        supporting = self._supporting_claims(subj, pred, obj)
        docs = sorted({c["doc_id"] for c in supporting})
        n_support = len(docs)
        indep = len({self._root_of(d) for d in docs})
        n_conflict = sum(1 for cf in self._conflicts
                         if claim_id in (cf["claim_id_a"], cf["claim_id_b"]))
        contra_ids = sorted({cf["claim_id_a"] if cf["claim_id_b"] == claim_id
                             else cf["claim_id_b"]
                             for cf in self._conflicts
                             if claim_id in (cf["claim_id_a"], cf["claim_id_b"])})

        support = 1.0 - 1.0 / (n_support + 1) if n_support > 0 else 0.0
        contradiction = 1.0 - 1.0 / (n_conflict + 1) if n_conflict > 0 else 0.0
        coverage = 1.0 if n_support > 0 else 0.0
        value = support * (1.0 - contradiction)

        dims = {"support": support, "contradiction": contradiction, "coverage": coverage}
        basis = (f"지지 근거 {n_support}건 (독립 출처 {indep}건), "
                 f"반박 근거 {n_conflict}건")
        confidence = {
            "value": value,
            "evidence_count": n_support,
            "independent_source_count": indep,
            "basis": basis,
            "dimensions": dims,
        }
        return AssertionEvidence(
            assertion_id=a["assertion_id"], claim_id=claim_id,
            subject_id=subj, predicate=pred, confidence=confidence,
            supporting_docs=tuple(docs),
            supporting_claims=tuple(c["claim_candidate_id"] for c in supporting),
            contradicting_claims=tuple(contra_ids),
            evidence_count=n_support, independent_source_count=indep,
        )

    def for_assertion(self, assertion_id: str) -> AssertionEvidence | None:
        for a in self._assertions:
            if a["assertion_id"] == assertion_id:
                return self._compute(a)
        return None

    def for_subject(self, subject_id: str) -> list[AssertionEvidence]:
        return [self._compute(a) for a in self._assertions
                if a["subject_id"] == subject_id]

    def all(self) -> list[AssertionEvidence]:
        return [self._compute(a) for a in self._assertions]
