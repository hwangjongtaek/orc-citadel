"""raw 존 parquet 샤드 저장 (03 §2.1) — doc당 파일 레이아웃의 대체.

레이아웃: `raw/<source_id>/shard-<ts>-<rand>.parquet` (zstd). 한 샤드가 `shard_size`
건을 담고, 기록된 샤드는 **수정하지 않는다** — 추가분은 항상 새 샤드다 (raw
immutable append-only, 03 §2.1).

doc당 디렉터리+2파일 레이아웃이 1,000만 건에서 무너지는 세 축을 바꾼다
(2026-09-20 동일 코퍼스 104,471건 실측):
- 디스크 888MB → 67.3MB (content 실제 298MB — 나머지는 블록 패딩 낭비였다)
- inode 313,413 → 11 (샤드 수)
- skip 인덱스 18.9s → 0.02s · 재처리 입력 전량 RAM 상주 → 스트리밍 peak 0.54GB

불변식은 그대로다: `doc_id = sha256(content)[:24]`, 동일 bytes 재저장은 no-op.
"""
from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone
from typing import Iterator

import duckdb

from .identity import doc_id_for, new_ulid

# (doc_id, source_id, url, fetched_at, http_status, robots_allowed, license, meta_json, content)
_COLUMNS = ("doc_id VARCHAR, source_id VARCHAR, url VARCHAR, fetched_at VARCHAR, "
            "http_status INTEGER, robots_allowed BOOLEAN, license VARCHAR, "
            "meta_json VARCHAR, content BLOB")
_SHARD_SIZE = 10_000


class RawShardStore:
    """source 별 parquet 샤드로 raw 존을 영속한다."""

    def __init__(self, raw_dir: str | pathlib.Path, *, shard_size: int = _SHARD_SIZE) -> None:
        self.raw_dir = pathlib.Path(raw_dir)
        self.shard_size = shard_size
        self._buffer: dict[str, list[tuple]] = {}
        self._known: dict[str, set[str]] = {}

    # ---- 쓰기 ----
    def append(self, source_id: str, url: str, content: bytes, meta: dict) -> tuple[str, bool]:
        """샤드 버퍼에 추가. returns (doc_id, created) — created=False 는 기수집분."""
        doc_id = doc_id_for(content)
        if doc_id in self._known_ids(source_id):
            return doc_id, False
        meta = dict(meta)
        row = (
            doc_id, source_id, url,
            # 이관되는 문서는 수집 시각을 이미 들고 있다 — 덮어쓰면 provenance 가 오늘로 바뀐다.
            meta.pop("fetched_at", None) or datetime.now(timezone.utc).isoformat(),
            meta.pop("http_status", None),
            meta.pop("robots_allowed", True),
            meta.pop("license", "unknown"),
            json.dumps(meta, ensure_ascii=False) if meta else None,
            content,
        )
        self._buffer.setdefault(source_id, []).append(row)
        self._known[source_id].add(doc_id)
        if len(self._buffer[source_id]) >= self.shard_size:
            self._write_shard(source_id)
        return doc_id, True

    def flush(self) -> None:
        """버퍼 잔량을 샤드로 확정한다. 수집 런 종료 시 반드시 호출."""
        for source_id in list(self._buffer):
            self._write_shard(source_id)

    def _write_shard(self, source_id: str) -> None:
        rows = self._buffer.pop(source_id, [])
        if not rows:
            return
        out = self.raw_dir / source_id
        out.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        path = out / f"shard-{stamp}-{new_ulid('r').split('-')[1]}.parquet"
        con = duckdb.connect()
        try:
            con.execute(f"CREATE TABLE shard({_COLUMNS})")
            con.executemany("INSERT INTO shard VALUES (?,?,?,?,?,?,?,?,?)", rows)
            con.execute(f"COPY shard TO '{path}' (FORMAT PARQUET, COMPRESSION zstd)")
        finally:
            con.close()

    # ---- 읽기 ----
    def stored_urls(self, source_id: str) -> set[str]:
        """해당 source 의 기수집 URL 집합 (04 §2.1 S1 재수집 방지)."""
        shards = self._shards([source_id])
        urls = {row[0] for row in self._query(shards, "SELECT url")} if shards else set()
        urls.update(row[2] for row in self._buffer.get(source_id, []))
        return {u for u in urls if u}

    def iter_docs(self, source_ids: list[str] | None = None,
                  doc_ids: list[str] | None = None) -> Iterator[dict]:
        """재처리 입력 — 샤드를 순회하며 문서를 하나씩 내보낸다 (전량 적재 금지).

        `doc_ids` 를 주면 그 문서만 낸다 — 증분 승격이 신규분만 읽는 경로다
        (content 컬럼은 일치 행에서만 읽힌다).
        """
        for shard in self._shards(source_ids):
            con = duckdb.connect()
            try:
                sql = "SELECT doc_id, source_id, url, content FROM read_parquet(?)"
                params: list = [str(shard)]
                if doc_ids is not None:
                    sql += " WHERE doc_id IN (SELECT unnest(?))"
                    params.append(list(doc_ids))
                cur = con.execute(sql, params)
                while True:
                    chunk = cur.fetchmany(1_000)
                    if not chunk:
                        break
                    for doc_id, source_id, url, content in chunk:
                        yield {"doc_id": doc_id, "source_id": source_id,
                               "url": url, "content": bytes(content)}
            finally:
                con.close()

    def fetch_records(self, source_ids: list[str] | None = None) -> list[dict]:
        """viewer intake·governance 패널 입력 — content 를 읽지 않는 메타 전용 조회."""
        shards = self._shards(source_ids)
        if not shards:
            return []
        rows = self._query(
            shards,
            "SELECT source_id, doc_id, url, fetched_at, http_status, robots_allowed, license")
        keys = ("source_id", "doc_id", "url", "fetched_at",
                "http_status", "robots_allowed", "license")
        return [dict(zip(keys, row)) for row in rows]

    def count_by_source(self, source_ids: list[str] | None = None) -> dict[str, int]:
        """source 별 문서 수 — 집계 쿼리(content 미판독). 재처리 로그·viewer 입력."""
        shards = self._shards(source_ids)
        counts = {source: n for source, n in
                  self._query(shards, "SELECT source_id, count(*)",
                              group_by="source_id")} if shards else {}
        for source_id, rows in self._buffer.items():
            if source_ids is None or source_id in source_ids:
                counts[source_id] = counts.get(source_id, 0) + len(rows)
        return counts

    def get_content(self, doc_id: str) -> bytes:
        """단건 provenance 왕복 — 미보유는 KeyError (정직 실패, 03 §8.1)."""
        shards = self._shards(None)
        if shards:
            rows = self._query(shards, "SELECT content", where="doc_id = ?", params=[doc_id])
            if rows:
                return bytes(rows[0][0])
        for rows in self._buffer.values():
            for row in rows:
                if row[0] == doc_id:
                    return row[-1]
        raise KeyError(doc_id)

    # ---- 내부 ----
    def _shards(self, source_ids: list[str] | None) -> list[pathlib.Path]:
        if not self.raw_dir.is_dir():
            return []
        sources = ([self.raw_dir / s for s in source_ids] if source_ids
                   else sorted(p for p in self.raw_dir.iterdir() if p.is_dir()))
        return [shard for source in sources if source.is_dir()
                for shard in sorted(source.glob("shard-*.parquet"))]

    def _query(self, shards: list[pathlib.Path], select: str, *,
               where: str = "", group_by: str = "", params: list | None = None) -> list[tuple]:
        con = duckdb.connect()
        try:
            sql = (f"{select} FROM read_parquet(?)"
                   + (f" WHERE {where}" if where else "")
                   + (f" GROUP BY {group_by}" if group_by else ""))
            return con.execute(sql, [[str(s) for s in shards]] + (params or [])).fetchall()
        finally:
            con.close()

    def _known_ids(self, source_id: str) -> set[str]:
        """이미 저장된 doc_id 집합 — source 당 1회 조회 후 캐시."""
        if source_id not in self._known:
            shards = self._shards([source_id])
            self._known[source_id] = (
                {row[0] for row in self._query(shards, "SELECT doc_id")} if shards else set())
        return self._known[source_id]
