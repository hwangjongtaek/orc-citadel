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
import json
from dataclasses import asdict

from orc_citadel.llm_judge import (
    DeterministicStub,
    validate_canonical_verdict,
    validate_contradiction_verdict,
)

# ADR-701: L4 판정 모델 alias (버전 전환 지점 — 여기만 교체).
MODEL_ID = "claude-opus-4-8"
OUTPUT_SCHEMA_VERSION = "0.1.0"
ONTOLOGY_VERSION = "1.0.0"

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
 "evidence_spans": [<지지 구간, 없으면 빈 배열>]}
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
        text = resp.content[0].text if resp.content else ""
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            # ADR-704·07 §7: 구조화 실패는 후보 유지 — None 유도.
            parsed = {}
        return parsed if isinstance(parsed, dict) else {}


def _build_default_client():
    """anthropic 사용 가능 시 실제 client, 아니면 None (오프라인 → stub 폴백)."""
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return None
    return _AnthropicClient(model=MODEL_ID)


class ClaudeJudge:
    """Anthropic Claude 판정 — LlmJudge 규약(05 §5)·version tuple 부착(07 §6.1).

    클라이언트를 주입받으면 그대로 사용, 없으면 anthropic 기본 래퍼. 검증 실패·예외
    시 `None`(canonical/contradiction) 또는 stub 폴백 — 자동 병합·반박 금지(ADR-507).
    """

    def __init__(self, client=None):
        self._client = client if client is not None else _build_default_client()
        self._stub = DeterministicStub()
        self._canonical_prompt = _CANONICAL_SCHEMA_INSTRUCTION
        self._contradiction_prompt = _CONTRADICTION_SCHEMA_INSTRUCTION

    # --- version tuple (07 §6.1) ---
    def _version(self) -> dict:
        return {
            "model_provider": "anthropic",
            "model_id": MODEL_ID,
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
                max_tokens=512, temperature=0,
            )
        except Exception:
            # API 예외 → 안전 폴백 (외부 의존 격리).
            return self._stub.judge_canonicalization(pair)
        verdict = validate_canonical_verdict(raw)
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
                max_tokens=512, temperature=0,
            )
        except Exception:
            return self._stub.judge_contradiction(pair)
        verdict = validate_contradiction_verdict(raw)
        if verdict is None:
            return None
        return {**asdict(verdict), **self._version()}
