"""S21 실제 LLM 주입 — ClaudeJudge (07 §7, 05 §4.2·§5.2) TDD.

Anthropic Claude로 canonicalization(7라벨)·contradiction(verdict) 판정을 강제 JSON
schema로 수행. 출력 역직렬화·검증(validate_* 재사용), 실패 시 DeterministicStub 폴백.
ANTHROPIC 호출은 모의(mock)로 오프라인 검증 — 모델/프롬프트 교체 자유.
"""
from __future__ import annotations

import pytest

from orc_citadel.claude_judge import ClaudeJudge, _CONTRADICTION_SCHEMA_INSTRUCTION
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


def test_contradiction_prompt_specifies_dict_evidence_spans():
    """contradiction 스키마 프롬프트는 05 §5.2 의 evidence_spans dict 구조를 명시.

    무비용 LLM 실측(SLO-06)에서 contradiction verdict 가 evidence_spans 를 str
    리스트로 반환해 스키마 검증 실패가 체계적으로 발생한 원인이 프롬프트의 모호한
    '<지지 구간>' 표기였음. 검증 함수(`validate_contradiction_verdict`)는 dict 항목을
    요구(05 §5.2 line 158) 하므로, 프롬프트가 그 계약을 LLM 에 명확히 전달해야 한다 —
    설계-프롬프트 정합 회귀 고정.
    """
    p = _CONTRADICTION_SCHEMA_INSTRUCTION
    # dict 필드가 스키마에 명시되어 있어야 한다(설계 05 §5.2 dict 구조).
    assert '"doc_id"' in p and '"char_start"' in p and '"char_end"' in p
    assert 'evidence_spans' in p
    # "dict 객체" 요구가 명시되어야 한다.
    assert 'dict 객체' in p


# --- max_tokens: reasoning 모델 수용 (A30) --------------------------------------

class _CaptureMaxTokens(_FakeClient):
    """max_tokens 캡처 — judge 호출 예산 검증."""

    def messages_create(self, model, system, user, max_tokens, temperature):
        self.max_tokens = max_tokens
        return super().messages_create(model, system, user, max_tokens, temperature)


_VALID_CANONICAL = {"relation": "equivalent", "canonical_text": "t",
                    "confidence": 0.9, "rationale": "r"}


def test_judge_max_tokens_default_covers_reasoning(monkeypatch):
    """기본 max_tokens ≥ 2048 — reasoning 토큰(1200+) 소비 수용 (A29 실측).

    glm-4.7-flash 등 reasoning 모델은 completion 예산에서 reasoning 토큰을
    소비해 512 로는 본문이 잘렸다 (SLO-06 validation fail 근본 원인 중 하나).
    """
    monkeypatch.delenv("LLM_MAX_TOKENS", raising=False)
    client = _CaptureMaxTokens([_VALID_CANONICAL])
    j = ClaudeJudge(client=client)
    j.judge_canonicalization(("clm-a", "clm-b"))
    assert client.max_tokens >= 2048


def test_judge_max_tokens_env_override(monkeypatch):
    """LLM_MAX_TOKENS 환경으로 판정 예산 조정 (배포 환경별 모델 소유)."""
    monkeypatch.setenv("LLM_MAX_TOKENS", "4096")
    client = _CaptureMaxTokens([_VALID_CANONICAL])
    j = ClaudeJudge(client=client)
    j.judge_canonicalization(("clm-a", "clm-b"))
    assert client.max_tokens == 4096


def test_judge_max_tokens_bad_env_falls_back(monkeypatch):
    """비정수 LLM_MAX_TOKENS → 기본값 폴백 (설정 오류가 판정을 죽이지 않는다)."""
    monkeypatch.setenv("LLM_MAX_TOKENS", "many")
    client = _CaptureMaxTokens([_VALID_CANONICAL])
    j = ClaudeJudge(client=client)
    j.judge_canonicalization(("clm-a", "clm-b"))
    assert client.max_tokens >= 2048
