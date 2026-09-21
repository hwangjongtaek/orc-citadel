#!/usr/bin/env bash
# 원격지(운영) 서비스 SSH 터널 — 존별 브라우징 도구를 로컬로 끌어온다.
#
# 사용법:
#   scripts/tunnel.sh <ssh-host>                    # 전체 터널, 포그라운드 (Ctrl-C 종료)
#   scripts/tunnel.sh <ssh-host> viewer duckdb      # 지정 타깃만
#   scripts/tunnel.sh <ssh-host> all --daemon       # 백그라운드 (PID 파일)
#   scripts/tunnel.sh --status                      # 열린 터널·포트 실측
#   scripts/tunnel.sh --stop                        # 백그라운드 터널 종료
#
# 계약 (docs/operating/data-browsing.md §1·§7):
# - prod 는 viewer·grafana·duckdb-ui 만 호스트 loopback publish 이고, minio·neo4j·
#   opensearch·postgres 는 publish 자체가 없다 (docker-compose.prod.yml `!override []`).
#   publish 없는 서비스는 **컨테이너 IP** 로 포워딩한다 — 원격이 Linux+bridge 라
#   호스트에서 컨테이너 IP 가 라우팅된다(실측). IP 는 컨테이너 재생성마다 바뀌므로
#   접속할 때마다 원격에서 조회한다 (하드코딩 금지).
# - 자격증명은 이 스크립트가 다루지 않는다 — SoT 는 원격 .env.
# - 이미 점유된 로컬 포트는 건너뛴다 (기존 뷰어 터널과 공존).
set -euo pipefail

COMPOSE_PROJECT='orc-citadel'
PIDFILE="${TMPDIR:-/tmp}/orc-citadel-tunnel.pid"

# 이름|로컬포트|컨테이너 서비스(빈칸=원격 loopback publish)|원격포트|안내
TARGETS=(
  "viewer|18791||8791|Citadel 뷰어    http://127.0.0.1:18791"
  "grafana|3000||3000|Grafana         http://localhost:3000"
  "duckdb|4213||4213|DuckDB UI       http://localhost:4213  (반드시 localhost — Origin 검증)"
  "minio|9001|minio|9001|MinIO Console   http://localhost:9001  (로그인: 원격 .env)"
  "minio-api|9000|minio|9000|└ S3 API"
  "neo4j|7474|neo4j|7474|Neo4j Browser   http://localhost:7474"
  "neo4j-bolt|7687|neo4j|7687|└ bolt (브라우저가 실제로 붙는 곳)"
  "opensearch|9200|opensearch|9200|OpenSearch      http://localhost:9200/_cat/indices?v"
  "postgres|15432|postgres|5432|PostgreSQL SoT  psql -h 127.0.0.1 -p 15432"
)

port_busy() { nc -z 127.0.0.1 "$1" >/dev/null 2>&1; }

usage() {
  echo "usage: $0 <ssh-host> [target...|all] [--daemon]" >&2
  echo "       $0 --status | --stop" >&2
  echo "타깃: $(printf '%s ' "${TARGETS[@]%%|*}")" >&2
  exit 2
}

do_status() {
  echo "== 로컬 포트 실측 =="
  for spec in "${TARGETS[@]}"; do
    IFS='|' read -r name lport _svc _rport note <<<"$spec"
    if port_busy "$lport"; then echo "  [열림] $lport  $name — $note"
    else echo "  [   ] $lport  $name"; fi
  done
  if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "백그라운드 터널 PID $(cat "$PIDFILE") 실행 중"
  else
    echo "이 스크립트가 띄운 백그라운드 터널 없음 (포그라운드/수동 터널은 위 포트로 확인)"
  fi
}

do_stop() {
  [[ -f "$PIDFILE" ]] || { echo "PID 파일 없음 — 종료할 백그라운드 터널 없음"; exit 0; }
  pid="$(cat "$PIDFILE")"
  kill "$pid" 2>/dev/null && echo "터널 종료 (PID $pid)" || echo "이미 종료됨 (PID $pid)"
  rm -f "$PIDFILE"
}

case "${1:-}" in
  ""|-h|--help) usage ;;
  --status) do_status; exit 0 ;;
  --stop) do_stop; exit 0 ;;
esac

HOST="$1"; shift
DAEMON=0
WANTED=()
for arg in "$@"; do
  case "$arg" in
    --daemon|-d) DAEMON=1 ;;
    all) WANTED=() ;;
    *) WANTED+=("$arg") ;;
  esac
done

# publish 없는 서비스의 컨테이너 IP 를 한 번에 조회 (compose 프로젝트 고정 이름).
declare -A CONTAINER_IP=()
need_ip=0
for spec in "${TARGETS[@]}"; do
  IFS='|' read -r name _lport svc _rport _note <<<"$spec"
  [[ -z "$svc" ]] && continue
  if [[ ${#WANTED[@]} -eq 0 ]] || [[ " ${WANTED[*]} " == *" $name "* ]]; then need_ip=1; fi
done
if [[ $need_ip -eq 1 ]]; then
  echo "원격 컨테이너 IP 조회 중 ($HOST)…"
  while read -r svc ip; do
    [[ -n "${ip:-}" ]] && CONTAINER_IP["$svc"]="$ip"
  done < <(ssh "$HOST" "for c in minio neo4j opensearch postgres; do
      printf '%s %s\n' \"\$c\" \"\$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' ${COMPOSE_PROJECT}-\$c-1 2>/dev/null)\"
    done")
fi

FORWARDS=()
echo "== 터널 =="
for spec in "${TARGETS[@]}"; do
  IFS='|' read -r name lport svc rport note <<<"$spec"
  if [[ ${#WANTED[@]} -gt 0 && " ${WANTED[*]} " != *" $name "* ]]; then continue; fi
  host_target="127.0.0.1"
  if [[ -n "$svc" ]]; then
    host_target="${CONTAINER_IP[$svc]:-}"
    if [[ -z "$host_target" ]]; then
      echo "  [건너뜀] $name — ${COMPOSE_PROJECT}-${svc}-1 컨테이너 IP 조회 실패 (미기동?)"
      continue
    fi
  fi
  if port_busy "$lport"; then
    echo "  [건너뜀] $name — 로컬 $lport 이미 사용 중 (기존 터널이면 그대로 쓰면 됩니다)"
    continue
  fi
  FORWARDS+=(-L "${lport}:${host_target}:${rport}")
  echo "  [   여는 중] ${lport} → ${host_target}:${rport}   $note"
done

if [[ ${#FORWARDS[@]} -eq 0 ]]; then
  echo "열 터널이 없습니다 (전부 사용 중이거나 타깃 미선택)."
  exit 0
fi

# ExitOnForwardFailure: 포워딩이 하나라도 실패하면 조용히 반쪽 터널로 두지 않는다.
SSH_OPTS=(-N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30)
if [[ $DAEMON -eq 1 ]]; then
  # stdio 분리 — 파이프를 물고 있으면 호출자(`| tail`)가 영원히 블로킹된다 (실측).
  ssh "${SSH_OPTS[@]}" "${FORWARDS[@]}" "$HOST" >/dev/null 2>&1 &
  echo $! > "$PIDFILE"
  sleep 2
  kill -0 "$(cat "$PIDFILE")" 2>/dev/null \
    && echo "백그라운드 터널 PID $(cat "$PIDFILE") — 종료: $0 --stop" \
    || { echo "터널 기동 실패" >&2; rm -f "$PIDFILE"; exit 1; }
else
  echo "(Ctrl-C 로 종료)"
  exec ssh "${SSH_OPTS[@]}" "${FORWARDS[@]}" "$HOST"
fi
