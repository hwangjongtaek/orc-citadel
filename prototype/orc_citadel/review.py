"""S19 quarantine review 워크플로 (05 §8) — 상태 전이 + human review as data.

quarantine/저신뢰 element를 사람 리뷰로 흘려 승격/폐기 결정을 내리고, 그 결정을
**골든셋**(원 모델출력·인간 결정·이유·reviewer)으로 저장한다 (불변식 §3-7).

- 상태 전이 (05 §8.1): pending → in_review → approved / corrected / rejected / escalated.
- Human review as data (§8.2): `review_history[]`에 원출력·결정·이유 보존 → 회귀 평가 골든셋.
- approve/correct는 승격(re-promote) 후보, reject는 근거와 함께 폐기, escalate는 온톨로지 제안.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

VALID_STATUS = {"pending", "in_review", "approved", "corrected", "rejected", "escalated"}


@dataclass
class ReviewRecord:
    element_ref: str
    original_model_output: dict
    reason: str
    status: str = "pending"
    reviewer: str = ""
    reviewed_at: str | None = None
    human_decision: dict = field(default_factory=dict)

    def to_golden(self) -> dict:
        """골든셋 레코드 (05 §8.2) — 원출력·결정·이유·reviewer."""
        return {
            "element_ref": self.element_ref,
            "status": self.status,
            "original_model_output": self.original_model_output,
            "human_decision": self.human_decision,
            "reason": self.reason,
            "reviewer": self.reviewer,
            "reviewed_at": self.reviewed_at,
        }


class ReviewQueue:
    """quarantine 리뷰 큐 — 상태 전이 + 골든셋 저장."""

    def __init__(self) -> None:
        self._records: dict[str, ReviewRecord] = {}

    def enqueue(self, element_ref: str, original: dict, reason: str) -> None:
        """quarantine → 리뷰 큐 (pending)."""
        self._records[element_ref] = ReviewRecord(
            element_ref=element_ref, original_model_output=original, reason=reason)

    def status(self, element_ref: str) -> str:
        if element_ref not in self._records:
            raise KeyError(element_ref)
        return self._records[element_ref].status

    def assign(self, element_ref: str, reviewer: str) -> None:
        """pending → in_review (reviewer 지정)."""
        rec = self._records[element_ref]
        if rec.status != "pending":
            raise ValueError(f"cannot assign from {rec.status}")
        rec.reviewer = reviewer
        rec.status = "in_review"

    def _decide(self, element_ref: str, verdict: str, reviewer: str,
                reason: str | None, corrected: dict | None = None) -> None:
        if not reviewer:
            raise ValueError("reviewer required (05 §8.2)")
        rec = self._records[element_ref]
        rec.reviewer = reviewer
        rec.human_decision = {"verdict": verdict}
        if corrected is not None:
            rec.human_decision["corrected_value"] = corrected
        if reason:
            rec.reason = reason
        rec.reviewed_at = datetime.now(timezone.utc).isoformat()
        rec.status = verdict

    def approve(self, element_ref: str, reviewer: str) -> None:
        """in_review → approved (승격, 05 §8.1)."""
        self._decide(element_ref, "approved", reviewer, None)

    def correct(self, element_ref: str, reviewer: str, corrected: dict) -> None:
        """수정본 승격 (corrected, §8.1)."""
        self._decide(element_ref, "corrected", reviewer, None, corrected)

    def reject(self, element_ref: str, reviewer: str, reason: str) -> None:
        """근거 남기고 폐기 (rejected)."""
        self._decide(element_ref, "rejected", reviewer, reason)

    def escalate(self, element_ref: str, reviewer: str) -> None:
        """온톨로지 proposal (escalated, → 02 §6.2)."""
        self._decide(element_ref, "escalated", reviewer, "ontology proposal")

    def all_history(self) -> list[dict]:
        """전체 골든셋 레코드 (영속·회귀 평가 입력용, 05 §8.2)."""
        return [r.to_golden() for r in self._records.values()]

    def history(self, element_ref: str) -> dict:
        """골든셋 레코드 반환 (05 §8.2)."""
        return self._records[element_ref].to_golden()


# 골든 파생에 인정되는 인간 결정 (05 §8.2) — pending/in_review 는 골든 원천 아님.
_GOLDEN_VERDICTS = {"approved", "corrected"}
# claim pair 골든 라벨 (10 §2.1) — human 교정본의 verdict 가 된다.
_CLAIM_LABELS = {"equivalent", "contradicts", "unrelated"}
# entity pair 골든 라벨 (10 §2.1, ADR-1001) — same/not_same.
_ENTITY_LABELS = {"same", "not_same"}


def _human_decision(rec) -> dict:
    d = rec.human_decision or {}
    return d


def derive_golden(rq: ReviewQueue, zone, gold_version: str = "g1",
                  labeled_by: str | None = None, split: str = "dev") -> int:
    """human review 결정 → zone 의 골든 claim/entity pair 로 파생 (05 §8.2, ADR-506).

    인간의 검토 결정(원 모델출력 + 수정결과 + 이유)이 회귀 평가 골든셋의 원천이 된다
    (불변식 §3-7). corrected/approved 결정만 파생하고, 인간 교정본(`corrected_value`, 또는
    approved 의 원 출력)의 verdict 를 골든 라벨로, 쌍 상대를 `claim_b`(claim pair) 또는
    `entity_a`/`entity_b`(entity pair) 로 추출한다.

    - claim 골든: corrected_value.verdict ∈ {equivalent, contradicts, unrelated} + claim_b.
    - entity 골든: corrected_value.verdict ∈ {same, not_same} + entity_a/entity_b.
    - 인정되지 않은 결정(pending/in_review)과 verdict 는 파생하지 않는다.
    - 결정적 멱등: zone.persist_golden_* 의 결정적 golden_id(ON CONFLICT no-op, 03 §5).
    - split/gold_version 은 호출자가 결정 (ADR-1007 dev/test, ADR-1005 gold_version).
    파생된 골든 개수를 반환.
    """
    n = 0
    for rec in rq._records.values():
        if rec.status not in _GOLDEN_VERDICTS:
            continue  # 아직 인간 결정 없음.
        cv = _human_decision(rec).get("corrected_value") or {}
        if cv.get("verdict") not in _CLAIM_LABELS and \
           cv.get("verdict") not in _ENTITY_LABELS:
            continue
        reason = cv.get("reason") or rec.reason or ""
        label = cv["verdict"]
        reviewer = labeled_by or rec.reviewer or ""
        if label in _CLAIM_LABELS and cv.get("claim_b"):
            zone.persist_golden_pair(
                rec.element_ref, cv["claim_b"], label, split,
                gold_version, reviewer, None, reason)
            n += 1
        elif label in _ENTITY_LABELS and cv.get("entity_a") and cv.get("entity_b"):
            zone.persist_golden_entity_pair(
                cv["entity_a"], cv["entity_b"], label, split,
                gold_version, reviewer, None, reason)
            n += 1
    return n
