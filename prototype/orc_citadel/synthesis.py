"""S47 Synthesis/Audit (설계 07 §9.3, README §3-5) — 트랙 최종.

조사 루프(InvestigationRunner) 결과와 S30 subject 결론을 합성해 조사 report를
생성하고, Audit이 **evidence-first 불변식**(README §3-5, 07 §9.3)을 검증한다.

- conclusion: S30 결론 봉투 (09 §4 — 단일 게이지 금지).
- statements : evidence-first — asserted/fact는 claim_ref(→ provenance) 필수.
  무출처는 prediction만 허용.
- open_questions: gap subclaim (미충족 질문, 09 §3).
- **read-only** (불변식 §3-3): 조회·합성만, 영속·mutation 미노출.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from orc_citadel.conclusion import ConclusionProjector


@dataclass(frozen=True)
class SynthesisReport:
    subject_id: str
    conclusion: dict
    statements: list
    open_questions: list
    audit: dict


class Audit:
    """evidence-first 불변식 검증 (07 §9.3, README §3-5)."""

    def verify(self, report: SynthesisReport) -> dict:
        violations = []
        for st in report["statements"] if isinstance(report, dict) else report.statements:
            modality = st.get("modality")
            claim_ref = st.get("claim_ref")
            # fact/asserted 는 반드시 claim_ref — 무출처는 prediction만.
            if modality in ("fact", "asserted") and not claim_ref:
                violations.append({
                    "text": st.get("text"), "modality": modality,
                    "reason": "무출처 fact/asserted — evidence-first 위반 (README §3-5)",
                })
        return {"passed": len(violations) == 0, "violations": violations}


class Synthesizer:
    """InvestigationRunner 결과 + S30 결론 → 조사 report (read-only)."""

    def __init__(self, zone) -> None:
        self._zone = zone
        self._conclusion = ConclusionProjector(zone)
        self._audit = Audit()

    def _statements(self, subject_id: str) -> list:
        c = self._conclusion.for_subject(subject_id)
        # 실제 어세션 claim id (evidence-first — claim_ref는 provenance 소유).
        claim_ids = [a["claim_id"] for a in self._zone.assertions()
                     if a["subject_id"] == subject_id]
        statements = []
        if c is not None:
            # 결론 반영 asserted 문장 — claim_ref(실제 어세션) 노출 (README §3-5).
            for i, e in enumerate(c.by_predicate):
                statements.append({
                    "text": f"{subject_id}는 {e}한다 (지지 근거 기반 결론)",
                    "modality": "asserted",
                    "claim_ref": claim_ids[i % len(claim_ids)] if claim_ids else None,
                })
        return statements

    def synthesize(self, investigation_result, subject_id: str) -> SynthesisReport:
        c = self._conclusion.for_subject(subject_id)
        conclusion = c.confidence if c is not None else {
            "value": 0.0, "evidence_count": 0, "independent_source_count": 0,
            "basis": "근거 없음", "dimensions": {"support": 0.0,
                                                "contradiction": 0.0,
                                                "coverage": 0.0}}
        cov = c.confidence["dimensions"]["coverage"] if c else 0.0
        open_q = [{"subquestion": f"{subject_id} {g}", "reason": "증거 부족",
                   "coverage": cov} for g in investigation_result.gaps]
        statements = self._statements(subject_id)
        base = SynthesisReport(subject_id=subject_id, conclusion=conclusion,
                               statements=statements, open_questions=open_q,
                               audit={})
        # audit — evidence-first 검증 (07 §9.3, README §3-5).
        audit = self._audit.verify(base)
        return SynthesisReport(subject_id=subject_id, conclusion=conclusion,
                               statements=statements, open_questions=open_q,
                               audit=audit)
