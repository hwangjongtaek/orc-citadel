# S21 실제 LLM 주입 — Claude Judge (07 §7, 05 §4.2·§5.2)

> 권장안 1. `LlmJudge`(S15)의 실제 구현체 — Anthropic Claude로 canonicalization(7라벨)·
> contradiction(verdict) 판정을 강제 JSON schema로 수행한다. 환경: `ANTHROPIC_API_KEY`
> 설정됨 + proxy base URL — 실호출 가능.
> 대상: [07-llm-and-agents](../../docs/design/07-llm-and-agents.md) §7(강제 schema)·§6.1(버전 튜플), ADR-704(prefill 금지), ADR-701(L4 `claude-opus-4-8`).

## 배경·범위

| 결정 | 근거 |
| --- | --- |
| **강제 JSON schema**(`output_config.format`) — 자유 요약 금지 | 07 §7, ADR-704, blueprint §8.6. prefill 금지 |
| **출력 역직렬화·검증** 후 송출, 실패 시 quarantine | 07 §7: raw 매칭 금지, schema/provenance 실패 시 quarantine |
| **버전 튜플 부착** (07 §6.1 5축) | 재현성·모델 교체 추적. `model_id`는 산출물 핀/date란 상태 |
| **실패·무키 폴백 → DeterministicStub** | 외부 의존 격리 (S15) — 키 문제·네트워크 시 결정적 안전 |
| **모델**: L4 judge `claude-opus-4-8` (alias) — 교체 가능 | ADR-701 |

## 구현 계획

- **`claude_judge.py`** (신규): `ClaudeJudge(LlmJudge)` — Anthropic API (`anthropic` SDK 또는 HTTP
  POST)로 structured output request → 파싱 → `llm_judge.validate_canonical_verdict`/
  `validate_contradiction_verdict` 통과 시 반환, 아니면 None(후보 유지)·상용 폴백.
  - canonicalization 프롬프트(7라벨)·contradiction 프롬프트(verdict/conflict_type) JSON schema.
  - version tuple (model_provider anthropic, model_id, prompt hash, output_schema_version 0.1.0,
    ontology 1.0.0, inference temperature 0).
- **TDD**: 모의 Anthropic 응답으로 프롬프트·파싱·검증·폴백 (오프라인).
- **Smoke**: 실 API로 소량 판정 (키 실재) + 계약 검증.

## DoD

- ClaudeJudge가 valid structured 판정 반환(7라벨·verdict), invalid→None(후보 유지)
- 실패/무키 → DeterministicStub 폴백 (isolated)
- version tuple 붙임, 전체 테스트 통과, code-only 커밋
- (실 smoke는 키 존재 시 — 이 환경 key set 확인됨)

## 한계 (문서화)

- JSON schema 본문은 0.1.0 초기(TBD, 07 §7) — 여기서 초안 확정
- 실 API는 비용·네트워크 — smoke는 소량, 회귀는 사용자
