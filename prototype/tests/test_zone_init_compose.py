"""zone-init one-shot 배선 — compose 계약 (2026-09-22 cutover 결함 후속).

grafana·duckdb-ui 와 같은 정책: 실행 없이 커밋된 텍스트만 검사한다.

계약: Iceberg 존을 읽는 서비스는 테이블이 존재한 뒤에 떠야 한다. cutover 배포에서
이 단계가 없어 viewer 가 `NoSuchTableError` 로 죽었고, 사람이 이관 스크립트를 손으로
돌려 메웠다 — 다음 호스트에서 그대로 재현될 함정이었다.

**이관을 거는 게 아니다.** 배포가 보장하는 건 초기화뿐이고, 이관은 살아 있는 존을
legacy 로 덮어쓰므로 배포 경로에 있으면 안 된다 (zone_bootstrap 모듈 주석 참조).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def compose() -> str:
    return (REPO / "docker-compose.yml").read_text(encoding="utf-8")


def _service(compose: str, name: str) -> str:
    m = re.search(rf"^  {re.escape(name)}:\n((?:    .*\n|\n)+)", compose, re.M)
    assert m, f"docker-compose.yml 에 {name} 서비스가 없다"
    return m.group(1)


def test_zone_init_is_a_one_shot_that_only_initializes(compose: str) -> None:
    service = _service(compose, "zone-init")
    assert "orc_citadel.zone_bootstrap" in service, "초기화 진입점이 아니다"
    assert 'restart: "no"' in service, "one-shot 은 재시작하지 않는다"
    # 이관은 배포 경로에 있으면 안 된다 — 살아 있는 존을 legacy 로 덮어쓴다.
    assert "migrate_" not in service


def test_zone_init_waits_for_the_catalog_and_object_store(compose: str) -> None:
    service = _service(compose, "zone-init")
    for dependency in ("lakekeeper", "minio"):
        assert dependency in service, f"{dependency} 기동 전에 테이블을 만들 수 없다"


@pytest.mark.parametrize("name", ["prototype", "promotion-consumer"])
def test_iceberg_readers_wait_for_zone_init(compose: str, name: str) -> None:
    """viewer 가 빈 카탈로그를 읽고 죽은 것이 이 계약의 계기다."""
    service = _service(compose, name)
    assert re.search(r"zone-init:\n\s+condition: service_completed_successfully",
                     service), f"{name} 가 zone-init 완료를 기다리지 않는다"


@pytest.fixture(scope="module")
def prod() -> str:
    return (REPO / "docker-compose.prod.yml").read_text(encoding="utf-8")


def test_prod_overlay_points_zone_init_at_the_named_data_volume(prod: str) -> None:
    """prod data 는 named volume 이다 — 다른 서비스와 같은 경로를 봐야 한다."""
    service = _service(prod, "zone-init")
    assert "profiles: !reset []" in service, "prod 에서는 프로필 없이 항상 뜬다"
    assert "proddata:/app/data" in service
    assert "orc-citadel-prototype:latest" in service, "prod 는 태그 이미지를 재사용한다"


def test_promotion_consumer_can_reach_the_metrics_store(compose: str) -> None:
    """승격 비용 메트릭은 postgres 로 간다 — 자격증명이 없으면 조용히 실패한다."""
    service = _service(compose, "promotion-consumer")
    for key in ("POSTGRES_HOST", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"):
        assert key in service, f"{key} 없이는 flush 가 매번 실패한다"
    assert re.search(r"postgres:\n\s+condition: service_healthy", service)


def test_parquet_snapshot_watcher_owns_the_ui_export(compose: str, prod: str) -> None:
    """ADR-107 이 scheduler 에서 빼낸 갱신 주체 — 전용 프로세스가 갖는다.

    duckdb-ui 는 `data/parquet` 만 읽으므로 갱신자가 없으면 마지막 수동 export 에
    고정된다 (handoff §8-3).
    """
    service = _service(compose, "parquet-snapshot")
    assert "orc_citadel.parquet_snapshot" in service
    assert "PARQUET_SNAPSHOT_INTERVAL_S" in service, "1회 실행이면 UI 가 다시 고정된다"
    assert re.search(r"zone-init:\n\s+condition: service_completed_successfully",
                     service)
    # scheduler(prod 오버레이 소유)는 dispatch+metrics 전용이어야 한다 (ADR-107).
    assert "parquet_snapshot" not in _service(prod, "scheduler")


def test_prod_overlay_shares_the_data_volume_with_the_ui(prod: str) -> None:
    """워처가 쓴 parquet 를 사이드카가 읽어야 의미가 있다 — 같은 볼륨."""
    service = _service(prod, "parquet-snapshot")
    assert "proddata:/app/data" in service
    assert "orc-citadel-prototype:latest" in service
