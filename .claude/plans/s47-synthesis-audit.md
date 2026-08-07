# S47 · Synthesis/Audit (설계 07 §9.3) — 트랙 최종

## 목표
조사 루프(S46) 결과와 S30 subject 결론을 합성해 **조사 report**를 생성하고, Audit이 **evidence-first 불변식**(07 §9.3·README §3-2/§3-5)을 검증한다. 새 기능 트랙(조사 에이전트)의 완결.

## 계약 (07 §9.3, README §3-5)
- report 문장은 evidence-first — 검증 subgraph 안의 문장만, 무출처 문장은 `prediction`만 가능.
- Subject 결론(S30)을 basis로: conclude 문장 = 결론 봉투(value/dimensions) + 근거.
- Gap(S43/S46) → open_questions (아직 증거 부족 질문).
- **Audit 검증**: 모든 verify 문장이 claim_ref(→ provenance)를 가짐; 무출처는 prediction만; 결론 봉투 필수 (09 §4 단일 게이지 금지).

## module·API
`prototype/orc_citadel/synthesis.py`:
```python
@dataclass(frozen=True)
class SynthesisReport:
    subject_id: str
    conclusion: dict       # S30 결론 봉투
    statements: list       # [{text, modality, claim_ref}]  (evidence-first)
    open_questions: list   # gap subclaim (미충족)
    audit: dict            # {passed, violations[]}

class Synthesizer:
    def synthesize(self, investigation_result, subject_id) -> SynthesisReport
class Audit:
    def verify(self, report) -> dict   # evidence-first 불변식 검증
```
read-only — 조회·합성만, 영속·mutation 미노출.

## TDD (Red→Green→Refactor)
`test_synthesis.py`:
- conclusion 봉투 포함 (S30 재사용), statement는 claim_ref 가짐.
- 무출처 statement → prediction만 허용 (fact/asserted는 claim_ref 필수 → violation).
- gap subclaim → open_questions 포함.
- audit: passed/위반 목록 (무출처 asserted → violation).
- read-only, 결정성.

## 커밋 code-only behavioral, main 직접 머지. 트랙 완성.
