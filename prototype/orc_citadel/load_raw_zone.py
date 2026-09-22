"""raw 샤드 → 파이프라인 입력.

- `iter_raw_zone` : 스트리밍(제너레이터). 대량 재처리(`rebuild_zones`)의 입력.
- `load_raw_zone` : 전량 적재 (store, metas). in-memory `RawStore` 가 필요한
  스모크 경로 전용 — 코퍼스 전체를 RAM 에 올리므로 대량 경로에 쓰지 않는다
  (2026-09-20 실측 105,271건/1.13GB).

저장 레이아웃은 `raw/<source_id>/shard-*.parquet` (03 §2.1, `raw_shard`).
"""
from __future__ import annotations

import pathlib
from typing import Iterator

from .raw_shard import RawShardStore
from .raw_store import RawStore

RAW_DIR = pathlib.Path(__file__).resolve().parent.parent / "data" / "raw"


def iter_raw_zone(raw_dir: pathlib.Path = RAW_DIR,
                  source_ids: list[str] | None = None) -> Iterator[dict]:
    """raw 샤드를 순회하며 문서를 하나씩 내보낸다 — 전량 적재 금지 (대량 재처리 입력).

    yield {source_id, url, doc_id, content}.
    """
    yield from RawShardStore(raw_dir).iter_docs(source_ids)


def load_raw_zone(raw_dir: pathlib.Path = RAW_DIR) -> tuple:
    """raw 샤드 전량을 RawStore 에 적재하고 (store, metas) 반환 — 스모크 전용.

    metas = [{source_id, url, doc_id, content}]. 대량 경로는 `iter_raw_zone` 을 쓴다.
    """
    store = RawStore()
    meta: list[dict] = []
    for doc in iter_raw_zone(raw_dir):
        store.put(doc["source_id"], doc["url"], doc["content"])
        meta.append(doc)
    return store, meta


def load_raw_zone_minio(minio_store) -> tuple:
    """Load MinIO Parquet shards through the store's streaming row API.

    This smoke-only compatibility shape mirrors :func:`load_raw_zone`; large
    consumers should iterate ``minio_store.iter_docs()`` directly.
    """
    store = RawStore()
    meta: list[dict] = []
    for doc in minio_store.iter_docs():
        store.put(doc["source_id"], doc["url"], doc["content"])
        meta.append(doc)
    return store, meta
