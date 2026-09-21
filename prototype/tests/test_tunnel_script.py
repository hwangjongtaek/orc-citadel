"""원격 서비스 SSH 터널 스크립트 계약 (TS-7 운영 도구) — 실행 없이 텍스트만 검사.

compose 가드(test_duckdb_ui_compose·test_grafana_compose)와 같은 정책이다:
커밋된 정의만 본다. 실제 터널 기동은 운영 절차(수동 검증).

계약:
- prod 는 viewer·grafana·duckdb-ui 만 호스트 loopback publish 이고 minio·neo4j·
  opensearch·postgres 는 publish 가 없다 (docker-compose.prod.yml `ports: !override []`).
  publish 없는 서비스는 컨테이너 IP 로 포워딩해야 하며, IP 는 재생성마다 바뀌므로
  **런타임 조회**한다 — 하드코딩 금지.
- DuckDB UI 는 로컬 포트도 4213 이어야 한다 (ui 확장 Origin 검증 — data-browsing.md §3).
- Neo4j Browser 는 bolt 까지 있어야 붙는다.
- 자격증명은 스크립트가 다루지 않는다 (SoT 는 원격 .env).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "tunnel.sh"


@pytest.fixture(scope="module")
def script() -> str:
    if not SCRIPT.exists():  # pragma: no cover - 스크립트 누락 시에만
        pytest.fail(f"{SCRIPT} 없음")
    return SCRIPT.read_text(encoding="utf-8")


def test_script_is_executable_and_strict() -> None:
    assert os.access(SCRIPT, os.X_OK), "실행 비트 필요"
    assert "set -euo pipefail" in SCRIPT.read_text(encoding="utf-8")


@pytest.mark.parametrize("target", ["viewer", "grafana", "duckdb", "minio",
                                    "neo4j", "opensearch", "postgres"])
def test_every_browsing_tool_has_a_target(script: str, target: str) -> None:
    """data-browsing.md §1 의 존별 도구가 전부 터널 타깃으로 있다."""
    assert re.search(rf'"{target}\|', script), target


def test_unpublished_services_resolve_container_ip_at_runtime(script: str) -> None:
    """publish 없는 서비스는 컨테이너 IP 로 — IP 하드코딩은 재생성 즉시 깨진다."""
    assert "docker inspect" in script and "IPAddress" in script
    assert not re.search(r"\b172\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", script), \
        "컨테이너 IP 하드코딩 금지"


def test_duckdb_ui_keeps_port_4213_locally(script: str) -> None:
    """ui 확장 Origin 검증 — 로컬도 4213/localhost 여야 401 을 피한다."""
    assert re.search(r'"duckdb\|4213\|', script)
    assert "localhost:4213" in script


def test_neo4j_browser_also_forwards_bolt(script: str) -> None:
    assert re.search(r'"neo4j-bolt\|7687\|', script)


def test_script_carries_no_credentials(script: str) -> None:
    """자격증명 SoT 는 원격 .env — 스크립트는 값을 담지 않는다."""
    for leak in ("MINIO_ROOT_PASSWORD=", "NEO4J_PASSWORD=", "POSTGRES_PASSWORD="):
        assert leak not in script, leak


def test_daemon_mode_detaches_stdio(script: str) -> None:
    """백그라운드 ssh 가 부모 stdout 을 물고 있으면 호출자가 파이프에서 멈춘다 (실측).

    `scripts/tunnel.sh <host> all --daemon | tail` 이 영원히 블로킹됐다 —
    백그라운드 프로세스가 파이프의 쓰기 끝을 계속 잡고 있었기 때문.
    """
    m = re.search(r'ssh "\$\{SSH_OPTS\[@\]\}".*&\s*$', script, re.M)
    assert m, "데몬 모드 ssh 기동 라인을 찾지 못함"
    assert ">/dev/null 2>&1 &" in m.group(0), "백그라운드 ssh 는 stdio 를 분리해야 한다"
