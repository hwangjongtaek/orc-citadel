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
