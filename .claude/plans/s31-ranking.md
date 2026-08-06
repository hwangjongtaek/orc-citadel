# S31 · Subject 신뢰도 랭킹 (Ranked Conclusion Projection)

## 목표

**S30 결론 프로젝터**(`ConclusionProjector.for_subject`)를 소비해, 전체 subject들을 신뢰도 기준으로 **정렬된 read-only 랭킹**으로 노출한다. 조사 UX(09 §2.1 investigation 목록·War Table 우선순위)가 "어떤 주체를 먼저 주목할지"를 결정하는 재료.

09 §4 원칙 유지 (value 단일 게이지 금지) — 랭킹 항목마다 봉투·정렬 근거를 함께 노출한다.

## 축

`RankedConclusion`:

| 필드 | 설명 |
| --- | --- |
| `subject_id` | 주체 |
| `confidence` | S30 결론 봉투 (09 §4) 재사용 |
| `rank` | 1-based 정렬 순위 |
| `signal` | 랭킹 사유: `high_confidence`(신뢰 확립) / `contradicted`(반박 존재) / `low_evidence`(근거 부족) / `normal` |
| `predicates` | predicate별 요약 (S30 by_predicate 재사용) |

## 계산 규칙 (결정적)

S30 `ConclusionEvidence` (subject별)를 정렬. 정렬 기준 (multi-key, 결정적):

1. **`value` DESC** — 결론 신뢰도.
2. tie-breaker: **`independent_source_count` DESC** — 같은 신뢰도면 독립 출처 많은 쪽 우선.
3. tie-breaker: **`subject_id` ASC** — 완전 결정적 (동률 순서 고정).

**signal 분류** — subject가 "뭐가 주목할 만한지"를 표현:
- `contradicted` — `dimensions.contradiction > 0` (반박 위험 존재 → 조사 우선).
- `low_evidence` — `independent_source_count == 0` 또는 `evidence_count == 0` (근거 미확립).
- `high_confidence` — `value >= 상위신뢰 임계(0.8 placeholder)` (신뢰 확립).
- `normal` — 그 외.
> 조사 우선순위 관점(blueprint §5.1)에서는 `contradicted`/`low_evidence`가 "확인 필요" 신호로 가장 주목 대상이고, `high_confidence`는 "확립" 신호다. `rank`는 신뢰도 순(정렬 순)이며, `signal`이 검토 우선 신호를 담당한다.

## 모듈·API

`prototype/orc_citadel/ranking.py`:

```python
@dataclass(frozen=True)
class RankedConclusion:
    subject_id: str
    rank: int
    confidence: dict
    signal: str
    predicates: dict

class ConclusionRanking:
    """S30 결론 프로젝터를 정렬하는 read-only subject 랭킹."""
    def __init__(self, zone, high_confidence=0.8, low_confidence=None): ...
    def ranked(self, signal: str | None = None, limit: int | None = None) -> list[RankedConclusion]: ...
    def by_signal(self) -> dict:  # signal별 subject 묶음
```

`signal=` 필터, `limit=` 커서/정렬된 상위 N. **read-only** (불변식 §3-3).

## TDD (Red→Green→Refactor)

`test_ranking.py` — S30 `_seed_claims`/`_populate_zone` 패턴 재사용.

1. **Red**:
   - `ranked` — value DESC 정렬, 1-based rank.
   - tie-breaker — 동률 value 시 독립 출처 DESC.
   - `signal` — contradiction>0 → `contradicted`; 근거 0 → `low_evidence`; value≥0.8 → `high_confidence`; else `normal`.
   - `signal=` 필터.
   - `limit=` 상위 N.
   - `by_signal` — signal별 subject 묶음.
   - read-only — mutation 미노출; zone 상태 불변.
   - 빈 zone → [].
2. **Green** — 최소 구현.
3. **Refactor** — 중복 없음.

## 실데이터 스모크

curated.duckdb (3 subject 결론) — ranked 목록·signal 분류 출력, S29/S30 값과 정합.

## 커밋

**code-only (behavioral)**: `feat(S31): subject confidence ranking (read-only)`. 문서·README·ROADMAP 변경 없음.

## 완료 기준

- [ ] Red→Green→Refactor, 전체 테스트 통과 (기존 248 + 신규).
- [ ] 결정성 — 동일 zone → 동일 순위.
- [ ] read-only — 쓰기 경로 미노출.
- [ ] 실데이터 스모크 — 정렬·signal pad.
