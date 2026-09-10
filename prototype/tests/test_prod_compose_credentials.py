"""prod 오버레이 — 앱 컨테이너 커넥터 자격증명 주입 계약.

2026-09-10 prod 실측 결함: scheduler·prototype(viewer) 에 POSTGRES_HOST 등
호스트만 주입되고 자격증명(POSTGRES_PASSWORD 등)이 없어, 컨테이너 안에서
build_dsn()/minio/neo4j 클라이언트가 로컬 개발 기본값으로 폴백 → prod postgres
인증 실패 → run_metrics flush 가 조용히 실패해 메트릭 테이블이 영영 안 생겼다.

계약: 코드가 읽는 자격증명 env (postgres_mutation_log.build_dsn ·
minio_raw_store · neo4j_graph_store) 는 prod 오버레이의 prototype·scheduler
environment 에 ${VAR} 보간으로 모두 주입되어야 한다. 값은 .env 만이 SoT
(compose 파일에 리터럴 금지).

grafana compose 테스트와 같은 정책 — 실행 없이 커밋 텍스트만 검사 (오프라인).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

# 코드(클라이언트 빌더)가 os.environ 에서 읽는 자격증명 키.
CREDENTIAL_ENVS = (
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "MINIO_ROOT_USER",
    "MINIO_ROOT_PASSWORD",
    "NEO4J_PASSWORD",
)


@pytest.fixture(scope="module")
def prod_compose() -> str:
    return (REPO / "docker-compose.prod.yml").read_text(encoding="utf-8")


def _service_block(compose: str, name: str) -> str:
    m = re.search(rf"^  {name}:\n((?:    .*\n|\n)+)", compose, re.M)
    assert m, f"prod 오버레이에 {name} 서비스가 없다"
    return m.group(1)


@pytest.mark.parametrize("service", ["prototype", "scheduler"])
def test_app_containers_get_connector_credentials(prod_compose: str,
                                                  service: str) -> None:
    """호스트(DNS)만 주입하고 자격증명을 빠뜨리면 클라이언트가 로컬 기본값으로
    폴백해 조용히 인증 실패한다 — 전 자격증명 키가 ${VAR} 보간으로 있어야 한다."""
    block = _service_block(prod_compose, service)
    for env in CREDENTIAL_ENVS:
        assert re.search(rf"{env}:\s*\$\{{{env}", block), \
            f"{service}: {env} 미주입 (자격증명은 .env 보간으로)"


@pytest.mark.parametrize("service", ["prototype", "scheduler"])
def test_no_credential_literals_in_compose(prod_compose: str,
                                           service: str) -> None:
    """자격증명 값의 SoT 는 원격 .env — compose 에 리터럴 금지."""
    block = _service_block(prod_compose, service)
    for env in CREDENTIAL_ENVS:
        m = re.search(rf"{env}:\s*(\S+)", block)
        if m:
            assert m.group(1).startswith("${"), \
                f"{service}: {env} 가 리터럴이다 — ${{{env}}} 보간이어야 한다"
