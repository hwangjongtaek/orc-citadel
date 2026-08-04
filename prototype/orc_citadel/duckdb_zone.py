"""DuckDB 정규화 zone (design 03 §3, prototype).

raw zone은 파일로 유지(content.bin + fetch.json, 설계 §2.1)하고, 이 모듈은
정규화 산출물(documents + segments)을 DuckDB로 영속·조회한다. 그래프/큐레이션
(mentions·claims·S4 dedup)은 이 단계 범위 밖.

- `documents.doc_id` = sha256(raw HTML bytes)[:24] (설계 §2.1, provenance anchor).
- upsert key = (doc_id, parser_version) — 동일 버전 재persist는 no-op,
  version bump는 새 row(04 §3.3). segments는 같은 key로 전체 교체(replace).
- offsets는 문자(char) 단위 (ADR-302, UTF-8 다중 바이트 정합).
"""
from __future__ import annotations

import duckdb

from .identity import doc_id_for
from .parse import ParsedDoc, parse_document


class NormalizedZone:
    """DuckDB 백드 정규화 zone."""

    def __init__(self, path: str = ":memory:") -> None:
        self._conn = duckdb.connect(path)
        self._path = path

    def initialize(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                doc_id         VARCHAR NOT NULL,
                source_id      VARCHAR NOT NULL,
                url            VARCHAR NOT NULL,
                title          VARCHAR,
                language       VARCHAR,
                publication_time TIMESTAMP,
                revision_time  TIMESTAMP,
                parser_version VARCHAR NOT NULL,
                char_len       BIGINT,
                PRIMARY KEY (doc_id, parser_version)
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS segments (
                segment_id     VARCHAR PRIMARY KEY,
                doc_id         VARCHAR NOT NULL,
                kind           VARCHAR NOT NULL,
                text           VARCHAR NOT NULL,
                char_start     BIGINT NOT NULL,
                char_end       BIGINT NOT NULL,
                norm_char_start BIGINT NOT NULL,
                norm_char_end  BIGINT NOT NULL,
                ord            BIGINT NOT NULL,
                parser_version VARCHAR NOT NULL
            )
            """
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_segments_doc ON segments(doc_id)")

    def tables(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
        ).fetchall()
        return [r[0] for r in rows]

    def persist(self, source_id: str, url: str, raw_html: bytes, doc: ParsedDoc) -> str:
        """문서+segments를 DuckDB에 영속. (doc_id, parser_version) upsert.

        raw_html로 doc_id(내용 기반)를 만들고, clean text를 segment로 분절해 저장.
        returns doc_id (raw HTML 기반, 설계 §2.1).
        """
        doc_id = doc_id_for(raw_html)
        self._conn.execute(
            """
            INSERT INTO documents
                (doc_id, source_id, url, title, language, publication_time,
                 revision_time, parser_version, char_len)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (doc_id, parser_version) DO UPDATE SET
                source_id=excluded.source_id, url=excluded.url, title=excluded.title,
                publication_time=excluded.publication_time, char_len=excluded.char_len
            """,
            [
                doc_id, source_id, url, doc.title, "en",
                doc.publication_time, None, doc.parser_version,
                len(doc.text),
            ],
        )
        # 동일 (doc_id, parser_version)의 옛 segment 제거 후 재삽입 (재파싱 교체).
        self._conn.execute(
            "DELETE FROM segments WHERE doc_id=? AND parser_version=?",
            [doc_id, doc.parser_version],
        )
        segments = parse_document(doc_id, doc)
        for s in segments:
            self._conn.execute(
                """INSERT INTO segments
                   (segment_id, doc_id, kind, text, char_start, char_end,
                    norm_char_start, norm_char_end, ord, parser_version)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    s.segment_id, doc_id, s.kind, s.text,
                    s.char_start, s.char_end, s.norm_char_start, s.norm_char_end,
                    s.order, doc.parser_version,
                ],
            )
        return doc_id

    def documents(self) -> list[dict]:
        rows = self._conn.execute(
            """SELECT doc_id, source_id, url, title, language, publication_time,
                      revision_time, parser_version, char_len FROM documents"""
        ).fetchall()
        cols = ["doc_id", "source_id", "url", "title", "language",
                "publication_time", "revision_time", "parser_version", "char_len"]
        return [dict(zip(cols, r)) for r in rows]

    def segments(self, doc_id: str) -> list[dict]:
        rows = self._conn.execute(
            """SELECT segment_id, doc_id, kind, text, char_start, char_end,
                      norm_char_start, norm_char_end, ord, parser_version
               FROM segments WHERE doc_id=?""",
            [doc_id],
        ).fetchall()
        cols = ["segment_id", "doc_id", "kind", "text", "char_start", "char_end",
                "norm_char_start", "norm_char_end", "ord", "parser_version"]
        return [dict(zip(cols, r)) for r in rows]

    def export_parquet(self, out_dir: str) -> None:
        """documents/segments를 Parquet으로 내보내기 (05 이후 쿼리·그래프 입력용)."""
        import pathlib

        p = pathlib.Path(out_dir)
        p.mkdir(parents=True, exist_ok=True)
        self._conn.execute(
            f"COPY documents TO '{p / 'documents.parquet'}' (FORMAT PARQUET)"
        )
        self._conn.execute(
            f"COPY segments TO '{p / 'segments.parquet'}' (FORMAT PARQUET)"
        )

    def close(self) -> None:
        self._conn.close()
