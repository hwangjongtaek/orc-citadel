#!/usr/bin/env bash
# 원격지(운영) 배포 — design 01 §6.1 Docker Compose 단일 호스트 토폴로지.
#
# 사용법 (현재 확정 배포 대상: hwangjongtaek@10.0.0.11):
#   scripts/deploy.sh hwangjongtaek@10.0.0.11              # 실배포
#   scripts/deploy.sh hwangjongtaek@10.0.0.11 --dry-run    # 전송 대상만 출력, 원격 변경 없음
#   scripts/deploy.sh hwangjongtaek@10.0.0.11 --status     # 원격 스택 상태 확인 (배포 안 함)
#   scripts/deploy.sh hwangjongtaek@10.0.0.11 --logs [svc] # 원격 로그 추적 (svc 생략이면 전체)
# 임의 ssh-host 도 받는다 (~/.ssh/config 이름 권장).
#
# 계약:
# - 원격 경로 고정: ~/Projects/private/orc-citadel (운영 디렉터리).
# - 코드는 rsync 로만 보낸다 (git 미clone, .env/데이터/캐시 제외). 커밋 여부와
#   무관하게 로컬 작업본이 배포되므로, 배포 전 main 브랜치 상태 확인은 운영자 책임.
# - 크리덴셜 수동 프로비저닝: 원격 .env 가 없으면 템플릿을 설치하고 안내 후 종료.
#   절대 .env 을 전송/덮어쓰지 않는다.
# - 데이터는 named volume (orc-citadel-proddata) — 코드 재배포와 무관하게 보존.
set -euo pipefail

REMOTE_PATH='Projects/private/orc-citadel'   # ~ 기준 (배포 경로 고정 지시)
COMPOSE_FILES="-f docker-compose.yml -f docker-compose.prod.yml --profile prototype"
COMPOSE_PROJECT='orc-citadel'

HOST="${1:-}"
MODE="${2:-deploy}"
if [[ -z "$HOST" ]]; then
  echo "usage: $0 <ssh-host> [--dry-run|--status|--logs [svc]]" >&2
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 로컬→원격 전송 제외 목록 (.env 절대 전송 금지 포함)
EXCLUDES=(
  --exclude .git
  --exclude .env
  --include '.env.production.example'
  --exclude '.env.*'
  --exclude .venv
  --exclude __pycache__
  --exclude '.pytest_cache'
  --exclude .DS_Store
  --exclude '*.egg-info'
  --exclude prototype/data
  --exclude .direnv
  --exclude .claude
  --exclude .omp
  --exclude .codex
  --exclude 'orc-citadel-hero.png'
)

# 원격 조건 검사 — **연결 실패와 "조건이 거짓" 을 구분한다.**
# `ssh host "test -d ..." || FIRST=1` 은 둘을 섞어버려, 호스트가 내려가 있으면
# "한 번도 배포된 적 없는 호스트" 로 판정하고 프로비저닝 경로로 들어갔다
# (2026-09-25·26 실측). 반쯤 살아 있는 호스트에서는 `.env` 확인 한 번 실패하는
# 것만으로 템플릿이 운영 크리덴셜을 덮어쓸 수 있다 — 이 스크립트가 선언한
# 계약이 바로 그 지점에서 깨진다. ssh 는 자기 연결 오류를 255 로 낸다.
remote_test() {
  local rc=0
  ssh -o BatchMode=yes -o ConnectTimeout=15 "$HOST" "$1" >/dev/null 2>&1 || rc=$?
  if [[ "$rc" == 255 ]]; then
    echo "ERROR: $HOST 에 SSH 연결 실패 — 호스트 상태를 확인하고 다시 실행하세요." >&2
    echo "       (연결 실패를 '미배포 호스트' 로 오판해 프로비저닝하지 않습니다.)" >&2
    exit 3
  fi
  return "$rc"
}

compose_up() {
  ssh "$HOST" "set -e
    cd ~/$REMOTE_PATH
    [ -f .env ] || { echo 'ERROR: ~/$REMOTE_PATH/.env 없음 — first-run 안내대로 수동 생성' >&2; exit 1; }
    docker compose -p $COMPOSE_PROJECT $COMPOSE_FILES --env-file .env build
    # duckdb-ui 는 proddata/parquet subpath만 read-only로 마운트한다.
    # 새 named volume에도 subpath를 먼저 만들어야 compose가 컨테이너를 생성할 수 있다.
    docker volume create orc-citadel-proddata >/dev/null
    docker run --rm -v orc-citadel-proddata:/data orc-citadel-prototype:latest mkdir -p /data/parquet
    # 빈 운영 데이터만 기본 스키마를 만든다. 기존 viewer가 잡은 DuckDB 잠금은 건드리지 않는다.
    if ! docker run --rm -v orc-citadel-proddata:/app/data orc-citadel-prototype:latest test -f /app/data/curated.duckdb; then
      docker run --rm -v orc-citadel-proddata:/app/data orc-citadel-prototype:latest \
        python -c \"from orc_citadel.curated_zone import CuratedZone; zone = CuratedZone('/app/data/curated.duckdb'); zone.initialize(); zone.close()\"
    fi
    # Lakekeeper metadata is persisted in the existing PostgreSQL. Migration and
    # bootstrap are deploy-time one-shots; only the catalog server stays running.
    docker compose -p $COMPOSE_PROJECT $COMPOSE_FILES --env-file .env run --rm lakekeeper migrate
    docker compose -p $COMPOSE_PROJECT $COMPOSE_FILES --env-file .env up -d --wait lakekeeper
    docker compose -p $COMPOSE_PROJECT $COMPOSE_FILES --env-file .env run --rm prototype python deploy/lakekeeper/smoke.py
    docker compose -p $COMPOSE_PROJECT $COMPOSE_FILES --env-file .env up -d
    echo '== 상태 =='
    docker compose -p $COMPOSE_PROJECT $COMPOSE_FILES --env-file .env ps
  "
}

case "$MODE" in
  --dry-run)
    echo "== dry-run: 전송 대상 (원격 변경 없음) =="
    rsync -avvn --delete --stats "${EXCLUDES[@]}" \
      "$REPO_ROOT/" "$HOST:~/$REMOTE_PATH/"
    ;;
  --status)
    ssh "$HOST" "cd ~/$REMOTE_PATH && docker compose -p $COMPOSE_PROJECT $COMPOSE_FILES --env-file .env ps"
    ;;
  --logs)
    SVC="${3:-}"
    ssh -t "$HOST" "cd ~/$REMOTE_PATH && docker compose -p $COMPOSE_PROJECT $COMPOSE_FILES --env-file .env logs -f --tail=100 $SVC"
    ;;
  deploy)
    FIRST=0
    remote_test "test -d ~/$REMOTE_PATH" || FIRST=1
    if [[ "$FIRST" == 1 ]]; then
      echo "== first-run: 원격 디렉터리 및 .env 프로비저닝 =="
      ssh "$HOST" "mkdir -p ~/$REMOTE_PATH"
    fi
    echo "== rsync 코드 전송 =="
    rsync -av --delete --stats "${EXCLUDES[@]}" \
      "$REPO_ROOT/" "$HOST:~/$REMOTE_PATH/"
    if [[ "$FIRST" == 1 ]] || ! remote_test "test -f ~/$REMOTE_PATH/.env"; then
      # `[ -f .env ] ||` 가드 — 위 판정이 어떤 이유로든 틀렸을 때 기존 크리덴셜을
      # 덮어쓰지 않는다 (계약: 절대 .env 을 전송/덮어쓰지 않는다).
      ssh "$HOST" "cd ~/$REMOTE_PATH && { [ -f .env ] || cp .env.production.example .env; } && chmod 600 .env"
      cat <<EOF

[첫 배포] 원격 .env 를 템플릿에서 생성했습니다 (chmod 600).
운영 크리덴셜을 직접 주입한 뒤 다시 실행하세요:

  ssh $HOST "vi ~/$REMOTE_PATH/.env"
  scripts/deploy.sh $HOST

EOF
      exit 0
    fi
    echo "== 원격 빌드 & 기동 =="
    compose_up
    cat <<EOF

배포 완료. viewer 확인 (loopback 바인딩 기본):
  ssh -N -L 8791:127.0.0.1:8791 $HOST   # → http://localhost:8791
EOF
    ;;
  *)
    echo "unknown mode: $MODE" >&2
    exit 2
    ;;
esac
