"""S22 LLM 판정 하이브리드 통합 (설계 05 §4.2·§5.2) TDD.

결정적-우선 원칙(05 §5/§6, blueprint §9.2): 규칙이 판정 가능한 것은 LLM에 보내지 않는다.
`canonicalize_claims(..., judge=None)`·`find_conflict_candidates(..., judge=None)`가
**미결 쌍에만** 선택적 `LlmJudge`를 주입한다.
- judge 미주입 → S9/S10과 동일 결정적 결과 (재생성 안전, 03 §5).
- judge 주입 → 미결 쌍만 LLM 판정 반영, `judged_by="llm"` 구분.
"""
from __future__ import annotations

from orc_citadel.canonicalize import canonicalize_claims
from orc_citadel.contradiction import find_conflict_candidates
from orc_citadel.extract_claims import ClaimCandidate


def _c(claim_id: str, pred: str, subj: str, seg: int = 0, start: int = 0,
       end: int = 4, frag: str = "x", polarity: str = "positive",
       obj: str | None = None) -> ClaimCandidate:
    return ClaimCandidate(
        claim_candidate_id=claim_id, doc_id="doc-1", predicate=pred,
        subject_id=subj, object_id=obj, object_literal=None,
        modality="asserted", polarity=polarity, confidence=0.8,
        seg_order=seg, char_start=start, char_end=end, surface_fragment=frag,
        event_type_hint=None, status="candidate",
    )


class _RecordJudge:
    """모의 LlmJudge — 호출된 쌍 기록, 미리 정한 판정 dict 반환."""

    def __init__(self, canonical=None, contradiction=None):
        self.canonical = canonical
        self.contradiction = contradiction
        self.canonical_calls = []
        self.contradiction_calls = []

    def judge_canonicalization(self, pair):
        self.canonical_calls.append(tuple(pair))
        return self.canonical

    def judge_contradiction(self, pair):
        self.contradiction_calls.append(tuple(pair))
        return self.contradiction


# ---------------------------------------------------------------- canonicalize

def test_canonical_llm_merges_undecided_pair():
    """결정적 미결 쌍(다른 표면형)을 LLM `equivalent`로 병합 — judge 주입 시."""
    claims = [
        _c("clm-a", "announces", "org-1", seg=0, start=0, end=4, frag="coproc"),
        _c("clm-b", "announces", "org-1", seg=3, start=0, end=5, frag="accelerator"),
    ]
    judge = _RecordJudge(canonical={
        "relation": "equivalent", "canonical_text": "CoWoS 확장", "confidence": 0.9,
        "rationale": "동일 subject·predicate·의미", "judged_by": "llm",
    })
    cc = canonicalize_claims(claims, judge=judge)
    # 미결 쌍이 LLM으로 병합됨 → 한 CanonicalClaim.
    assert len(cc) == 1
    assert set(cc[0].member_claim_ids) == {"clm-a", "clm-b"}


def test_canonical_rule_decided_pairs_no_llm():
    """결정적 `equivalent`(같은 표면형) 쌍은 LLM 호출하지 않음 (결정적-우선)."""
    claims = [
        _c("clm-a", "announces", "org-1", seg=0, start=0, end=4, frag="power"),
        _c("clm-b", "announces", "org-1", seg=5, start=0, end=4, frag="power"),
    ]
    judge = _RecordJudge()
    canonicalize_claims(claims, judge=judge)
    assert judge.canonical_calls == []  # 결정적 — LLM 무호출


def test_canonical_llm_undecided_separate_when_not_equivalent():
    """LLM `unrelated` → 미결 쌍은 병합하지 않음 (후보 유지)."""
    claims = [
        _c("clm-a", "announces", "org-1", seg=0, start=0, end=4, frag="coproc"),
        _c("clm-b", "announces", "org-1", seg=3, start=0, end=5, frag="accelerator"),
    ]
    judge = _RecordJudge(canonical={
        "relation": "unrelated", "canonical_text": "", "confidence": 0.0,
        "rationale": "무관", "judged_by": "llm",
    })
    cc = canonicalize_claims(claims, judge=judge)
    assert len(cc) == 2  # 미병합
    assert set(judge.canonical_calls) == {("clm-a", "clm-b")}


def test_canonical_no_judge_deterministic():
    """judge 미주입 → S9와 동일 (결정성·재생성 안전, 03 §5)."""
    claims = [
        _c("clm-a", "announces", "org-1", seg=0, start=0, end=4, frag="host"),
        _c("clm-b", "announces", "org-1", seg=3, start=0, end=5, frag="powr"),
    ]
    assert len(canonicalize_claims(claims)) == 2  # 미병합 — 미결 그대로


# -------------------------------------------------------------- contradiction

def test_contradiction_llm_confirms_real_conflict():
    """결정적 후보 쌍을 LLM이 real_conflict로 확정 (기본 유지 + judged_by=llm)."""
    a = _c("clm-a", "depends_on", "org-1", polarity="positive")
    b = _c("clm-b", "depends_on", "org-1", polarity="negative")
    judge = _RecordJudge(contradiction={
        "verdict": "real_conflict", "conflict_type": "value_conflict",
        "rationale": "충돌", "confidence": 0.9, "evidence_spans": [],
        "judged_by": "llm",
    })
    cc = find_conflict_candidates([a, b], judge=judge)
    assert len(cc) == 1
    assert cc[0].judged_by == "llm"

    # LLM에 해당 쌍 전달됨.
    assert ("clm-a", "clm-b") in judge.contradiction_calls or \
           ("clm-b", "clm-a") in judge.contradiction_calls


def test_contradiction_llm_not_conflict_removes_candidate():
    """LLM `not_conflict` → 결정적 후보 제거 (허위 모순 감소, precision)."""
    a = _c("clm-a", "has_market_share", "org-1", obj="org-a")
    b = _c("clm-b", "has_market_share", "org-1", obj="org-b")
    judge = _RecordJudge(contradiction={
        "verdict": "not_conflict", "conflict_type": None,
        "rationale": "시간차/범위차", "confidence": 0.85, "evidence_spans": [],
        "judged_by": "llm",
    })
    cc = find_conflict_candidates([a, b], judge=judge)
    assert cc == []  # 모순 아님 — 후보 제거


def test_contradiction_no_judge_deterministic():
    """judge 미주입 → S10과 동일 (결정성·재생성 안전)."""
    a = _c("clm-a", "depends_on", "org-1", polarity="positive")
    b = _c("clm-b", "depends_on", "org-1", polarity="negative")
    cc = find_conflict_candidates([a, b])
    assert len(cc) == 1
    assert cc[0].judged_by == "pipeline"
