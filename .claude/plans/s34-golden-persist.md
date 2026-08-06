# S34 · 골든셋 영속화 + 평가 파이프라인 통합 (design 10 §2.3)

## 목표

S33 하네스는 `golden`을 **주입**받아야 동작한다. 실데이터에는 골든셋이 없어 gate가 FN 신호만 본다. 이 단계에서 **골든셋을 curated zone에 영속**하고, S33 하네스가 **파이프라인 산출(캐노니컬·모순)과 자동 대조**하는 평가 파이프라인을 구현한다 (design 10 §2.3 저장·버저닝).

## 골든셋 계약 (design 10 §2.3)

curated zone에 `golden_pairs` 테이블 추가 — claim pair 골든셋:

| 컬럼 | 설명 |
| --- | --- |
| `golden_id` | 결정적 PK (`. sha256`) |
| `claim_a` / `claim_b` | claim pair |
| `label` | `equivalent | contradicts | unrelated` (design 10 §2.1) |
| `split` | `dev | test` (ADR-1007) |
| `gold_version` | 레코드 버전 (온톨로지·벌크 버전 추적) |
| `labeled_by` | `human:<user>` (human review as data) |
| `labeled_at` | labeling 시각 |
| `rationale` | 검토 이유 (불변식 §3-7 3자 보존) |
| `original_prediction` | 파이프라인이 원래 판정한 것 (회귀 대조용) |

결정적 PK — 재실행 idempotent (03 §5, ON CONFLICT no-op).

## 평가 파이프라인 통합

`EvalHarness` 확장 — zone에서 골든셋을 직접 읽어 파이프라인 산출과 대조:
- `EvalHarness(zone=..., golden=None)` → `zone.golden_pairs()`에서 골든 자동 로드 (기존 주입은 유지, 뒤쪽 호환).
- **gate 반영**: design 10 §3.1 "승격 게이트" — 골든 gate 미달 시 `report()`가 `promotion_blocked=True` + 미달 지표 명시. 단 phase 0 소량이라 **block 여부만 트래킹, CI 차단 아님**.

## module·API

**`curated_zone.py`** — `golden_pairs` 테이블 + `persist_golden_pair` + `golden_pairs()` + parquet export 추가.

**`eval_harness.py`** — `EvalHarness`가 zone로부터 골든 자동 로드, `promotion_blocked` in report.

## TDD (Red→Green→Refactor)

1. **Red** — `test_golden_persist.py` / `test_eval_harness` 확장:
   - `persist_golden_pair` — 결정적 golden_id, 2회 upsert idempotent (동일 식별).
   - `golden_pairs()` — JSON 복원.
   - EvalHarness zone 모드 — 골든 자동 로드, 캐노니컬 대조 (골든 기반 P/R).
   - `promotion_blocked` — 골든 gate 미달 시 True.
   - parquet export에 golden_pairs 포함.
   - read-only — harness는 쓰기 미노출 유지.
2. **Green** — 최소 구현.
3. **Refactor** — 중복 없음.

## 실데이터 스모크

curated.duckdb에 소량 골든셋 영속 → EvalHarness 파이프라인 평가 → gate 리포트.

## 커밋

**code-only (behavioral)**: `feat(S34): golden-set persistence + pipeline eval integration (design 10 §2.3)`. 문서·README·ROADMAP 변경 없음.

## 완료 기준

- [ ] Red→Green→Refactor, 전체 테스트 통과 (기존 284 + 신규).
- [ ] 결정성 — 동일 골든셋 → 동일 평가.
- [ ] read-only — harness 쓰기 미노출.
- [ ] 실데이터 스모크 — 골든 영속 + 파이프라인 평가 + gate pad.
