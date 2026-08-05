# S23 LLM 판정 영속화 (03 §7.1 version tuple, 05 §4.2·§5.2)

> 권장안: S22가 계산한 LLM 판정 산출물(canonical 7라벨·contradiction verdict)을 version
> tuple(03 §7.1 5축)과 함께 curated zone에 영속해, provenance·재실행(replay)·모델 교체
> 추적이 가능하게 한다. 룰-결정 산출물과 LLM 판정을 분리 저장(judged_by)한다.

## 배경·범위

결정적 파이프라인에서 LLM 판정은 현재 휘발(스모크에서만 계산). 저장해야 그래프·검증·감사
계약(불변식 §3-2)이 지켜진다.

| 결정 | 근거 |
| --- | --- |
| `canonical_llm_records` 新테이블 — 7라벨 판정 근거 | 05 §4.2, 비equivalent도 근거 보존 |
| `conflict_verdicts` 新테이블 — verdict 실체 | 05 §5.2, ADR-504 |
| `version_tuple` JSON 5축 저장 | 03 §7.1: ontology/schema/prompt_hash/model_id/code |
| 결정적 (a,b) PK · idempotent upsert · Parquet export | 03 §5 재생성, curated_zone 패턴 재사용 |
| 룰결정(`pipeline`)과 LLM(`llm`) 판정을 judged_by로 구분 | 저장 계약 02 §3.1 |

## 구현 계획

- **curated_zone.py**: 신규 테이블 2 + `persist_canonical_llm_record`/
  `persist_conflict_verdict`/`canonical_llm_records`/`conflict_verdicts`/Parquet export.
- **llm_pipeline_smoke.py**: `_BoundedJudge`가 실제 LLM 판정 dict를 기록 →
  `persist_llm_verdicts(zone, judged)`가 S21 평면 version 키를 03 §7.1 5축 JSON으로 조립해 영속.
- **TDD**: Red→Green — 저장·조회·idempotent upsert·Parquet 포함 검증.
- **Smoke**: 395문서 하이브리드로 실제 LLM 판정 20건을 영속해 version tuple 확인.

## DoD

- 두 테이블 저장·조회, (a,b) PK idempotent upsert
- version_tuple이 03 §7.1 5축 JSON으로 왕복 (model_id/prompt_hash 포함)
- Parquet export 포함, 전체 테스트 통과, code-only 커밋
- 실 스모크: LLM 판정이 version tuple과 함께 영속되는지 확인

## 한계 (문서화)

- 실 LLM 판정은 비용·네트워크 의존 — 스모크는 소량, 회귀는 사용자가 실행
- version tuple의 model_id는 산출물 핀/date란 (ADR-701) — 배포 시 교체 지점만 모델
