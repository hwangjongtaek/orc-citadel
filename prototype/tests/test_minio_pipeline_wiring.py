"""P1 후속 ① — MinIO ↔ 파이프라인 실배선 (design 03 §2, ADR-301).

수집(`collect_large._save_zone`)이 raw 를 MinIO 에 쓰고, 파이프라인 입력
(`load_raw_zone_minio`)이 MinIO 로부터 읽는 end-to-end 를 검증한다. 기존 로컬 fs
경로는 default 로 유지(파괴 없음), MinIO 는 선택 백엔드.

전용 버킷 격리(② `raw-test-*` 패턴), 연결 불가 skip — 기존 스위트 446 유지.
"""
from __future__ import annotations

import pytest

from orc_citadel.collect_large import _save_zone
from orc_citadel.load_raw_zone import load_raw_zone_minio
from orc_citadel.minio_raw_store import build_minio_client

minio_mod = pytest.importorskip("minio")


def build_minio_store(bucket="raw-wiring-test"):
    try:
        client = build_minio_client()
        # 첫 실제 연결은 여기서 일어난다 (client 생성은 lazy — 연결 안 함).
        # 가드 밖에 두면 오프라인에서 skip 아닌 ERROR 가 된다.
        bucket_exists = client.bucket_exists(bucket)
    except Exception as exc:
        pytest.skip(f"MinIO 연결 불가: {exc}")
    if bucket_exists:
        for o in client.list_objects(bucket, recursive=True):
            client.remove_object(bucket, o.object_name)
        client.remove_bucket(bucket)
    client.make_bucket(bucket)
    from orc_citadel.minio_raw_store import MinioRawStore

    store = MinioRawStore(client, bucket=bucket)
    return client, store, bucket


@pytest.fixture()
def minio_env():
    client, store, bucket = build_minio_store()
    yield client, store, bucket
    try:
        for o in client.list_objects(bucket, recursive=True):
            client.remove_object(bucket, o.object_name)
        client.remove_bucket(bucket)
    except Exception:
        pass


def test_save_zone_writes_to_minio(minio_env):
    """_save_zone(+minio_store) → MinIO 객체 키 §2.1 로 raw 영속."""
    client, store, bucket = minio_env
    doc_id, created = _save_zone(
        "src-x", "https://e/a", b"<html>payload</html>",
        {"http_status": 200}, minio_store=store,
    )
    assert created
    assert store.has(doc_id)
    # 객체 키 존재 (content.bin + fetch.json)
    names = [o.object_name for o in client.list_objects(bucket, recursive=True)]
    assert f"raw/src-x/{doc_id}/content.bin" in names
    assert f"raw/src-x/{doc_id}/fetch.json" in names


def test_save_zone_minio_idempotent(minio_env):
    """동일 bytes 재수집 → 동일 doc_id, created=False, 중복 객체 없음."""
    client, store, bucket = minio_env
    d1, c1 = _save_zone("src-x", "https://e/a", b"same", {}, minio_store=store)
    d2, c2 = _save_zone("src-x", "https://e/b", b"same", {}, minio_store=store)
    assert d1 == d2
    assert c1 and not c2
    assert store.count_docs() == 1


def test_load_raw_zone_minio_reconstructs_meta(minio_env):
    """MinIO 로부터 파이프라인 meta list 재구성 — doc_id·content 왕복."""
    client, store, bucket = minio_env
    _save_zone("src-y", "https://e/y", b"<html>doc y</html>",
               {"http_status": 200}, minio_store=store)
    _store, meta = load_raw_zone_minio(store)
    assert len(meta) == 1
    assert meta[0]["source_id"] == "src-y"
    assert meta[0]["url"] == "https://e/y"
    assert meta[0]["content"] == b"<html>doc y</html>"
    assert meta[0]["doc_id"].startswith("doc-")


def test_fetch_json_has_governance_fields(minio_env):
    """fetch.json 에 license/robots_allowed (governance 11) 완비."""
    client, store, bucket = minio_env
    _save_zone("src-z", "https://e/z", b"content", {}, minio_store=store)
    doc_id = [o.object_name.split("/")[2] for o in client.list_objects(bucket, recursive=True)
              if o.object_name.endswith("/content.bin")][0]
    meta = store.fetch_meta(doc_id)
    assert "license" in meta
    assert "robots_allowed" in meta
    assert "content_hash" in meta
    assert "fetched_at" in meta
