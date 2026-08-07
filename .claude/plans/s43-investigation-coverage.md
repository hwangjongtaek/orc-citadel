# S43 · 조사 루프 — evidence coverage 계산기 (설계 07 §4, 10 §1.3)

## 목표

investigation loop(설계 07 §4)의 핵심 지표인 **evidence coverage**(10 §1.3 subclaim coverage)와 **graph gap 식별**을 구현한다. 조회 계층(S25-S31)을 read-only로 재사용해, planner가 나눈 subclaim(질문 분해) 각각이 충분한 근거로 뒷받침되는지 계산한다 (10 §1.3 `covered_subclaims / planned_subclaims`, gate ≥ 0.80; 07 §4 state B).

## 조사 루프 계약 (07 §4)

- **PLAN**: question → subclaim 트리. prototype은 결정적 분해(주제·predicate) 단순화로, subclaim = coverage 평가 단위.
- **RETRIEVE_SUBGRAPH**: Graph Explorer(read-only) — subclaim → 기존 subgraph (S26, S31 재사용).
- **IDENTIFY_GAPS**: subgraph → 근거 부족 subclaim 목록 = `expected_info_gain`(coverage-delta 휴리스틱, 07 §2.3)의 입력.
- **read-only** (불변식 §3-3): 평가·공백 식별만 — graph mutation·영속 없음.

## 모듈·API

`prototype/orc_citadel/investigation.py`:

```python
@dataclass(frozen=True)
class Subclaim:
    id: str
    subject_id: str | None      # 특정 subject 질문이면
    text: str
    covered: bool = False
    evidence_count: int = 0
    gap_reason: str | None = None

@dataclass(frozen=True)
class CoverageResult:
    coverage: float             # covered/planned (10 §1.3)
    subclaims: list[Subclaim]
    gaps: list[str]             # 미충족 subclaim id (07 IDENTIFY_GAPS)
    expected_info_gain: dict    # gap → Δcoverage 휴리스틱 (07 §2.3)

class InvestigationCoverage:
    """조사 루프의 evidence coverage 계산 (07 §4 state B, read-only)."""
    def __init__(self, zone): ...
    def coverage(self, subclaims) -> CoverageResult
    def gap_identification(self, subclaims) -> CoverageResult  # 곧
```

- subclaim이 `subject_id`를 가지면 그 subject의 어세션·근거(S29)로 coverage 계산.
- subject 없는 subclaim은 평가 불가 → gap(공백)으로.
- `expected_info_gain`: 미충족 subclaim 1개당 Δcoverage 근사 (07 §2.3).

## TDD (Red→Green→Refactor)

`test_investigation.py` — zone + 어세션/근거 배치.

1. **Red**:
   - coverage 계산 — 2 subclaim 중 1개 근거 충족 → 0.5 (10 §1.3).
   - 근거 있는 subclaim → covered=True, evidence_count.
   - 없는 subclaim → gap_reason, gaps 목록.
   - subject 없는 subclaim → 항상 gap.
   - `expected_info_gain` — gap subclaim의 Δcoverage 휴리스틱.
   - read-only — `apply`/`persist` 미노출.
2. **Green** — 최소 구현.
3. **Refactor** — 중복 없음.

## 실데이터 스모크

curated.duckdb — 실 subclaims coverage·gap·expected_info_gain 출력.

## 커밋

**code-only (behavioral)**: `feat(S43): investigation loop — evidence coverage & gap identification (07 §4, 10 §1.3)`. main에 직접 머지(PR 없음, 사용자 승인).

## 완료 기준
- [ ] Red→Green→Refactor, 전체 테스트 통과 (기존 366 + 신규).
- [ ] 결정성 — 동일 subclaims/zone → 동일 coverage.
- [ ] read-only — 쓰기 미노출.
- [ ] 실데이터 — coverage·gap·gain pad.
