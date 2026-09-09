#!/bin/sh
# DuckDB UI 기동 — parquet 스냅샷을 존별 스키마의 뷰로 노출한다.
#
# 뷰는 read_parquet() 경유라 쿼리 시점에 파일을 다시 연다 — 스냅샷이 원자
# 교체돼도 다음 쿼리부터 새 내용을 본다. 새 존/테이블이 *추가*된 경우만
# 컨테이너 재시작이 필요하다 (뷰 목록은 기동 시 1회 열거).
set -eu

PARQUET_ROOT="${PARQUET_ROOT:-/data/parquet}"
INIT=/tmp/init.sql
: > "$INIT"

for zone_dir in "$PARQUET_ROOT"/*/; do
    [ -d "$zone_dir" ] || continue
    zone="$(basename "$zone_dir")"
    case "$zone" in
        *.bak|*.new) continue ;;   # 스냅샷 교체 잔재는 뷰로 만들지 않는다
    esac
    printf 'CREATE SCHEMA IF NOT EXISTS "%s";\n' "$zone" >> "$INIT"
    for f in "$zone_dir"*.parquet; do
        [ -e "$f" ] || continue
        t="$(basename "$f" .parquet)"
        printf 'CREATE OR REPLACE VIEW "%s"."%s" AS SELECT * FROM read_parquet('"'"'%s'"'"');\n' \
            "$zone" "$t" "$f" >> "$INIT"
    done
done

echo "CALL start_ui_server();" >> "$INIT"

# ui 확장은 Origin 이 정확히 http://localhost:<ui_local_port> 인 요청만 받는다
# (그 외 /ddb/run 401 — 실측). 그래서 내부 포트를 기본 4213 그대로 두고 브라우저도
# localhost:4213 으로 접속해야 한다 (127.0.0.1 은 401). socat 은 루프백과 충돌하지
# 않게 컨테이너 eth0 IP 에만 붙는다 — ui 서버는 localhost(::1, 실측)에 붙는다.
socat "TCP-LISTEN:4213,fork,reuseaddr,bind=$(hostname -i | awk '{print $1}')" \
      'TCP6:[::1]:4213' &

echo "[duckdb-ui] views:" && grep -c 'CREATE OR REPLACE VIEW' "$INIT" || true

# stdin 을 열어둔 채 대기 — duckdb 프로세스(=ui 서버)를 상주시킨다.
# 카탈로그는 컨테이너 로컬 스크래치 DB — 존 파일에는 접근 자체가 없다.
exec sh -c 'tail -f /dev/null | duckdb -init /tmp/init.sql /tmp/browse.duckdb'
