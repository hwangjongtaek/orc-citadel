"""Grafana 사이드카 회귀 (TS-6, Step 14b) — compose·provisioning 이 계약을 지키는지.

frontend dist 와 같은 정책: 실행 없이 커밋된 텍스트만 검사한다 (오프라인 가드).
실기동 검증(컨테이너 헬스·datasource 쿼리)은 이관 커밋의 수동 검증 절차.

계약 (specs TS-6):
- 이미지 버전 핀 (latest 금지) · loopback 바인딩(SSH 터널 접근) · 익명 Viewer
- provisioning as code (datasource·dashboard provider 커밋, read-only 마운트)
- postgres 접속은 read-only 계정(grafana_reader) — 메트릭 테이블 SELECT 한정
- 플러그인 설치 없음 · 외부 콜아웃(analytics/update check) 차단
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
GRAFANA = REPO / "deploy" / "grafana"


@pytest.fixture(scope="module")
def compose() -> str:
    return (REPO / "docker-compose.yml").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def grafana_block(compose: str) -> str:
    """docker-compose.yml 의 grafana 서비스 블록만 잘라낸다 (들여쓰기 기준)."""
    m = re.search(r"^  grafana:\n((?:    .*\n|\n)+)", compose, re.M)
    assert m, "docker-compose.yml 에 grafana 서비스가 없다"
    return m.group(1)


def test_grafana_image_is_pinned(grafana_block: str) -> None:
    m = re.search(r"image:\s*(\S+)", grafana_block)
    assert m, "grafana image 미지정"
    image = m.group(1)
    assert re.fullmatch(r"grafana/grafana-oss:\d+\.\d+\.\d+", image), \
        f"버전 핀 필요 (latest 금지): {image}"


def test_grafana_binds_loopback_only(grafana_block: str) -> None:
    """viewer 와 동일 접근 정책 — loopback + SSH 터널. 0.0.0.0 노출 금지."""
    ports = re.findall(r'-\s*"([^"]+)"', grafana_block)
    binds = [p for p in ports if ":" in p]
    assert binds, "grafana 포트 바인딩이 없다"
    for p in binds:
        assert p.startswith("127.0.0.1:"), f"loopback 이 아니다: {p}"


def test_grafana_anonymous_viewer(grafana_block: str) -> None:
    assert "GF_AUTH_ANONYMOUS_ENABLED" in grafana_block
    assert re.search(r"GF_AUTH_ANONYMOUS_ORG_ROLE:\s*Viewer", grafana_block), \
        "익명은 Viewer 역할이어야 한다 (read-only 관측)"


def test_grafana_no_external_callouts(grafana_block: str) -> None:
    """오프라인 런타임 유지 — 원격 analytics·업데이트 체크 차단, 플러그인 설치 없음."""
    assert re.search(r'GF_ANALYTICS_REPORTING_ENABLED:\s*"false"', grafana_block)
    assert re.search(r'GF_ANALYTICS_CHECK_FOR_UPDATES:\s*"false"', grafana_block)
    assert "GF_INSTALL_PLUGINS" not in grafana_block, "플러그인 설치 금지 (코어 postgres 만)"


def test_grafana_provisioning_mounted_read_only(grafana_block: str) -> None:
    assert re.search(
        r"\./deploy/grafana/provisioning:/etc/grafana/provisioning:ro", grafana_block
    ), "provisioning as code 는 read-only 마운트여야 한다"


def test_datasource_uses_readonly_account() -> None:
    ds = (GRAFANA / "provisioning" / "datasources" / "citadel.yaml") \
        .read_text(encoding="utf-8")
    assert "type: postgres" in ds
    assert re.search(r"user:\s*grafana_reader", ds), "read-only 계정으로 접속해야 한다"
    # 크리덴셜은 커밋하지 않는다 — grafana 의 env 보간으로 주입.
    assert "$GRAFANA_DB_PASSWORD" in ds
    assert re.search(r"editable:\s*false", ds)
    # compose 서비스 DNS — 호스트 경유 금지.
    assert re.search(r"url:\s*postgres:5432", ds)


def test_dashboard_provider_committed() -> None:
    provider = (GRAFANA / "provisioning" / "dashboards" / "provider.yaml") \
        .read_text(encoding="utf-8")
    assert "type: file" in provider
    assert "/etc/grafana/provisioning/dashboards" in provider
    assert re.search(r"allowUiUpdates:\s*false", provider), \
        "대시보드는 as-code 가 SoT — UI 편집 영속 금지"


def test_readonly_sql_grants_select_only() -> None:
    """grafana_reader 는 메트릭 테이블 SELECT 한정 — 그래프 SoT 접근 없음."""
    sql = (GRAFANA / "init-readonly.sql").read_text(encoding="utf-8")
    assert "grafana_reader" in sql
    for table in ("pipeline_run_metrics", "pipeline_slo_observations"):
        assert table in sql, table
    upper = re.sub(r"--[^\n]*", "", sql).upper()  # 주석 제외
    assert "GRANT SELECT" in upper
    for verb in ("INSERT", "UPDATE", "DELETE", "ALL PRIVILEGES", "SUPERUSER"):
        assert verb not in upper, f"read-only 위반: {verb}"


def test_prod_overlay_keeps_grafana_managed() -> None:
    """prod 에서도 상주(restart) — loopback 바인딩은 base 상속이라 재정의 불필요."""
    prod = (REPO / "docker-compose.prod.yml").read_text(encoding="utf-8")
    m = re.search(r"^  grafana:\n((?:    .*\n|\n)+)", prod, re.M)
    assert m, "prod 오버레이에 grafana 가 없다"
    assert "restart: unless-stopped" in m.group(1)
    assert "ports" not in m.group(1), "포트 재정의 금지 — base 의 loopback 을 상속"


def test_env_example_documents_grafana_credentials() -> None:
    env = (REPO / ".env.example").read_text(encoding="utf-8")
    assert "GRAFANA_DB_PASSWORD=" in env
    assert "GRAFANA_ADMIN_PASSWORD=" in env
