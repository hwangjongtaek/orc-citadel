"""Zone concurrent-read contracts for the shared ThreadingHTTPServer objects."""
from __future__ import annotations

import concurrent.futures as cf


from orc_citadel.curated_zone import CuratedZone  # noqa: E402
from orc_citadel.iceberg_zone import NormalizedZone  # noqa: E402


def _hammer(fn, threads: int = 16, rounds: int = 48):
    with cf.ThreadPoolExecutor(threads) as ex:
        return list(ex.map(lambda _: fn(), range(rounds)))


def test_curated_extraction_records_stable_under_threads(tmp_path):
    z = CuratedZone(tmp_path / "iceberg")
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
    z = CuratedZone(tmp_path / "iceberg")
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
    z = NormalizedZone(tmp_path / "iceberg")
    z.initialize()

    def read():
        return len(z.documents())

    got = _hammer(read)
    assert len(set(got)) == 1, f"교차 오염: {set(got)}"
    z.close()
