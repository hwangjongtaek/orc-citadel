"""curated 쓰기 배치화 — 계약 TDD (2026-09-23 실측 결함 후속).

문서 238건을 이벤트 경로로 승격한 뒤 Iceberg 스냅샷 합계가 **13 → 1,254** 로
늘었다. 최악은 `curated.mentions` — **행 589개에 스냅샷 476개**, 행 하나 남짓마다
커밋 한 번이다. 원인은 `_put` 이 행마다 `table.append` 를 호출한다는 것이고,
`normalized.documents`(238행/8스냅샷)가 배치 쓰기로 멀쩡한 것과 대비된다.

compaction·snapshot expiry 는 이 위에 발라도 소용이 없다 — 쓰기 경로가 계속
같은 속도로 메타데이터를 만들기 때문이다. 배치화가 선행이다.
"""
from __future__ import annotations

import pytest

from orc_citadel.curated_zone import CuratedZone
from orc_citadel.extract import Mention, extract_mentions
from orc_citadel.identity import doc_id_for
from orc_citadel.parse import ParsedDoc, parse_document


@pytest.fixture
def zone(tmp_path):
    z = CuratedZone(tmp_path / "iceberg")
    z.initialize()
    yield z
    z.close()


def _snapshots(zone: CuratedZone, name: str) -> int:
    return len(list(zone._table(name).snapshots()))


def _mentions(text: str) -> list[Mention]:
    doc_id, doc = doc_id_for(text.encode()), ParsedDoc(text=text, title="")
    return extract_mentions(doc_id, doc, parse_document(doc_id, doc))


TEXT = ("NVIDIA and AMD supply accelerators. TSMC fabricates them in Taiwan. "
        "Samsung and SK Hynix ship HBM to NVIDIA for the data center.")


def test_row_at_a_time_writes_commit_once_per_row(zone):
    """회귀 기준선 — 배치 밖 동작은 그대로 행당 1커밋이다."""
    mentions = _mentions(TEXT)
    assert len(mentions) >= 3

    for mention in mentions:
        zone.persist_mention(mention)

    assert _snapshots(zone, "mentions") == len(mentions)


def test_a_batch_commits_once_no_matter_how_many_rows(zone):
    mentions = _mentions(TEXT)

    with zone.batched_writes():
        for mention in mentions:
            zone.persist_mention(mention)

    assert _snapshots(zone, "mentions") == 1
    assert {row["mention_id"] for row in zone.mentions()} == \
        {mention.mention_id for mention in mentions}


def test_an_update_inside_the_batch_does_not_force_an_early_commit(zone):
    """행을 쓰고 곧바로 고치는 것이 파이프라인의 실제 형태다.

    `persist_mention` → `set_mention_authoritative` 는 같은 행을 두 번 건드린다.
    버퍼가 자기 행을 못 찾으면 매번 존을 되읽어 커밋이 그대로 터진다.
    """
    mentions = _mentions(TEXT)

    with zone.batched_writes():
        for mention in mentions:
            zone.persist_mention(mention)
            zone.set_mention_authoritative(mention.mention_id)

    assert _snapshots(zone, "mentions") == 1
    assert all(row["authoritative"] for row in zone.mentions())


def test_a_read_inside_the_batch_sees_the_pending_rows(zone):
    """버퍼는 읽기 정합을 깨면 안 된다 — 필요하면 그 테이블만 먼저 내린다."""
    mentions = _mentions(TEXT)

    with zone.batched_writes():
        for mention in mentions:
            zone.persist_mention(mention)
        seen = {row["mention_id"] for row in zone.mentions()}

    assert seen == {mention.mention_id for mention in mentions}


def test_a_buffered_insert_does_not_clobber_an_existing_row(zone):
    """재승격은 멱등이어야 한다 — 이미 판정된 행을 초기값으로 되돌리지 않는다."""
    mention = _mentions(TEXT)[0]
    zone.persist_mention(mention)
    zone.set_mention_authoritative(mention.mention_id)

    with zone.batched_writes():
        zone.persist_mention(mention)

    rows = zone.mentions()
    assert len(rows) == 1 and rows[0]["authoritative"] is True


def test_a_failed_batch_leaves_no_partial_commit(zone):
    """배치가 깨지면 재배달이 다시 만든다 — 반쪽 커밋을 남길 이유가 없다."""
    mentions = _mentions(TEXT)

    with pytest.raises(RuntimeError):
        with zone.batched_writes():
            for mention in mentions:
                zone.persist_mention(mention)
            raise RuntimeError("promotion blew up mid-batch")

    assert zone.counts()["mentions"] == 0


def test_signature_and_bands_of_one_doc_cost_two_commits_not_nine(zone):
    """`persist_signature` 는 문서당 서명 1 + 밴드 8 행을 쓴다 (b=8×r=8)."""
    signature = list(range(64))

    with zone.batched_writes():
        zone.persist_signature("doc-batched", signature, text_hash="hash-batched")

    assert _snapshots(zone, "dup_signatures") == 1
    assert _snapshots(zone, "dup_bands") == 1
    assert zone.counts()["dup_bands"] == 8
