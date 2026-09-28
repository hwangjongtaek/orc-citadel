# 운영 배포 Runbook — 로컬 개발 / 원격지 운영 (SSH · Docker Compose)

상태: **Stable** (v1.2.0) · 갱신: 2026-09-17 · 소유: design 01 §6.2가 참조하는 운영 runbook 정본의 배포 절.
토폴로지·정책의 정본은 [`../design/01-architecture.md`](../design/01-architecture.md) §6이고,
본 문서는 **절차(operation)** 만 소유한다.

## 1. 운용 모델

| 환경 | 역할 | 실행 형태 | 코드 |
|---|---|---|---|
| 로컬 (Mac) | 개발·테스트 | venv 네이티브 + launchd (§6.2 현행) | 작업 디렉터리 |
| 원격지 — `10.0.0.11` (§1.1) | **운영 (prod)** | Docker Compose 전체 스택 (§6.1) | `~/Projects/private/orc-citadel` |

- 배포 통로: **SSH** (`scripts/deploy.sh`). git clone/pull 없이 rsync 코드 전송 → 원격 빌드·기동.
- 데이터: named volume `orc-citadel-proddata` (viewer/scheduler/investigation-worker의
  `/app/data`) + 스토어 볼륨 (pgdata/minio-data/neo4j-data/opensearch-data). 코드 재배포와 무관하게 보존.
- **데이터 정책 (확정 · 2026-09-17): 새 원격 prod 는 빈 상태로 시작한다** — 기존 원격
  volume 및 로컬 corpus(raw ~105k·curated·slo06 누적)는 이관하지 않는다. rsync 도
  `prototype/data`를 제외한다. 따라서 원격 viewer 의 curated 존·SLO-06 7d 누적은
  **0에서 새로 시작**하며, 이전 원격·로컬 실측 이력(ROADMAP §5)과 운영 지표는 서로 다른 모집단이다.
- **단일 발화 주체 이전**: 운영 nightly(07:07 수집 / 07:37 SLO-06)는 원격 `scheduler`
  컨테이너가 소유한다. 원격 기동 후 로컬 launchd 는 반드시 정지 (§3.5) — 이중 발화 금지.

### 1.1 배포 대상 (2026-09-17 전환)

이하 예시 명령의 `<host>`는 모두 이 대상이다 (`deploy.sh`는 임의 ssh-host를 받는 일반 스크립트).

| 항목 | 값 |
|---|---|
| 호스트 | `10.0.0.11` (LAN) |
| 계정 | `hwangjongtaek` |
| SSH | `hwangjongtaek@10.0.0.11` — 공개키 인증 설정 완료 |
| 인증 | BatchMode 로그인 가능 |
| 리포 경로 | `~/Projects/private/orc-citadel` (`deploy.sh`의 `REMOTE_PATH`와 동일) |
| Docker 런타임 | Docker 29.3.0 · Docker Compose v5.1.0 (2026-09-17 확인) |
| viewer 접근 | loopback 바인딩 유지 → SSH 터널 (§3.3) |

### 1.2 compose 서비스 목록

| 서비스 | 역할 | 호스트 포트 (prod) | 비고 |
|---|---|---|---|
| postgres / minio / neo4j / opensearch | 인프라 스토어 | 없음 (loopback 도 제거) | `exec`/터널로만 |
| prototype | viewer (API + 정적 서빙) | `127.0.0.1:8791` | §3.3 |
| scheduler | nightly dispatch 상주 | 없음 | §4 |
| investigation-worker | PostgreSQL 조사 queue 소비·read-only evidence 실행 | 없음 | §3.2.1 |
| grafana | 파이프라인 모니터링 | `127.0.0.1:3000` | §3.4 |
| duckdb-ui | 존 브라우징 사이드카 | `127.0.0.1:4213` | [data-browsing.md](data-browsing.md) |
| redpanda-init | S1–S7 토픽 28개 멱등 생성 후 종료 | 없음 | one-shot |
| zone-init | Iceberg 존 테이블 멱등 생성 후 종료 | 없음 | one-shot · §3.7 |

## 2. 최초 1회 프로비저닝 (원격 호스트)

```bash
# 사전 조건 확인 (없으면 설치)
ssh hwangjongtaek@10.0.0.11 'docker --version && docker compose version'
ssh hwangjongtaek@10.0.0.11 'sudo usermod -aG docker $USER'   # Docker socket 권한이 없을 때만; 재로그인 필요

# 코드 + .env 설치 (deploy.sh가 첫 실행 시 자동)
scripts/deploy.sh hwangjongtaek@10.0.0.11          # → .env 템플릿 생성 안내 후 종료
ssh hwangjongtaek@10.0.0.11 "vi ~/Projects/private/orc-citadel/.env"   # 운영 크리덴셜 수동 주입
scripts/deploy.sh hwangjongtaek@10.0.0.11          # → 빌드 & 기동
```

> 새 원격지에서 Docker/Compose 실행은 확인했다. 재부팅 뒤에도 Docker daemon이 자동으로
> 기동되도록, 해당 호스트의 Docker 런타임 방식에 맞춰 별도로 구성해야 한다. daemon이
> 멈추면 스택 전체와 nightly 수집도 멈춘다.

`.env` 규칙: 원격 호스트의 리포 최상위에만 존재, `chmod 600`, **git/전송 대상 절대 제외**
(`deploy.sh`의 rsync 필터와 `.gitignore`가 이중 봉인). 템플릿은 `.env.production.example`.

## 3. 일상 배포 / 운영 절차

### 3.1 배포 (로컬 작업본 → 원격)
```bash
scripts/deploy.sh hwangjongtaek@10.0.0.11              # rsync → compose build → up -d → ps
scripts/deploy.sh hwangjongtaek@10.0.0.11 --dry-run    # 전송 대상 사전 확인
```
> 배포 소스는 로컬 **작업 디렉터리**다 (커밋 여부 무관). 배포 전 `git status`로
> 의도하지 않은 변경이 섞이지 않았는지 확인할 것. 스크립트 일반성(임의 ssh-host)은 §1.1 참조.

### 3.2 상태 / 로그
```bash
scripts/deploy.sh hwangjongtaek@10.0.0.11 --status
scripts/deploy.sh hwangjongtaek@10.0.0.11 --logs              # 전체 추적
scripts/deploy.sh hwangjongtaek@10.0.0.11 --logs scheduler    # 서비스별
scripts/deploy.sh hwangjongtaek@10.0.0.11 --logs investigation-worker
```

### 3.2.1 durable investigation worker 확인

`prototype`이 `202`로 생성한 job은 `investigation-worker`가 소비한다. worker는
PostgreSQL에 investigation/job/step/report만 쓰고 `/app/data/curated.duckdb`는
read-only로 연다.

```bash
scripts/deploy.sh hwangjongtaek@10.0.0.11 --logs investigation-worker
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  --profile prototype --env-file .env ps investigation-worker
```

worker 재시작 뒤 lease가 만료된 `running` job은 같은 investigation ID로 재claim된다.
Council의 `queued`가 계속되면 worker 상태·PostgreSQL 연결과 `/app/data/curated.duckdb`
존재를 순서대로 확인한다.


### 3.3 viewer 접근
운영 기본은 loopback 바인딩(`VIEWER_BIND=127.0.0.1`) — 외부 공개 대신 SSH 터널:
```bash
ssh -N -L 8791:127.0.0.1:8791 hwangjongtaek@10.0.0.11     # → 브라우저 http://localhost:8791
```
전 인터페이스 공개가 불가피하면 `.env`의 `VIEWER_BIND=0.0.0.0` 변경 후 재배포
(방화벽 검토 선행). 인프라 스토어(pg/minio/neo4j/opensearch)는 항상 loopback 고정.

### 3.4 Grafana 접근 (파이프라인 모니터링, TS-6)
viewer 와 동일 정책 — loopback 바인딩(`127.0.0.1:3000`) + SSH 터널:
```bash
ssh -N -L 3000:127.0.0.1:3000 hwangjongtaek@10.0.0.11    # → 브라우저 http://localhost:3000
```
- 익명 접속은 **Viewer(읽기 전용)**. 대시보드 편집은 `admin` /
  `.env` 의 `GRAFANA_ADMIN_PASSWORD` 로 로그인 — 단, 대시보드·datasource 는
  provisioning as code(`deploy/grafana/provisioning/`)가 SoT 라 UI 편집은 영속되지 않는다.
- 대시보드: `Orc Citadel · Pipeline` (`/d/citadel-pipeline`). 소스는 nightly flush 가
  쌓는 `pipeline_run_metrics`·`pipeline_slo_observations` 뿐이며, stage 처리량·quarantine
  패널의 **No data 는 미계측의 정직한 표시**다(honest-gap — 계측 배선 전까지 그대로 둔다).
- **최초 1회**: read-only DB 계정 적용(첫 flush 로 메트릭 테이블 생성된 이후):
  ```bash
  set -a; source .env; set +a
  docker compose exec -T postgres \
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
         -v grafana_password="$GRAFANA_DB_PASSWORD" \
    < deploy/grafana/init-readonly.sql
  ```
- 이미지(`grafana/grafana-oss` 버전 핀)는 배포 1회 pull 필요. 원격 pull 불가 시
  로컬에서 `docker save grafana/grafana-oss:<핀버전> | ssh <host> docker load`.

### 3.5 로컬 스케줄러 정지 (원격 운영 전환 시 1회)
```bash
launchctl unload ~/Library/LaunchAgents/com.orc-citadel.nightly.plist
# plist가 개체 저장소에 없으면: prototype/scripts/com.orc-citadel.nightly.plist 참조
pgrep -f scheduler_runner.py   # 로컬 잔존 프로세스 없어야 함
```

### 3.5.1 호스트가 응답하지 않을 때

배포는 **연결 실패를 "미배포 호스트" 로 오판하지 않는다.** ssh 가 자기 연결
오류(255)를 내면 즉시 멈추고 이유를 말한다 — 프로비저닝 경로로 들어가거나
rsync 를 시도하지 않는다. 2026-09-25·26 에 호스트가 내려가 있을 때 배포가
`== first-run: 원격 디렉터리 및 .env 프로비저닝 ==` 을 출력하던 오동작의
수정이다. 프로비저닝 경로 자체에도 `[ -f .env ] ||` 가드가 있어, 판정이 어떤
이유로 틀리더라도 기존 운영 크리덴셜을 덮어쓰지 않는다.

호스트가 돌아오면 같은 명령을 다시 실행하면 된다. nightly 는 grace 하루(§6.2)라
내려가 있던 동안 놓친 발화를 기동 후 보충하고, 보충되지 못한 공백은 다음 런의
`promotion_gap` 지표로 드러난다(§4).

### 3.6 롤백
코드는 rsync 미러이므로 `git checkout <직전 release 커밋>` 후 `deploy.sh` 재실행.
이전 이미지 태그는 남아있지 않으므로(`:latest` 단일 태그), 코드만 롤백하면 다음
`up -d`에서 해당 코드로 재빌드된다. 데이터는 volume 보존이라 코드 롤백과 무관.

### 3.7 존 초기화와 데이터 이관은 다른 일이다

`zone-init` one-shot 이 배포마다 **Iceberg 테이블을 멱등 생성**하고, viewer·
promotion-consumer 는 그 완료를 기다린 뒤 뜬다. cutover 배포에서 이 단계가 없어
viewer 가 빈 카탈로그를 읽고 `NoSuchTableError` 로 죽었던 것이 계기다. 신규
호스트든 운영 중 호스트든 결과가 같고, legacy DuckDB 유무와 무관하다.

**legacy → Iceberg 이관은 배포에 걸려 있지 않다. 일부러 그렇다.**
`migrate_normalized_to_iceberg`·`migrate_curated_to_iceberg` 는 대상 존이 원본과
어긋나고 비어 있지 않으면 **전량 삭제 후 legacy 로 덮어쓴다** — 일회성 cutover
도구로서는 맞는 동작이지만 운영 중 시스템에서는 데이터 파괴다. 실제 격차
(2026-09-26 prod): curated `mentions` **656 vs legacy 494**, `dup_signatures`
**303 vs 183** — 배포마다 이관이 돌았다면 cutover 이후 이벤트 경로 산출이 통째로
사라졌다. legacy `*.duckdb` 는 롤백 경로로 의도적으로 남겨둔 파일이라 "원본이
있으면 이관" 규칙도 성립하지 않는다.

그래서 이관은 비어 있지 않은 대상을 만나면 **거부하고 무엇이 지워질지 알린다.**
정말로 legacy 를 정본으로 되돌리는 경우에만 `--force` 를 명시한다:

```bash
# 신규 호스트 cutover (대상이 비어 있음 — force 불필요)
docker compose -p orc-citadel -f docker-compose.yml -f docker-compose.prod.yml \
  --profile prototype --env-file .env run --rm prototype \
  python scripts/migrate_normalized_to_iceberg.py
# 운영 중 존을 legacy 로 되돌린다 (cutover 이후 산출이 사라진다 — 거의 항상 오답)
#   ... migrate_curated_to_iceberg.py --force
```

### 3.8 스냅샷 보존 (메타데이터 정리)

Iceberg 스냅샷 이력은 커밋마다 길어지고, 그 길이가 **커밋 비용**에 들어간다
(로컬 실측: 이력 401개에서 커밋 388.3ms, 정리 후 263.6ms). 기본은 **dry-run** —
무엇이 사라질지 먼저 본다:

```bash
docker compose -p orc-citadel -f docker-compose.yml -f docker-compose.prod.yml \
  --profile prototype --env-file .env exec -T promotion-consumer \
  python -m orc_citadel.snapshot_retention            # dry-run (기본)
#   ... snapshot_retention --apply                     # 실제 정리
```

보존 규칙: 기본 7일 창 + **나이와 무관하게 최근 3개**(롤백 여지) + 현재 스냅샷은
절대 제외. 이력을 지우는 작업이므로 `--apply` 전에 dry-run 결과를 확인한다.

**읽기는 빨라지지 않는다.** 읽기 비용은 스냅샷 수가 아니라 **데이터 파일 수**에
묶인다(같은 400행: 400파일 545.5ms vs 1파일 3.9ms). 파일 수를 줄이는 compaction 은
PyIceberg 0.12 에 없으므로 이 명령의 범위 밖이다 — handoff §8-1 참조.

### 3.9 작은 파일 재작성 (읽기 비용 회수)

읽기 비용은 **데이터 파일 수**에 묶인다(실측: 400행이 400파일이면 436.5ms,
1파일이면 7.1ms). 쓰기 배치화 이후 새로 쌓이는 파일은 배치당 1개지만, 사고 때
흩어진 파일은 남아 있다. 기본은 **dry-run**:

```bash
docker compose -p orc-citadel -f docker-compose.yml -f docker-compose.prod.yml \
  --profile prototype --env-file .env exec -T promotion-consumer \
  python -m orc_citadel.compaction --data-dir /app/data          # dry-run
#   ... compaction --data-dir /app/data --apply                   # 실제 재작성
```

테이블 전량을 덮어쓰므로 **승격이 돌지 않는 시점에** 실행한다(lag 0 확인).
재작성 전후 내용 digest 를 비교하고, 불일치면 이전 스냅샷으로 되돌린 뒤 실패를
알린다. `--max-rows`(기본 500k)를 넘는 테이블은 거부한다 — 전량을 메모리에
올리는 방법이라 그 경계가 곧 이 명령의 유효 범위다.

## 4. nightly 운영 확인

원격 스케줄러는 grace 하루(§6.2)로 당일 보충 실행한다. 정상 축적 여부:
```bash
scripts/deploy.sh hwangjongtaek@10.0.0.11 --logs scheduler   # [collect]/[slo06] 발화 로그
docker compose ... exec prototype python -c "print(open('/app/data/slo06_accum.json').read()[-500:])"
```
수집 원문은 `/app/data/raw/<source>/...` (proddata 볼륨).

> **전제 — 대상 호스트 가동**: `10.0.0.11`의 Docker daemon과 호스트 자체가 실행 중이어야
> 스케줄러가 발화한다. 슬립·전원차단 구간은 §6.2의 grace 하루 정책이 당일만 보충하며, 이틀 이상 끊기면 그날은 결측으로 남는다.
>
> **알려진 한계 (2026-09-05 실측)**: grace 보충은 **스케줄러 프로세스가 살아있는 동안의
> 슬립**만 커버한다. 컨테이너/데몬 재시작 시 `scheduler_runner` 가
> `add_job(replace_existing=True)` 로 job 을 재생성해 영속 store 의 미발화 시각이
> 리셋되므로, **재시작을 가로지르는 놓친 발화는 보충되지 않는다** (09-05 07:07 실측 —
> 데몬 다운 중 놓친 당일 발화가 재기동 후 next_run=익일로 스킵). 코드 수정 전까지
> 데몬 재기동 후에는 당일치 수동 보충을 검토: `... exec scheduler python
> scripts/nightly_collect.py`.

## 5. 백업

| 대상 | 명령 |
|---|---|
| 애플리케이션 data (duckdb·raw·slo06) | `docker run --rm -v orc-citadel-proddata:/data:ro -v $(pwd):/out alpine tar czf /out/proddata-$(date +%F).tar.gz -C /data .` |
| Postgres | `docker compose ... exec -T postgres pg_dump -U $POSTGRES_USER $POSTGRES_DB \| gzip > citadel-pg-$(date +%F).sql.gz` |
| MinIO / Neo4j / OpenSearch | phase 초기엔 볼륨 스냅샷 수준: 스택 정지 후 `docker run --rm -v <vol>:/data -v $(pwd):/out alpine tar czf ...` |

백업 주기는 nightly 수집 직후 권장.

## 6. 승격 지점 (design 01 §6.3)

K8s·분리 worker 승격은 **측정된 병목**이 정당화할 때만 (blueprint §7.2). 본 compose
구조는 그 때까지 정본이다. 승격 시 변경 대상: `docker-compose.prod.yml` 교체,
`deploy.sh`는 유지(호스트 프로비저닝 스크립트로 축소).

## 뷰어 정적 자산 (2026-09-07)

viewer 는 `/assets/*` 로 테마·폰트·히어로 이미지를 서빙한다. 이미지에는
`prototype/` 만 COPY 되므로(§prototype/Dockerfile) 자산은 compose 바인드 마운트로
주입한다 — 히어로 PNG 19MB 를 이미지에 굽지 않기 위해서다.

    ./docs/mockups/assets                       -> /app/static/img        (ro)
    ./design-system/theme-citadel/dist/theme.css -> /app/static/theme-citadel.css (ro)
    ./design-system/fonts/dist                   -> /app/static/fonts     (ro)

rsync 가 `docs/`·`design-system/` 을 원격에 보내므로 원격에서도 그대로 물린다.
경로를 바꾸려면 `VIEWER_ASSETS_IMG` · `VIEWER_ASSETS_THEME` · `VIEWER_ASSETS_FONTS`.
자산이 없어도 뷰어는 뜬다 — 토큰 폴백 hex 로 화면은 서고 이미지만 빠진다(정직 갭).
