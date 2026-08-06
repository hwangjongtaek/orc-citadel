# S29 · 어세션별 근거·신뢰도 다차원 집계 프로젝션

## 목표

설계 09 §4 Confidence 표현 계약(다차원) — `value` 단일 게이지 금지. 어세션(assertion) 카탈로그 위에, 각 assertion의 **근거(evidence) 구조 기반 다차원 신뢰도**를 계산하는 read-only 투사 계층을 추가한다. 조사 UX(09 §3 conclusion, §2.3 claims/evidence)가 바로 소비할 수 있는 집계 봉투를 채운다.

**근거(evidence) 정의 (현재 prototype 데이터 계층 기준):** assertion은 `claim_candidates`(provenance_ref = claim_id)를 거쳐 `mentions`(문서·문장)로 연결된다. 서로 다른 문서(doc_id)에서 동일 (subject, predicate) 주장을 입증하는 mention-claim이 **지지 근거**다. `conflict_candidates`(같은 subject, 모순 predicate 쌍)는 **반박 증거** 신호다. 문서 중복은 `dup_clusters`(뿌리 클러스터)로 **독립성 보정**한다 (09 §3 note, §2.4 lineage).

## 축 (설계 09 §4)

각 assertion의 집계 봉투:

| 필드 | 설명 |
| --- | --- |
| `value` | 집계 신뢰도 ∈ [0,1] — 증거 구조 기반. |
| `evidence_count` | 지지 근거 수 (주장을 입증하는 서로 다른 claim-문서). |
| `independent_source_count` | dup_cluster 보정 후 독립 출처 수 (지지 근거 문서의 뿌리 클러스터 수). |
| `basis` | 계산 근거의 사람 읽는 설명 (독립성 보정·반박 존재·신뢰도 성분). |
| `dimensions` | 분해 축: `support` / `contradiction` / `coverage`. |

> 09 §4 원칙: ① `value`만으로 UI 구성 금지 → 봉투 필수. ② `value`는 source reputation이 아니라 **claim별 증거 구조**로 계산 (blueprint §11). ③ confidence(집계)·Claim.confidence(추출 신뢰도)·Claim.certainty(화자 확실성) 별개 축 (ADR-202) — 집계는 자체 증거 구조로만, 추출 confidence를 `value`에 직접 곧이곧대로 쓰지 않음.

## 계산 규칙 (결정적)

**support** (지지 성분): assertion의 claim을 입증하는 서로 다른 문서에서의 지지 근거 수에 따라 정규화.
- `n_support = # distinct doc_id` (해당 (subject, predicate, object) 주장을 담은 서로 다른 문서)
- `support = 1 - 1/(n_support + 1)` — 근거 0이면 0, 1이면 0.5, 2면 2/3, … (미관측 한계: 한 문서만으로는 확정 불가, blueprint §11).

**contradiction** (반박 성분): 같은 subject의 모순 신호에 따라 하락 위험 노출.
- `conflict_records = # conflict_candidates` (이 assertion의 claim 쌍을 포함하는 모순)
- `contradiction = 1 - 1/(conflict_count + 1)`, 단 conflict 없으면 0.

**coverage** (증거 공백): 근거가 시간·측면을 덮는 정도 — 지지 근거 수에 비례하는 커버리지 축.
- `coverage = n_support / max(n_support + n_unknown, 1)` — prototype은 미관측 subclaim 추정 없음, n_unknown=0 → coverage = 1.0 (n_support>0), 0.0 (n_support=0).

**confidence `value`** (집계 증거 구조):
- `value = support * (1 - contradiction)` — 지지 성분에 반박 위험으로 감쇄. 0 ≤ value ≤ 1.

**독립성 보정** — `independent_source_count`:
- 지지 근거 문서의 doc_id 각각에 대해 `dup_clusters`에서 `root_doc_id`(뿌리)를 찾아 **고유 root 수**로 집계. 클러스터 미포함 문서는 자기 자신을 root로 간주 (독립 1). 09 §3 note "복제 500건 = 독립 증거 2건" 보정.

**basis** — 사람 읽는 설명:
- `"지지 근거 {n_support}건 (독립 출처 {indep}건), 반박 근거 {n_conflict}건"` + 신뢰도 성분.

## 모듈·API

`prototype/orc_citadel/assertion_evidence.py`:

```python
@dataclass(frozen=True)
class AssertionEvidence:
    assertion_id: str
    confidence: dict  # 09 §4 봉투: value/evidence_count/independent_source_count/basis/dimensions
    supporting_docs: list[str]   # 지지 근거 문서 (root 기준 중복 시 대표 1)
    contradicting_claims: list[str]  # 반박 근거 claim
    evidence_count: int
    independent_source_count: int

class AssertionEvidenceProjector:
    """curated zone (assertions+claim_candidates+conflict_candidates+dup_clusters)의
    read-only 투사. 조사 UX(09 §2.3·§3)가 소비하는 근거·신뢰도 집계."""
    def __init__(self, zone): ...
    def for_assertion(self, assertion_id) -> AssertionEvidence | None: ...
    def for_subject(self, subject_id) -> dict:  # subject 내 어세션 요약 (조사 결론 입력)
    def all(self) -> list[AssertionEvidence]: ...
```

**read-only** (불변식 §3-3): 어떤 메서드도 쓰기·영속·그래프 mutation 하지 않는다. zone 행 읽기만.

## TDD (Red→Green→Refactor)

데이터 픽스처는 `test_catalog.py` 패턴 재사용 (`_populate_zone`). 테스트:

1. **Red** — `test_assertion_evidence.py`:
   - `evidence_count`/`support` — 서로 다른 2문서가 동일 (subj,pred) 주장 → `evidence_count=2`, `dimensions.support≈0.667`.
   - `independent_source_count` — dup_cluster로 묶인 2문서(같은 root) → `independent_source_count=1` (독립성 보정).
   - `contradiction` — conflict_candidates 존재 시 `dimensions.contradiction>0`, `value`가 감쇄.
   - `value` 범위·성분 — `value = support*(1-contradiction)` 인과성 (+반박 시 하락).
   - `basis` — 사람 읽는 설명 포함 (`지지 근거`, `독립 출처`, `반박 근거`).
   - read-only — projector에 `apply`/`persist`/mutation 미노출; zone 상태 불변.
2. **Green** — 최소 구현.
3. **Refactor** — 중복 없음·의도 명확.

## 실데이터 스모크

기존 수집 데이터(curated zone, 395문서)로 projector를 실행해 어세션별 신뢰도를 출력하고 09 §4 값 범위·독립성 보정을 확인한다.

## 커밋

**code-only (behavioral)**: `feat(S29): assertion evidence & multi-dimension confidence projector (09 §4)`. 문서·README·ROADMAP 변경 없음 — 09 §4 이미 Review 스펙.

## 완료 기준

- [ ] Red→Green→Refactor, 전체 테스트 통과 (기존 227 + 신규).
- [ ] 결정성 — 동일 zone → 동일 집계.
- [ ] read-only — 쓰기 경로 미노출.
- [ ] 실데이터 스모크 — 09 §4 봉투 필드가 pad.
