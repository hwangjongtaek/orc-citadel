"""동반 구성요소 도달성 프로브 — Watchtower 접속 패널의 데이터원.

citadel 서비스와 함께 도는 compose 구성요소(데이터 계층·관측 사이드카)의
도달 가능성을 TCP 연결 수락으로 실측한다. 판정은 연결 수락 여부뿐 — 앱 레벨
헬스가 아니며, 미도달은 unreachable 그대로 낸다 (§6.2 — 가짜 up 금지).

호스트 해석: 컨테이너 안(prod 뷰어)에서는 compose 서비스 DNS 우선, 로컬
뷰어에서는 127.0.0.1 우선 — 실패하면 반대쪽을 시도한다. 사이드카가 전부
loopback publish(또는 compose 내부 포트 동일)라 포트 번호는 양쪽이 같다.
"""

from __future__ import annotations

import pathlib
import socket
from concurrent.futures import ThreadPoolExecutor

# compose 동반 구성요소 카탈로그 — docker-compose.yml 과 함께 바꾼다.
# ui_port 가 None 이면 웹 UI 없음(프런트가 링크 없이 note 만 표기).
CATALOG: tuple[dict, ...] = (
    {"id": "postgres", "name": "PostgreSQL", "service": "postgres", "port": 5432,
     "layer": "SoT — graph_mutations · run 메트릭",
     "ui_port": None, "ui_path": None,
     "note": "직접 UI 없음 — 조회는 Grafana Explore(read-only 계정) 경유"},
    {"id": "minio", "name": "MinIO Console", "service": "minio", "port": 9001,
     "layer": "raw 존 — 오브젝트 원형",
     "ui_port": 9001, "ui_path": "/"},
    {"id": "neo4j", "name": "Neo4j Browser", "service": "neo4j", "port": 7474,
     "layer": "그래프 투영",
     "ui_port": 7474, "ui_path": "/"},
    {"id": "opensearch", "name": "OpenSearch", "service": "opensearch", "port": 9200,
     "layer": "검색 인덱스",
     "ui_port": 9200, "ui_path": "/_cluster/health?pretty"},
    {"id": "grafana", "name": "Grafana", "service": "grafana", "port": 3000,
     "layer": "파이프라인 관측 — run 메트릭 · SLO",
     "ui_port": 3000, "ui_path": "/d/citadel-pipeline"},
    {"id": "duckdb-ui", "name": "DuckDB UI", "service": "duckdb-ui", "port": 4213,
     "layer": "normalized·curated 존 — parquet 스냅샷",
     "ui_port": 4213, "ui_path": "/", "requires_localhost": True,
     "note": "반드시 localhost 로 접속 — ui 확장 Origin 검증이 127.0.0.1 을 "
             "401 처리한다 (실측, data-browsing.md §3)"},
)


def _hosts(service: str) -> tuple[str, str]:
    """컨테이너면 서비스 DNS 우선, 로컬이면 loopback 우선 (반대쪽 폴백)."""
    if pathlib.Path("/.dockerenv").exists():
        return (service, "127.0.0.1")
    return ("127.0.0.1", service)


def _reachable(service: str, port: int, timeout: float = 0.25) -> bool:
    for host in _hosts(service):
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            continue
    return False


def probe_components(catalog: list[dict] | None = None,
                     timeout: float = 0.25) -> list[dict]:
    cat = list(CATALOG if catalog is None else catalog)
    with ThreadPoolExecutor(max_workers=max(1, len(cat))) as ex:
        flags = list(ex.map(
            lambda c: _reachable(c["service"], c["port"], timeout), cat))
    return [{
        "id": c["id"], "name": c["name"], "layer": c["layer"], "port": c["port"],
        "ui_port": c.get("ui_port"), "ui_path": c.get("ui_path"),
        "requires_localhost": bool(c.get("requires_localhost", False)),
        "note": c.get("note"), "reachable": flag,
    } for c, flag in zip(cat, flags)]
