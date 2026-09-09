"""LLM 조사 종합 (W2 — on-request·read-only, 07 §9.3 evidence-first 유지).

결정적 Synthesizer 의 템플릿 문장을 LLM 생성 문장으로 대체하는 표현 계층 —
근거는 zone 실측 claim rows 뿐이고, LLM 은 제공 목록 밖의 사실을 실을 수 없다:

- asserted 문장의 claim_ref 는 제공된 claim_id 화이트리스트 강제 — 목록 밖
  ref·허용 외 modality·빈 텍스트는 폐기(discarded) 되고 응답에 실리지 않는다.
- prediction/opinion 은 무출처 허용(07 §9.3)하되 claim_ref 는 제거(목록 밖
  ref 가 흘러들지 않게).
- LLM 오류·미설정은 예외 전파 없이 None — 호출측이 결정적 경로를 유지한다.
- 판정은 mock client 로 격리 (실 LLM 은 수동 E2E) — claude_judge 와 동일 정책.
"""

from __future__ import annotations

from orc_citadel.llm_investigation import LlmSynthesis, evidence_rows


class FakeClient:
    model = "fake-model"
    provider = "fake"

    def __init__(self, payload=None, error=False):
        self._payload = payload
        self._error = error
        self.last_usage = {"input_tokens": 100, "output_tokens": 42}
        self.calls = []

    def messages_create(self, model, system, user, max_tokens, temperature):
        self.calls.append({"system": system, "user": user})
        if self._error:
            raise RuntimeError("simulated provider failure")
        return self._payload


EVIDENCE = [
    {"claim_id": "clm-1", "predicate": "announces", "object": "x", "surface": "s1"},
    {"claim_id": "clm-2", "predicate": "supplies", "object": "y", "surface": "s2"},
]


def test_synthesize_enforces_claim_ref_whitelist():
    """목록 밖 claim_ref·무출처 asserted·이상 modality 는 폐기 — 지어낸 근거 차단."""
    payload = {"statements": [
        {"text": "정상 문장", "modality": "asserted", "claim_ref": "clm-1"},
        {"text": "지어낸 근거", "modality": "asserted", "claim_ref": "clm-fake"},
        {"text": "무출처 단정", "modality": "asserted"},
        {"text": "허용 외", "modality": "fact", "claim_ref": "clm-2"},
        {"text": "전망", "modality": "prediction", "claim_ref": "clm-fake"},
    ]}
    out = LlmSynthesis(FakeClient(payload)).synthesize("NVIDIA", "질문", EVIDENCE)
    assert [s["text"] for s in out["statements"]] == ["정상 문장", "전망"]
    # prediction 의 목록 밖 claim_ref 는 제거 — 무출처 전망으로만 실린다.
    assert out["statements"][1]["claim_ref"] is None
    assert out["discarded"] == 3


def test_synthesize_captures_usage_and_model():
    payload = {"statements": [
        {"text": "t", "modality": "asserted", "claim_ref": "clm-1"}]}
    out = LlmSynthesis(FakeClient(payload)).synthesize("N", "q", EVIDENCE)
    assert out["usage"] == {"input_tokens": 100, "output_tokens": 42}
    assert out["model"] == "fake-model" and out["provider"] == "fake"


def test_synthesize_prompt_carries_only_given_evidence():
    """프롬프트 user 페이로드는 제공 evidence·질문뿐 — zone 전체 노출 없음."""
    client = FakeClient({"statements": []})
    LlmSynthesis(client).synthesize("NVIDIA", "신제품 조사", EVIDENCE)
    user = client.calls[0]["user"]
    assert "clm-1" in user and "clm-2" in user and "신제품 조사" in user


def test_synthesize_provider_failure_returns_none():
    """LLM 오류 → None (예외 전파 없음) — 호출측 결정적 폴백."""
    assert LlmSynthesis(FakeClient(error=True)).synthesize(
        "N", "q", EVIDENCE) is None


def test_synthesize_schema_mismatch_is_empty_not_fabricated():
    """비스키마 응답 → 빈 statements (지어내기 금지, §6.2)."""
    out = LlmSynthesis(FakeClient({"junk": 1})).synthesize("N", "q", EVIDENCE)
    assert out["statements"] == []


def test_available_false_without_client():
    assert LlmSynthesis(client=False).available() is False


def test_evidence_rows_from_assertions_deterministic():
    """근거는 subject 의 assertions 승격 claim 만 — 결정적 순서·상한."""
    class Z:
        def assertions(self):
            return [{"subject_id": "org-1", "claim_id": "clm-b"},
                    {"subject_id": "org-1", "claim_id": "clm-a"},
                    {"subject_id": "org-2", "claim_id": "clm-x"}]

        def claims(self):
            return [{"claim_candidate_id": c, "predicate": "p",
                     "object_literal": "o", "object_id": None,
                     "surface_fragment": "s"}
                    for c in ("clm-a", "clm-b", "clm-x")]

    rows = evidence_rows(Z(), "org-1")
    assert [r["claim_id"] for r in rows] == ["clm-a", "clm-b"]
    assert all(set(r) >= {"claim_id", "predicate", "object", "surface"}
               for r in rows)
    assert len(evidence_rows(Z(), "org-1", cap=1)) == 1
