"""DuckDB UI parquet 스냅샷 자동 갱신 — 계약 TDD (handoff §8-3).

K5 가 scheduler 를 collection dispatch+metrics 전용으로 좁히면서(ADR-107)
`_snapshot_parquet` 훅이 제거됐다. `parquet_snapshot` 모듈 자체는 Iceberg 읽기로
동작하지만 **프로덕션 호출자가 0개**였고(테스트만 참조), duckdb-ui 는 여전히
`data/parquet` 를 마운트한다 → **UI 가 마지막 수동 export 시점에 고정된다.**

훅을 scheduler 로 되살리면 ADR-107 경계를 다시 여는 셈이다. 승격 consumer 에
붙이면 서빙 계층 export 가 승격 hot path 에 끼어들고 배치마다 돈다. 그래서
**전용 프로세스**가 소유한다 — promotion-consumer 와 같은 형태의 단일 책임
상주 프로세스다.

핵심 계약은 "변경이 없으면 내보내지 않는다" 이다. 전량 export 는 코퍼스와 함께
비싸지므로, 존 스냅샷 토큰이 그대로면 건너뛴다.
"""
from __future__ import annotations

import pytest

from orc_citadel.curated_zone import CuratedZone
from orc_citadel.iceberg_zone import NormalizedZone
from orc_citadel.parquet_snapshot import watch_zones
from orc_citadel.parse import ParsedDoc


@pytest.fixture
def data_dir(tmp_path):
    normalized = NormalizedZone(tmp_path / "iceberg")
    curated = CuratedZone(tmp_path / "iceberg")
    normalized.initialize()
    curated.initialize()
    normalized.close()
    curated.close()
    return tmp_path


def _promote_one(data_dir, tag: str) -> None:
    zone = NormalizedZone(data_dir / "iceberg")
    zone.initialize()
    zone.persist("official-nvidia-news", f"https://e/{tag}",
                 f"<html><body><p>{tag}</p></body></html>".encode(),
                 ParsedDoc(text=f"{tag} body", title=tag))
    zone.close()


def test_both_zones_expose_a_snapshot_token(data_dir):
    """변경 감지의 근거 — curated 에만 있던 API 를 normalized 에도 맞춘다."""
    normalized = NormalizedZone(data_dir / "iceberg")
    normalized.initialize()
    try:
        before = normalized.snapshot_token()
        normalized.persist("official-nvidia-news", "https://e/x", b"<p>x</p>",
                           ParsedDoc(text="x body", title="x"))
        assert normalized.snapshot_token() != before
    finally:
        normalized.close()


def test_watch_exports_when_a_zone_advances(data_dir):
    _promote_one(data_dir, "first")
    runs = []

    watch_zones(data_dir, interval=0.0, iterations=1,
                sleep=lambda _s: None,
                export=lambda root: runs.append(root) or {"exported": True})

    assert len(runs) == 1
    assert (data_dir / "parquet").exists() or runs, "export 가 호출되지 않았다"


def test_watch_skips_export_when_nothing_changed(data_dir):
    """전량 export 는 코퍼스와 함께 비싸진다 — 안 변했으면 돌 이유가 없다."""
    _promote_one(data_dir, "first")
    runs = []

    def export(root):
        runs.append(root)
        return {"exported": True}

    watch_zones(data_dir, interval=0.0, iterations=3,
                sleep=lambda _s: None, export=export)

    assert len(runs) == 1, f"변경이 없는데 {len(runs)}회 내보냈다"


def test_watch_exports_again_after_a_new_promotion(data_dir):
    runs = []

    def export(root):
        runs.append(root)
        return {"exported": True}

    watch_zones(data_dir, interval=0.0, iterations=1,
                sleep=lambda _s: None, export=export)
    _promote_one(data_dir, "second")
    watch_zones(data_dir, interval=0.0, iterations=2,
                sleep=lambda _s: None, export=export)

    # 새 승격 이후 정확히 한 번 더 — 그 뒤 반복은 변경이 없으므로 건너뛴다.
    assert len(runs) == 2


def test_watch_survives_an_export_failure(data_dir, capsys):
    """서빙 계층 export 실패가 상주 프로세스를 죽이면 UI 는 영영 멈춘다."""
    _promote_one(data_dir, "first")
    calls = {"n": 0}

    def flaky(root):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("warehouse unreachable")
        return {"exported": True}

    watch_zones(data_dir, interval=0.0, iterations=2,
                sleep=lambda _s: None, export=flaky)

    assert calls["n"] == 2, "실패 후 다시 시도하지 않았다"
    assert "warehouse unreachable" in capsys.readouterr().out
