"""존 부트스트랩·이관 안전장치 — 계약 TDD (2026-09-22 cutover 결함 후속).

cutover 배포에서 스택이 뜨자 viewer 가 `NoSuchTableError` 로 죽었다. 배포 어디에도
Iceberg 테이블을 만드는 단계가 없었기 때문이고, 수동 이관으로 메웠다. 그 상태가
그대로면 **다음 호스트에서 같은 함정이 재현된다.**

다만 "그러니 이관을 배포에 걸자" 는 틀린 답이다. `migrate()` 는 대상이 원본과
어긋나고 비어 있지 않으면 `zone.reset()` 으로 **전량 삭제 후 legacy 로 덮어쓴다**.
prod 의 curated 는 이벤트 경로로 legacy 보다 앞서 있으므로(2026-09-26 실측:
mentions 656 vs legacy 494, dup_signatures 303 vs 183) 배포마다 이관이 돌면
cutover 이후 산출이 통째로 사라진다.

그래서 둘로 나눈다: **배포는 초기화만** 보장하고(멱등·legacy 무관), **이관은
일회성 cutover 도구**로 두되 살아 있는 존을 말없이 지우지 못하게 막는다.
"""
from __future__ import annotations

import duckdb
import pytest

from orc_citadel.curated_zone import CuratedZone
from orc_citadel.extract import Mention
from orc_citadel.iceberg_zone import NormalizedZone
from orc_citadel.zone_bootstrap import DivergentTarget, bootstrap_zones


def _mention(mention_id: str) -> Mention:
    return Mention(
        mention_id=mention_id, doc_id="doc-1", segment_id="seg-1",
        surface_text="NVIDIA", mention_type="Organization", char_start=0, char_end=6,
        context_window="NVIDIA", resolved_entity_id=None,
        extraction_version={"model_id": "det", "schema_version": "1"},
    )


def test_bootstrap_creates_both_zones_on_a_fresh_host(tmp_path):
    """신규 호스트에는 legacy 가 없다 — 그래도 테이블은 있어야 viewer 가 산다."""
    summary = bootstrap_zones(tmp_path)

    assert summary["normalized"]["documents"] == 0
    assert summary["curated"]["mentions"] == 0
    curated = CuratedZone(tmp_path / "iceberg")
    try:
        assert len(curated.tables()) == 18
    finally:
        curated.close()


def test_bootstrap_is_idempotent(tmp_path):
    """배포마다 돈다 — 두 번째 실행이 스냅샷을 만들면 안 된다."""
    bootstrap_zones(tmp_path)
    zone = CuratedZone(tmp_path / "iceberg")
    zone.initialize()
    token = zone.snapshot_token()
    zone.close()

    bootstrap_zones(tmp_path)

    reopened = CuratedZone(tmp_path / "iceberg")
    reopened.initialize()
    try:
        assert reopened.snapshot_token() == token
    finally:
        reopened.close()


def test_bootstrap_leaves_a_live_zone_and_its_legacy_database_alone(tmp_path):
    """prod 의 형태 — 존은 legacy 보다 앞서 있고, 부트스트랩은 그걸 되돌리지 않는다."""
    bootstrap_zones(tmp_path)
    zone = CuratedZone(tmp_path / "iceberg")
    zone.initialize()
    zone.persist_mention(_mention("men-live"))
    zone.close()
    (tmp_path / "curated.duckdb").write_bytes(b"")  # legacy 잔존 — 롤백 경로

    bootstrap_zones(tmp_path)

    reopened = CuratedZone(tmp_path / "iceberg")
    reopened.initialize()
    try:
        assert [row["mention_id"] for row in reopened.mentions()] == ["men-live"]
    finally:
        reopened.close()


# ---- 이관 안전장치 ----

def _legacy_curated(tmp_path):
    from scripts.migrate_curated_to_iceberg import TABLES

    seed = CuratedZone(tmp_path / "seed-iceberg")
    seed.initialize()
    seed.persist_mention(_mention("men-legacy"))
    export = tmp_path / "legacy-parquet"
    seed.export_parquet(export)
    seed.close()
    source = tmp_path / "curated.duckdb"
    conn = duckdb.connect(str(source))
    try:
        for name in TABLES:
            conn.execute(f'CREATE TABLE "{name}" AS SELECT * FROM read_parquet(?)',
                         [str(export / f"{name}.parquet")])
    finally:
        conn.close()
    return source


def test_curated_migration_refuses_to_purge_a_live_divergent_zone(tmp_path):
    """2026-09-26 prod 실측: 이관이 배포에 걸려 있었다면 mentions 656 → 494."""
    from scripts.migrate_curated_to_iceberg import migrate

    source = _legacy_curated(tmp_path)
    target = tmp_path / "iceberg"
    migrate(source, target)
    live = CuratedZone(target)
    live.initialize()
    live.persist_mention(_mention("men-promoted-after-cutover"))
    live.close()

    with pytest.raises(DivergentTarget) as raised:
        migrate(source, target)

    # 무엇이 지워질 뻔했는지 메시지가 말해야 한다 — 조용한 거부는 도움이 안 된다.
    assert "mentions" in str(raised.value)
    survivor = CuratedZone(target)
    survivor.initialize()
    try:
        assert len(survivor.mentions()) == 2
    finally:
        survivor.close()


def test_curated_migration_rebuilds_when_the_operator_says_so(tmp_path):
    from scripts.migrate_curated_to_iceberg import migrate

    source = _legacy_curated(tmp_path)
    target = tmp_path / "iceberg"
    migrate(source, target)
    live = CuratedZone(target)
    live.initialize()
    live.persist_mention(_mention("men-promoted-after-cutover"))
    live.close()

    migrate(source, target, force=True)

    rebuilt = CuratedZone(target)
    rebuilt.initialize()
    try:
        assert [row["mention_id"] for row in rebuilt.mentions()] == ["men-legacy"]
    finally:
        rebuilt.close()


def test_normalized_migration_refuses_to_purge_a_live_divergent_zone(tmp_path):
    from scripts.migrate_normalized_to_iceberg import migrate
    from orc_citadel.parse import ParsedDoc

    source = tmp_path / "oc.duckdb"
    conn = duckdb.connect(str(source))
    try:
        conn.execute("CREATE TABLE documents (doc_id VARCHAR, source_id VARCHAR, "
                     "url VARCHAR, title VARCHAR, language VARCHAR, "
                     "publication_time TIMESTAMP, revision_time TIMESTAMP, "
                     "parser_version VARCHAR, char_len BIGINT)")
        conn.execute("INSERT INTO documents VALUES ('doc-1','src','https://e/1',"
                     "'T','en',NULL,NULL,'p1',10)")
        conn.execute("CREATE TABLE segments (segment_id VARCHAR, doc_id VARCHAR, "
                     "kind VARCHAR, text VARCHAR, char_start BIGINT, char_end BIGINT, "
                     "norm_char_start BIGINT, norm_char_end BIGINT, ord BIGINT, "
                     "parser_version VARCHAR)")
    finally:
        conn.close()
    target = tmp_path / "iceberg"
    migrate(source, target)

    live = NormalizedZone(target)
    live.initialize()
    live.persist("src", "https://e/2", b"<html><body><p>after</p></body></html>",
                 ParsedDoc(text="after cutover", title="After"))
    live.close()

    with pytest.raises(DivergentTarget) as raised:
        migrate(source, target)

    assert "documents" in str(raised.value)
    survivor = NormalizedZone(target)
    survivor.initialize()
    try:
        assert survivor.counts()["documents"] == 2
    finally:
        survivor.close()
