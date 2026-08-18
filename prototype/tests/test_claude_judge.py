"""S21 실제 LLM 주입 — ClaudeJudge (07 §7, 05 §4.2·§5.2) TDD.

Anthropic Claude로 canonicalization(7라벨)·contradiction(verdict) 판정을 강제 JSON
schema로 수행. 출력 역직렬화·검증(validate_* 재사용), 실패 시 DeterministicStub 폴백.
ANTHROPIC 호출은 모의(mock)로 오프라인 검증 — 모델/프롬프트 교체 자유.
"""
from __future__ import annotations

import pytest

from orc_citadel.claude_judge import ClaudeJudge
from orc_citadel.llm_judge import DeterministicStub


class _FakeClient:
    """모의 Anthropic — 요청 body 기록, 미리 정한 응답 반환."""

    def __init__(self, responses):
        self.responses = list(responses)  # (url, system, user) → output dict
        self.calls = []

    def messages_create(self, model, system, user, max_tokens, temperature):
        self.calls.append({"model": model, "user": user})
        # responses에서 판정 dict 반환.
        out = self.responses[0]
        self.responses = self.responses[1:]
        return out


def _judge(client):
    return ClaudeJudge(client=client)


def test_claude_judge_canonical_valid():
    """valid canonicalization 판정 반환 (7라벨·필드)."""
    client = _FakeClient([{"relation": "equivalent", "canonical_text": "TSMC는 확장한다.",
                           "confidence": 0.9, "rationale": "동일 subject·predicate·window"}])
    j = _judge(client)
    v = j.judge_canonicalization(("clm-a", "clm-b"))
    assert v["relation"] == "equivalent"
    assert v["confidence"] == 0.9
    # version tuple 부착 (07 §6.1).
    assert "model_id" in v and "prompt_template_hash" in v
    assert v["model_provider"] == "anthropic"


def test_claude_judge_contradiction_valid():
    """valid contradiction verdict 반환."""
    client = _FakeClient([{"verdict": "real_conflict", "conflict_type": "value_conflict",
                           "rationale": "서로 다른 값", "confidence": 0.8,
                           "evidence_spans": []}])
    j = _judge(client)
    v = j.judge_contradiction(("clm-a", "clm-b"))
    assert v["verdict"] == "real_conflict"
    assert v["conflict_type"] == "value_conflict"


def test_invalid_output_returns_none():
    """invalid 스키마 output → None (후보 유지, 07 §7 quarantine 정합)."""
    client = _FakeClient([{"relation": "banana"}] )
    j = _judge(client)
    assert j.judge_canonicalization(("a", "b")) is None


def test_prompt_sent_includes_pair():
    """프롬프트에 판정 대상 쌍(claim) 포함."""
    client = _FakeClient([{"relation": "unrelated", "canonical_text": "", "confidence": 0.0,
                           "rationale": "no relation"}])
    j = _judge(client)
    j.judge_canonicalization(("clm-a", "clm-b"))
    assert client.calls[0]["user"]  # 대상 포함


def test_fallback_on_client_error():
    """API 예외 → DeterministicStub 안전 폴백 (외부 의존 격리)."""
    class _Boom:
        def messages_create(self, *a, **k):
            raise RuntimeError("api down")

    j = _judge(_Boom())
    # canonical → stub(계약-유효), contradiction → stub.
    c = j.judge_canonicalization(("a", "b"))
    assert c["relation"] == "unrelated"  # stub 기본
    ct = j.judge_contradiction(("a", "b"))
    assert ct["verdict"] == "not_conflict"


def test_uses_configured_model():
    """요청에 모델 id(Alias/L4) 전달."""
    client = _FakeClient([{"relation": "unrelated", "canonical_text": "", "confidence": 0.0,
                           "rationale": ""}])
    j = _judge(client)
    j.judge_canonicalization(("a", "b"))
    assert client.calls[0]["model"]  # 지정 모델


# --- Phase 6: SLO-06 schema 검증 관측 배선 (design 11 §2.3) ---


def test_canonical_verdict_feeds_slo06_schema_log():
    """canonical verdict 검증 통과/실패 → SLO-06 schema 로그 기록."""
    from orc_citadel.slo_observation_log import SloObservationLog
    from orc_citadel.slo_metrics_harness import schema_pass_rate

    log = SloObservationLog()
    # valid 1건 + invalid 1건 (검증 2회).
    client = _FakeClient([
        {"relation": "equivalent", "canonical_text": "TSMC는 확장한다.",
         "confidence": 0.9, "rationale": "동일"},
        {"relation": "banana"},  # invalid → validate None
    ])
    j = ClaudeJudge(client=client, slo_log=log)
    assert j.judge_canonicalization(("a", "b")) is not None
    assert j.judge_canonicalization(("c", "d")) is None
    res = schema_pass_rate(log.schema_results())
    assert res["measured"] is True
    assert res["n_total"] == 2 and res["pass_rate"] == 0.5


def test_contradiction_verdict_feeds_slo06_schema_log():
    """contradiction verdict 검증 통과/실패 → SLO-06 schema 로그."""
    from orc_citadel.slo_observation_log import SloObservationLog
    from orc_citadel.slo_metrics_harness import schema_pass_rate

    log = SloObservationLog()
    client = _FakeClient([
        {"verdict": "real_conflict", "conflict_type": "value_conflict",
         "rationale": "값 충돌", "confidence": 0.8, "evidence_spans": []},
        {"verdict": "nope"},  # invalid
    ])
    j = ClaudeJudge(client=client, slo_log=log)
    assert j.judge_contradiction(("a", "b")) is not None
    assert j.judge_contradiction(("c", "d")) is None
    res = schema_pass_rate(log.schema_results())
    assert res["n_total"] == 2 and res["pass_rate"] == 0.5


def test_stub_fallback_not_logged_as_schema():
    """스텁 폴백(LLM 미검증)은 SLO-06 계수에서 제외 — 빈 로그 → not-measured."""
    from orc_citadel.slo_observation_log import SloObservationLog
    from orc_citadel.slo_metrics_harness import schema_pass_rate

    log = SloObservationLog()
    j = ClaudeJudge(client=None, slo_log=log)  # 오프라인 → stub 폴백
    v = j.judge_canonicalization(("a", "b"))
    assert v is not None  # stub 반환
    assert log.schema_results() == []  # 검증 기록 없음
    assert schema_pass_rate(log.schema_results())["measured"] is False
