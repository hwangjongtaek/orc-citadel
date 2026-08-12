"""S7 Claim 추출 — 결정적 규칙 기반 (설계 05 §3, 02 §2.4·§5.1).

해소된 entity·mention 위에서 **결정적 predicate 규칙**(정규식)으로 하가 claim 후보를
추출한다. LLM 텐츠 기반 추출·canonicalization(§4)·contradiction(§5)은 후속 — 여기선
규칙·사전으로 판정 가능한 것만 (05 §5 deterministic-first, precision 우선).

- source_span은 **clean text 축** `(seg_order, char_start, char_end)` (ADR-302, provenance
  03 §8.2). raw HTML 축 역매핑은 일반 케이스에서 후속 (04 §3.4).
- subject_id는 해소된 mention의 resolved entity (02 §4-3 Reference 무결성).
- claim_candidate_id는 결정적 (doc_id, seg_order, span, predicate) hash (03 §5).
- 산출물은 `claim_candidates`(03 §4.2) 테이블의 `status=candidate`로 저장된다.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from .normalize import Segment
from .parse import ParsedDoc
from .resolve import Entity, ResolvedMention

# 추출 규칙·파라미터 식별 — 변경 시 bump (03 §5, 재추출·idempotency).
CLAIM_EXTRACTION_VERSION = "c1"
ONTOLOGY_VERSION = "1.0.0"
EXTRACTION_MODEL = "rule-claim-1"


@dataclass(frozen=True)
class ClaimCandidate:
    claim_candidate_id: str
    doc_id: str
    predicate: str
    subject_id: str
    object_id: str | None
    object_literal: object | None
    modality: str
    polarity: str
    confidence: float
    seg_order: int
    char_start: int
    char_end: int
    surface_fragment: str
    event_type_hint: str | None = None
    status: str = "candidate"
    # §8.2 extraction_record id[] — authoritative graph 진입 전 ADR-305 게이트가 요구.
    # 추출 단계가 record를 영속하고 이 ref를 채운다. 기본값 빈 list.
    provenance_ref: list | None = None

    def to_row(self) -> dict:
        """curated_zone claim_candidates 테이블(row)로 변환 (03 §4.2)."""
        return {
            "claim_candidate_id": self.claim_candidate_id,
            "doc_id": self.doc_id,
            "predicate": self.predicate,
            "subject_id": self.subject_id,
            "object_id": self.object_id,
            "object_literal": self.object_literal,
            "modality": self.modality,
            "polarity": self.polarity,
            "confidence": self.confidence,
            "seg_order": self.seg_order,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "surface_fragment": self.surface_fragment,
            "event_type_hint": self.event_type_hint,
            "status": self.status,
            "ontology_version": ONTOLOGY_VERSION,
            "extraction_model": EXTRACTION_MODEL,
        }


def claim_id_for(doc_id: str, seg_order: int, start: int, end: int, predicate: str) -> str:
    """결정적 claim_candidate_id — (doc, seg, span, predicate) hash (03 §5)."""
    key = f"{doc_id}:{seg_order}:{start}:{end}:{predicate}"
    return "clm-" + hashlib.sha256(key.encode()).hexdigest()[:24]


# 결정적 predicate 규칙: (정규식, predicate, modality, event_type_hint).
# 도메인 초기 규칙 (02 §5.1, prototype 배정 — 확장은 규칙 추가).
_PREDICATE_RULES: list[tuple[re.Pattern, str, str, str | None]] = [
    # earnings/이벤트 발표 — conference call/webcast
    (re.compile(r"(?:will host|hosts?)\s+a conference call", re.I),
     "announces", "asserted", "earnings"),
    (re.compile(r"conference call", re.I), "announces", "asserted", "earnings"),
    (re.compile(r"will\s+be\s+webcast|webcast", re.I), "announces", "asserted", "earnings"),
    # 제품·기술 역량 — powers/enables
    (re.compile(r"\bpower(s|ed)?\b", re.I), "announces", "asserted", "product_launch"),
    (re.compile(r"\benables?\b", re.I), "announces", "asserted", "product_launch"),
    # 공급망 제조 — produce/suppl/manufactur (02 §5.1 반도체·데이터센터 공급망).
    (re.compile(r"\b(produces|produce|manufactur\w*|suppl\w*|fabricat\w*|makes)\b", re.I),
     "supplies", "asserted", "manufacturing"),
    (re.compile(r"\b(supplies|provides|delivers)\s+(chips?|processors?|gpus?|semiconductor\w*)", re.I),
     "supplies", "asserted", "manufacturing"),
    # 공급망 파트너십/수급 계약 — partnership/agreement (02 §5.1 협력·공급관계).
    (re.compile(r"\b(partnership|strategic\s+partnership|agreement|alliance)\b", re.I),
     "partners", "asserted", "partnership"),
]


def _subject_for(seg: Segment, resolved: list[ResolvedMention]) -> tuple[str, str]:
    """segment 내 첫 해소 mention의 entity_id·surface (Reference 무결성, 02 §4-3).

    seg.text는 기존 mention span(clean text 축)과 일치하므로, resolved mention들 중
    segment offset 안에 surface가 등장하는 첫 것의 entity를 반환. 없으면 "".
    """
    for rm in resolved:
        if rm.resolved_entity_id is None:
            continue
        if rm.mention.surface_text in seg.text:
            return rm.resolved_entity_id, rm.mention.surface_text
    return "", ""


def _object_for(seg: Segment, resolved: list[ResolvedMention],
                subject_id: str, match_end: int) -> str | None:
    """정규 삼항의 object — predicate 매치 이후 첫 해소 엔티티 (공급망 관계).

    "TSMC supplies NVIDIA" → subject=TSMC, predicate 뒤 NVIDIA 를 object 로. subject 와
    다른, predicate 매치 span(match_end) 이후에 surface 가 등장하는 첫 해소 entity 를
    반환 (02 §4-3 Reference 무결성: object 도 해소되어야 엣지로 배선). 없으면 None.
    """
    for rm in resolved:
        if rm.resolved_entity_id is None:
            continue
        if rm.resolved_entity_id == subject_id:
            continue
        # predicate match 이후 위치에 있다면 object.
        if rm.mention.char_start >= match_end:
            return rm.resolved_entity_id
    return None


def extract_claims(
    doc_id: str,
    segments: list[Segment],
    resolved: list[ResolvedMention],
    entities: dict[str, Entity],
) -> list[ClaimCandidate]:
    """세그먼트에서 결정적 predicate 규칙으로 claim 후보를 추출.

    - 각 segment 문장에 규칙 매칭 → predicate/event_type 확정, subject는 segment 내
      해소 mention에서. object는 predicate 이후 첫 해소 엔티티(정규 삼항 — 공급망 엣지용).
      없으면 object_literal=null (prototype 최소).
    - surface_fragment: 매칭된 최초 형태소까지의 segment 텍스트 (source span slice).
    - 결정적 id, status=candidate.
    """
    claims: list[ClaimCandidate] = []
    for order, seg in enumerate(segments):
        text = seg.text
        seen_predicates: set[str] = set()
        for pat, predicate, modality, event_type in _PREDICATE_RULES:
            m = pat.search(text)
            if not m:
                continue
            if predicate in seen_predicates:
                continue  # 동일 segment 내 predicate당 첫 매칭만 (중복 방지, precision)
            seen_predicates.add(predicate)
            subject_id, _ = _subject_for(seg, resolved)
            if not subject_id:
                # subject 미해소 → Reference 무결성 위반 (02 §4-3). promote 대상 아님 —
                # 규칙 단계에서 폐기 (precision-first, 05 §5).
                continue
            start, end = m.start(), m.end()
            fragment = text[start:end]  # provenance span slice와 정확 일치
            object_id = _object_for(seg, resolved, subject_id, end)
            claims.append(ClaimCandidate(
                claim_candidate_id=claim_id_for(doc_id, order, start, end, predicate),
                doc_id=doc_id,
                predicate=predicate,
                subject_id=subject_id,
                object_id=object_id,
                object_literal=None,
                modality=modality,
                polarity="positive",
                confidence=0.8,  # 규칙 기반 고정 (튜닝은 10소유)
                seg_order=order,
                char_start=start,
                char_end=end,
                surface_fragment=fragment,
                event_type_hint=event_type,
                status="candidate",
            ))
    # 결정적 정렬 (순서 일정).
    claims.sort(key=lambda c: (c.seg_order, c.char_start, c.predicate))
    return claims
