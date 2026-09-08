"""존 동시 접근 계약 — 뷰어는 ThreadingHTTPServer 라 zone 객체를 공유한다.

DuckDB 커넥션은 스레드 안전하지 않다. 두 스레드가 한 커넥션에서 `execute` 를
교차하면 결과가 뒤섞이는데, 특히 `extraction_records()` 처럼 `SELECT *` 와
`DESCRIBE` 를 나눠 부르는 경로는 컬럼과 행이 어긋나 `KeyError` 로 터진다
(Hall of Witnesses 가 evidence 30건에 provenance 를 동시 요청하며 실제 재현).
zone 은 스레드별 커서를 써서 이 교차를 없앤다.
"""
from __future__ import annotations

import concurrent.futures as cf

import pytest

pytest.importorskip("duckdb")

from orc_citadel.curated_zone import CuratedZone  # noqa: E402
from orc_citadel.duckdb_zone import NormalizedZone  # noqa: E402


def _hammer(fn, threads: int = 16, rounds: int = 48):
    with cf.ThreadPoolExecutor(threads) as ex:
        return list(ex.map(lambda _: fn(), range(rounds)))


def test_curated_extraction_records_stable_under_threads(tmp_path):
    """컬럼 메타와 행이 어긋나면 `element_id` 가 사라진다 — 실제 터진 지점."""
    z = CuratedZone(str(tmp_path / "c.duckdb"))
    z.initialize()
    for i in range(25):
        z.persist_extraction_record(
            element_id=f"clm-{i:04d}", doc_id=f"doc-{i:04d}",
            segment_id=f"seg-{i:04d}", char_start=0, char_end=10,
            content_hash=f"h{i}",
        )

    def read():
        recs = z.extraction_records()
        assert all("element_id" in r for r in recs), "컬럼 어긋남"
        return len(recs)

    got = _hammer(read)
    assert set(got) == {25}, f"스레드마다 다른 결과: {set(got)}"
    z.close()


def test_curated_mixed_reads_stable_under_threads(tmp_path):
    """서로 다른 테이블을 오가는 조회가 섞여도 각자 자기 결과를 받는다."""
    z = CuratedZone(str(tmp_path / "c2.duckdb"))
    z.initialize()
    for i in range(12):
        z.persist_extraction_record(
            element_id=f"clm-{i:04d}", doc_id=f"doc-{i:04d}",
            segment_id=f"seg-{i:04d}", char_start=0, char_end=5, content_hash="h",
        )

    def read():
        return (len(z.extraction_records()), len(z.claims()), len(z.assertions()))

    got = _hammer(read)
    assert len(set(got)) == 1, f"교차 오염: {set(got)}"
    z.close()


def test_normalized_reads_stable_under_threads(tmp_path):
    z = NormalizedZone(str(tmp_path / "n.duckdb"))
    z.initialize()

    def read():
        return len(z.documents())

    got = _hammer(read)
    assert len(set(got)) == 1, f"교차 오염: {set(got)}"
    z.close()
