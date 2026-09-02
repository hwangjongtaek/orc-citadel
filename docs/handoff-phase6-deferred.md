# 위임 지시문 — Phase 6 deferred 실측 항목 (여건 충족 시 실행)

> 새 세션에 이 문서 전체를 전달한다. 목표: Phase 6 에서 **실데이터·인프라·모집단 종속으로 deferred 된 실측 항목**을, 아래 "착수 조건"이 충족된 시점에 실측·measured 전환한다. **착수 조건이 미충족이면 억지로 진행하지 않는다** — 인위 데이터로 채우는 것은 honest-gap(§6.2) 위반.

## 0. 컨텍스트 (30초 요약)

- Phase 6(Stable 운용) 코드 봉인 축은 **완결** (스위트 1064 Green, 2026-09-02). 남은 것은 전부 외부 조건 종속 실측.
- 진행 SSOT: `docs/ROADMAP.md` §1·§3 Phase 6·§5 Changelog. SLO 정의 정본: `docs/design/11-observability-and-governance.md` §2.3.
- 수집은 APScheduler 상주 스케줄러(`prototype/scripts/scheduler_runner.py`, launchd)가 매일 07:07 수집·07:37 SLO-06 누적을 자동 수행 중 (design 01 §6.2 상시 로컬 네이티브 운용).

## 1. 항목별 착수 조건·실행 절차

### 1-1. SLO-06 7d rolling 재확정 (최근접 — 자동 축적 중)

- **착수 조건**: `prototype/data/slo06_accum.json` 에 **7일치 이상** nightly 관측이 누적된 시점 (nightly_slo06 이 매일 append — launchd 상주 정상 동작 전제).
- **실행**: `slo06_accum.accum_recent`(7d) → `accum_slo06` 재판정. `schema_pass_rate` 기준 `evaluate_slo06`.
- **완료 처리**: SLO-06 "확정(잠정)" → **확정** 전환을 ROADMAP §1·§3·design 11 §2.3 에 기록.
- **함정**: 맥 슬립으로 결측일이 생길 수 있음(A28 misfire grace 는 '깨어난 뒤 당일치'만 보충). 결측일은 정직하게 n 부족으로 기록하고 7일 채워질 때까지 대기.

### 1-2. #4 contradiction·lineage 실데이터 골든 (모순 재료 확보됨 — 우선 시도 가치)

- **착수 조건 (근접)**: 같은 사건에 대한 **독립 소스 상이 보도** 문서쌍 존재. A25 로 재료 확보됨 — `press-tomshardware`(독립 언론 50+건, nightly 로 증가 중) ↔ `nvidia` 공식(38건), URL 겹침 0 완전 독립. 수출통제/제재·반도체 기사가 겹치는 사건 영역.
- **실행**:
  1. raw 에서 같은 사건(예: H200 중국 수출, SMIC 가격)을 다룬 Tom's Hardware ↔ 벤더 공식 문서쌍 식별.
  2. 해당 문서만 파이프라인(추출→canonicalize→contradiction, `contradiction.py`·`counter_evidence.py`)에 투입해 **자연발생 모순**이 검출되는지 실측.
  3. 검출 시: 골든 등록 — `eval_harness.EvalHarness` 의 `golden`(GoldenPair)·`golden_lineage` 주입 계약, zone 영속은 `zone.golden_pairs()` 경로 (design 10 §2.3). lineage 골든은 dedup cluster(`dedup.py`) 계보로 동일 방식.
  4. 미검출 시: **미검출을 그대로 기록** (모순 후보 문서쌍·판정 결과·원인 분석). 가짜 골든 제작 금지.
- **주의**: SLO-06 무비용 LLM(judge) 경로(`claude_judge.py`, bunker-flash)를 판정 보조로 쓸 수 있으나, 골든의 정답 라벨은 사람 확인을 거친다.

### 1-3. SLO-07 (quarantine dwell-time) measured 전환

- **착수 조건**: **real quarantine 모집단 > 0**. 현재 0건은 데이터 셰이프 특성으로 확정됨(2026-08-18 조사 완결) — 비해소 subject claim 은 추출 단계에서 폐기되어 게이트에 도달 불가.
- **모집단이 생기는 경로**: 재평가/저신뢰(LLM judge) 경로·exploration 추출 등 **새 기능이 추가될 때** 자연 발생. 1-2 의 contradiction 실측이 저신뢰 claim 을 만들면 그때 재확인.
- **금지**: 추출/게이트 임계를 낮춰 quarantine 을 **인위 유발하지 않는다** — precision-first 불변식 §3-4·design 05 §3 위배로 이미 기각된 방안.
- **실행(조건 충족 시)**: dwell-time 분포 실측 → `not-measured(모집단 0)` → measured 전환, 목표치(≤3d) 재확인.

### 1-4. 1M 물리 부하 실측 (#9)

- **착수 조건**: (a) 1M 규모 corpus (현 raw ~105k, 포화 — **새 소스 대량 확보 또는 부하 인프라의 합성 아닌 실데이터** 필요) 또는 (b) 별도 부하 인프라에서의 재개 결정.
- **현재 상태**: 실측 분모 확보됨 — SLO-08 전체 104,677건 병렬(k=10) 완주 334,033ms → per-doc 3.191ms. 1M 투영 병렬 ≈53.2min·순차 ≈4.5h — **투영은 measured=False 유지** (물리 완주가 아니면 measured 라 쓰지 않는다).
- **실행(조건 충족 시)**: `distributed_batch.shard`(k 파티셔닝) + `bulk_pipeline` 로 SLO-08 실측과 동일 방법론으로 1M 완주 → `phase4_report.project_time_to_scale` measured=True 전환.

### 1-5. SLO-01/07/08 목표치 확정

- **착수 조건**: 각 SLO 의 실측 표본이 충분히 축적된 뒤 (SLO-01 은 축적 중, 07 은 1-3, 08 은 벤치 공개 계약이라 게이트 없음 — 목표치를 둘지 자체를 결정).
- **실행**: design 11 §2.3 의 목표치를 실측 분포 기반으로 확정하고 nightly 게이트(`slo_nightly_gate`) 임계에 반영. **계약 변경이므로 Spec 번프 검토** 대상.

## 2. 지켜야 할 불변식·규약

1. **honest-gap (§6.2)** — 실측 없이 measured 라 쓰지 않는다. 투영·잠정·모집단 0 은 그대로 라벨링.
2. **precision-first (§3-4)** — 모집단을 만들려고 품질 게이트를 완화하지 않는다.
3. **AGENTS.md** — TDD·Tidy First·최소 변경. 코드 변경 없는 실측 런은 문서만 커밋(raw 데이터는 gitignore).
4. **재현 가능 기록** — 실측 런의 파라미터(윈도우·k·n·cap)와 원수치를 changelog 에 남긴다.

## 3. 알려진 함정

- `slo_log`(`SloObservationLog`) 는 **in-memory — 런 간 누적 없음**. SLO-05 표본 n 은 런별 arXiv `total` 파라미터 연동 (과거 "런 간 누적" 서술은 정정됨).
- DuckDB 잠금: 실측 런과 viewer·수집 파이프라인을 동시 실행하지 않는다 (read-only 연결 사용).
- content-hash idempotency 는 **동적 페이지에서 중복 저장**을 일으킨다(A9 gov 사례 — 보류·미배선). 새 소스 추가 시 본문이 요청마다 달라지는지 먼저 확인.
- arXiv 과거 연대는 2025-03 까지 전 소진 — arXiv 재수집 시도는 skip 만 쌓는다.

## 4. 검증 (완료 조건)

1. 항목별 실측 원수치가 changelog 에 기록되고, ROADMAP §1·§3 상태 행이 not-measured/measured=False → measured 로 전환.
2. 코드 변경이 있으면 전체 스위트 무회귀 (기준선 1064 passed, 2026-09-02).
3. 착수 조건 미충족 항목은 "미충족 확인 + 근거"만 기록하고 종료해도 완료로 인정.

## 5. 완료 후 기록 (3단계 규칙)

(1) design 11 §2.3(및 해당 설계 절) 수정 → (2) `docs/design/README.md` Spec version 갱신(계약 변경 시) → (3) `docs/ROADMAP.md` §5 Changelog 기록. 커밋 메시지 한글 관례.
