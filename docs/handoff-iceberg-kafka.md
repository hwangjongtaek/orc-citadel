# Apache Iceberg (Q6) · Kafka (Q7) 도입 — handoff

> 작성 2026-09-22. 근거: 코드·데이터·원격 호스트 **실측**(본문 §1에 측정 명령 포함).
> 위임 대상: **단일 세션**. 완료 시 ROADMAP §5 changelog + design/README Spec 반영.
>
> **상태: 미착수.** 선결 결정 3건(§2)은 사용자 판단 사항이며, 결정 전에는 G1 이후로 진행하지 않는다.

## 0. 배경 — 여기까지 끝났고, 여기서 멈췄다

2026-09-20~21 세션에서 "1,000만 문서에서 현재 스택이 durable 한가"를 판정하고 블로커 4건을 해소했다.

| 해소 | 수단 | 실측 |
| --- | --- | --- |
| RAM 전량 상주 | raw parquet 샤드 스트리밍 (ADR-308) | 15k→20k 문서 구간 RSS 1,728MB 평탄 |
| inode 30M 요구 | source 별 샤드 | 313,413 → 1 (같은 코퍼스) |
| nightly 전량 재빌드 | 증분 승격 (`incremental_promote`) | 신규 1건 0.147–0.158s · 무변경 0.01s |
| 커넥터 부재 | kind 3종 + `COLLECTORS` (ADR-405) | — |
| (부수) dedup O(N²) | LSH 밴딩 + 서명 영속 (ADR-404) | 배증비 2.41→2.00 · 12.4ms/doc · **재현율 1.0000**(703건·790쌍) |

2026-09-21 결정: **추가 측정과 소스 등록을 중단하고 Iceberg·Kafka 도입 후 재개한다.**
남은 확장이 "더 모으기"가 아니라 **저장·스트리밍 기반 자체를 바꾸는 문제**로 넘어갔기 때문이다.
ROADMAP Q6 유보→도입 결정, Q7 신규 등록 (ROADMAP §5 2026-09-21, ADR 표 Q6/Q7).

### 0.1 단일 세션 범위 — 정직하게

전 범위(I+K)를 한 세션에 욱여넣으면 **검증이 얕아진다**. 그래서 **게이트 3개**로 끊었고,
각 게이트는 커밋 경계이자 중단 가능 지점이다. 게이트에서 멈춰도 저장소는 Green 이다.

- **G1** — 의존성·카탈로그 기동 (인프라만, 데이터 경로 무변)
- **G2** — normalized zone Iceberg 전환 + 스키마 진화 실측  ← **한 세션 권장 종착점**
- **G3** — curated zone 전환
- **K** — Kafka. **별도 세션 권장** (§6). 이 문서에 계약까지 적어두되 착수는 G3 이후.

## 1. 실측 근거 — 트리거가 실제로 걸린 곳

Iceberg 승격 트리거는 01 §122 의 "테이블 >수천만 row, 스키마 진화 필요"다.
**curated 가 아니라 normalized 의 `segments` 에서 먼저 걸린다.**

| 축 | 현재 실측 | 1,000만 투영 | 판정 |
| --- | --- | --- | --- |
| `segments` 행 수 | 105,252 docs → **823,629행** (7.83행/doc) | **≈7,830만 행** | 트리거 초과 |
| normalized 파일 | `prototype/data/oc.duckdb` **261.6MB 단일 파일** | **≈24.9GB 단일 파일** | 단일 writer 한계 |
| curated 행 수 | claims 722 · mentions 2,957 · conflicts 2,917 | **투영 불가** — 신호 슬라이스만 처리된 상태 | 미측정 (§5 T7) |
| 원격 디스크 | 502G 중 **183G 여유** | 03 §9 목표 "총 수백 GB" | **같은 자릿수 — 위험** |
| 원격 자원 | 125GB RAM · 64 core | — | 브로커·카탈로그 수용 가능 |

재현 명령:

```bash
# 행 수·파일 크기
cd prototype && .venv/bin/python -c "
import duckdb,pathlib
c=duckdb.connect('data/oc.duckdb',read_only=True)
print(c.execute('SELECT count(*) FROM documents').fetchone(),
      c.execute('SELECT count(*) FROM segments').fetchone(),
      round(pathlib.Path('data/oc.duckdb').stat().st_size/1e6,1),'MB')"
# 원격 자원
ssh hwangjongtaek@10.0.0.11 'free -g | head -2; df -h / | tail -1; nproc'
```

## 2. 선결 결정 3건 — 사용자 판단 (착수 전 질의할 것)

| # | 결정 | 배경 | 기본안 |
| --- | --- | --- | --- |
| **D1** | 원격 디스크 증설 여부 | 183G 여유 vs 목표 "수백 GB". **Iceberg 는 스냅샷·메타데이터 보존으로 저장량을 늘린다**(미측정 — 증가율은 G2 에서 실측해 보고할 것) | 증설 없이 G2 까지 진행, G2 실측치로 재판단 |
| **D2** | Iceberg REST catalog 구현체 | 새 컨테이너 1개. Lakekeeper / Apache Polaris / Nessie | 단일 호스트·운영 단순성 기준으로 후보 비교표를 만들어 제시 후 결정 |
| **D3** | Kafka vs Redpanda | 단일 호스트 compose. Redpanda 는 JVM·ZooKeeper 부담 없음, Kafka(KRaft)는 생태계 표준. RAM 125GB 라 양쪽 가능 | Redpanda (단일 호스트 전제) |

**D2·D3 은 후보를 임의 선택하지 말 것.** 비교 근거를 만들어 사용자에게 올리고 답을 받는다.

## 3. 착수 전 정정해야 할 설계 오표기 1건

**ADR-102 의 전제가 코드와 다르다.**

- 01 §124 표는 event stream 을 `PostgreSQL queue (SKIP LOCKED)` → `Kafka/Redpanda` **승격**으로 적는다.
- 그러나 `SKIP LOCKED` 큐는 **조사 job 경로에만** 존재한다 (`prototype/orc_citadel/investigation_store.py:335`).
- **수집→승격 경로에는 큐가 없다.** APScheduler 상주 프로세스가 함수를 직접 호출한다
  (`prototype/scripts/scheduler_runner.py` → `_promote_zones` → `_promote_new_docs` → `promote_incremental`).

→ Q7 착수 시 **ADR-102 를 정정**하고 Kafka 를 "승격"이 아니라 **수집·승격 경로의 신규 도입**으로 기록한다.
조사 job 경로의 Postgres 큐는 **그대로 둔다** (W3 계약·11 §113 감사 경로 — 건드리면 감사 추적이 깨진다).

## 4. Phase I — Apache Iceberg (Q6)

Kafka 보다 **먼저**다. 이유: 다중 writer 안전한 테이블 포맷 없이 Kafka consumer 를 늘리면
curated/normalized 동시 쓰기가 깨진다. **Iceberg 의 낙관적 커밋이 Kafka 병렬화의 전제조건이다.**

### G1 · 의존성·카탈로그 (데이터 경로 무변)

| 파일 | 작업 | 내용 |
| --- | --- | --- |
| `prototype/pyproject.toml` | 수정 | `pyarrow`·`pyiceberg` 추가. **둘 다 현재 미설치** — `duckdb 1.5.5` 의 iceberg 확장은 읽기 중심이라 쓰기 경로는 pyiceberg 가 현실적 (설치 후 실제 쓰기 지원 범위를 **확인하고 기록**할 것) |
| `prototype/Dockerfile` | 수정 | 의존성 반영 |
| `docker-compose.yml` · `docker-compose.prod.yml` | 수정 | REST catalog 서비스 추가 (D2 결정 후). 현재 prod 9컨테이너 → 10 |
| `deploy/` | 확인 | 신규 서비스 볼륨·헬스체크 |
| `prototype/tests/test_prod_compose_credentials.py` 외 compose 테스트 | 수정 | 신규 서비스의 자격증명·포트 계약 |

**G1 종료 조건:** 카탈로그 컨테이너 기동 + 빈 테이블 생성/조회 왕복 1회. **기존 스위트 Green.**

### G2 · normalized zone 전환  ← 권장 종착점

대상은 `documents`·`segments` 2테이블. 03 §1.1 확정 파티션을 **그대로** 쓴다.

| 테이블 | 파티션 키 | 정렬 |
| --- | --- | --- |
| `documents` / `segments` | `source_id`, `publication_time`(월 버킷) | `doc_id` |

| 파일 | 작업 | 주의 |
| --- | --- | --- |
| `prototype/orc_citadel/duckdb_zone.py` | 전환 | `NormalizedZone` 의 백엔드 교체. **upsert key `(doc_id, parser_version)` 계약 불변** — 동일 버전 재persist 는 no-op, version bump 는 새 row (04 §3.3) |
| `prototype/orc_citadel/viewer.py` | **필수 동반** | `duckdb.connect` **직접 호출 6곳** — `NormalizedZone` 을 우회한다. 여기를 빠뜨리면 뷰어가 조용히 빈 화면을 낸다 (§5 T1) |
| `prototype/orc_citadel/incremental_promote.py` | 수정 | `NormalizedZone(str(data_dir/"oc.duckdb"))` (72행). 신규 문서 anti-join 이 DuckDB `ATTACH` 기반 (§5 T3) |
| `prototype/scripts/rebuild_zones.py` | 수정 | 79행 |
| `prototype/orc_citadel/parquet_snapshot.py` | 검토 | `duckdb.connect` 2곳 — Iceberg 전환 후 존 스냅샷의 의미 재정의 |
| `prototype/orc_citadel/persist_smoke.py` | 수정 | 스모크 |
| 테스트 8종 | 수정 | `test_duckdb_zone` · `test_rebuild_zones` · `test_incremental_promote` · `test_zone_concurrency` · `test_viewer_{gate,archive,witnesses,aux}` |
| `docs/design/03-storage-and-data-model.md` | 수정 | §1 표(초기 저장소)·§2 인접 절 + **ADR 신규 1행** |

**G2 에서 반드시 실측할 것 (Iceberg 도입의 나머지 절반):**

1. **스키마 진화** — `parser_version` bump 시 03 §1.1 이 약속한 **파티션 단위 교체**가 성립하는가.
   지금은 전량 재빌드뿐이다. 성립하면 이것이 Iceberg 도입의 최대 이득이다.
2. **저장량 증감** — D1 판단 근거. 전환 전 261.6MB 대비 스냅샷 포함 실크기.
3. **증분 승격 회귀** — 기준선 대비 (아래 §6 표).

**G2 종료 조건:** 위 3개 실측 + 스위트 Green + 로컬 뷰어 실기동 확인.

### G3 · curated zone 전환

**G2 보다 훨씬 위험하다 — `CuratedZone` 소비 파일이 65개다** (normalized 는 12개).
G2 를 커밋·검증한 뒤에만 착수한다.

| 테이블 | 파티션 키 | 정렬 |
| --- | --- | --- |
| `mentions` / `claim_candidates` / `evidence_candidates` | `dedup_version`, `status` | `doc_id` |
| `assertions` | `tx_from`(월 버킷) | `subject_id`, `predicate` |

- **`dup_signatures`/`dup_bands`(ADR-404) 가 최대 리스크.** 증분 승격의 dedup 은 밴드 키
  SQL 조회로 후보만 가져온다(전체 서명 ≈5GB 적재 회피). Iceberg 로 옮기면 이 조회의
  물리 특성이 바뀐다 — **전환 후 반드시 재측정**(§6).
- `assertions` 는 ADR-307 상 `graph_mutations` 의 projection 이다. **SoT 가 아니므로**
  재생성 가능성만 지키면 된다. 반대로 mutation log(Postgres) 전환은 **범위 밖**(§8).

### G3 이후 · raw / 객체 백엔드 정리 (Iceberg 와 함께 닫을 것)

- raw 는 이미 parquet 샤드다(ADR-308). **Iceberg 테이블로 올릴지, immutable append-only
  계약 때문에 파일 백엔드로 둘지 명시 결정**하고 03 §2.1 에 기록한다.
- **MinIO 객체 백엔드(03 §2.1 ②)가 아직 샤드 미전환** — 파일 백엔드와 물리 배치가 갈라져 있고,
  이는 ADR-308 에 "정직 표기"로 남아 있는 미해결 항목이다. 여기서 닫는다.

## 5. 함정 — 전부 이 저장소에서 실제로 밟은 것

| # | 함정 | 회피 |
| --- | --- | --- |
| **T1** | `viewer.py` 가 `duckdb.connect` 로 normalized 를 **직접 6회** 연다 — zone 클래스를 우회 | G2 에서 반드시 동반 수정. 누락 시 실패가 아니라 **빈 화면**으로 나타난다 |
| **T2** | DuckDB `ATTACH` 는 **prepared parameter 를 받지 않는다** (`ATTACH ? AS zone` → ParserException) | `incremental_promote` 는 f-string + "경로는 caller 소유" 주석으로 처리 중. 같은 패턴 유지 |
| **T3** | 증분 승격은 **배치 스트리밍**이다 (`BATCH_SIZE=1_000`) | 리팩터링 중 `list(...)` 로 전량 물질화하면 cold-start RAM 블로커가 되살아난다. 회귀 테스트가 이미 있다 |
| **T4** | 전량 재빌드 경로가 서명을 영속하지 않으면 다음 증분 dedup 이 **조용히** 코퍼스를 못 본다 | `pipeline_runner` 의 `signature_sink` 경로 유지 |
| **T5** | 아카이브/API 상한을 조용히 끊지 않는다 — `ResultCapReached` (ADR-405) | Kafka 이벤트 모델링에도 그대로 적용 (§6 K2) |
| **T6** | ROADMAP 의 "16.28ms/doc → 1M 4.5h" 류 투영은 **2,000건 배치 계수라 스케일에서 무효**(dedup 이차항 미포함) | 인용 금지. 유효 계수는 LSH 후 12.4ms/doc 선형 |
| **T7** | curated 행 수는 신호 슬라이스만 처리된 값(claims 722) — **1,000만 투영 근거로 쓸 수 없다** | honest-gap §6.2. 미측정은 미측정으로 표기 |
| **T8** | 환경 의존 실패 2건이 상시 존재: `test_claude_cost.py::test_usage_zero_when_stub`, `test_claude_judge.py::test_stub_fallback_not_logged_as_schema` (LLM 프로바이더가 env 에 있으면 stub 경로 미진입) | 신규 실패와 혼동하지 말 것. 파일 격리로 무관함 확인됨 |

## 6. Phase K — Kafka / Redpanda (Q7) · 별도 세션 권장

G3 완료 후 착수. 이 문서는 **계약까지만** 고정한다.

| # | 작업 | 계약 |
| --- | --- | --- |
| K1 | 브로커 기동 | D3 결정. compose base/prod + deploy |
| K2 | 토픽·실패 시맨틱 | 01 §4 stage 경계(S1–S7)를 토픽으로. **01 §4.1 의 lease/retry/DLQ 를 consumer group + DLQ topic 으로 이관** (01 §114 에 이미 예고). **quarantine 은 DLQ 가 아니다** — 재시도로 해소 불가한 데이터 결함은 quarantine, transient 만 retry/DLQ |
| K3 | 수집측 producer | ADR-405 커넥터 3종이 fetch 결과를 토픽으로. `ResultCapReached` 를 **이벤트로 어떻게 표현할지** 설계 — 조용한 누락 금지 계약(T5)이 큐 경계를 넘어야 한다 |
| K4 | 승격측 consumer 병렬화 | `promote_incremental` 을 consumer 로. **멱등성이 관건** — at-least-once 배달을 content-hash `doc_id` 가 흡수하는지, 특히 `dup_signatures` 영속이 중복 실행에 안전한지 **테스트로 고정**(01 §4.1 "at-least-once + idempotent = effectively-once") |
| K5 | 스케줄러 역할 축소 | APScheduler 는 dispatch 만. `_rebuild_zones`(전량) / `_promote_new_docs`(증분) 경계 재정의 |
| K6 | ADR-102 정정 | §3 |

## 7. 검증

**도입 전 기준선 — 전환 후 이 표를 다시 채워 비교하고, 악화 시 보고한다.**

| 축 | 기준선 | 측정 방법 |
| --- | --- | --- |
| 증분 승격 · 신규 1건 | **0.147–0.158s** | `promote_incremental(raw, data)` 1건 투입 |
| 증분 승격 · 무변경 | **0.01s** | 동일 호출 재실행 |
| 증분 승격 · 758건 배치 | **70.6s** | — |
| dedup | **12.4ms/doc** · 배증비 2.00 · 재현율 **1.0000** | `test_dedup_lsh` + 실코퍼스 |
| raw skip 인덱스 | **0.02s** (전환 전 18.9s/103k) | `RawShardStore.stored_urls` |
| raw 디스크 | 888MB → **67.3MB** (13.2×) | 같은 코퍼스 |
| normalized 저장 | **261.6MB / 823,629행** | §1 명령 |

공통:

- 스위트: `cd prototype && .venv/bin/python -m pytest -q` — **현재 1,536건 수집**. T8 2건 제외 Green 유지.
- TDD 준수 (AGENTS.md): Red→Green→Refactor. 구조 변경과 행위 변경은 **커밋 분리**(Tidy First).
- 로컬 뷰어 실기동: `.venv/bin/python -m orc_citadel.viewer` → 8공간 라우트 200.

## 8. 배포·규약

- 배포: **저장소 루트에서** `scripts/deploy.sh hwangjongtaek@10.0.0.11` (prototype/ 에서 실행하면 실패한다).
  원격 접근은 **VPN 필요**.
- git 상태(2026-09-22): 브랜치 `feat/scale-10m-storage-and-promotion`, **origin 대비 4커밋 미푸시**, 트리 깨끗.
  기반 커밋 `e0f020a`(raw 샤드·증분 승격·커넥터 3종).
- 문서 3단계(design/README §104): ① 해당 설계 문서 수정 ② **README Spec version**(현재 `1.6.0`) ③ ROADMAP §5 changelog.
- ADR 신규 행 필요: Iceberg 전환(03) · Kafka 도입(01) · ADR-102 정정(01).
- honest-gap §6.2 — **미측정을 측정된 것으로 쓰지 않는다.** 추정치는 추정으로 표기.
- 커밋 트레일러: `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`

## 9. 범위 밖 (이 handoff 에서 하지 않는다)

- **소스 등록** — 라이선스 깨끗한 2건(arXiv non-cs 1.73M · Federal Register 1.01M), 미확인 6건 합산 3.3M.
  1,000만 수집 재개는 Iceberg·Kafka 도입 **이후**다 (2026-09-21 결정).
- **`_arxiv_date_windows` 결함 2건** — 10k 초과 월 조용한 누락, 상한 `start="202608112359"` 하드코딩.
  별도 수정 건으로 남긴다.
- **mutation log 의 Iceberg 전환**(03 §1 표 `Postgres(→Iceberg)`) — replay 정확성이 걸려 있어 G3 안정화 후 별건.
- **조사 job 경로의 Postgres 큐**(W3) — §3 참조. 건드리지 않는다.
- **ClickHouse·K8s 승격** — 각자 별도 트리거(01 §5).
