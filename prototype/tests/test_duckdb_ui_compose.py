"""DuckDB UI 사이드카 회귀 (TS-7, Step 16b) — compose·이미지 정의 계약.

grafana 와 같은 정책: 실행 없이 커밋된 텍스트만 검사한다 (오프라인 가드).
실기동 검증(컨테이너 빌드·UI 쿼리)은 이관 커밋의 수동 검증 절차.

계약 (specs TS-7):
- 사이드카는 **parquet 스냅샷만** 읽는다 — `.duckdb` 마운트 금지 (뷰어 RW
  잠금 함정 원천 차단), read-only 마운트 (존 오염 불가, §3-3 정합).
- duckdb CLI 버전 핀 + `INSTALL ui` 는 빌드 시 1회 — 런타임 확장 설치 없음.
- loopback 바인딩 + SSH 터널 (viewer·Grafana 동일 정책).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SIDECAR = REPO / "deploy" / "duckdb-ui"


@pytest.fixture(scope="module")
def compose() -> str:
    return (REPO / "docker-compose.yml").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def service(compose: str) -> str:
    m = re.search(r"^  duckdb-ui:\n((?:    .*\n|\n)+)", compose, re.M)
    assert m, "docker-compose.yml 에 duckdb-ui 서비스가 없다"
    return m.group(1)


def test_dockerfile_pins_duckdb_and_installs_ui_at_build() -> None:
    df = (SIDECAR / "Dockerfile").read_text(encoding="utf-8")
    assert re.search(r"DUCKDB_VERSION=v\d+\.\d+\.\d+", df), "duckdb CLI 버전 핀 필요"
    assert "INSTALL ui" in df, "ui 확장은 빌드 시 1회 설치 (런타임 오프라인)"
    assert "latest" not in df.lower()


def test_sidecar_binds_loopback_only(service: str) -> None:
    ports = [p for p in re.findall(r'-\s*"([^"]+)"', service) if ":" in p]
    assert ports, "duckdb-ui 포트 바인딩이 없다"
    for p in ports:
        assert p.startswith("127.0.0.1:"), f"loopback 이 아니다: {p}"


def test_sidecar_mounts_parquet_read_only_and_never_duckdb(service: str) -> None:
    """잠금 함정 원천 차단 — parquet 디렉터리만, read-only 로만."""
    assert re.search(r"\./prototype/data/parquet:.*:ro", service), \
        "parquet 스냅샷 read-only 마운트가 없다"
    # data 디렉터리 통마운트 금지 — .duckdb 가 딸려 들어온다
    assert not re.search(r"\./prototype/data:(?!.*parquet)", service), \
        "data 통마운트 금지 (.duckdb 노출)"
    assert ".duckdb:" not in service, ".duckdb 직접 마운트 금지"


def test_prod_overlay_mounts_volume_subpath_read_only() -> None:
    """prod 는 proddata named volume 의 parquet subpath 만 read-only."""
    prod = (REPO / "docker-compose.prod.yml").read_text(encoding="utf-8")
    m = re.search(r"^  duckdb-ui:\n((?:    .*\n|\n)+)", prod, re.M)
    assert m, "prod 오버레이에 duckdb-ui 가 없다"
    block = m.group(1)
    assert "restart: unless-stopped" in block
    assert "source: proddata" in block
    assert re.search(r"subpath:\s*parquet", block), "proddata 통마운트 금지 — subpath"
    assert re.search(r"read_only:\s*true", block)


def test_start_script_builds_views_and_starts_ui() -> None:
    """뷰는 read_parquet 경유(쿼리 시점 해석 — 원자 교체와 정합), UI 서버 기동."""
    sh = (SIDECAR / "start.sh").read_text(encoding="utf-8")
    assert "read_parquet" in sh
    assert "start_ui_server" in sh
    # .bak/.new 스냅샷 잔재를 뷰로 만들지 않는다
    assert ".bak" in sh and ".new" in sh


# ── Step 16c: 브라우징 가이드 문서 ───────────────────────────────────────────


def test_data_browsing_guide_covers_mandated_content() -> None:
    """plans 16c 계약 — 존→도구 매핑·예제 쿼리 3종·터널 절차·attach 금지."""
    doc = (REPO / "docs" / "operating" / "data-browsing.md") \
        .read_text(encoding="utf-8")
    # 존 → 도구 매핑 전 계층
    for tool in ("MinIO Console", "DuckDB UI", "Grafana", "Neo4j Browser",
                 "OpenSearch"):
        assert tool in doc, tool
    # 접속 URL 함정 — localhost 강제 (127.0.0.1 은 Origin 검증 401)
    assert "localhost:4213" in doc
    # 복붙 예제 쿼리 3종 재료
    for marker in ("normalized.segments", "dup_clusters", "claim_candidates"):
        assert marker in doc, marker
    # 잠금 함정 규칙 명문화
    assert ".duckdb" in doc and "금지" in doc
    # prod 터널 절차
    assert "ssh -N -L" in doc


def test_deployment_doc_lists_sidecar_services() -> None:
    doc = (REPO / "docs" / "operating" / "deployment.md") \
        .read_text(encoding="utf-8")
    assert "duckdb-ui" in doc
    assert "data-browsing.md" in doc, "브라우징 가이드 상호 링크가 없다"
