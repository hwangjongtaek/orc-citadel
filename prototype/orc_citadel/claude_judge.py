"""S21 실제 LLM 주입 — ClaudeJudge (07 §7, 05 §4.2·§5.2).

Anthropic Claude로 Canonicalization 7라벨·Contradiction verdict를 강제 JSON schema로
판정한다 (ADR-701: L4 judge = `claude-opus-4-8` alias; ADR-704: prefill 금지).

- 클라이언트는 **주입 가능**(테스트는 모의 client). 기본값은 anthropic SDK 래퍼.
- 판정 출력은 `llm_judge.validate_*`로 재검증 — 실패 시 `None` (후보 유지, ADR-507).
- API 예외 시 `DeterministicStub` 안전 폴백 (외부 의존 격리, 오프라인).
- version tuple(07 §6.1)을 판정 dict에 부착: model_provider/model_id/
  prompt_template_hash/output_schema_version/ontology_version.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import asdict

from orc_citadel.llm_judge import (
    DeterministicStub,
    validate_canonical_verdict,
    validate_contradiction_verdict,
)
from orc_citadel.llm_providers import parse_json_content

# ADR-701: L4 판정 모델 alias (버전 전환 지점 — 여기만 교체).
MODEL_ID = "claude-opus-4-8"
OUTPUT_SCHEMA_VERSION = "0.1.0"
ONTOLOGY_VERSION = "1.0.0"

# 판정 호출 completion 예산 기본값. reasoning 모델(glm-4.7-flash 등)은 completion
# 예산에서 reasoning 토큰(1200+ 실측, A29)을 소비해 512 로는 본문이 잘렸다 —
# SLO-06 validation fail 근본 원인. LLM_MAX_TOKENS 환경으로 배포별 조정.
DEFAULT_MAX_TOKENS = 2048


def _judge_max_tokens() -> int:
    """판정 max_tokens — LLM_MAX_TOKENS 우선, 비정수/부재 시 기본 2048."""
    try:
        return int(os.environ.get("LLM_MAX_TOKENS", "") or DEFAULT_MAX_TOKENS)
    except ValueError:
        return DEFAULT_MAX_TOKENS

# §4.2 canonicalization 출력 schema (강제 JSON).
_CANONICAL_SCHEMA_INSTRUCTION = """\
답은 반드시 유효한 JSON 객체로만 출력하라 (설명·마크다운 금지). 스키마:
{"relation": <one of equivalent | more_specific | more_general | supports | \
contradicts | unrelated | temporally_superseded>,
 "canonical_text": <정규화 문장, 관계 없으면 빈 문자열>,
 "confidence": <0.0~1.0 실수>,
 "rationale": <판정 근거 한 문장>}
relation은 다음 7라벨 중 하나여야 한다. 병합 가능 여부를 결정한다(ADR-503).
"""

# §5.2 contradiction schema.
_CONTRADICTION_SCHEMA_INSTRUCTION = """\
답은 반드시 유효한 JSON 객체로만 출력하라 (설명·마크다운 금지). 스키마:
{"verdict": <one of real_conflict | temporal | scope | not_conflict>,
 "conflict_type": <value_conflict | temporal | scope | null>,
 "rationale": <모순 여부 근거 한 문장 이상>,
 "confidence": <0.0~1.0 실수>,
 "evidence_spans": [{"doc_id": "...", "char_start": <정수>, "char_end": <정수>}, ...]}
evidence_spans 각 항목은 반드시 dict 객체여야 한다 (없으면 빈 배열 []).
verdict/conflict_type은 05 §5.2·ADR-504 라벨만 허용한다.
"""


def _prompt_hash(text: str) -> str:
    return "ph-" + hashlib.sha256(text.encode()).hexdigest()[:16]


class _AnthropicClient:
    """실제 anthropic SDK 래퍼 — `messages_create`가 역직렬화된 판정 dict를 반환.

    주입 계약(모의 client와 동일 시그니처)을 유지한다. anthropic 미설치/키 부재 시
    생성 실패(빌더가 None 반환) → ClaudeJudge는 stub 폴백한다.
    """

    def __init__(self, model: str, api_key: str | None = None, base_url: str | None = None):
        import anthropic  # 지연 import — 설치 여부에 따라 존재/부재.

        self._client = anthropic.Anthropic(api_key=api_key, base_url=base_url)
        self.model = model
        self.provider = "anthropic"
        self.last_usage = {}  # 최근 호출 usage (S42 비용 집계).

    def messages_create(self, model, system, user, max_tokens, temperature):
        # 주입된 client의 자체 모델을 우선 — judge가 넘긴 alias(MODEL_ID)를 덮어써서
        # 배포 환경별 모델 선택을 client 소유로 둔다 (dev proxy는 L4 alias 미제공).
        m = self.model
        resp = self._client.messages.create(
            model=m,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": user}],
        )
        # S42: 응답 usage(input/output tokens)를 캡처 — judge가 누적·비용 집계.
        usage = getattr(resp, "usage", None)
        self.last_usage = {
            "input_tokens": getattr(usage, "input_tokens", 0) or 0,
            "output_tokens": getattr(usage, "output_tokens", 0) or 0,
        }
        text = resp.content[0].text if resp.content else ""
        # 관용 파싱 (fence·전후 설명, A30) — 구조화 실패는 {} → 판정 None (ADR-704).
        return parse_json_content(text)


def _build_default_client():
    """실제 client — LLM_PROVIDER/LLM_MODEL/API_KEY/BASE_URL 환경 config 로 선택.

    `llm_providers.build_llm_client` 가 Anthropic·OpenRouter·LiteLLM 중 선택하고,
    SDK 부재·인식 불가 provider → None (오프라인 → stub 폴백, ADR-507). 빌더가
    anthropic SDK 를 lazy import 하므로 미설치 시에도 import 는 안전.
    """
    from orc_citadel.llm_providers import build_llm_client

    return build_llm_client()


class ClaudeJudge:
    """Anthropic Claude 판정 — LlmJudge 규약(05 §5)·version tuple 부착(07 §6.1).

    클라이언트를 주입받으면 그대로 사용, 없으면 anthropic 기본 래퍼. 검증 실패·예외
    시 `None`(canonical/contradiction) 또는 stub 폴백 — 자동 병합·반박 금지(ADR-507).
    """

    def __init__(self, client=None, slo_log=None):
        self._client = client if client is not None else _build_default_client()
        self._stub = DeterministicStub()
        self._canonical_prompt = _CANONICAL_SCHEMA_INSTRUCTION
        self._contradiction_prompt = _CONTRADICTION_SCHEMA_INSTRUCTION
        # SLO-06(schema 검증 통과율, 11 §2.3) — verdict 스키마 검증 통과/실패를
        # 선택 주입 로그에 기록 (기본 None → 동작 무변경, Spec 1.0.0).
        self._slo_log = slo_log
        # S42: LLM 비용·토큰 누적 (design 10 §1.4). 기본 환산율은 placeholder.
        self._input_tokens = 0
        self._output_tokens = 0
        self._calls = 0
        self._IN_PER_MT = 3.0    # USD / MTok input (placeholder)
        self._OUT_PER_MT = 15.0  # USD / MTok output (placeholder)

    # --- S42 비용·토큰 (Q5 해소 진행) ---
    def _accumulate_usage(self) -> None:
        """최근 client 호출의 usage를 누적 (실제 LLM 호출 시)."""
        if self._client is None:
            return
        u = getattr(self._client, "last_usage", None) or {}
        self._input_tokens += u.get("input_tokens", 0)
        self._output_tokens += u.get("output_tokens", 0)
        self._calls += 1

    def usage(self) -> dict:
        """누적 토큰·호출 수 (design 10 §1.4 tokens_in/out·tool_calls)."""
        return {"input_tokens": self._input_tokens,
                "output_tokens": self._output_tokens, "calls": self._calls}

    def cost_usd(self, input_per_mtok: float | None = None,
                 output_per_mtok: float | None = None) -> float:
        """누적 비용 USD — token→USD 환산 (placeholder, 프로바이더별 조정).

        design 10 §1.4 `llm_usd`. 기본 환산율은 생성자 placeholder.
        """
        i = input_per_mtok if input_per_mtok is not None else self._IN_PER_MT
        o = output_per_mtok if output_per_mtok is not None else self._OUT_PER_MT
        return self._input_tokens / 1e6 * i + self._output_tokens / 1e6 * o

    # --- version tuple (07 §6.1) ---
    def _version(self) -> dict:
        # 실제 client 가 지닌 provider·model 로 정직하게 산출 (재현성 §6.1) —
        # stub 폴백(주입 client None)이면 alias 기본값 사용.
        provider = getattr(self._client, "provider", "anthropic")
        model = getattr(self._client, "model", MODEL_ID)
        return {
            "model_provider": provider,
            "model_id": model,
            "prompt_template_hash": _prompt_hash(self._canonical_prompt),
            "output_schema_version": OUTPUT_SCHEMA_VERSION,
            "ontology_version": ONTOLOGY_VERSION,
        }

    # --- canonicalization (05 §4.2) ---
    def _build_canonical_user(self, pair: tuple[str, str]) -> str:
        left_id, right_id = pair
        return (
            f"두 claim 후보가 병합 가능한지 판정하라.\n"
            f"pair: ({left_id!r}, {right_id!r})\n"
            f"동일 subject·predicate·window를 공유하면 equivalent로 판정하라."
        )

    def _build_canonical_prompt(self, pair: tuple[str, str]) -> tuple[str, str]:
        return self._canonical_prompt, self._build_canonical_user(pair)

    def judge_canonicalization(self, pair: tuple[str, str]) -> dict:
        if self._client is None:
            return self._stub.judge_canonicalization(pair)
        try:
            system, user = self._build_canonical_prompt(pair)
            raw = self._client.messages_create(
                model=MODEL_ID, system=system, user=user,
                max_tokens=_judge_max_tokens(), temperature=0,
            )
            self._accumulate_usage()  # S42: 성공 LLM 호출 토큰 누적.
        except Exception:
            # API 예외 → 안전 폴백 (외부 의존 격리).
            return self._stub.judge_canonicalization(pair)
        verdict = validate_canonical_verdict(raw)
        if self._slo_log is not None:
            self._slo_log.record_schema("claude_judge", kind="canonical_verdict",
                                        valid=verdict is not None)
        if verdict is None:
            return None
        return {**asdict(verdict), **self._version()}

    # --- contradiction (05 §5.2) ---
    def _build_contradiction_user(self, pair: tuple[str, str]) -> str:
        left_id, right_id = pair
        return (
            f"두 claim 후보가 모순인지 판정하라.\n"
            f"pair: ({left_id!r}, {right_id!r})\n"
            f"같은 subject·predicate에 값/방향이 충돌하면 real_conflict로 판정하라."
        )

    def _build_contradiction_prompt(self, pair: tuple[str, str]) -> tuple[str, str]:
        return self._contradiction_prompt, self._build_contradiction_user(pair)

    def judge_contradiction(self, pair: tuple[str, str]) -> dict:
        if self._client is None:
            return self._stub.judge_contradiction(pair)
        try:
            system, user = self._build_contradiction_prompt(pair)
            raw = self._client.messages_create(
                model=MODEL_ID, system=system, user=user,
                max_tokens=_judge_max_tokens(), temperature=0,
            )
            self._accumulate_usage()  # S42: 성공 LLM 호출 토큰 누적.
        except Exception:
            return self._stub.judge_contradiction(pair)
        verdict = validate_contradiction_verdict(raw)
        if self._slo_log is not None:
            self._slo_log.record_schema("claude_judge", kind="contradiction_verdict",
                                        valid=verdict is not None)
        if verdict is None:
            return None
        return {**asdict(verdict), **self._version()}
