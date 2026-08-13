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
    ontology_version: str = ""  # 02 §2 — authoritative claim 의 온톨로지 버전 (MVP #3).


class AssertionEvidenceProjector:
    """curated zone 부산물에 대한 read-only 근거·신뢰도 투사."""

    def __init__(self, zone) -> None:
        self._zone = zone
        self._claims = zone.claims()
        self._conflicts = zone.conflict_candidates()
        self._assertions = zone.assertions()
        self._doc_root = self._build_doc_root()
        self._independent_addition = self._build_independent_addition()
        # C2: 근거·모순 조회를 O(1) 인덱스로 — 전체 스캔 반복 제거.
        # _supporting_claims / n_conflict 가 모든 assertion에서 전체 claims·conflicts를
        # 매번 스캔해 ConclusionProjector.all() 이 O(subjects×claims) 로 비약했다.
        self._claims_by_key = {}
        for c in self._claims:
            self._claims_by_key.setdefault(
                (c["subject_id"], c["predicate"], _obj_key(c)), []).append(c)
        self._conflict_count = {}
        self._conflict_others = {}
        for cf in self._conflicts:
            a, b = cf["claim_id_a"], cf["claim_id_b"]
            for cid in (a, b):
                self._conflict_count[cid] = self._conflict_count.get(cid, 0) + 1
            self._conflict_others.setdefault(a, set()).add(b)
            self._conflict_others.setdefault(b, set()).add(a)

    def _build_doc_root(self) -> dict:
        """doc_id → dup_cluster root (복제 보정). 무클러스터는 미등록(자기=root)."""
        root = {}
        for cl in self._zone.clusters():
            r = cl["root_doc_id"]
            for member in cl.get("member_doc_ids", []):
                root[member] = r
        return root

    def _build_independent_addition(self) -> set:
        """독립 추가 파생 문서 집합 (§1.4 둘째 항 input).

        `independent_addition_doc_ids[]` ⊆ `member_doc_ids[]` (04 §4.2), root ∉ 이므로,
        이 집합은 오직 독립적 추가 정보를 담은 파생 문서만 담는다. 이 문서가 특정
        claim 의 지지 근거로 등장할 때만 §1.4 공식 둘째 항으로 가산된다.
        """
        indep = set()
        for cl in self._zone.clusters():
            for doc in cl.get("independent_addition_doc_ids", []):
                indep.add(doc)
        return indep

    def _supporting_claims(self, subj: str, pred: str, obj: tuple) -> list[dict]:
        """같은 (subject, predicate, object) 주장을 입증하는 claim 후보 전체.

        C2: 인덱스 조회(구축 시 1회 스캔, 이후 O(1)) — 전체 claims 스캔 반복 제거.
        """
        return self._claims_by_key.get((subj, pred, obj), [])

    def _root_of(self, doc_id: str) -> str:
        return self._doc_root.get(doc_id, doc_id)

    def _compute(self, a: dict) -> AssertionEvidence:
        claim_id = a["claim_id"]
        subj, pred = a["subject_id"], a["predicate"]
        obj = _obj_key(a)

        supporting = self._supporting_claims(subj, pred, obj)
        docs = sorted({c["doc_id"] for c in supporting})
        n_support = len(docs)
        # §1.4 독립 증거 수 보정: distinct(root_source) + 독립 추가 중 새 증거를
        # 더하는 문서. 지지 근거로 등장하는 독립 추가 파생 문서만 가산한다.
        # (root ∉ independent_addition 이므로 중복 계상 없음 — 04 §4.2 disjoint.)
        root_sources = {self._root_of(d) for d in docs}
        adding = {d for d in docs if d in self._independent_addition}
        indep = len(root_sources) + len(adding)
        # C2: 모순 조회 O(1) 인덱스 — 전체 conflicts 스캔 제거.
        n_conflict = self._conflict_count.get(claim_id, 0)
        contra_ids = sorted(self._conflict_others.get(claim_id, ()))

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
            ontology_version=a.get("ontology_version", ""),
        )

    def for_assertion(self, assertion_id: str) -> AssertionEvidence | None:
        for a in self._assertions:
            if a["assertion_id"] == assertion_id:
                return self._compute(a)
        return None

    def for_assertion_by_claim(self, claim_id: str) -> AssertionEvidence | None:
        """claim_id가 포함된 어세션의 근거 (S32 API 파사드의 claim→근거 조회)."""
        for a in self._assertions:
            if a["claim_id"] == claim_id:
                return self._compute(a)
        return None

    def for_subject(self, subject_id: str) -> list[AssertionEvidence]:
        return [self._compute(a) for a in self._assertions
                if a["subject_id"] == subject_id]

    def all(self) -> list[AssertionEvidence]:
        return [self._compute(a) for a in self._assertions]
