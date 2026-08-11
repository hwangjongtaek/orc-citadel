"""P1 저장 계층 키스톤 ② — MinIO raw 객체 스토어 (design 03 §2, ADR-301).

raw zone(§2.1)이 로컬 fs+in-memory `RawStore`뿐이던 것을 **MinIO 객체 스토어**에
영속화한다. §2 객체 레이아웃(`raw/<source_id>/<doc_id>/content.bin + fetch.json`),
content-hash idempotency(불변식 §3-6), ADR-301(URL 변경분은 새 doc_id로 보존).

테스트는 전용 버킷을 실행마다 삭제·재생성으로 격리한다. MinIO 드라이버/연결 불가
(오프라인) 시 전체 skip — 기존 스위트 430 보존.
"""
from __future__ import annotations

import hashlib
import io
import json

import pytest

from orc_citadel.minio_raw_store import MinioRawStore, build_minio_client

minio_mod = pytest.importorskip("minio")

# 전용 격리 버킷 (실제 운영 버킷과 분리 — CI/로컬 안전). 적절한 접두사.
TEST_BUCKET = "raw-test-orc"


@pytest.fixture()
def store():
    """실 MinIO에 연결해 전용 버킷을 삭제·재생성으로 격리 (테스트마다 초기화)."""
    try:
        client = build_minio_client()
    except Exception as exc:  # 오프라인/드라이버 부재 — 전체 skip
        pytest.skip(f"MinIO 연결 불가: {exc}")
    if client.bucket_exists(TEST_BUCKET):
        for obj in client.list_objects(TEST_BUCKET, recursive=True):
            client.remove_object(TEST_BUCKET, obj.object_name)
        client.remove_bucket(TEST_BUCKET)
    client.make_bucket(TEST_BUCKET)
    log = MinioRawStore(client, bucket=TEST_BUCKET)
    yield log
    # teardown — 전용 버킷 정리
    try:
        for obj in client.list_objects(TEST_BUCKET, recursive=True):
            client.remove_object(TEST_BUCKET, obj.object_name)
        client.remove_bucket(TEST_BUCKET)
    except Exception:
        pass


def _large_bytes(n: int = 64) -> bytes:
    return b"x" * n


def test_put_get_content_roundtrip(store):
    """put → get 으로 원문 bytes가 왕복 보존된다 (§2.1 content.bin)."""
    doc_id = store.put("src-test", "https://example.com/a", _large_bytes())
    assert doc_id.startswith("doc-")
    assert store.get_raw(doc_id) == _large_bytes()


def test_content_hash_idempotency_same_bytes_no_dup(store):
    """동일 bytes 재put 은 동일 doc_id — 중복 객체 없음 (불변식 §3-6)."""
    b = _large_bytes()
    d1 = store.put("src-test", "https://example.com/a", b)
    d2 = store.put("src-other", "https://example.com/other", b)  # 다른 소스·url — 내용 동일
    assert d1 == d2  # 내용 기반 doc_id — 동일
    assert store.count_docs() == 1  # 중복 객체 없음


def test_url_change_new_doc_id_preserved(store):
    """ADR-301 — 동일 url의 변경 버전은 새 doc_id로 보존 (덮어쓰기 금지)."""
    doc1 = store.put("src-test", "https://example.com/a", b"version-1-content")
    doc2 = store.put("src-test", "https://example.com/a", b"version-2-different")
    assert doc1 != doc2  # 새 doc_id
    assert store.get_raw(doc1) == b"version-1-content"
    assert store.get_raw(doc2) == b"version-2-different"
    assert store.count_docs() == 2  # 둘 다 보존


def test_fetch_json_metadata_roundtrip(store):
    """fetch.json catch: doc_id/source_id/url/content_hash/fetched_at 왕복 (§2.2)."""
    b = _large_bytes()
    doc_id = store.put("src-test", "https://example.com/a", b, meta={"http_status": 200})
    meta = store.fetch_meta(doc_id)
    assert meta["doc_id"] == doc_id
    assert meta["source_id"] == "src-test"
    assert meta["url"] == "https://example.com/a"
    assert meta["content_hash"] == "sha256:" + hashlib.sha256(b).hexdigest()
    assert "fetched_at" in meta


def test_object_layout_uses_source_and_doc(store):
    """§2.1 — 객체 키가 raw/<source_id>/<doc_id>/...(content.bin+fetch.json) 구조."""
    doc_id = store.put("src-alpha", "https://e/a", b"payload")
    prefix = f"raw/src-alpha/{doc_id}/"
    names = sorted(o.object_name for o in store.client.list_objects(store.bucket, prefix=prefix, recursive=True))
    assert f"raw/src-alpha/{doc_id}/content.bin" in names
    assert f"raw/src-alpha/{doc_id}/fetch.json" in names


def test_has_reports_existence(store):
    """has(doc_id) — 존재 여부 (재개 스킵용)."""
    doc_id = store.put("src-test", "https://e/a", b"data")
    assert store.has(doc_id)
    assert not store.has("doc-nonexistent")
