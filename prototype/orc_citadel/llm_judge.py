"""S15 LLM 판정 — 구조화 I/O 계약·검증·클라이언트 경계 (설계 05 §4.2·§5.2).

LLM은 결정적 규칙이 못 결정한 애매 쌍만 판정한다 (deterministic-first, 05 §5·§6).
여기서는 LLM 호출의 **구조화 계약**을 정의하고:
- `validate_canonical_verdict` — §4.2 7라벨, 필수 필드, confidence ∈[0,1] 검증
- `validate_contradiction_verdict` — §5.2 verdict/conflict_type/rationale/confidence/
  evidence_spans 검증
- `LlmJudge` 프로토콜 — canonicalization/contradiction 판정 경계
- `DeterministicStub` — 외부 의존(키·네트워크) 부재 시 계약-유효 결정적 출력 (오프라인)

검증 실패 시 `None` 반환 → 호출 측이 후보를 유지 (자동 병합 금지, ADR-507).
실제 LLM API(claude 등)는 LlmJudge를 구현해 주입한다 (외부 의존 — 이 모듈은 격리).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

# §4.2 canonicalization 7라벨 (ADR-503).
CANONICAL_RELATIONS = {
    "equivalent", "more_specific", "more_general", "supports",
    "contradicts", "unrelated", "temporally_superseded",
}
# §5.2 verdict·conflict_type (ADR-504).
CONTRADICTION_VERDICTS = {"real_conflict", "temporal", "scope", "not_conflict"}
CONFLICT_TYPES = {"value_conflict", "temporal", "scope"}


@dataclass(frozen=True)
class CanonicalVerdict:
    relation: str
    canonical_text: str
    confidence: float
    rationale: str
    judged_by: str = "llm"


@dataclass(frozen=True)
class ContradictionVerdict:
    verdict: str
    conflict_type: str | None
    rationale: str
    confidence: float
    evidence_spans: tuple = field(default_factory=tuple)
    judged_by: str = "llm"


def validate_canonical_verdict(d: dict) -> CanonicalVerdict | None:
    """§4.2 출력 검증 — 유효하지 않으면 None (후보 유지)."""
    if not isinstance(d, dict):
        return None
    rel = d.get("relation")
    if rel not in CANONICAL_RELATIONS:
        return None
    text = d.get("canonical_text")
    conf = d.get("confidence")
    # canonical_text는 문자열이면 빈 값 허용 (unrelated/병합 없는 라벨).
    if not isinstance(text, str):
        return None
    if not isinstance(conf, (int, float)) or not (0.0 <= conf <= 1.0):
        return None
    return CanonicalVerdict(
        relation=rel, canonical_text=text, confidence=float(conf),
        rationale=d.get("rationale", ""),
    )


def validate_contradiction_verdict(d: dict) -> ContradictionVerdict | None:
    """§5.2 출력 검증 — verdict/conflict_type/rationale/confidence 범위."""
    if not isinstance(d, dict):
        return None
    v = d.get("verdict")
    if v not in CONTRADICTION_VERDICTS:
        return None
    ctype = d.get("conflict_type")
    if ctype is not None and ctype not in CONFLICT_TYPES:
        return None
    conf = d.get("confidence")
    rationale = d.get("rationale")
    if not isinstance(conf, (int, float)) or not (0.0 <= conf <= 1.0):
        return None
    if not isinstance(rationale, str) or not rationale.strip():  # §5.3 필수.
        return None
    spans = tuple(tuple(s.items()) for s in (d.get("evidence_spans") or []))
    return ContradictionVerdict(
        verdict=v, conflict_type=ctype, rationale=rationale, confidence=float(conf),
        evidence_spans=spans,
    )


class LlmJudge(Protocol):
    """canonicalization/contradiction 판정 경계 (구조화 출력)."""

    def judge_canonicalization(self, pair: tuple[str, str]) -> dict:
        ...

    def judge_contradiction(self, pair: tuple[str, str]) -> dict:
        ...


class DeterministicStub:
    """외부 의존 부재 시 계약-유효 결정적 출력 (오프라인 검증·격리).

    결정적 규칙이 판정 못 한 쌍에 대해: canonicalization은 `unrelated`,
    contradiction은 `not_conflict` — 병합/반박을 만들지 않는 안전 기본값 (신중).
    """

    def judge_canonicalization(self, pair: tuple[str, str]) -> dict:
        return {
            "relation": "unrelated",
            "canonical_text": "",
            "confidence": 0.0,
            "rationale": "deterministic stub: 규칙 미결 쌍 — 자동 병합 없음 (ADR-507)",
            "judged_by": "stub",
        }

    def judge_contradiction(self, pair: tuple[str, str]) -> dict:
        return {
            "verdict": "not_conflict",
            "conflict_type": None,
            "rationale": "deterministic stub: 모순 미확정 — 후보 유지",
            "confidence": 0.0,
            "evidence_spans": [],
            "judged_by": "stub",
        }
