# S41 · 실데이터 승격 적용 + Open Question 실측 리포트

## 목표

S38–S40의 승격 파이프라인을 **실데이터에 실제 적용**해 design 10 §3.1 동작을 검증하고, Open Question(Q3/Q5)의 **최소 실측**을 read-only 리포트로 산출한다. 소스 데이터 오염 없이 **임시 복사** zone 사용.

## 범위 (명확한 경계)

**결정적·read-mostly 파이프라인 적용** (골든 영속은 임시 복사에서만):
- 실데이터 캐노니컬 병합 멤버 → 골든(equivalent) 영속 (S34 패턴).
- `PromotionPipeline.run(version_tuple=...)` 5축 판정: 초기(INITIALIZED) → model 교체 minor(PROMOTED) → 온톨로지 major(BLOCKED+revalidate).
- **Q3 실측** (ER/컨피던스 임계): 실데이터 claim·mention의 confidence 분포(min/max/분위) → 저신뢰 임계 후보 관찰.
- **Q5 실측**: LLM 비용 — 실데이터는 결정적 체인만 실행(LLM 미실행)이므로 **"결정적-only, LLM 비용 미발생(측정 불가)"** 으로 명시 (†표기). 후속 LLM 조사 실행 시 측정.

**read-only** (불변식 §3-3): 리포트 생성은 조회, 골든 영속은 임시 복사에서만.

## module·API

`prototype/orc_citadel/phase0_report.py`:

```python
@dataclass(frozen=True)
class Phase0Report:
    promotion: dict      # 5축 판정 (INITIALIZED/PROMOTED/BLOCKED major/minor)
    q3: dict             # confidence 분포 + 저신뢰 임계 후보
    q5: dict             # LLM 비용 상태 (deterministic-only)
    summary: str         # 한국어 요약

def generate_report(zone, model_axes=...) -> Phase0Report   # read-mostly
```

## TDD (결정성·shape에 한해)

`test_phase0_report.py`:
1. **Red** — module 미존재.
2. generate_report → promotion/q3/q5 필드, summary 포함.
3. confidence 분포 — 0~1 범위, min/max/p50.
4. read-mostly — zone(원본) 영속 미발생 (임시 복사에서만 골든).
5. 결정성 — 동일 zone → 동일 리포트.

## 실데이터 실행

임시 복사 curated.duckdb → generate_report → Phase0Report 출력 + Open Question 표 갱신 근거.

## 커밋

**code-only (behavioral)**: `feat(S41): phase0 promotion smoke + Q3/Q5 minimal empirical report`.

## 완료 기준
- [ ] Red→Green, 전체 테스트 통과 (기존 353 + 신규).
- [ ] 결정성 — 동일 zone → 동일 리포트.
- [ ] read-only — 원본 zone 상태 불변.
- [ ] 실데이터 — 5축 판정·Q3 실측·Q5 상태 pad.
