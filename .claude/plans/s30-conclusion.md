# S30 · 조사 결론·신뢰도 종합 (Subject-level Conclusion Projection)

## 목표

**S29 어세션 근거 프로젝터**(`AssertionEvidenceProjector`)를 바로 소비해, 조사 UX(설계 09 §3 conclusion, blueprint §5.2)가 필요로 하는 **subject-level 결론 신뢰도 봉투**를 생성하는 read-only 투사 계층을 추가한다.

09 §3 conclusion.confidence 역시 09 §4 다차원 봉투를 따른다. S29가 어세션 1건의 증거 구조를 집계했다면, S30은 한 subject(예: `org-nvda`)의 **전체 어세션 신뢰도 집합을 종합**해 하나의 결론 봉투 + 근거 분포 + 저신뢰/미결 신호를 만든다.

> 09 §4 원칙 유지: `value` 단일 게이지 금지 — 봉투(evidence_count/independent_source_count/basis/dimensions) 필수. confidence는 source reputation이 아니라 증거 구조로 계산 (blueprint §11).

## 축

`ConclusionEvidence` (subject 1명 분 종합):

| 필드 | 설명 |
| --- | --- |
| `confidence` | 종합 결론 봉투 (09 §4): value/evidence_count/independent_source_count/basis/dimensions |
| `by_predicate` | predicate별 어세션 신뢰도 분포 (predicate → {count, indep, max_value}) |
| `open_questions` | 저신뢰·증거 미달 어세션 신호 (09 §3 open_questions, coverage 부족) |
| `contradicting_subjects` | 반박 신호가 있는 관계 (어세션 conflict에 걸린 상대) |

## 계산 규칙 (결정적)

**결론 신뢰도 종합** — subject의 모든 어세션 신뢰도 (S29 `AssertionEvidence`)를 통합:
- `evidence_count = Σ 어세션별 evidence_count` (전체 지지 근거)
- `independent_source_count = Σ 어세션별 independent_source_count` (독립 출처 통합, 중복은 어세션별로 이미 보정됨)
- `contradiction_total = Σ 어세션별 contradiction (>0 인 것에 대한 위험 통합 — subject가 직면한 반박 신호)`
- `value = mean_value × (1 − contradiction_total)` — 평균 어세션 신뢰도에 반박 위험으로 감쇄 (09 §3 conclusion이 "전체 결론 신뢰도"를 한 값으로 표현).
- `dimensions = {support, contradiction, coverage}`:
  - `support = mean(subject 어세션 support)`
  - `contradiction = contradiction_total` (반박 위험)
  - `coverage = 지지 근거가 있는 어세션 비율` (`has_evidence_assertions / total_assertions`)

**open_questions** (09 §3) — 커버리지 부족·저신뢰 어세션을 미결 질문으로 노출:
- `coverage < 1.0`(지지 근거 0) 이거나 `value < 저신뢰 임계(0.4 placeholder)` 인 어세션 → `{assertion_id, predicate, reason: "증거 부족" / "저신뢰", value}`.

**by_predicate 분포** — subject 어세션을 predicate별로 묶어 `{count, independent_source_count, max_value}` 요약. 조사 보고서의 섹션·타임라인 재료 (09 §3 report.sections[].title = predicate).

**read-only** (불변식 §3-3): 쓰기·영속·그래프 mutation 미노출. S29 projector + zone 행 읽기만.

## 모듈·API

`prototype/orc_citadel/conclusion.py`:

```python
@dataclass(frozen=True)
class ConclusionEvidence:
    subject_id: str
    confidence: dict            # 09 §4 봉투
    by_predicate: dict          # predicate -> {count, independent_source_count, max_value}
    open_questions: list         # 저신뢰·증거 미달 어세션 신호
    contradicting_subjects: list  # 반박 신호가 걸린 관계

class ConclusionProjector:
    """S29 어세션 근거 프로젝터를 소비하는 subject-level 결론 종합 (09 §3)."""
    def __init__(self, zone, low_confidence=0.4): ...
    def for_subject(self, subject_id) -> ConclusionEvidence | None: ...
    def all(self) -> list[ConclusionEvidence]: ...
```

## TDD (Red→Green→Refactor)

`test_conclusion.py` — S29 `_seed_claims` 패턴 재사용.

1. **Red**:
   - `value` — subject의 어세션 평균 support에 반박 위험 감쇄 (`value = mean_support × (1−contradiction_total)`).
   - `evidence_count` — subject 전체 지지 근거 합.
   - `independent_source_count` — 어세션별 독립 출처 합 (dup_cluster 보정 유지).
   - `by_predicate` — predicate별 {count, max_value}.
   - `open_questions` — 지지 근거 0 or 저신뢰 어세션 노출 (reason 포함).
   - `dimensions` — support/contradiction/coverage 포함.
   - read-only — `apply`/`persist`/`create_*` 미노출; zone 상태 불변.
   - no-subject → None.
2. **Green** — 최소 구현.
3. **Refactor** — 중복 없음.

## 실데이터 스모크

curated.duckdb (29 어세션, org-6c775b7dbbb1 announces) — subject 결론 봉투·by_predicate·open_questions 출력, S29 값과 정합 확인.

## 커밋

**code-only (behavioral)**: `feat(S30): subject-level conclusion confidence projection (09 §3)`. 09 §3 already Review spec — 문서·README·ROADMAP 변경 없음.

## 완료 기준

- [ ] Red→Green→Refactor, 전체 테스트 통과 (기존 237 + 신규).
- [ ] 결정성 — 동일 zone → 동일 종합.
- [ ] read-only — 쓰기 경로 미노출.
- [ ] 실데이터 스모크 — 09 §4 봉투 + by_predicate + open_questions pad.
