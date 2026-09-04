#!/usr/bin/env bash
# 원격지(운영) 배포 — design 01 §6.1 Docker Compose 단일 호스트 토폴로지.
#
# 사용법 (현재 확정 배포 대상: orchwang-macbookpro — tailnet MacBook Pro):
#   scripts/deploy.sh orchwang-macbookpro              # 실배포
#   scripts/deploy.sh orchwang-macbookpro --dry-run    # 전송 대상만 출력, 원격 변경 없음
#   scripts/deploy.sh orchwang-macbookpro --status     # 원격 스택 상태 확인 (배포 안 함)
#   scripts/deploy.sh orchwang-macbookpro --logs [svc] # 원격 로그 추적 (svc 생략이면 전체)
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

compose_up() {
  ssh "$HOST" "set -e
    cd ~/$REMOTE_PATH
    [ -f .env ] || { echo 'ERROR: ~/$REMOTE_PATH/.env 없음 — first-run 안내대로 수동 생성' >&2; exit 1; }
    docker compose -p $COMPOSE_PROJECT $COMPOSE_FILES --env-file .env build
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
    ssh "$HOST" "test -d ~/$REMOTE_PATH" || FIRST=1
    if [[ "$FIRST" == 1 ]]; then
      echo "== first-run: 원격 디렉터리 및 .env 프로비저닝 =="
      ssh "$HOST" "mkdir -p ~/$REMOTE_PATH"
    fi
    echo "== rsync 코드 전송 =="
    rsync -av --delete --stats "${EXCLUDES[@]}" \
      "$REPO_ROOT/" "$HOST:~/$REMOTE_PATH/"
    if [[ "$FIRST" == 1 ]] || ! ssh "$HOST" "test -f ~/$REMOTE_PATH/.env"; then
      ssh "$HOST" "cd ~/$REMOTE_PATH && cp .env.production.example .env && chmod 600 .env"
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
