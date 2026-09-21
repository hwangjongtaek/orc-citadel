"""뷰어 존 갱신 계약 — 수집·승격이 재시작 없이 화면에 반영된다.

2026-09-18 prod 실측: nightly 수집(raw 127건)과 승격(claims 107건)이 끝난 뒤에도
뷰어는 raw 0 / curated 0 을 계속 표기했다. 원인은 둘 다 프로세스 수명 캐시다.

  ① raw 카운트·fetch 레코드가 클래스 캐시에 박혀 재스캔되지 않는다.
  ② facade 가 기동 시 1회 연 `curated.duckdb` 핸들을 유지한다 — `rebuild_zones`
     는 `.new` → rename 으로 교체하므로, 뷰어는 교체 전 inode 를 계속 읽는다.

nightly 가 매일 도는 환경에서 매일 재발하는 조건이라 재시작 의존을 없앤다.
다만 **바뀌지 않았을 때는 다시 열지 않는다** — facade 재생성은 assertion 전수로
그래프 프로젝션을 다시 쌓는 비용이다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orc_citadel import viewer
from orc_citadel.curated_zone import CuratedZone
from orc_citadel.pipeline_runner import run_pipeline
from orc_citadel.viewer import Handler
from raw_fixture import write_raw_shard

# test_viewer_gate 와 같은 fixture — 추출기가 claim 을 뽑으려면 발행시각 메타와
# 주체·서술이 갖춰진 문장이 필요하다 (최소 HTML 로는 promoted 0 이라 교체를 구분 못 한다).
HTML = b"""<html><head>
<title>NVIDIA Conference Call</title>
<meta property="article:published_time" content="2026-08-01T14:00:00+00:00"/>
</head><body><article>
<h1>NVIDIA Sets Conference Call</h1>
<p>NVIDIA will host a conference call on Wednesday, August 26.</p>
<p>NVIDIA powers the data center and announces new accelerator products.</p>
</article></body></html>"""


def _raw_doc(raw: Path, source: str, doc_id: str) -> None:
    """doc_id 를 본문에 섞는다 — content-hash 가 ID 이므로 같은 bytes 는 한 건이다."""
    write_raw_shard(raw, source, [{
        "content": HTML.replace(b"<h1>", b"<h1>" + doc_id.encode() + b" "),
        "url": f"https://e/{doc_id}", "fetched_at": "2026-09-18T00:00:00+00:00"}])


def _curated(path: Path, *, promoted: bool) -> None:
    """빈 스키마(배포 직후) 또는 승격된 존(rebuild_zones 이후)."""
    zone = CuratedZone(str(path))
    zone.initialize()
    if promoted:
        run_pipeline([{"source_id": "test", "url": "https://e/n",
                       "doc_id": "doc-refresh0000000000000001", "content": HTML}], zone)
    zone.close()


@pytest.fixture(autouse=True)
def _clean_caches():
    Handler._RAW_COUNT_CACHE.clear()
    Handler._FETCH_CACHE.clear()
    yield
    Handler._RAW_COUNT_CACHE.clear()
    Handler._FETCH_CACHE.clear()


def test_raw_counts_pick_up_newly_collected_docs(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    _raw_doc(raw, "src-a", "doc-1")
    _sources, total = viewer._count_raw(str(raw))
    assert total == 1

    _raw_doc(raw, "src-a", "doc-2")  # nightly 수집이 문서를 더한 상황
    _sources, total_after = viewer._count_raw(str(raw))
    assert total_after == 2, "캐시가 수집 결과를 가린다 — 재시작 없이 반영돼야 한다"


def test_fetch_records_pick_up_newly_collected_docs(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    _raw_doc(raw, "src-a", "doc-1")
    assert len(viewer._fetch_records(str(raw))) == 1

    _raw_doc(raw, "src-a", "doc-2")
    assert len(viewer._fetch_records(str(raw))) == 2


def test_facade_reopens_after_curated_file_is_replaced(tmp_path: Path, monkeypatch) -> None:
    """승격은 파일을 rename 으로 갈아끼운다 — 옛 inode 를 계속 읽으면 안 된다."""
    db = tmp_path / "curated.duckdb"
    _curated(db, promoted=False)
    monkeypatch.setattr(viewer, "DB", db)
    Handler.facade = None
    Handler._facade_stamp = None

    Handler._ensure_facade()
    assert len(Handler.facade.zone.assertions()) == 0

    new = tmp_path / "curated.duckdb.new"
    _curated(new, promoted=True)
    db.unlink()
    new.rename(db)

    Handler._ensure_facade()
    assert len(Handler.facade.zone.assertions()) > 0, \
        "교체된 존을 못 본다 — 뷰어 재시작 없이 반영돼야 한다"


def test_facade_is_reused_when_curated_file_is_unchanged(tmp_path: Path, monkeypatch) -> None:
    """변경이 없으면 재사용 — facade 재생성은 assertion 전수 재적재 비용이다."""
    db = tmp_path / "curated.duckdb"
    _curated(db, promoted=True)
    monkeypatch.setattr(viewer, "DB", db)
    Handler.facade = None
    Handler._facade_stamp = None

    Handler._ensure_facade()
    first = Handler.facade
    Handler._ensure_facade()
    assert Handler.facade is first
