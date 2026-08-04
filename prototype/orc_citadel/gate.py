"""S8 그래프 반영 게이트 (설계 05 §6, 03 §7).

curated claim 후보가 authoritative graph로 승격되기 전 거치는 4검증을 결정적으로
수행한다 (05 §6). 통과 → promoted + append-only `create_node` 이벤트 발행, 실패 →
quarantined + 검증 실패 reason 기록.

- (1) schema  : 필수 필드·confidence ∈ [0,1]·span 정상
- (2) provenance: source_span(seg_order, char_start/end) 유효
- (3) predicate 폐쇄성: predicate ∈ controlled vocabulary (02 §5.1)
- (4) confidence 임계: confidence ≥ PROMOTION_CONFIDENCE

- **promotion 임계값은 05 §6이 [10]에 위임** — 여기선 기본 placeholder 상수로 두고,
  실제 값은 평가 골든셋 dev/tuning 후속 (10 §2.4 ADR-1007/1008).
- append-only event는 idempotency(동일 claim 재평가 시 중복 발행 방지, 03 §7).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .edges import PossiblySameAsEdge
from .extract import Mention
from .extract_claims import ClaimCandidate

# 설계 02 §5.1 controlled vocabulary (predicate). 초기 도메인 어휘.
CONTROLLED_PREDICATES = {
    "depends_on", "supplies", "invests_in", "acquires", "partners_with",
    "manufactures", "regulates", "announces", "located_in", "has_capacity",
    "has_market_share",
}

# 게이트 (4) confidence 임계 (placeholder — 05 §6이 [10]에 위임, ADR 후속 튜닝).
PROMOTION_CONFIDENCE = 0.6

# mention_type 유효 어휘 (설계 02 §2.2 — initial 도메인).
_VALID_MENTION_TYPES = {
    "Person", "Organization", "Location", "Product", "Technology",
    "Event", "Source",
}


@dataclass(frozen=True)
class PromotionResult:
    claim_candidate_id: str
    promote: bool
    status: str  # "promoted" | "quarantined"
    reasons: list[str] = field(default_factory=list)


@dataclass
class Mutation:
    """append-only 승격 이벤트 (03 §7.2 — replay·idempotency)."""

    mutation_id: str
    op: str
    element_ref: str
    idempotency_key: str


class Gate:
    """claim_candidates → promotion/quarantine 게이트 + append-only 이벤트."""

    def __init__(self) -> None:
        self._mutations: list[Mutation] = []
        self._seen: set[str] = set()  # idempotency (03 §7.2, 불변식 §3-6)
        self._results: dict[str, PromotionResult] = {}

    def evaluate(self, c: ClaimCandidate) -> PromotionResult:
        """claim 후보를 검증해 promoted/quarantined 결정 + append-only 이벤트."""
        reasons: list[str] = []

        # (1) schema — 필수·범위.
        if not (0.0 <= c.confidence <= 1.0):
            reasons.append("confidence_out_of_range")
        if not c.doc_id:
            reasons.append("missing_doc_id")
        # (2) provenance — source_span 정상 (03 §8.2, ADR-302).
        if not (0 <= c.char_start < c.char_end):
            reasons.append("invalid_source_span")
        # (3) predicate 폐쇄성 (02 §4-2·§5.1).
        if c.predicate not in CONTROLLED_PREDICATES:
            reasons.append(f"unknown_predicate:{c.predicate}")
        # (4) confidence 임계 (05 §6 게이트 4).
        if c.confidence < PROMOTION_CONFIDENCE:
            reasons.append("low_confidence")
        # Reference 무결성 — subject 미해소 (02 §4-3).
        if not c.subject_id:
            reasons.append("missing_subject")

        promote = not reasons
        self._results[c.claim_candidate_id] = PromotionResult(
            claim_candidate_id=c.claim_candidate_id,
            promote=promote,
            status="promoted" if promote else "quarantined",
            reasons=reasons,
        )

        if promote:
            self._emit(c.claim_candidate_id, op="create_node")
        return self._results[c.claim_candidate_id]

    def evaluate_mention(self, m: Mention,
                         resolved_entity_id: str | None = None) -> PromotionResult:
        """mention 게이트 — span 유효 + 해소 entity + type 유효 → promote(create_node).

        설계 05 §6 mention: provenance(span) ≥ 1, 해소 entity 참조(02 §4-3),
        mention_type 유효. span 없는 mention은 폐기 (05 §1.1).

        `resolved_entity_id`: 해소 결과(ResolvedMention)가 보유한 entity id. 명시 전달
        안 하면 mention.resolved_entity_id를 사용 (prototype에서 해소는 별도 레코드).
        """
        reasons: list[str] = []
        if m.char_start >= m.char_end or m.char_start < 0:
            reasons.append("invalid_span")
        resolved = resolved_entity_id or getattr(m, "resolved_entity_id", None)
        if not resolved:
            reasons.append("missing_resolved_entity")
        if m.mention_type not in _VALID_MENTION_TYPES:
            reasons.append(f"unknown_mention_type:{m.mention_type}")
        if not m.surface_text:
            reasons.append("missing_surface")

        promote = not reasons
        self._results[m.mention_id] = PromotionResult(
            claim_candidate_id=m.mention_id,  # mention_id를 element ref로 재사용.
            promote=promote,
            status="promoted" if promote else "quarantined",
            reasons=reasons,
        )
        if promote:
            self._emit(m.mention_id, op="create_node")
        return self._results[m.mention_id]

    def evaluate_edge(self, e: PossiblySameAsEdge) -> PromotionResult:
        """edge 게이트 — score∈[0,1] + resolution_ref + 무자기 루프 → promote(create_edge).

        설계 02 §3.1(판정 근거 필수)·불변식4-7(weight∈[0,1])·4-5(무순환). 확정/자동
        병합(merge_entity)은 하지 않음 — 승격만 (ADR-507, precision-first).
        """
        reasons: list[str] = []
        if not (0.0 <= e.score <= 1.0):
            reasons.append(f"score_out_of_range:{e.score}")
        if not e.resolution_ref:
            reasons.append("missing_resolution_ref")
        if e.entity_a_id == e.entity_b_id:
            reasons.append("self_loop")
        if e.entity_a_id and e.entity_b_id and (not e.entity_a_id or not e.entity_b_id):
            reasons.append("missing_entity")

        promote = not reasons
        self._results[e.edge_id] = PromotionResult(
            claim_candidate_id=e.edge_id,
            promote=promote,
            status="promoted" if promote else "quarantined",
            reasons=reasons,
        )
        if promote:
            self._emit(e.edge_id, op="create_edge")
        return self._results[e.edge_id]

    def _emit(self, element_ref: str, op: str) -> None:
        """승격 이벤트 append (idempotent). 재구축 가능 (03 §7)."""
        key = f"promote:{element_ref}"
        if key in self._seen:
            return
        self._seen.add(key)
        self._mutations.append(Mutation(
            mutation_id=f"mut-{len(self._mutations) + 1:04d}",
            op=op,
            element_ref=element_ref,
            idempotency_key=key,
        ))

    def mutations(self) -> list[dict]:
        return [
            {"op": m.op, "element_ref": m.element_ref,
             "mutation_id": m.mutation_id, "idempotency_key": m.idempotency_key}
            for m in self._mutations
        ]

    def result(self, claim_candidate_id: str) -> PromotionResult | None:
        return self._results.get(claim_candidate_id)
