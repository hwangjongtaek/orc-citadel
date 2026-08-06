"""S30 조사 결론·신뢰도 종합 (설계 09 §3 conclusion, blueprint §5.2).

S29 어세션 근거 프로젝터(`AssertionEvidenceProjector`)를 소비해 **subject-level 결론
신뢰도 봉투**를 생성한다 (09 §4 — `value` 단일 게이지 금지). confidence는 source
reputation이 아니라 **증거 구조**로 계산 (blueprint §11, ADR-202 추출 confidence와 별개 축).

- value        : subject 어세션 평균 support × (1 − 반박 위험).
- evidence_count: 전체 지지 근거 합 (어세션별 evidence_count 누적).
- independent_source_count: 어세션별 독립 출처 통합 (dup_cluster 보정 유지).
- dimensions   : support(평균)/contradiction(반박 위험)/coverage(근거 있는 비율).
- by_predicate : predicate별 {count, independent_source_count, max_value} — 보고서
  섹션 재료 (09 §3 report.sections[].title).
- open_questions: 지지 근거 0(coverage 부족) or 저신뢰(value<임계) 어세션 신호 (09 §3).

**read-only** (불변식 §3-3) — S29 projector + zone 행 읽기만, 쓰기·영속·그래프 mutation
미노출. 조사 UX(09 §2.1 report, §3 conclusion)가 소비하는 결론 전구.
"""
from __future__ import annotations

from dataclasses import dataclass

from orc_citadel.assertion_evidence import AssertionEvidenceProjector

DEFAULT_LOW_CONFIDENCE = 0.4


@dataclass(frozen=True)
class ConclusionEvidence:
    subject_id: str
    confidence: dict                # 09 §4 봉투.
    by_predicate: dict              # predicate -> {count, independent_source_count, max_value}.
    open_questions: list            # 저신뢰·증거 부족 어세션 신호.
    contradicting_subjects: list    # 반박 신호 관계 (미구현 — 후속 확장).


class ConclusionProjector:
    """S29 어세션 근거를 종합하는 subject-level 결론 프로젝터 (read-only)."""

    def __init__(self, zone, low_confidence: float = DEFAULT_LOW_CONFIDENCE) -> None:
        self._evidence = AssertionEvidenceProjector(zone)
        self._low_confidence = low_confidence
        # dup_cluster root 보정 맵 (doc_id → root). 무클러스터는 자기 자신.
        self._doc_root = {m: cl["root_doc_id"]
                          for cl in zone.clusters()
                          for m in cl.get("member_doc_ids", [])}

    def _root_of(self, doc_id: str) -> str:
        return self._doc_root.get(doc_id, doc_id)

    def _compute(self, subject_id: str) -> ConclusionEvidence | None:
        evs = self._evidence.for_subject(subject_id)
        if not evs:
            return None
        n = len(evs)

        # subject 전체 지지 근거 — distinct 문서 (어세션 간 공유 근거 이중 집계 방지).
        subject_docs = {d for e in evs for d in e.supporting_docs}
        total_evidence = len(subject_docs)
        total_indep = len({self._root_of(d) for d in subject_docs})

        mean_support = sum(e.confidence["dimensions"]["support"] for e in evs) / n
        contradiction_total = sum(e.confidence["dimensions"]["contradiction"] for e in evs)
        has_evidence = sum(1 for e in evs if e.evidence_count > 0)
        coverage = has_evidence / n

        value = mean_support * (1.0 - contradiction_total)
        dims = {"support": mean_support, "contradiction": contradiction_total,
                "coverage": coverage}
        basis = (f"결론 신뢰도: 어세션 {n}건, 지지 근거 {total_evidence}건 "
                 f"(독립 출처 {total_indep}건), 반박 위험 {contradiction_total:.2f}")
        confidence = {
            "value": value,
            "evidence_count": total_evidence,
            "independent_source_count": total_indep,
            "basis": basis,
            "dimensions": dims,
        }

        # by_predicate — 보고서 섹션·타임라인 재료 (predicate별 distinct 독립 출처).
        by_predicate: dict = {}
        for e in evs:
            slot = by_predicate.setdefault(
                e.predicate,
                {"count": 0, "_docs": set(), "max_value": 0.0})
            slot["count"] += 1
            slot["_docs"].update(e.supporting_docs)
            slot["max_value"] = max(slot["max_value"], e.confidence["value"])
        for slot in by_predicate.values():
            slot["independent_source_count"] = len(
                {self._root_of(d) for d in slot.pop("_docs")})

        # open_questions — 지지 근거 0 (coverage 부족) or 저신뢰 (09 §3).
        open_q = []
        for e in evs:
            if e.evidence_count == 0:
                reason, kind = "증거 부족", "evidence"
            elif e.confidence["value"] < self._low_confidence:
                reason, kind = "저신뢰", "low_confidence"
            else:
                continue
            open_q.append({
                "assertion_id": e.assertion_id, "predicate": e.predicate,
                "value": e.confidence["value"], "reason": reason, "kind": kind,
            })
        open_q.sort(key=lambda o: o["value"])

        return ConclusionEvidence(
            subject_id=subject_id, confidence=confidence,
            by_predicate=by_predicate, open_questions=open_q,
            contradicting_subjects=[],
        )

    def for_subject(self, subject_id: str) -> ConclusionEvidence | None:
        return self._compute(subject_id)

    def all(self) -> list[ConclusionEvidence]:
        subjects = {a["subject_id"] for a in self._evidence._assertions}
        out = []
        for s in sorted(subjects):
            c = self._compute(s)
            if c is not None:
                out.append(c)
        return out
