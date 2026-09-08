# 운영 배포 Runbook — 로컬 개발 / 원격지 운영 (SSH · Docker Compose)

상태: **Stable** (v1.0.0) · 갱신: 2026-09-03 · 소유: design 01 §6.2가 참조하는 운영 runbook 정본의 배포 절.
토폴로지·정책의 정본은 [`../design/01-architecture.md`](../design/01-architecture.md) §6이고,
본 문서는 **절차(operation)** 만 소유한다.

## 1. 운용 모델

| 환경 | 역할 | 실행 형태 | 코드 |
|---|---|---|---|
| 로컬 (Mac) | 개발·테스트 | venv 네이티브 + launchd (§6.2 현행) | 작업 디렉터리 |
| 원격지 — `orchwang-macbookpro` (§1.1) | **운영 (prod)** | Docker Compose 전체 스택 (§6.1) | `~/Projects/private/orc-citadel` |

- 배포 통로: **SSH** (`scripts/deploy.sh`). git clone/pull 없이 rsync 코드 전송 → 원격 빌드·기동.
- 데이터: named volume `orc-citadel-proddata` (viewer/scheduler의 `/app/data`) +
  스토어 볼륨 (pgdata/minio-data/neo4j-data/opensearch-data). 코드 재배포와 무관하게 보존.
- **데이터 정책 (확정 · 2026-09-05): 원격 prod 는 신규 수집분만 누적한다** — 로컬
  corpus(raw ~105k·curated·slo06 누적)는 이관하지 않는다. rsync 도 `prototype/data`
  를 제외한다. 따라서 원격 viewer 의 curated 존·SLO-06 7d 누적은 **0에서 새로 시작**
  하며, 로컬 실측 이력(ROADMAP §5)과 원격 운영 지표는 서로 다른 모집단이다.
- **단일 발화 주체 이전**: 운영 nightly(07:07 수집 / 07:37 SLO-06)는 원격 `scheduler`
  컨테이너가 소유한다. 원격 기동 후 로컬 launchd 는 반드시 정지 (§3.5) — 이중 발화 금지.

### 1.1 배포 대상 (확정 · 2026-09-03)

이하 예시 명령의 `<host>`는 모두 이 대상이다 (`deploy.sh`는 임의 ssh-host를 받는 일반 스크립트).

| 항목 | 값 |
|---|---|
| 호스트 | `orchwang-macbookpro` — Tailscale MagicDNS (IP `100.124.230.96`) |
| 계정 / OS | `orchwang` · macOS 25.5.0 (arm64) |
| SSH | `~/.ssh/config`(머신별, 비커밋)의 `Host orchwang-macbookpro` — `User orchwang`, `IdentitiesOnly yes` |
| 인증 | 원격 `~/.ssh/authorized_keys`에 공개키 등록 완료 · BatchMode 로그인 실측 통과 |
| 리포 경로 | `~/Projects/private/orc-citadel` (`deploy.sh`의 `REMOTE_PATH`와 동일) |
| Docker 런타임 | OrbStack (설치 경위: §2 각주) |
| viewer 접근 | loopback 바인딩 유지 → SSH 터널 (§3.3) |

### 1.2 compose 서비스 목록

| 서비스 | 역할 | 호스트 포트 (prod) | 비고 |
|---|---|---|---|
| postgres / minio / neo4j / opensearch | 인프라 스토어 | 없음 (loopback 도 제거) | `exec`/터널로만 |
| prototype | viewer (API + 정적 서빙) | `127.0.0.1:8791` | §3.3 |
| scheduler | nightly dispatch 상주 | 없음 | §4 |
| grafana | 파이프라인 모니터링 | `127.0.0.1:3000` | §3.4 |
| duckdb-ui | 존 브라우징 사이드카 | `127.0.0.1:4213` | [data-browsing.md](data-browsing.md) |

## 2. 최초 1회 프로비저닝 (원격 호스트)

```bash
# 사전 조건 확인 (없으면 설치)
ssh orchwang-macbookpro 'docker --version && docker compose version'
ssh orchwang-macbookpro 'sudo usermod -aG docker $USER'   # 재로그인 필요 (rootless 대체 가능)

# 코드 + .env 설치 (deploy.sh가 첫 실행 시 자동)
scripts/deploy.sh orchwang-macbookpro          # → .env 템플릿 생성 안내 후 종료
ssh orchwang-macbookpro "vi ~/Projects/private/orc-citadel/.env"   # 운영 크리덴셜 수동 주입
scripts/deploy.sh orchwang-macbookpro          # → 빌드 & 기동
```

> 프로비저닝 실측 (2026-09-03): 대상엔 brew도 Docker도 없었고, OrbStack를 비-brew 방식으로 설치했다 —
> dmg를 `curl`로 내려받아 `cp -R`로 `/Applications`에 배치하고, `~/.orbstack/bin`의
> `docker`/`docker-compose` 심볼릭링크를 PATH에 등록 (`.zprofile`).
>
> 자동 기동 (2026-09-05 추가): OrbStack 는 GUI 앱이라 프로세스가 죽으면 docker 데몬도
> 함께 죽는다 — 실제로 배포 다음날 OrbStack 종료로 스택 전체가 다운된 사례 발생.
> `~/Library/LaunchAgents/com.orbstack.autostart.plist`(RunAtLoad, `open -a OrbStack
> --background`) 를 등록해 재로그인·재부팅 시 자동 기동한다. (osascript 로그인 아이템
> 방식은 SSH 에서 TCC 권한 프롬프트에 걸려 hang — LaunchAgent 로 대체.)

`.env` 규칙: 원격 호스트의 리포 최상위에만 존재, `chmod 600`, **git/전송 대상 절대 제외**
(`deploy.sh`의 rsync 필터와 `.gitignore`가 이중 봉인). 템플릿은 `.env.production.example`.

## 3. 일상 배포 / 운영 절차

### 3.1 배포 (로컬 작업본 → 원격)
```bash
scripts/deploy.sh orchwang-macbookpro              # rsync → compose build → up -d → ps
scripts/deploy.sh orchwang-macbookpro --dry-run    # 전송 대상 사전 확인
```
> 배포 소스는 로컬 **작업 디렉터리**다 (커밋 여부 무관). 배포 전 `git status`로
> 의도하지 않은 변경이 섞이지 않았는지 확인할 것. 스크립트 일반성(임의 ssh-host)은 §1.1 참조.

### 3.2 상태 / 로그
```bash
scripts/deploy.sh orchwang-macbookpro --status
scripts/deploy.sh orchwang-macbookpro --logs              # 전체 추적
scripts/deploy.sh orchwang-macbookpro --logs scheduler    # 서비스별
```

### 3.3 viewer 접근
운영 기본은 loopback 바인딩(`VIEWER_BIND=127.0.0.1`) — 외부 공개 대신 SSH 터널:
```bash
ssh -N -L 8791:127.0.0.1:8791 orchwang-macbookpro     # → 브라우저 http://localhost:8791
```
전 인터페이스 공개가 불가피하면 `.env`의 `VIEWER_BIND=0.0.0.0` 변경 후 재배포
(방화벽 검토 선행). 인프라 스토어(pg/minio/neo4j/opensearch)는 항상 loopback 고정.

### 3.4 Grafana 접근 (파이프라인 모니터링, TS-6)
viewer 와 동일 정책 — loopback 바인딩(`127.0.0.1:3000`) + SSH 터널:
```bash
ssh -N -L 3000:127.0.0.1:3000 orchwang-macbookpro    # → 브라우저 http://localhost:3000
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

### 3.6 롤백
코드는 rsync 미러이므로 `git checkout <직전 release 커밋>` 후 `deploy.sh` 재실행.
이전 이미지 태그는 남아있지 않으므로(`:latest` 단일 태그), 코드만 롤백하면 다음
`up -d`에서 해당 코드로 재빌드된다. 데이터는 volume 보존이라 코드 롤백과 무관.

## 4. nightly 운영 확인

원격 스케줄러는 grace 하루(§6.2)로 당일 보충 실행한다. 정상 축적 여부:
```bash
scripts/deploy.sh orchwang-macbookpro --logs scheduler   # [collect]/[slo06] 발화 로그
docker compose ... exec prototype python -c "print(open('/app/data/slo06_accum.json').read()[-500:])"
```
수집 원문은 `/app/data/raw/<source>/...` (proddata 볼륨).

> **전제 — 대상은 노트북**: `orchwang-macbookpro`의 물리 전원이 켜져 있어야 스케줄러가 발화한다.
> 슬립·전원차단 구간은 §6.2의 grace 하루 정책이 당일만 보충하며, 이틀 이상 끊기면 그날은 결측으로 남는다.
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
