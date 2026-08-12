"""워밍업 브리지: 수집 raw 3-zone 파일 → in-memory RawStore (스모크 전용).

`collect_sample.py`가 `data/raw/<source>/doc/<doc_id>/content.bin + fetch.json`으로
쓴 것을 읽어 기존 `RawStore.put` 계약에 재공급한다. 실제 영속화(DuckDB/Parquet)
로드백은 별도 단계 — prototype 파이프라인 스모크에서 in-memory 모델을 재사용하기 위함.
"""
from __future__ import annotations

import json
import pathlib

from .raw_store import RawStore

RAW_DIR = pathlib.Path(__file__).resolve().parent.parent / "data" / "raw"


def load_raw_zone(raw_dir: pathlib.Path = RAW_DIR) -> RawStore:
    """data/raw 아래 모든 doc 디렉토리를 RawStore에 적재하고 반환.

    각 doc 디렉토리: content.bin(HMTL bytes) + fetch.json(url, doc_id, source_id 파생).
    source_id는 디렉토리 경로(<raw>/<source_id>/doc/<doc_id>)에서 유도한다.
    반환 (store, meta_list): meta_list = [{source_id, url, doc_id, content}]
    """
    store = RawStore()
    meta: list[dict] = []
    if not raw_dir.exists():
        return store, meta
    for source_dir in raw_dir.iterdir():
        if not source_dir.is_dir():
            continue
        source_id = source_dir.name
        doc_root = source_dir / "doc"
        if not doc_root.is_dir():
            continue
        for doc_dir in doc_root.iterdir():
            content_bin = doc_dir / "content.bin"
            fetch_json = doc_dir / "fetch.json"
            if not content_bin.exists():
                continue
            content = content_bin.read_bytes()
            url = ""
            if fetch_json.exists():
                data = json.loads(fetch_json.read_text())
                url = data.get("url", "")
            doc_id = store.put(source_id, url, content)
            meta.append({
                "source_id": source_id,
                "url": url,
                "doc_id": doc_id,
                "content": content,
            })
    return store, meta


def load_raw_zone_minio(minio_store) -> tuple:
    """MinIO(raw 객체 스토어 ②)로부터 파이프라인 meta list 재구성.

    기존 `load_raw_zone`(로컬 fs)과 동일 계약 `(store, meta)` 를 반환해 파이프라인
    입력으로 재사용한다. meta = [{source_id, url, doc_id, content}].
    """
    import json

    store = RawStore()
    meta: list[dict] = []
    client = minio_store.client
    for obj in client.list_objects(minio_store.bucket, recursive=True):
        if not obj.object_name.endswith("/content.bin"):
            continue
        # §2.1 키: raw/<source_id>/<doc_id>/content.bin
        doc_id = obj.object_name.split("/")[2]
        resp = client.get_object(minio_store.bucket, obj.object_name)
        try:
            content = resp.read()
        finally:
            resp.close()
            resp.release_conn()
        # fetch.json → url
        url = ""
        try:
            rec = minio_store.fetch_meta(doc_id)
            url = rec.get("url", "")
        except KeyError:
            pass
        source_id = obj.object_name.split("/")[1]
        doc_id2 = store.put(source_id, url, content)
        meta.append({
            "source_id": source_id,
            "url": url,
            "doc_id": doc_id2,
            "content": content,
        })
    return store, meta
