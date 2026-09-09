# DuckDB UI 사이드카 (specs/ui-overhaul-astryx TS-7, Step 16b).
#
# - parquet 스냅샷 브라우징 전용 — 존 `.duckdb` 는 마운트조차 하지 않는다
#   (뷰어 RW 잠금 함정 원천 차단). /data/parquet 는 read-only 마운트.
# - duckdb CLI 버전 핀 + `INSTALL ui` 는 빌드 시 1회 네트워크 — 런타임에
#   확장을 내려받지 않는다.
# - ui 서버는 컨테이너 안 loopback 에만 붙으므로 socat 이 eth0 → loopback 을
#   중계한다 (호스트 publish 는 compose 가 loopback 으로 제한).
# - 접속은 반드시 http://localhost:4213 — ui 확장이 Origin 을 검증해
#   127.0.0.1 로는 401 이 난다 (start.sh 참조).
FROM debian:bookworm-slim

# ui 프런트 자산은 확장이 ui.duckdb.org 에서 가져온다(항상 최신) — 구버전
# CLI/확장과 프로토콜이 어긋나면 Initialization Error (v1.3.2 실측). 최신 안정 핀.
ARG DUCKDB_VERSION=v1.4.1
ARG TARGETARCH=arm64

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl unzip socat \
    && rm -rf /var/lib/apt/lists/*

# 릴리스 자산 이름이 버전대에 따라 arm64/aarch64 로 갈린다 — 순차 시도.
RUN set -eux; \
    arch="${TARGETARCH}"; [ "$arch" = "arm64" ] && alt="aarch64" || alt="$arch"; \
    base="https://github.com/duckdb/duckdb/releases/download/${DUCKDB_VERSION}"; \
    curl -fsSL -o /tmp/duckdb.zip "${base}/duckdb_cli-linux-${arch}.zip" \
      || curl -fsSL -o /tmp/duckdb.zip "${base}/duckdb_cli-linux-${alt}.zip"; \
    unzip /tmp/duckdb.zip -d /usr/local/bin; \
    rm /tmp/duckdb.zip; \
    chmod +x /usr/local/bin/duckdb; \
    duckdb -c "INSTALL ui;"

COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

EXPOSE 4213
CMD ["/usr/local/bin/start.sh"]
