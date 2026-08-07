# S40 · 5축 version-aware 승격 (design 10 §3.1, 03 §7.1, README §2.3)

## 목표

S39 `PromotionPipeline`이 승격 baseline을 불투명 문자열 `version`으로 다룬다. 설계는 version 5축 tuple(`ontology_version`/`schema_version`/`prompt_template_hash`/`model_id`/`extraction_code_version`) 변경 감지로 승격을 결정하도록 명시한다 (10 §3.1 "프롬프트 교체는 prompt_template_hash, 모델은 model_id, 온톨로지는 ontology_version … 변경으로 감지", 03 §7.1). 이 5축을 승격 baseline 키·판정에 반영한다.

**원칙:** 기존 문자열 version과 뒤쪽 호환 유지. 5축 dict가 주어지면 그 핑거프린트를 baseline version으로 사용.

## 5축 계약 (03 §7.1, README §2.3)

```python
version_tuple = {
  "ontology_version": "1.0.0",        # 02 §6 minor/major
  "schema_version": "0.1.0",
  "prompt_template_hash": "sha256:…",
  "model_id": "claude-opus-4-8",
  "extraction_code_version": "p1",
}
```

## 온톨로지 호환 (02 §6.3, 10 ADR-1005)

- **major**(`1.0.0→2.0.0`: 타입 제거·의미 변경) → **전량 재평가 필요** (재라벨·migration).
- **minor**(`1.0.0→1.1.0`: predicate 추가 등 하위호환) → 승격 baseline으로 계속 판정 가능 (부분).

`ontology_major_bump(cur, prev) -> bool` — major 변경 감지.

## module·API (확장, 뒤쪽 호환)

**`promotion_pipeline.py`** — version 인자를 5축 dict도 허용:
```python
class PromotionPipeline:
    def run(self, version=None, *, version_tuple=None) -> PromotionResult
        # version(문자열) 또는 version_tuple(dict) — 둘 다 없으면 "default".
        # version_tuple이면 fingerprint로 baseline version 결정 + ontology_major_bump 판정.
```

**`versioning.py`** (신규) — 5축 유틸:
```python
def fingerprint(vt: dict) -> str      # 결정적 hash: vt-<sha>
def ontology_major_bump(prev: str, cur: str) -> bool   # semver major 증가
def same_axis(prev, cur, axis) -> bool  # 특정 축만 변경 여부 (부분 재평가 감지)
```

## TDD (Red→Green→Refactor)

`test_versioning.py` / `test_promotion_pipeline` 확장:

1. **Red**:
   - `fingerprint` — 5축 dict → 결정적 `vt-` ID, 순서 무관.
   - `ontology_major_bump` — 1.0.0→2.0.0 True; 1.0.0→1.1.0 False; 동일 False.
   - `same_axis` — 해당 축만 변경 여부.
   - PromotionPipeline.run(version_tuple=...) — 5축 fingerprint baseline으로 INITALIZED/PROMOTED.
   - ontology major bump 시 → 결과에 `ontology_major_bump=True` + `revalidate_required` 신호.
   - minor bump → 재평가 불필요(정상 판정).
   - 뒤쪽 호환 — 기존 문자열 version 그대로 동작.
   - read-only — dry_run 영속 없음 유지; 결정성.
2. **Green** — 최소 구현.
3. **Refactor** — 중복 없음.

## 실데이터 스모크

임시 복사 — 5축 reader로 baseline → fingerprint → major/minor bump 판정 → PROMOTED·revalidate 신호.

## 커밋

**code-only (behavioral)**: `feat(S40): 5-axis version-aware promotion — ontology major revalidation (design 10 §3.1, 03 §7.1)`.

## 완료 기준

- [ ] Red→Green→Refactor, 전체 테스트 통과 (기존 336 + 신규).
- [ ] 결정성 — 동일 5축 → 동일 판정.
- [ ] 뒤쪽 호환 — 문자열 version 유지.
- [ ] 실데이터 스모크 — 5축 baseline·major/minor pad.
