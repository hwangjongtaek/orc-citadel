# S15 LLM 판정 — canonicalization/contradiction 관계 판정 (05 §4.2·§5.2)

> 권장안 2 선택. 결정적 규칙(스텁)이던 canonicalization(7라벨)·contradiction(verdict)
> 판정의 **LLM 경계를 구조화 계약으로 실현**한다. LLM 호출은 외부 의존이므로 클라이언트
> 인터페이스·JSON schema 계약·결정적-LLM 라우팅을 구현하고, 실제 호출은 플러그형 스텁.
> 대상: [05-resolution-and-extraction](../../docs/design/05-resolution-and-extraction.md) §4.2·§5.2,
> 02 §3.1, 07-llm-and-agents.

## 배경·범위

| 결정 | 근거 |
| --- | --- |
| **결정적 규칙 fast-path 유지, LLM은 애매 원만** | 05 §5/§6 deterministic-first: 규칙·사전으로 판정 가능한 것은 LLM에 보내지 않는다. LLM은 규칙이 못 결정한 쌍에만 |
| **구조화(JSON schema) LLM I/O 계약 정의** | §4.2 canonicalization 7라벨 output, §5.2 contradiction verdict/conflict_type/rationale/confidence/evidence_spans |
| **LLM 클라이언트는 플러그형(스텁) — 키/네트워크 부재 시 결정적 격리** | 외부 의존. 스텁은 계약(스키마)을 지키는 결정적 판정으로 대체 (오프라인 검증 가능) |
| **LLM 출력 검증** (schema 강제) | §5.3: rationale·judged_by 필수, verdict/conflict_type 유효값. 저신뢰/유효성 실패 → 후보 유지(자동 병합 금지, ADR-507) |
| **evidence_spans는 source_span 기반** | §5.2: LLM 판정도 span 근거 필요 (provenance) |

## 구현 계획

- **`llm_judge.py`** (신규): `LlmJudge` 인터페이스 + `StructuredJudgeClient`(구조화 프롬프트 계약).
  - `judge_canonicalization(pair) → CanonicalVerdict(relation, canonical_text, confidence, rationale)`
  - `judge_contradiction(pair) → ContradictionVerdict(verdict, conflict_type, rationale, confidence, evidence_spans)`
  - 각각 §4.2/§5.2 JSON schema에 대한 **출력 검증**(enum·범위·필수) — 실패 시 `None`(후보 유지).
- **`relational.py`** (신규): 결정적 규칙(fast-path) → LLM 라우팅.
  - canonicalize: 동일 surface(subject+predicate)는 결정적 equivalent (기존) → 이외 쌍은 LLM.
  - contradiction: 상충 신호는 결정적 후보(기존) → verdict 확정은 LLM.
  - LLM 판정 결과를 기존 canonical/conflict에 반영(탉sureed 저장은 후속 그래프).
- **pluggable**: `LlmClient`를 생성자 주입 — 기본은 결정적 스텁(`DeterministicStub`)으로 개수 규칙 미결 쌍을 격리(오프라인).

## DoD

- canonicalization·contradiction LLM I/O 구조화 계약 + 출력 검증 (TDD)
- 결정적 fast-path → LLM 라우팅 (규칙 결정 쌍은 LLM 미호출)
- LLM 출력 검증 실패 시 후보 유지(자동 병합 금지, ADR-507)
- 스텁 LLM으로 오프라인 E2E, 전체 테스트 통과, code-only 커밋

## 한계 (문서화)

- 실제 LLM API 호출(claude 등)은 키·네트워크 필요 — 이 세션은 계약+라우팅+스텁 검증,
  실 LLM 주입은 사용자(플러그인 교체)
- LLM 판정 저장(SUPPORTS/CONTRADICTS edge·MEMBER_OF)은 06 그래프 후속 — 이번은 결정/후보 반영 경계
- evidence_spans는 prototype source_span(clean text 축) 근사 (raw 정확 매핑은 04 §3.4 후속)
