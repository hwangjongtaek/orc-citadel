"""프로바이더 추상 계층 — OpenRouter·LiteLLM(OpenAI-compatible) 세팅 TDD.

OpenRouter와 LiteLLM proxy는 둘 다 OpenAI-compatible `/chat/completions` 엔드포인트를
제공하므로, 하나의 httpx 기반 어댑터(`OpenAICompatibleClient`)로 두 프로바이더를 모두
커버한다 (신규 의존성 0 — httpx 는 이미 있어 `messages_create` 와 동일 시그니처).

`build_llm_client()` 는 다른 백엔드(`build_neo4j_driver`/`build_minio_client`/
`build_dsn`) 와 동일한 **명시적 환경 config** 패턴으로 프로바이더를 선택한다:
  LLM_PROVIDER   = "anthropic" | "openrouter" | "litellm"
  LLM_MODEL      = 모델명 (예: openrouter "anthropic/claude-3.5-sonnet", litellm proxy)
  LLM_API_KEY    = API 키
  LLM_BASE_URL   = OpenRouter: https://openrouter.ai/api/v1 / LiteLLM proxy 엔드포인트
인식 불가 provider 또는 SDK 부재 시 None (오프라인 → stub 폴백, ADR-507).

- `_AnthropicClient` 는 기존 `claude_judge` 에 유지되며 빌더가 lazy import 로 분기한다.
- 프로바이더 불변xt: OpenAICompatibleClient 는 `provider`·`model` 속성을 노출해
  version tuple(07 §6.1) 의 `model_provider`/`model_id` 를 정직하게 산출한다.
"""
from __future__ import annotations

import sys

import pytest

import orc_citadel.llm_providers as LP


class _TransportRecorder:
    """모의 httpx.Transport — 요청 capture + 사전 정의 응답 반환.

    실제 프로바이더 네트워크 없이 OpenAICompatibleClient 의 요청-파싱 계약을 검증.
    """

    def __init__(self, status=200, payload=None, usage=None):
        self.status = status
        self.payload = payload if payload is not None else {
            "choices": [{"message": {"content": '{"relation": "equivalent"}'}}],
        }
        self.usage = usage if usage is not None else {"prompt_tokens": 11, "completion_tokens": 7}
        self.requests = []

    def handle_request(self, request):
        self.requests.append(request)
        import json

        body = {**self.payload}
        if self.usage is not None:
            body["usage"] = self.usage
        return __import__("httpx").Response(
            self.status, json=body, request=request,
        )


def _client(transport, provider="openrouter", model="anthropic/claude-sonnet", **kw):
    import httpx

    c = LP.OpenAICompatibleClient(
        base_url=kw.get("base_url", "https://openrouter.ai/api/v1"),
        api_key=kw.get("api_key", "test-key"),
        model=model,
        provider=provider,
    )
    # transport 주입 — httpx.Client(transport=...).
    c._client = httpx.Client(transport=httpx.MockTransport(transport.handle_request))
    return c


# --- OpenAICompatibleClient: 요청·응답 계약 ------------------------------------

def test_openai_compatible_post_chat_completions():
    """OpenAI-compatible `/chat/completions` POST — system/user 프롬프트 전달."""
    tr = _TransportRecorder(usage={"prompt_tokens": 5, "completion_tokens": 3})
    c = _client(tr)
    out = c.messages_create(model="anthropic/claude-sonnet", system="SYS",
                            user="USER", max_tokens=512, temperature=0)
    assert out == {"relation": "equivalent"}
    req = tr.requests[0]
    assert req.method == "POST"
    assert req.url.path.endswith("/chat/completions")
    import json

    body = json.loads(req.content)
    assert body["model"] == "anthropic/claude-sonnet"
    assert body["max_tokens"] == 512
    assert body["temperature"] == 0
    assert body["messages"][0] == {"role": "system", "content": "SYS"}
    assert body["messages"][1] == {"role": "user", "content": "USER"}


def test_openai_compatible_captures_usage():
    """응답 usage(prompt/completion tokens) 캡처 — S42 비용 집계 정합."""
    tr = _TransportRecorder(usage={"prompt_tokens": 11, "completion_tokens": 7})
    c = _client(tr)
    c.messages_create(model="m", system="s", user="u", max_tokens=100, temperature=0)
    assert c.last_usage["input_tokens"] == 11
    assert c.last_usage["output_tokens"] == 7


def test_openai_compatible_bad_json_returns_empty():
    """비-JSON 응답 → {} (ADR-704·07 §7 구조화 실패 → 후보 유지 None 유도)."""
    tr = _TransportRecorder(status=200, payload={
        "choices": [{"message": {"content": "not json"}}]})
    c = _client(tr)
    assert c.messages_create(model="m", system="s", user="u",
                             max_tokens=10, temperature=0) == {}


# --- build_llm_client: 환경 config 선택 ---------------------------------------

def test_build_llm_client_openrouter(monkeypatch):
    """LLM_PROVIDER=openrouter → OpenAICompatibleClient(OpenRouter 기반)."""
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("LLM_MODEL", "anthropic/claude-sonnet")
    monkeypatch.setenv("LLM_API_KEY", "or-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
    c = LP.build_llm_client()
    assert c is not None
    assert c.provider == "openrouter"
    assert c.model == "anthropic/claude-sonnet"


def test_build_llm_client_litellm(monkeypatch):
    """LLM_PROVIDER=litellm → OpenAICompatibleClient(LiteLLM proxy)."""
    monkeypatch.setenv("LLM_PROVIDER", "litellm")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o via proxy")
    monkeypatch.setenv("LLM_API_KEY", "lmk")
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:4000")
    c = LP.build_llm_client()
    assert c is not None
    assert c.provider == "litellm"
    assert c.model == "gpt-4o via proxy"


def test_build_llm_client_anthropic_uses_sdk(monkeypatch):
    """LLM_PROVIDER=anthropic → 기존 anthropic 래퍼 (SDK 설치 시)."""
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_MODEL", "claude-opus-4-8")
    c = LP.build_llm_client()
    # anthropic 미설치 환경은 None(stub 폴백) — 설치 시 _AnthropicClient.
    if c is not None:
        assert c.provider == "anthropic"


def test_build_llm_client_default_provider(monkeypatch):
    """LLM_PROVIDER 미설정 + anthropic SDK 없음 → None (오프라인 stub 폴백)."""
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    # anthropic import 강제 차단으로 오프라인 시뮬레이션.
    import importlib

    saved = sys.modules.get("anthropic")
    sys.modules["anthropic"] = None  # ImportError 유도
    try:
        c = LP.build_llm_client()
    finally:
        if saved is not None:
            sys.modules["anthropic"] = saved
        else:
            sys.modules.pop("anthropic", None)
    assert c is None


def test_build_llm_client_unknown_provider_defaults_offline(monkeypatch):
    """인식 불가 provider → None (안전 — 잘못된 설정이 stub 폴백을 유발)."""
    monkeypatch.setenv("LLM_PROVIDER", "bogus-proxy")
    monkeypatch.setenv("LLM_API_KEY", "k")
    c = LP.build_llm_client()
    assert c is None


def test_openai_compatible_defaults_provider_to_openrouter():
    """OpenAICompatibleClient 기본 provider=openrouter."""
    c = LP.OpenAICompatibleClient(base_url="https://x", api_key="k", model="m")
    assert c.provider == "openrouter"


# --- ClaudeJudge 연동: 실제 client 로 version tuple 정직 산출 (07 §6.1) ---------


def test_judge_version_tuple_reflects_openrouter(monkeypatch):
    """ClaudeJudge + OpenAICompatibleClient(openrouter) → version tuple 이 실제
    provider·model 을 반영 (재현성 §6.1) — hardcode "anthropic" 아님."""
    import httpx
    from orc_citadel.claude_judge import ClaudeJudge

    tr = _TransportRecorder(usage={"prompt_tokens": 5, "completion_tokens": 3},
                            payload={"choices": [{"message": {"content":
                                '{"relation": "unrelated", "canonical_text": "", '
                                '"confidence": 0.0, "rationale": "no relation"}'}}]})
    c = LP.OpenAICompatibleClient(
        base_url="https://openrouter.ai/api/v1", api_key="or-key",
        model="anthropic/claude-sonnet", provider="openrouter")
    c._client = httpx.Client(transport=httpx.MockTransport(tr.handle_request))

    j = ClaudeJudge(client=c)
    v = j.judge_canonicalization(("a", "b"))
    assert v["model_provider"] == "openrouter"
    assert v["model_id"] == "anthropic/claude-sonnet"
    # 요청에 구성된 모델이 전송됨 (alias 가 아닌 LLM_MODEL).
    assert tr.requests[0] and True
    import json
    body = json.loads(tr.requests[0].content)
    assert body["model"] == "anthropic/claude-sonnet"


# --- parse_json_content: reasoning 모델 관용 파싱 (A30) -------------------------

def test_parse_json_content_plain():
    """순수 JSON — 기존 경로 그대로."""
    assert LP.parse_json_content('{"a": 1}') == {"a": 1}


def test_parse_json_content_markdown_fence():
    """```json fence 제거 — glm-4.7-flash 등 reasoning 모델 실측 사례 (A29)."""
    text = '```json\n{"verdict": "not_conflict"}\n```'
    assert LP.parse_json_content(text) == {"verdict": "not_conflict"}


def test_parse_json_content_prose_wrapped():
    """전후 설명 문장에 감싸인 JSON — 첫 '{'~마지막 '}' 구간 재시도."""
    text = '판정 결과는 다음과 같다.\n{"relation": "equivalent"}\n이상.'
    assert LP.parse_json_content(text)["relation"] == "equivalent"


def test_parse_json_content_truncated_returns_empty():
    """잘린 JSON(max_tokens 소진) → {} — 관용 파싱이 내용을 지어내지 않는다."""
    assert LP.parse_json_content('```json\n{"verdict": "real_conf') == {}
    assert LP.parse_json_content("") == {}
    assert LP.parse_json_content(None) == {}


def test_parse_json_content_non_dict_returns_empty():
    """dict 가 아닌 JSON(배열·스칼라) → {} (판정 계약은 dict)."""
    assert LP.parse_json_content("[1, 2]") == {}
    assert LP.parse_json_content('```json\n[1]\n```') == {}


def test_openai_compatible_fenced_json_parsed():
    """어댑터가 fence 응답을 판정 dict 로 파싱 — ADR-704 검증은 그대로 후속."""
    tr = _TransportRecorder(payload={"choices": [{"message": {
        "content": '```json\n{"relation": "equivalent"}\n```'}}]})
    c = _client(tr)
    out = c.messages_create(model="m", system="s", user="u",
                            max_tokens=10, temperature=0)
    assert out == {"relation": "equivalent"}
