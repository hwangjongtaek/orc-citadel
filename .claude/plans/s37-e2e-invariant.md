# S37 · 전 계층 종합 통합 검증 (E2E Invariant Suite)

## 목표

S27의 `test_integration_invariants.py`를 확장해 **파이프라인 → 영속 → read-only 소비 계층(S28-S31) → 평가 계층(S33-S36)**까지의 end-to-end 왕복을 하나의 결정적 harness로 검증한다. 개별 stage가 green이지만 계층 간 접점에서 깨질 수 있는 불변식을 fixture golden으로 고정한다.

## 검증할 E2E 불변식

소규모 결정적 raw docs(재사용)를 `run_pipeline`으로 처리한 후:

1. **소비 계층 일관성** — 파이프라인 산출(어세션)·Catalog·evidence·conclusion·ranking이 서로 일치:
   - Catalog assertions 수 == pipeline assertions 수 (영속·조회 왕복).
   - assertion마다 `for_assertion_by_claim`의 근거가 claim 포함 — evidence ≥ 1 (만족 주장).
   - Conclusion `evidence_count`는 subject 전체 distinct 근거 문서 수.
   - Ranking subject 목록 == conclusion subject 목록 (일관).
2. **평가 계층 일관성** — EvalHarness가 파이프라인 캐노니컬·모순과 대조 가능:
   - `EvalHarness(zone=...)`가 캐노니컬·conflict를 Auro로 읽음 (빈 골든 vacuous).
   - 골든 영속(S34) 후 EvalSuite가 zone에서 로드 → metrics·gate 리포트 (결정성).
3. **총괄 결정성** — 동일 입력 재실행 → 소비·평가 산출 동일.

## module·test

`tests/test_e2e_invariants.py` — S27 DOC1/DOC2 픽스처 재사용(복사), + 골든 1건 영속.

## TDD (Red→Green→Refactor)

- S27에 이미 파이프라인·캐노니컬이 동작하므로 대부분 Green 기대. Red는 "아직 없는 계층 접점 검증"으로 최소 실패 1개를 만들어 Green으로.

계획 테스트:
1. **Red** — E2E 접점 불변식 (위 3묶음). 예비 실행으로 어느 접점이 깨지는지 확인.
2. **Green** — 깨진 접점에 대한 최소 수정.
3. 이 stage는 주로 **검증 테스트 추가** (S27처럼) — 구현 기능 변경 최소화.

## 실데이터 스모크

curated.duckdb — 파이프라인 없이 존재하는 상태로 소비·평가 계층 E2E 일관성 확인 (S28-S36 산출 간 정합).

## 커밋

**code-only**: `feat(S37): end-to-end invariant suite — pipeline→consumption→eval consistency`.

## 완료 기준

- [ ] Red→Green, 전체 테스트 통과 (기존 311 + 신규).
- [ ] E2E 왕복 — 파이프라인→소비→평가 일관.
- [ ] 결정성 — 재실행 동일.
