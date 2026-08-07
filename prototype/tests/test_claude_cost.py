"""S42 LLM 비용·토큰 집계 (design 10 §1.4, Q5 해소 진행) TDD.

`_AnthropicClient.messages_create`가 응답 `usage`(input/output tokens)를 캡처하고,
`ClaudeJudge`가 판정(LLM 호출)마다 이를 누적해 **토큰·비용을 측정 가능**하게 한다.
실제 LLM 실행(Phase 1) 후 기준선 확정. token→USD 환산은 프로바이더별 placeholder.

- cost_tokens(input/output): LLM 판정 호출 누적.
- cost_usd: 환산 placeholder (input/output per-Mtok).
- backward 호환: usage 없는 fake client는 0 집계 (기존 테스트 무손상).

Atomic TDD: Red → Green.
"""
from __future__ import annotations

import pytest

from orc_citadel.claude_judge import ClaudeJudge


class _FakeClient:
    """usage 제공 fake — usage를 응답에 담는 내용."""
    def __init__(self, responses, last_usage=None):
        self.responses = list(responses)
        self.calls = []
        self.last_usage = {}
        if last_usage:
            self.last_usage = last_usage

    def messages_create(self, model, system, user, max_tokens, temperature):
        self.calls.append({"model": model, "user": user})
        out = self.responses[0]
        self.responses = self.responses[1:]
        # last_usage 는 call 마다 유지 — judge가 호출 후 읽음.
        return out


def _judge(client):
    return ClaudeJudge(client=client)


def test_usage_accumulated_per_call():
    """LLM 호출마다 usage 누적 (input/output tokens)."""
    client = _FakeClient(
        [{"relation": "equivalent", "canonical_text": "x", "confidence": 0.9,
          "rationale": "r"}],
        last_usage={"input_tokens": 150, "output_tokens": 60})
    j = _judge(client)
    j.judge_canonicalization(("clm-a", "clm-b"))
    u = j.usage()
    assert u["input_tokens"] == 150
    assert u["output_tokens"] == 60
    assert u["calls"] == 1


def test_usage_multiple_calls():
    """여러 판정 호출 → 누적."""
    client = _FakeClient(
        [{"relation": "equivalent", "canonical_text": "x", "confidence": 0.9, "rationale": "r"},
         {"relation": "unrelated", "canonical_text": "y", "confidence": 0.8, "rationale": "s"}],
        last_usage={"input_tokens": 100, "output_tokens": 40})
    j = _judge(client)
    j.judge_canonicalization(("a", "b"))
    j.judge_canonicalization(("c", "d"))
    u = j.usage()
    assert u["input_tokens"] == 200
    assert u["output_tokens"] == 80
    assert u["calls"] == 2


def test_usage_zero_when_stub():
    """client 없음(stub 폴백) → usage 0, calls 0."""
    j = ClaudeJudge(client=None)  # DeterministicStub.
    j.judge_canonicalization(("a", "b"))
    u = j.usage()
    assert u["input_tokens"] == 0 and u["output_tokens"] == 0
    assert u["calls"] == 0


def test_usage_zero_when_no_usage_field():
    """usage 없는 fake client → 0 집계 (backward 호환, 기존 테스트 무손상)."""
    client = _FakeClient([{"relation": "equivalent", "canonical_text": "x",
                           "confidence": 0.9, "rationale": "r"}])
    j = _judge(client)
    j.judge_canonicalization(("a", "b"))
    assert j.usage()["input_tokens"] == 0
    assert j.usage()["output_tokens"] == 0


def test_cost_usd_placeholder():
    """cost_usd — token→USD 환산 placeholder (input/output per-Mtok)."""
    client = _FakeClient(
        [{"relation": "equivalent", "canonical_text": "x", "confidence": 0.9, "rationale": "r"}],
        last_usage={"input_tokens": 1000, "output_tokens": 500})
    j = _judge(client)
    j.judge_canonicalization(("a", "b"))
    c = j.cost_usd(input_per_mtok=3.0, output_per_mtok=15.0)
    # 1000/1e6 * 3 + 500/1e6 * 15 = 0.003 + 0.0075 = 0.0105.
    assert c == pytest.approx(0.003 + 0.0075)


def test_cost_usd_default_rates():
    """기본 환산율로 cost_usd."""
    client = _FakeClient(
        [{"relation": "equivalent", "canonical_text": "x", "confidence": 0.9, "rationale": "r"}],
        last_usage={"input_tokens": 1_000_000, "output_tokens": 100_000})
    j = _judge(client)
    j.judge_canonicalization(("a", "b"))
    c = j.cost_usd()
    # 기본 placeholder 환산율 (문서에 정의) 사용.
    assert c == pytest.approx(j._IN_PER_MT * 1_000_000 / 1e6 + j._OUT_PER_MT * 100_000 / 1e6)
