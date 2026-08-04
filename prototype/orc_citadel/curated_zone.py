"""DuckDB curated zone (설계 03 §4) — prototype.

normalized zone(duckdb_zone.py)과 분리된 **curated zone**으로, S5 추출 mention과
S4 dedup cluster를 영속·조회·Parquet export한다. 그래프 반영/해소는 후속 단계.

- `mentions`(설계 §4.1) : L1 추출 산출물. PK를 결정적 mention_id로 유지(03 §5).
  `resolved_entity_id`는 해소 전 null (설계 05 §1.2).
- `entities` : 해소된 canonical 엔터티 (설계 02 §2.2). mention.resolved_entity_id가 참조.
- `claim_candidates`(설계 §4.2) : 규칙 기반 추출 claim 후보. status=candidate.
  (별도 claims 테이블 없음 — ADR-306, promote 시 claim-of-record.)
- `dup_clusters`(설계 §4.3) : 출처 계보. member_doc_ids는 배열(duckdb LIST).
- offsets는 clean text 축 (03 §3.2, ADR-302) — normalized segments와 동일 축.
"""
from __future__ import annotations

import json

import duckdb

from .extract import Mention
from .extract_claims import ClaimCandidate
from .resolve import Entity, ResolvedMention


class CuratedZone:
    """DuckDB 백드 curated zone (mentions + dup_clusters)."""

    def __init__(self, path: str = ":memory:") -> None:
        self._conn = duckdb.connect(path)
        self._path = path

    def initialize(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mentions (
                mention_id     VARCHAR PRIMARY KEY,
                doc_id         VARCHAR NOT NULL,
                segment_id     VARCHAR,
                surface_text   VARCHAR NOT NULL,
                mention_type   VARCHAR NOT NULL,
                char_start     BIGINT NOT NULL,
                char_end       BIGINT NOT NULL,
                context_window VARCHAR,
                resolved_entity_id VARCHAR,
                extraction_version VARCHAR
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dup_clusters (
                cluster_id                  VARCHAR PRIMARY KEY,
                root_doc_id                 VARCHAR NOT NULL,
                member_doc_ids              VARCHAR[] NOT NULL,
                independent_addition_doc_ids VARCHAR[] NOT NULL,
                dedup_method                VARCHAR NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entities (
                entity_id      VARCHAR PRIMARY KEY,
                mention_type   VARCHAR NOT NULL,
                canonical_name VARCHAR NOT NULL,
                identifiers    VARCHAR,
                surface_forms  VARCHAR[]
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS claim_candidates (
                claim_candidate_id VARCHAR PRIMARY KEY,
                doc_id             VARCHAR NOT NULL,
                predicate          VARCHAR NOT NULL,
                subject_id         VARCHAR,
                object_id          VARCHAR,
                object_literal     VARCHAR,
                modality           VARCHAR NOT NULL,
                polarity           VARCHAR NOT NULL,
                confidence         DOUBLE NOT NULL,
                seg_order          BIGINT NOT NULL,
                char_start         BIGINT NOT NULL,
                char_end           BIGINT NOT NULL,
                surface_fragment   VARCHAR,
                event_type_hint    VARCHAR,
                status             VARCHAR NOT NULL,
                quarantine_reason  VARCHAR,
                ontology_version   VARCHAR,
                extraction_model   VARCHAR
            )
            """
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_mentions_doc ON mentions(doc_id)")

    def tables(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
        ).fetchall()
        return [r[0] for r in rows]

    def persist_mention(self, m: Mention) -> None:
        """mention 1건 upsert (결정적 mention_id → ON CONFLICT no-op)."""
        self._conn.execute(
            """
            INSERT INTO mentions
                (mention_id, doc_id, segment_id, surface_text, mention_type,
                 char_start, char_end, context_window, resolved_entity_id,
                 extraction_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (mention_id) DO NOTHING
            """,
            [
                m.mention_id, m.doc_id, m.segment_id, m.surface_text, m.mention_type,
                m.char_start, m.char_end, m.context_window, m.resolved_entity_id,
                # dict → JSON 문자열로 저장 (prototype — 후속 variant/역직렬화).
                json.dumps(m.extraction_version, ensure_ascii=False),
            ],
        )

    def persist_entity(self, e: Entity) -> None:
        """canonical entity 1건 upsert (결정적 entity_id → ON CONFLICT no-op)."""
        self._conn.execute(
            """
            INSERT INTO entities
                (entity_id, mention_type, canonical_name, identifiers, surface_forms)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (entity_id) DO NOTHING
            """,
            [
                e.entity_id, e.mention_type, e.canonical_name,
                json.dumps(e.identifiers, ensure_ascii=False), list(e.surface_forms),
            ],
        )

    def persist_resolved(self, entity: Entity, resolved: list[ResolvedMention]) -> None:
        """해소 result를 영속: entity + 각 mention의 resolved_entity_id 반영.

        mention은 이미 persist_mention으로 저장됐다고 가정하고, resolved_entity_id만
        UPDATE한다 (결정적 — 원자적 재실행).
        """
        self.persist_entity(entity)
        for rm in resolved:
            if rm.resolved_entity_id is None:
                continue
            self._conn.execute(
                "UPDATE mentions SET resolved_entity_id=? WHERE mention_id=?",
                [rm.resolved_entity_id, rm.mention.mention_id],
            )

    def persist_claim(self, c: ClaimCandidate) -> None:
        """claim 후보 1건 upsert (결정적 ID → ON CONFLICT no-op, 03 §4.2)."""
        self._conn.execute(
            """
            INSERT INTO claim_candidates
                (claim_candidate_id, doc_id, predicate, subject_id, object_id,
                 object_literal, modality, polarity, confidence, seg_order,
                 char_start, char_end, surface_fragment, event_type_hint,
                 status, ontology_version, extraction_model)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (claim_candidate_id) DO NOTHING
            """,
            [
                c.claim_candidate_id, c.doc_id, c.predicate, c.subject_id,
                c.object_id, c.object_literal, c.modality, c.polarity, c.confidence,
                c.seg_order, c.char_start, c.char_end, c.surface_fragment,
                c.event_type_hint, c.status, c.to_row()["ontology_version"],
                c.to_row()["extraction_model"],
            ],
        )

    def update_claim_status(self, claim_candidate_id: str, status: str,
                            reason: str | None = None) -> None:
        """claim 후보의 상태를 게이트 결과로 업데이트 (05 §6, 03 §4.2)."""
        self._conn.execute(
            "UPDATE claim_candidates SET status=?, quarantine_reason=? "
            "WHERE claim_candidate_id=?",
            [status, reason, claim_candidate_id],
        )

    def claims(self, doc_id: str | None = None) -> list[dict]:
        cols = ["claim_candidate_id", "doc_id", "predicate", "subject_id", "object_id",
                "object_literal", "modality", "polarity", "confidence", "seg_order",
                "char_start", "char_end", "surface_fragment", "event_type_hint",
                "status", "quarantine_reason", "ontology_version", "extraction_model"]
        if doc_id is None:
            rows = self._conn.execute(f'SELECT {", ".join(cols)} FROM claim_candidates').fetchall()
        else:
            rows = self._conn.execute(
                f'SELECT {", ".join(cols)} FROM claim_candidates WHERE doc_id=?', [doc_id]
            ).fetchall()
        return [dict(zip(cols, r)) for r in rows]

    def persist_cluster(
        self,
        cluster_id: str,
        root_doc_id: str,
        member_doc_ids: list[str],
        independent_addition_doc_ids: list[str],
        dedup_method: str,
    ) -> None:
        """dup_cluster 1건 upsert (설계 §4.3)."""
        self._conn.execute(
            """
            INSERT INTO dup_clusters
                (cluster_id, root_doc_id, member_doc_ids,
                 independent_addition_doc_ids, dedup_method)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (cluster_id) DO NOTHING
            """,
            [cluster_id, root_doc_id, member_doc_ids,
             independent_addition_doc_ids, dedup_method],
        )

    def mentions(self, doc_id: str | None = None) -> list[dict]:
        cols = ["mention_id", "doc_id", "segment_id", "surface_text", "mention_type",
                "char_start", "char_end", "context_window", "resolved_entity_id",
                "extraction_version"]
        if doc_id is None:
            rows = self._conn.execute(f'SELECT {", ".join(cols)} FROM mentions').fetchall()
        else:
            rows = self._conn.execute(
                f'SELECT {", ".join(cols)} FROM mentions WHERE doc_id=?', [doc_id]
            ).fetchall()
        out = []
        for r in rows:
            d = dict(zip(cols, r))
            # extraction_version: JSON 문자열 → dict로 복원.
            try:
                d["extraction_version"] = json.loads(d["extraction_version"])
            except (TypeError, ValueError):
                d["extraction_version"] = {}
            out.append(d)
        return out

    def clusters(self) -> list[dict]:
        cols = ["cluster_id", "root_doc_id", "member_doc_ids",
                "independent_addition_doc_ids", "dedup_method"]
        rows = self._conn.execute(
            f'SELECT {", ".join(cols)} FROM dup_clusters'
        ).fetchall()
        return [dict(zip(cols, r)) for r in rows]

    def entities(self) -> list[dict]:
        cols = ["entity_id", "mention_type", "canonical_name", "identifiers",
                "surface_forms"]
        rows = self._conn.execute(
            f'SELECT {", ".join(cols)} FROM entities'
        ).fetchall()
        out = []
        for r in rows:
            d = dict(zip(cols, r))
            try:
                d["identifiers"] = json.loads(d["identifiers"])
            except (TypeError, ValueError):
                d["identifiers"] = {}
            out.append(d)
        return out

    def export_parquet(self, out_dir: str) -> None:
        """mentions/dup_clusters를 Parquet으로 export (그래프·검색 입력용)."""
        import pathlib

        p = pathlib.Path(out_dir)
        p.mkdir(parents=True, exist_ok=True)
        self._conn.execute(f"COPY mentions TO '{p / 'mentions.parquet'}' (FORMAT PARQUET)")
        self._conn.execute(f"COPY entities TO '{p / 'entities.parquet'}' (FORMAT PARQUET)")
        self._conn.execute(
            f"COPY claim_candidates TO '{p / 'claim_candidates.parquet'}' (FORMAT PARQUET)"
        )
        self._conn.execute(
            f"COPY dup_clusters TO '{p / 'dup_clusters.parquet'}' (FORMAT PARQUET)"
        )

    def close(self) -> None:
        self._conn.close()
