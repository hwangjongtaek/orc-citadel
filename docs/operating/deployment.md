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
- **단일 발화 주체 이전**: 운영 nightly(07:07 수집 / 07:37 SLO-06)는 원격 `scheduler`
  컨테이너가 소유한다. 원격 기동 후 로컬 launchd 는 반드시 정지 (§3.4) — 이중 발화 금지.

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

### 3.4 로컬 스케줄러 정지 (원격 운영 전환 시 1회)
```bash
launchctl unload ~/Library/LaunchAgents/com.orc-citadel.nightly.plist
# plist가 개체 저장소에 없으면: prototype/scripts/com.orc-citadel.nightly.plist 참조
pgrep -f scheduler_runner.py   # 로컬 잔존 프로세스 없어야 함
```

### 3.5 롤백
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
