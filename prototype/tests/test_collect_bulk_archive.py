"""`bulk_archive` 커넥터 — 계약 TDD (04 §1.3 download, 블로커 ④).

2026-09-20 조사에서 1,000만 달성의 실질 병목으로 지목된 경로다 — Federal Register
월 zip(요청 1회당 ≈2,700 docs)·CFPB CSV·govinfo bulk·Companies House 월 zip 이
전부 이 하나로 덮인다.

계약:
- zip/tar(.gz) 내부 엔트리 **1건 = 문서 1건**.
- 엔트리 식별은 `{archive_url}#{entry_path}` — 아카이브 URL 하나로는 내부를 구분할
  수 없으므로 URL-skip(04 §2.1)이 성립하도록 합성 키를 문서 URL 로 쓴다.
- 디렉터리·빈 엔트리는 건너뛴다. 이미 수집한 엔트리는 재저장하지 않는다.
"""
from __future__ import annotations

import io
import tarfile
import zipfile

import pytest

import orc_citadel.collect_large as cl
from orc_citadel.collect_large import collect_bulk_archive
from orc_citadel.raw_shard import RawShardStore


@pytest.fixture(autouse=True)
def _isolate_raw(tmp_path, monkeypatch):
    monkeypatch.setattr(cl, "RAW", tmp_path / "raw")
    monkeypatch.setattr(cl, "_SHARD_STORES", {})
    return tmp_path / "raw"


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buf.getvalue()


def _tar_gz_bytes(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as archive:
        for name, data in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _serve(monkeypatch, payload: bytes, content_type: str):
    def download(_url, output):
        output.write(payload)
        output.seek(0)
        return {"Content-Type": content_type}

    monkeypatch.setattr(cl, "_download_to_file", download)



def test_archive_download_streams_fixed_size_chunks_to_spool(monkeypatch):
    payload = _zip_bytes({"a.xml": b"A" * 32})
    chunks = [payload[:7], payload[7:19], payload[19:]]
    reads = []

    class Response:
        headers = {"Content-Type": "application/zip", "ETag": '"archive-v1"'}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, size):
            assert size > 0, "archive download used an unbounded read"
            reads.append(size)
            return chunks.pop(0) if chunks else b""

    monkeypatch.setattr(cl.urllib.request, "urlopen",
                        lambda _request, timeout: Response())
    spool = io.BytesIO()

    headers = cl._download_to_file("https://bulk/x.zip", spool)

    assert spool.getvalue() == payload
    assert len(reads) == 4
    assert headers == {
        "Content-Type": "application/zip", "ETag": '"archive-v1"',
    }


def test_archive_download_rejects_compressed_size_limit(monkeypatch):
    chunks = [b"1234", b"5678", b""]

    class Response:
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _size):
            return chunks.pop(0)

    monkeypatch.setattr(cl, "MAX_ARCHIVE_BYTES", 6)
    monkeypatch.setattr(cl.urllib.request, "urlopen",
                        lambda _request, timeout: Response())

    with pytest.raises(cl.ArchiveLimitExceeded, match="compressed"):
        cl._download_to_file("https://bulk/large.zip", io.BytesIO())


def test_archive_entry_rejects_decompressed_size_limit(monkeypatch, _isolate_raw):
    monkeypatch.setattr(cl, "MAX_ARCHIVE_ENTRY_BYTES", 4)
    _serve(monkeypatch, _zip_bytes({"large.xml": b"12345"}), "application/zip")

    result = collect_bulk_archive("https://bulk/large.zip", "gov-bulk")

    assert result == {"saved": 0, "skipped": 0, "errors": 1}


def test_archive_entry_rejects_expansion_ratio_limit(monkeypatch, _isolate_raw):
    monkeypatch.setattr(cl, "_ARCHIVE_CHUNK_SIZE", 1024)
    monkeypatch.setattr(cl, "MAX_ARCHIVE_EXPANSION_RATIO", 2)
    compressed = io.BytesIO()
    with zipfile.ZipFile(
            compressed, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("bomb.txt", b"A" * 100_000)
    _serve(monkeypatch, compressed.getvalue(), "application/zip")

    result = collect_bulk_archive("https://bulk/bomb.zip", "gov-bulk")

    assert result == {"saved": 0, "skipped": 0, "errors": 1}


def test_zip_declared_entry_count_is_rejected_before_directory_load(monkeypatch):
    import struct

    monkeypatch.setattr(cl, "MAX_ARCHIVE_ENTRIES", 2)
    eocd = struct.pack(
        "<4s4H2LH", b"PK\x05\x06", 0, 0, 3, 3, 0, 0, 0)

    with pytest.raises(cl.ArchiveLimitExceeded, match="entries"):
        list(cl._archive_entries(io.BytesIO(eocd)))

def test_zip_entries_become_documents(monkeypatch, _isolate_raw):
    _serve(monkeypatch, _zip_bytes({"2026/01/a.xml": b"<doc>A</doc>",
                                    "2026/01/b.xml": b"<doc>B</doc>"}),
           "application/zip")

    counts = collect_bulk_archive("https://bulk/fr-2026-01.zip", "gov-federal-register")

    assert counts["saved"] == 2
    store = RawShardStore(_isolate_raw)
    docs = {d["url"]: d["content"] for d in store.iter_docs()}
    assert docs == {
        "https://bulk/fr-2026-01.zip#2026/01/a.xml": b"<doc>A</doc>",
        "https://bulk/fr-2026-01.zip#2026/01/b.xml": b"<doc>B</doc>"}


def test_tar_gz_entries_become_documents(monkeypatch, _isolate_raw):
    _serve(monkeypatch, _tar_gz_bytes({"x.json": b'{"k": 1}'}), "application/gzip")

    counts = collect_bulk_archive("https://bulk/set.tar.gz", "gov-bulk")

    assert counts["saved"] == 1
    store = RawShardStore(_isolate_raw)
    assert [d["url"] for d in store.iter_docs()] == ["https://bulk/set.tar.gz#x.json"]


def test_known_entries_are_skipped(monkeypatch, _isolate_raw):
    """아카이브를 다시 받아도 이미 저장한 엔트리는 재저장하지 않는다."""
    _serve(monkeypatch, _zip_bytes({"a.xml": b"A", "b.xml": b"B"}), "application/zip")

    counts = collect_bulk_archive(
        "https://bulk/x.zip", "gov-bulk",
        known_urls={"https://bulk/x.zip#a.xml"})

    assert counts["saved"] == 1 and counts["skipped"] == 1


def test_directory_and_empty_entries_are_ignored(monkeypatch, _isolate_raw):
    _serve(monkeypatch, _zip_bytes({"dir/": b"", "dir/real.xml": b"<x/>"}), "application/zip")

    counts = collect_bulk_archive("https://bulk/y.zip", "gov-bulk")

    assert counts["saved"] == 1


def test_unsupported_archive_is_reported_not_silently_empty(monkeypatch, _isolate_raw):
    """해석 못 하는 바이트는 0건 성공이 아니라 오류로 집계한다 (정직 실패)."""
    _serve(monkeypatch, b"not-an-archive", "application/octet-stream")

    counts = collect_bulk_archive("https://bulk/bad.zip", "gov-bulk")

    assert counts["saved"] == 0 and counts["errors"] == 1


def test_entries_are_saved_before_next_entry_is_requested(monkeypatch, _isolate_raw):
    _serve(monkeypatch, b"spooled archive", "application/zip")
    saved = []

    def guarded_entries(archive_file):
        assert hasattr(archive_file, "read") and not isinstance(archive_file, bytes)
        yield "a", b"A"
        assert saved == ["a"], "collector materialized decompressed entries"
        yield "b", b"B"

    monkeypatch.setattr(cl, "_archive_entries", guarded_entries)
    original = cl._save_zone

    def record_save(source_id, url, content, meta, **kwargs):
        saved.append(url.rsplit("#", 1)[-1])
        return original(source_id, url, content, meta, **kwargs)

    monkeypatch.setattr(cl, "_save_zone", record_save)

    result = collect_bulk_archive("https://bulk/x.zip", "gov-bulk")

    assert result["saved"] == 2
