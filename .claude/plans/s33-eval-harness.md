# S33 · 평가 하네스 (design 10 §1·§2, 소량 골든셋)

## 목표

프로젝트 핵심 가치(design 10 §8 "KG가 얼마나 정확한가")에 수치로 답하는 **경량 평가 하네스**를 추가한다. design 10 §1.2 KG 품질 지표 중, S29/S30 신뢰도 프로젝션이 **정확한지 P/R로 검증**하는 소량 골든셋 기반 harness.

**범위 축소**: 전체 design 10 (entity/claim/조사 품질 전 지표)는 대형 — 이번 stage는 **claim pair 기반 골든셋으로 S29 근거·S30 결론·S31 랭킹이 기대와 일치하는지** 판정하는 핵심 경로만 구현한다. 나머지(§1.1 데이터품질, §1.3 조사품질, §1.4 성능)는 후속.

**골든셋 계약** (design 10 §2.1):
- claim pair 세트: 각 쌍 `(claim_a, claim_b, gold_label)` — gold_label ∈ `equivalent / contradicts / unrelated` (design 10 §2.1 캐노니컬·모순 라벨에서 필수 3종).
- 골든셋은 **human review as data** (design 10 §2.2, 불변식 §3-7) — 원 모델 출력·정답·이유 3자 보존.
- `split ∈ {dev, test}` 표기 (ADR-1007 — 튜닝/게이트 분리).

## 지표 (design 10 §1.2, claim/contradiction)

골든 claim pairs 대신 **S29-S31 프로젝션으로 파생**한다 — harness는 골든 라벨과 파이프라인이 실제로 처리한 결과를 대조:

- **Canonicalization 정확도** (design 10 §1.2): golden `equivalent` 쌍이 S9 캐노니컬화로 실제 병합(member_of 동일 캐노니컬)되는지 — **TP/FP/FN** → P/R/F1.
  - `TP = 골든 equivalent 쌍이 실제 같은 CanonicalClaim`
  - `FP = 골든 unrelated/contradicts 쌍이 잘못 같은 캐노니컬`
  - `FN = 골든 equivalent 쌍이 서로 다른 캐노니컬로 분리`
- **Contradiction P/R** (design 10 §1.2): golden `contradicts` 쌍이 실제 conflict_candidates에 존재하는지.
  - `TP = 골든 contradicts 쌍이 conflict로 발견`
  - `FP = 골든 unrelated가 conflict로 잘못 판정`
  - `FN = 골든 contradicts가 미발견`

**gate**: design 10 §1.2 — canonicalization `gate: ≥ 0.85`, contradiction `gate: P ≥ 0.90`, `target: R ≥ 0.75`. (phase 0 소량이므로 리포트에 표시, gate 미충족 시 리포트 명시 — CI block은 후속.)

## module·API

`prototype/orc_citadel/eval_harness.py`:

```python
@dataclass(frozen=True)
class GoldenPair:
    claim_a: str
    claim_b: str
    label: str            # equivalent | contradicts | unrelated
    split: str = "dev"    # dev | test (ADR-1007)
    rationale: str = ""

@dataclass(frozen=True)
class Metric:
    tp: int; fp: int; fn: int
    @property precision/recall/f1

class EvalHarness:
    """골든셋(claim pair) 대비 파이프라인 산출을 대조하는 read-only 평가."""
    def __init__(self, zone, golden=None): ...
    def from_clusters(self, canonical_claims, member_of, conflicts): ...  # 직접 주입
    def canonicalization_metrics(self, split=None) -> Metric
    def contradiction_metrics(self, split=None) -> Metric
    def report(self, split=None) -> dict   # 지표 + gate 통과 여부
```

**read-only** (불변식 §3-3): 골든셋 대조만 — 영속·mutation 없음. 골든셋은 harness 외부에서 주입(디버깅용 클러스터·conflict 주입은 harness에 포함 안 함, `from_clusters`는 조회만).

## 데이터 계층 (재사용)

- 캐노니컬: `zone.canonical_claims()`(member_claim_ids) · `zone.member_of()`
- 모순: `zone.conflict_candidates()`
- 파라미터로 직접 주입 가능 (unit 테스트에서 결정적 확인)

## TDD (Red→Green→Refactor)

`test_eval_harness.py` — 골든셋 + 캐노니컬/conflict 상태 주입.

1. **Red**:
   - `canonicalization_metrics` — 골든 equivalent 병합 쌍 → TP; unrelated 분리 → 정확.
   - FP — 골든 unrelated가 캐노니컬로 잘못 병합 → FP 반영, precision 하락.
   - FN — 골든 equivalent가 분리 → FN 반영, recall 하락.
   - `contradiction_metrics` — 골든 contradicts 발견 TP; 누락 FN; 오판 FP.
   - `split` 필터 — dev/test 각각 평가 (ADR-1007).
   - `report` — 지표 + gate 통과 여부 (precision/recall/f1, gate 임계).
   - `Metric.precision/recall/f1` — 0/0 경계 안전 (division by zero → 0.0).
   - read-only — `apply`/`persist` 미노출.
2. **Green** — 최소 구현.
3. **Refactor** — 중복 없음.

## 실데이터 스모크

curated.duckdb (29 어세션) — 캐노니컬·conflict 상태로 실제 P/R/F1 계산, gate 대비 리포트.

## 커밋

**code-only (behavioral)**: `feat(S33): eval harness — golden claim-pair P/R for canonicalization & contradiction (design 10)`.

## 완료 기준

- [ ] Red→Green→Refactor, 전체 테스트 통과 (기존 271 + 신규).
- [ ] 결정성 — 동일 골든셋·상태 → 동일 지표.
- [ ] read-only — 쓰기 미노출.
- [ ] 실데이터 스모크 — P/R/F1 + gate 리포트 pad.
