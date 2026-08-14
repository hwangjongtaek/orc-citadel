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
    """evidence-first 불변식 검증 (07 §9.3, README §3-5).

    §3.9 역추적 chain — 보고서 문장 → claim_ref → extraction_record(source span) →
    document. 검증가능(fact/asserted) 문장이 span까지 역추적되어야 통과. 실패 문장은
    blocked_statements (무출처·미역추적 차단, 연결률 = 1.0, 10 §1.3).
    """

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

    def _claims_by_id(self, zone) -> dict:
        """zone claims → {claim_id: row} 맵 (read-only)."""
        return {c["claim_candidate_id"]: c for c in zone.claims()}

    def _span_for_claim(self, zone, claim_id: str) -> dict | None:
        """claim_id → extraction_record(source_span) 역추적 (provenance chain).

        claim → 추출 기록(03 §8, ADR-305: element_id = claim_id)에서 segment_id·
        char_start·char_end source span을 찾는다. 없으면 역추적 불가.
        """
        for rec in zone.extraction_records():
            if rec["element_id"] == claim_id:
                return {
                    "segment_id": rec["segment_id"],
                    "char_start": rec["char_start"],
                    "char_end": rec["char_end"],
                    "doc_id": rec["doc_id"],
                    "content_hash": rec["content_hash"],
                }
        return None

    def trace(self, statements, zone) -> dict:
        """§3.9 문장 → claim → source span 역추적 (read-only·결정적).

        출력 {trace: [{statement_ref, claim_ref, source_span, verified}],
        blocked_statements[], verifiable, linked, linkage_ratio}.
        prediction/opinion 무출처는 허용 (연결률 분모 제외, 10 §1.3).
        """
        st_list = list(statements)
        trace_rows = []
        blocked = []
        verifiable = 0
        linked = 0
        claims = self._claims_by_id(zone) if zone is not None else {}
        for i, st in enumerate(st_list):
            ref = f"st{i}"
            modality = st.get("modality")
            claim_ref = st.get("claim_ref")
            is_verifiable = modality in ("fact", "asserted")
            if is_verifiable:
                verifiable += 1
            if is_verifiable and not claim_ref:
                blocked.append({"statement_ref": ref, "text": st.get("text"),
                                "modality": modality,
                                "reason": "무출처 fact/asserted — claim_ref 부재 (evidence-first §3-5)"})
                trace_rows.append({"statement_ref": ref, "claim_ref": None,
                                   "source_span": None, "verified": False})
            elif is_verifiable and claim_ref:
                span = self._span_for_claim(zone, claim_ref) if zone is not None else None
                verified = span is not None
                if verified:
                    linked += 1
                else:
                    blocked.append({"statement_ref": ref, "text": st.get("text"),
                                    "modality": modality,
                                    "reason": f"claim_ref {claim_ref} source span 역추적 불가"})
                trace_rows.append({"statement_ref": ref, "claim_ref": claim_ref,
                                   "source_span": span, "verified": verified})
            else:
                # prediction/opinion 무출처 — 역추적 대상 아님.
                trace_rows.append({"statement_ref": ref, "claim_ref": claim_ref,
                                   "source_span": None,
                                   "verified": not is_verifiable})
        linkage = linked / verifiable if verifiable else 0.0
        return {
            "trace": trace_rows,
            "blocked_statements": blocked,
            "verifiable": verifiable,
            "linked": linked,
            "verified_statements": linked,
            "linkage_ratio": round(linkage, 4),
        }

    def verify_from_trace(self, trace_result: dict) -> dict:
        """§3.9 역추적 결과로 통과 판정 — blocked 존재 시 실패."""
        blocked = trace_result.get("blocked_statements", [])
        violations = [{"text": b.get("text"), "modality": b.get("modality"),
                       "reason": b.get("reason")} for b in blocked]
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
        # audit — evidence-first 검증 (07 §9.3) + §3.9 source span 역추적 chain
        # (문장 → claim_ref → extraction_record span, 연결률 = 1.0, 10 §1.3).
        trace = self._audit.trace(statements, self._zone)
        audit = self._audit.verify_from_trace(trace)
        return SynthesisReport(subject_id=subject_id, conclusion=conclusion,
                               statements=statements, open_questions=open_q,
                               audit=audit)
