"""사이드카 구성요소 도달성 프로브 (Watchtower 접속 패널).

계약:
- 카탈로그는 compose 의 동반 구성요소 6종을 전부 나열한다 — postgres·minio·
  neo4j·opensearch·grafana·duckdb-ui.
- reachable 은 TCP 연결 수락 **실측** — 프로세스가 안 떠 있으면 False 를
  그대로 낸다 (§6.2 — 가짜 up 금지). 앱 레벨 헬스 판정이 아니다.
- 호스트 해석은 compose 서비스 DNS ↔ 127.0.0.1 폴백 — prod 컨테이너 뷰어와
  로컬 뷰어가 같은 카탈로그로 동작한다.
- duckdb-ui 는 localhost 강제 플래그를 나른다 (Origin 검증 401 실측 함정).
"""

from __future__ import annotations

import socket

from orc_citadel.component_status import CATALOG, _reachable, probe_components

EXPECTED_IDS = {"postgres", "minio", "neo4j", "opensearch", "grafana", "duckdb-ui"}


def test_catalog_covers_compose_components() -> None:
    ids = {c["id"] for c in CATALOG}
    assert ids == EXPECTED_IDS
    for c in CATALOG:
        assert c["name"] and c["layer"] and c["service"]
        assert isinstance(c["port"], int)


def test_catalog_flags_duckdb_localhost_trap() -> None:
    by_id = {c["id"]: c for c in CATALOG}
    assert by_id["duckdb-ui"].get("requires_localhost") is True
    assert "localhost" in (by_id["duckdb-ui"].get("note") or "")
    # postgres 는 웹 UI 가 없다 — 링크 없이 정직 표기.
    assert by_id["postgres"].get("ui_port") is None


def _ephemeral_listener() -> tuple[socket.socket, int]:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    return srv, srv.getsockname()[1]


def test_reachable_measures_real_tcp_accept() -> None:
    srv, port = _ephemeral_listener()
    try:
        assert _reachable("no-such-compose-service", port) is True  # loopback 폴백
    finally:
        srv.close()
    # 닫힌 뒤에는 False — 실측이지 캐시가 아니다.
    assert _reachable("no-such-compose-service", port) is False


def test_probe_components_shape_and_honesty() -> None:
    """어느 것도 안 떠 있어도 예외 없이 전 항목을 reachable bool 로 낸다."""
    catalog = [
        {"id": "up", "name": "Up", "layer": "test", "service": "nope",
         "port": None, "ui_port": 1, "ui_path": "/"},
        {"id": "down", "name": "Down", "layer": "test", "service": "nope",
         "port": 1, "ui_port": None},  # port 1 — 로컬에서 닫힘
    ]
    srv, port = _ephemeral_listener()
    catalog[0]["port"] = port
    try:
        rows = probe_components(catalog)
    finally:
        srv.close()
    by_id = {r["id"]: r for r in rows}
    assert by_id["up"]["reachable"] is True
    assert by_id["down"]["reachable"] is False
    for r in rows:
        assert set(r) >= {"id", "name", "layer", "port", "ui_port", "ui_path",
                          "requires_localhost", "note", "reachable"}
