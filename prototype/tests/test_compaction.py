"""작은 파일 재작성 — 계약 TDD (2026-09-27 실측 140배 후속).

읽기 비용은 스냅샷 수가 아니라 **데이터 파일 수**에 묶인다 — 동일한 400행이
400파일이면 읽기 545.5ms, 1파일이면 3.9ms. 쓰기 배치화는 **앞으로 만들어질**
파일 수를 잡았고 snapshot expiry 는 메타데이터·커밋 비용을 정리하지만, 사고
때 이미 쌓인 파일의 읽기 부담은 둘 다 건드리지 못한다.

PyIceberg 0.12 에 `rewrite_data_files` 가 없으므로 여기서는 **테이블 전량을 읽어
한 번에 덮어쓴다**. 현행 규모(최대 1,408행)에서만 성립하는 방법이고 스케일에서는
성립하지 않는다 — `max_rows` 가드가 그 경계를 코드로 박아둔다.

데이터를 통째로 바꾸는 작업이므로 안전장치가 계약의 중심이다:
- 재작성 전후 **내용이 같은지 검증**한다 (행 수만으로는 부족하다).
- 검증이 실패하면 **이전 스냅샷으로 롤백**하고 예외를 올린다.
- 이미 압축된 테이블은 **아무 커밋도 만들지 않는다**.
"""
from __future__ import annotations

import pytest

from orc_citadel.compaction import (
    MAX_REWRITE_ROWS,
    RewriteVerificationFailed,
    compact_zone_tables,
    rewrite_table,
)
from orc_citadel.curated_zone import CuratedZone
from orc_citadel.extract import Mention


def _mention(i: int) -> Mention:
    return Mention(
        mention_id=f"men-{i:04d}", doc_id=f"doc-{i % 3}", segment_id="seg-1",
        surface_text=f"NVIDIA {i}", mention_type="Organization",
        char_start=0, char_end=6, context_window="ctx", resolved_entity_id=None,
        extraction_version={"model_id": "det", "schema_version": "1"},
    )


@pytest.fixture
def zone(tmp_path):
    z = CuratedZone(tmp_path / "iceberg")
    z.initialize()
    for i in range(12):
        z.persist_mention(_mention(i))      # 행마다 1커밋 → 파일 12개
    yield z
    z.close()


def _files(zone, name="mentions") -> int:
    return len(list(zone._table(name).scan().plan_files()))


def test_rewrite_collapses_many_files_into_one(zone):
    assert _files(zone) == 12, "기준선이 없으면 압축을 검증할 수 없다"
    before = {row["mention_id"] for row in zone.mentions()}

    result = rewrite_table(zone._table("mentions"), sort_by=("mention_id",))

    assert result["files_before"] == 12 and result["files_after"] == 1
    assert {row["mention_id"] for row in zone.mentions()} == before


def test_rewrite_preserves_hidden_partition_columns(zone):
    """`mentions` 는 `_dedup_version` 으로 파티셔닝된다 — 잃으면 파티션이 깨진다."""
    from orc_citadel.dedup import DEDUP_VERSION

    rewrite_table(zone._table("mentions"), sort_by=("mention_id",))

    arrow = zone._table("mentions").scan().to_arrow()
    assert "_dedup_version" in arrow.column_names
    assert set(arrow.column("_dedup_version").to_pylist()) == {DEDUP_VERSION}


def test_rewrite_is_a_noop_when_already_compact(zone):
    rewrite_table(zone._table("mentions"), sort_by=("mention_id",))
    snapshots = len(list(zone._table("mentions").snapshots()))

    result = rewrite_table(zone._table("mentions"), sort_by=("mention_id",))

    assert result["rewritten"] is False
    assert len(list(zone._table("mentions").snapshots())) == snapshots


def test_rewrite_refuses_a_table_beyond_the_memory_budget(zone):
    """전량을 메모리에 올리는 방법이다 — 경계를 코드가 알고 있어야 한다."""
    with pytest.raises(ValueError) as raised:
        rewrite_table(zone._table("mentions"), sort_by=("mention_id",), max_rows=5)

    assert "12" in str(raised.value) and "5" in str(raised.value)
    assert _files(zone) == 12, "거부했는데 테이블을 건드렸다"


def test_failed_verification_rolls_back_and_raises(zone):
    """검증 실패는 조용히 넘어갈 일이 아니다 — 되돌리고 알린다."""
    rows_before = {row["mention_id"] for row in zone.mentions()}

    with pytest.raises(RewriteVerificationFailed):
        rewrite_table(zone._table("mentions"), sort_by=("mention_id",),
                      _corrupt=True)

    reopened = CuratedZone(zone._handle.root)
    reopened.initialize()
    try:
        assert {row["mention_id"] for row in reopened.mentions()} == rows_before
    finally:
        reopened.close()


def test_zone_sweep_reports_every_table(tmp_path, zone):
    report = compact_zone_tables(tmp_path)

    assert report["mentions"]["files_before"] == 12
    assert report["mentions"]["files_after"] == 1
    # 빈 테이블도 결과에 나와야 한다 — 조용히 건너뛰면 무엇이 안 됐는지 모른다.
    assert "entities" in report and report["entities"]["rewritten"] is False
    assert MAX_REWRITE_ROWS > 0
