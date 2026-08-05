# S24 정식 파이프라인 모듈 — 단일 진입점 통합

> 권장안: S5→S20 결정적 체인 + S21→S23 LLM 판정·영속을 하나의 파이프라인 모듈로 묶어,
> `load_raw_zone → authoritative graph`까지 단일 진입점(`run_pipeline`)으로 실행하고
> version tuple·provenance가 전 구간 끝까지 드러나도록 한다.

## 배경·범위

현재 체인은 스모크(`pipeline_full_smoke.py`/`llm_pipeline_smoke.py`)에 흩어져 있고,
그래프 재구축(graph_smoke)과 영속(S23)이 분리돼 있다. 정식 파이프라인은 이를 하나로
묶어 재사용·검증·감사 진입점을 단일화한다 (아키텍처 01, 06 §2).

| 결정 | 근거 |
| --- | --- |
| `run_pipeline(metas, zone, judge=None) -> PipelineResult` 단일 진입점 | 재사용·일관 검증 (01) |
| phase별 단계 함수 분리(추출/해소/게이트/캐노니컬/모순/어세션/그래프) | 테스트·가독성 (Tidy) |
| `judge` 선택 주입 → 결정적-우선, 미결만 LLM | 05 §5/§6 |
| `PipelineResult`에 aggregate·그래프·판정 요약 반환 | 검증·감사 계약 (불변식) |
| 그래프 이벤트(gate mutations) → GraphService 재구축으로 authoritative 노드-엣지 | 06 §2, 03 §7 replay |

## 구현 계획

- **`pipeline_runner.py`** (신규): `run_pipeline(metas, zone, judge=None)` —
  각 raw doc: extract_html→parse→mentions→resolve→mention 게이트→claims→claim 게이트
  →assertion materialize. 이후 canonicalize(judge)→contradiction(judge)→ LLM verdic트
  영속(S23 helper 재사용) → gate events→GraphService.apply → `PipelineResult`(counts,
  graph, 판정 요약) 반환.
- **TDD**: 모의 judge로 미결 쌍 판정·영속·그래프 노드 수·결정성 불변식 검증. judge
  미주입 시 결정적 결과 그대로.
- **Smoke**: 395문서로 단일 진입점 실행 — aggregate·그래프 노드·영속 LLM 판정 확인.

## DoD

- `run_pipeline`이 단일 호출로 raw→그래프·영속 전체 완료
- judge 미주입 = 결정적, 주입 = 미결만 LLM (05 §5/§6)
- LLM 판정이 S23 테이블에 version tuple로 영속
- GraphService가 authoritative 그래프 재구축, 결정성 불변식 유지
- 전체 테스트 통과, code-only 커밋 (behavioral)

## 한계 (문서화)

- 실 LLM 판정은 비용·네트워크 의존 — smoke 소량, 회귀는 사용자
- prototype 진입점 — 성능(병렬 수집 등)은 후속 최적화 단계
