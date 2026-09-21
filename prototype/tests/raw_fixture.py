"""테스트용 raw 샤드 작성 helper (03 §2.1 레이아웃).

운영 writer(`RawShardStore`)는 `fetched_at` 을 실제 수집 시각으로 찍는다. 도착
계측(intake)·governance 를 검증하는 테스트는 그 값을 스스로 정해야 하므로,
여기서는 같은 parquet 스키마를 **직접** 쓴다 — 예전 테스트가 `fetch.json` 을
직접 작성하던 것과 같은 자리다.
"""
from __future__ import annotations

import pathlib

import duckdb

from orc_citadel.identity import doc_id_for
from orc_citadel.raw_shard import _COLUMNS


def write_raw_shard(raw_dir, source_id: str, docs: list[dict]) -> list[str]:
    """`docs`([{content, url?, fetched_at?, http_status?, robots_allowed?}])를 샤드 1개로.

    returns 저장된 doc_id 목록 (content-hash — 동일 bytes 는 동일 ID).
    """
    out = pathlib.Path(raw_dir) / source_id
    out.mkdir(parents=True, exist_ok=True)
    rows = [(doc_id_for(d["content"]), source_id, d.get("url", ""), d.get("fetched_at"),
             d.get("http_status"), d.get("robots_allowed"),
             d.get("license"), None, d["content"]) for d in docs]
    path = out / f"shard-{len(list(out.glob('shard-*.parquet'))):04d}.parquet"
    con = duckdb.connect()
    try:
        con.execute(f"CREATE TABLE shard({_COLUMNS})")
        con.executemany("INSERT INTO shard VALUES (?,?,?,?,?,?,?,?,?)", rows)
        con.execute(f"COPY shard TO '{path}' (FORMAT PARQUET, COMPRESSION zstd)")
    finally:
        con.close()
    return [row[0] for row in rows]
