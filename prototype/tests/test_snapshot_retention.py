"""스냅샷 보존 정책 — 계약 TDD (handoff §8-1 후속).

쓰기 경로 배치화로 **새로 쌓이는** 커밋은 잡았지만, 사고 때 쌓인 이력은 그대로다
(2026-09-27 prod: `claim_candidates` 602 · `mentions` 482, 전 테이블 1,681).
이건 단순한 디스크 낭비가 아니라 **읽기·쓰기 비용**이다 — 프로파일에서 커밋마다
table metadata 를 deepcopy 하는 데 911k 호출 / 17.1s 가 나왔고, 그 크기는 곧
스냅샷 목록 길이다.

정직 경계: PyIceberg 0.12 는 `expire_snapshots` 만 제공하고 **데이터 파일 병합
(compaction)은 없다**. 따라서 이건 메타데이터 부채 정리이지 작은 파일 문제의
해결이 아니다 — 현재 스냅샷이 참조하는 파일 수는 그대로다.

이력을 지우는 작업이므로 안전장치가 계약의 중심이다:
- 현재 스냅샷은 절대 지우지 않는다 (branch head 보호).
- 나이와 무관하게 최근 N개는 남긴다 — 롤백 여지.
- dry-run 이 기본 검토 수단이다.
"""
from __future__ import annotations

import datetime as dt

import pytest

from orc_citadel.curated_zone import CuratedZone
from orc_citadel.extract import Mention
from orc_citadel.snapshot_retention import MIN_RETAINED, plan_expiry, expire_zone_snapshots


def _mention(mention_id: str) -> Mention:
    return Mention(
        mention_id=mention_id, doc_id="doc-1", segment_id="seg-1",
        surface_text="NVIDIA", mention_type="Organization", char_start=0, char_end=6,
        context_window="NVIDIA", resolved_entity_id=None,
        extraction_version={"model_id": "det", "schema_version": "1"},
    )


@pytest.fixture
def zone(tmp_path):
    z = CuratedZone(tmp_path / "iceberg")
    z.initialize()
    for i in range(6):
        z.persist_mention(_mention(f"men-{i}"))   # 행마다 1커밋 → 스냅샷 6개
    yield z
    z.close()


def _snapshots(zone, name="mentions"):
    return list(zone._table(name).snapshots())


def test_plan_keeps_everything_inside_the_retention_window(zone):
    snaps = _snapshots(zone)
    assert len(snaps) == 6, "기준선이 없으면 보존 판단을 검증할 수 없다"

    doomed = plan_expiry(snaps, now=dt.datetime.now(dt.timezone.utc),
                         retention_days=7, min_retained=MIN_RETAINED)

    assert doomed == []


def test_plan_expires_old_snapshots_but_keeps_a_rollback_floor(zone):
    snaps = _snapshots(zone)
    far_future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=365)

    doomed = plan_expiry(snaps, now=far_future, retention_days=7, min_retained=2)

    # 전부 낡았어도 최근 2개는 남는다 — 나이가 롤백 여지를 이기지 않는다.
    assert len(doomed) == len(snaps) - 2
    newest = sorted(snaps, key=lambda s: s.timestamp_ms)[-2:]
    assert not ({s.snapshot_id for s in newest} & set(doomed))


def test_plan_never_targets_the_current_snapshot(zone):
    snaps = _snapshots(zone)
    current = zone._table("mentions").current_snapshot().snapshot_id
    far_future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=365)

    doomed = plan_expiry(snaps, now=far_future, retention_days=0, min_retained=1)

    assert current not in doomed


def test_dry_run_reports_without_removing_anything(zone, tmp_path):
    before = len(_snapshots(zone))
    far_future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=365)

    report = expire_zone_snapshots(tmp_path, retention_days=7, min_retained=2,
                                   now=far_future, dry_run=True)

    assert report["mentions"]["expired"] == before - 2
    assert len(_snapshots(zone)) == before, "dry-run 이 이력을 지웠다"


def test_expiry_removes_history_and_keeps_the_table_readable(zone, tmp_path):
    before = len(_snapshots(zone))
    rows_before = len(zone.mentions())
    far_future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=365)

    report = expire_zone_snapshots(tmp_path, retention_days=7, min_retained=2,
                                   now=far_future)

    assert report["mentions"]["expired"] == before - 2
    reopened = CuratedZone(tmp_path / "iceberg")
    reopened.initialize()
    try:
        assert len(list(reopened._table("mentions").snapshots())) == 2
        assert len(reopened.mentions()) == rows_before, "행이 사라졌다"
    finally:
        reopened.close()
