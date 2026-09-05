"""LLM 프로바이더 추상 계층 — Anthropic·OpenRouter·LiteLLM 세팅 (07 §7).

S21 ClaudeJudge 의 하드코딩 anthropic 의존을 풀어 **명시적 환경 config**로
OpenRouter·LiteLLM 을 세팅 가능하게 한다. OpenRouter 와 LiteLLM proxy 는 둘 다
OpenAI-compatible `/chat/completions` 엔드포인트를 제공하므로, 하나의 httpx 기반
어댑터(`OpenAICompatibleClient`) 로 두 프로바이더를 모두 커버한다 (신규 의존성 0 —
httpx 는 기존 의존).

config 는 다른 백엔드(`build_neo4j_driver`/`build_minio_client`/`build_dsn`) 와 동일한
**명시적 환경변수 패턴**을 따른다:
  LLM_PROVIDER   = "anthropic" | "openrouter" | "litellm"   (기본: anthropic)
  LLM_MODEL      = 모델명 (예: openrouter "anthropic/claude-sonnet", litellm proxy 모델)
  LLM_API_KEY    = 프로바이더 API 키
  LLM_BASE_URL   = OpenRouter: https://openrouter.ai/api/v1 / LiteLLM proxy 엔드포인트
인식 불가 provider 또는 SDK 부재 시 `None` (→ ClaudeJudge 는 stub 폴백, ADR-507).

- `_AnthropicClient`(anthropic SDK 래퍼) 는 `claude_judge` 에 유지 — 이 모듈의
  빌더가 lazy import 로 분기한다 (moving target 최소화, 기존 import 호환).
- 어댑터는 `provider`·`model` 속성을 노출 → version tuple(07 §6.1) 의
  `model_provider`/`model_id` 를 실제 사용 프로바이더로 정직하게 산출(ref: §6.1 재현성).
"""
from __future__ import annotations

import json
import os


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def parse_json_content(text) -> dict:
    """LLM 응답 본문 → 판정 dict. 구조화 실패는 {} (검증이 None 유도, ADR-704).

    reasoning 모델이 markdown fence(```json)·전후 설명 문장을 붙이는 실측 사례
    (A29, glm-4.7-flash)를 수용하는 **관용 파싱**: fence 제거 → 실패 시 첫
    '{'~마지막 '}' 구간 재시도. 내용은 변형하지 않는다 — 잘린/비-dict JSON 은
    그대로 {} (지어내기 금지, honest-gap §6.2). 스키마 검증은 후속 단계 그대로.
    """
    if not isinstance(text, str) or not text.strip():
        return {}
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    try:
        parsed = json.loads(t)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        pass
    start, end = t.find("{"), t.rfind("}")
    if 0 <= start < end:
        try:
            parsed = json.loads(t[start:end + 1])
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


class OpenAICompatibleClient:
    """OpenRouter·LiteLLM 공용 — OpenAI-compatible `/chat/completions` 어댑터.

    `messages_create` 는 주입 계약(모의 client·_AnthropicClient 와 동일 시그니처) 을
    유지해 ClaudeJudge 가 프로바이더 무관하게 그대로 소비한다. 응답 `usage` 를
    캡처해 S42 비용 집계와 호환. 구조화 실패(비-JSON) 는 {} 반환 → 판정 None 유도
    (ADR-704·07 §7).
    """

    def __init__(self, base_url: str, api_key: str, model: str,
                 provider: str = "openrouter") -> None:
        import httpx  # 지연 import — httpx 는 프로바이더 계층에서만 필요.

        head = {"Content-Type": "application/json"}
        if api_key:
            head["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.Client(headers=head, timeout=60)
        self._base_url = base_url.rstrip("/")
        self.model = model
        self.provider = provider
        self.last_usage = {}  # 최근 호출 usage (S42 비용 집계).

    def messages_create(self, model, system, user, max_tokens, temperature):
        # 주입 client 의 자체 모델을 우선 (judge 가 넘긴 alias 를 덮어씀) — _AnthropicClient
        # 와 동일한 provider-neutral 계약. OpenRouter/LiteLLM 에는 LLM_MODEL 이 전송된다.
        m = self.model or model
        payload = {
            "model": m,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        resp = self._client.post(f"{self._base_url}/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json() if resp.content else {}
        usage = data.get("usage") or {}
        self.last_usage = {
            "input_tokens": usage.get("prompt_tokens", 0) or 0,
            "output_tokens": usage.get("completion_tokens", 0) or 0,
        }
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return {}
        # 관용 파싱 (fence·전후 설명) — 구조화 실패는 {} → 판정 None 유도 (ADR-704).
        return parse_json_content(content)


def build_llm_client():
    """LLM_PROVIDER/LLM_MODEL/LLM_API_KEY/LLM_BASE_URL 환경 config 로 client 생성.

    인식 불가 provider, SDK/HTTP 클라이언트 부재 → None (오프라인 → ClaudeJudge
    stub 폴백). 반환 객체는 `provider`·`model` 속성을 지녀 version tuple 산출
    (07 §6.1) 과 호환.
    """
    provider = (_env("LLM_PROVIDER") or "anthropic").strip().lower()
    model = _env("LLM_MODEL")
    api_key = _env("LLM_API_KEY")
    base_url = _env("LLM_BASE_URL")

    if provider in ("openrouter", "litellm"):
        default_url = ("https://openrouter.ai/api/v1" if provider == "openrouter"
                       else "http://localhost:4000")
        try:
            return OpenAICompatibleClient(
                base_url=base_url or default_url,
                api_key=api_key or "", model=model or "", provider=provider,
            )
        except ImportError:
            # httpx 미설치 → stub 폴백 (SDK 부재와 동일한 안전 경로).
            return None
    if provider == "anthropic":
        try:
            import anthropic  # noqa: F401  지연 import — SDK 부재 시 None(stub 폴백).
        except ImportError:
            return None
        from orc_citadel.claude_judge import _AnthropicClient
        return _AnthropicClient(model=model or "claude-opus-4-8",
                                api_key=api_key, base_url=base_url)
    # 인식 불가 provider → None (잘못된 설정이 stub 폴백을 유발, 안전).
    return None
