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

import threading

import duckdb

from .extract import Mention
from .extract_claims import ClaimCandidate
from .resolve import Entity, ResolvedMention


class CuratedZone:
    """DuckDB 백드 curated zone (mentions + dup_clusters)."""

    def __init__(self, path: str = ":memory:") -> None:
        self._root = duckdb.connect(path)
        self._local = threading.local()
        self._path = path

    @property
    def _conn(self):
        """스레드별 DuckDB 커서.

        뷰어는 `ThreadingHTTPServer` 라 동시 요청이 같은 zone 객체를 공유한다.
        DuckDB 커넥션은 스레드 안전하지 않아, 두 스레드가 한 커넥션에서
        `execute` 를 교차하면 결과가 뒤섞인다 — 실제로 `extraction_records()` 의
        `SELECT *` 와 `DESCRIBE` 가 어긋나 `KeyError: 'element_id'` 로 터졌다.
        `cursor()` 는 같은 DB 를 공유하는 독립 커넥션이라 이 교차를 없앤다.
        """
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._local.conn = self._root.cursor()
        return conn

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
                extraction_version VARCHAR,
                authoritative  BOOLEAN NOT NULL DEFAULT FALSE
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
                canonical_claim_id VARCHAR,
                ontology_version   VARCHAR,
                extraction_model   VARCHAR
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS canonical_claims (
                canonical_claim_id VARCHAR PRIMARY KEY,
                subject_id         VARCHAR NOT NULL,
                predicate          VARCHAR NOT NULL,
                object_id          VARCHAR,
                canonical_text     VARCHAR NOT NULL,
                member_claim_ids   VARCHAR[]
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS member_of (
                claim_id           VARCHAR NOT NULL,
                canonical_claim_id VARCHAR NOT NULL,
                PRIMARY KEY (claim_id, canonical_claim_id)
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conflict_candidates (
                claim_id_a     VARCHAR NOT NULL,
                claim_id_b     VARCHAR NOT NULL,
                conflict_type  VARCHAR NOT NULL,
                rationale      VARCHAR,
                judged_by      VARCHAR NOT NULL,
                PRIMARY KEY (claim_id_a, claim_id_b)
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS assertions (
                assertion_id    VARCHAR PRIMARY KEY,
                claim_id        VARCHAR NOT NULL,
                subject_id      VARCHAR NOT NULL,
                predicate       VARCHAR NOT NULL,
                object_id       VARCHAR,
                object_literal  VARCHAR,
                valid_from      TIMESTAMP,
                valid_to        TIMESTAMP,
                time_precision  VARCHAR NOT NULL,
                tx_from         TIMESTAMP NOT NULL,
                tx_to           TIMESTAMP,
                supersedes_id   VARCHAR,
                mutation_id     VARCHAR NOT NULL,
                provenance_ref  VARCHAR[],
                ontology_version VARCHAR NOT NULL DEFAULT ''
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS authoritative_edges (
                edge_id        VARCHAR PRIMARY KEY,
                entity_a_id    VARCHAR NOT NULL,
                entity_b_id    VARCHAR NOT NULL,
                relation       VARCHAR NOT NULL,
                score          DOUBLE,
                blocking_key   VARCHAR,
                resolution_ref VARCHAR NOT NULL,
                judged_by      VARCHAR NOT NULL
            )
            """
        )
        # S23: LLM 판정 산출물 영속 (설계 03 §7.1 version tuple, 05 §4.2·§5.2).
        # canonicalization 의사결정 근거 — 결정적 규칙이 미결로 남긴 쌍의 LLM 7라벨.
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS canonical_llm_records (
                claim_id_a     VARCHAR NOT NULL,
                claim_id_b     VARCHAR NOT NULL,
                relation       VARCHAR NOT NULL,
                canonical_text VARCHAR,
                confidence     DOUBLE NOT NULL,
                rationale      VARCHAR,
                judged_by      VARCHAR NOT NULL,
                version_tuple  VARCHAR,
                PRIMARY KEY (claim_id_a, claim_id_b)
            )
            """
        )
        # contradiction verdict — LLM 실제 모순 판정 (05 §5.2).
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conflict_verdicts (
                claim_id_a     VARCHAR NOT NULL,
                claim_id_b     VARCHAR NOT NULL,
                verdict        VARCHAR NOT NULL,
                conflict_type  VARCHAR,
                rationale      VARCHAR,
                confidence     DOUBLE NOT NULL,
                judged_by      VARCHAR NOT NULL,
                version_tuple  VARCHAR,
                PRIMARY KEY (claim_id_a, claim_id_b)
            )
            """
        )
        # S34: 골든셋 영속 (설계 10 §2.3 저장·버저닝, human review as data §3-7).
        # claim pair 골든셋 — split(ADR-1007), gold_version, labeled_by/at, rationale,
        # original_prediction(원 모델 출력 — 회귀 대조용).
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS golden_pairs (
                golden_id           VARCHAR PRIMARY KEY,
                claim_a             VARCHAR NOT NULL,
                claim_b             VARCHAR NOT NULL,
                label               VARCHAR NOT NULL,
                split               VARCHAR NOT NULL,
                gold_version        VARCHAR NOT NULL,
                labeled_by          VARCHAR,
                labeled_at          VARCHAR,
                rationale           VARCHAR,
                original_prediction VARCHAR
            )
            """
        )
        # Phase 2: entity pair 골든세트 (설계 10 §2.1 — Entity pair 판정, ADR-1001).
        # 골든 same/not_same 쌍 → ER 캐스케이드(ADR-507) 대조로 P/R·오병합률(≤0.02) 측정.
        # entity_key는 결정적 외부식별자(식별자 있으면 id, 없으면 (type, surface)).
        # split(ADR-1007), gold_version, labeled_by/at — human review as data (§3-7).
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS golden_entity_pairs (
                golden_id     VARCHAR PRIMARY KEY,
                entity_key_a  VARCHAR NOT NULL,
                entity_key_b  VARCHAR NOT NULL,
                label         VARCHAR NOT NULL,   -- same | not_same | uncertain
                split         VARCHAR NOT NULL,
                gold_version  VARCHAR NOT NULL,
                labeled_by    VARCHAR,
                labeled_at    VARCHAR,
                rationale     VARCHAR
            )
            """
        )
        # Phase 2: 계보 골든셋 (설계 10 §2.1 — 계보 클러스터 dup/independent).
        # 골든 dup/independent 쌍 → dup_clusters 멤버십 대조로 dup P/R 측정.
        # split(ADR-1007), gold_version, labeled_by/at — human review as data (§3-7).
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS golden_lineage_pairs (
                golden_id     VARCHAR PRIMARY KEY,
                doc_a         VARCHAR NOT NULL,
                doc_b         VARCHAR NOT NULL,
                label         VARCHAR NOT NULL,   -- dup | independent
                split         VARCHAR NOT NULL,
                gold_version  VARCHAR NOT NULL,
                labeled_by    VARCHAR,
                labeled_at    VARCHAR,
                rationale     VARCHAR
            )
            """
        )
        # S38: 승격 기준선 영속 (설계 10 §3.1, ADR-1003) — last-promoted baseline.
        # version 기반 결정적 PK, active(현재 last-promoted)/superseded(승격 이력).
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS promotion_baselines (
                baseline_id VARCHAR PRIMARY KEY,
                version     VARCHAR NOT NULL,
                metrics     VARCHAR NOT NULL,
                ontology    VARCHAR,
                promoted_at VARCHAR,
                promoted_by VARCHAR,
                status      VARCHAR NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS extraction_records (
                extraction_id          VARCHAR PRIMARY KEY,
                element_id             VARCHAR NOT NULL,
                doc_id                 VARCHAR NOT NULL,
                segment_id             VARCHAR,
                char_start             BIGINT NOT NULL,
                char_end               BIGINT NOT NULL,
                content_hash           VARCHAR,
                fetched_at             VARCHAR,
                published_at           VARCHAR,
                model_id               VARCHAR,
                prompt_template_hash   VARCHAR,
                schema_version         VARCHAR,
                preprocess_code_version VARCHAR,
                review_history         VARCHAR
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

    def persist_extraction_record(self, element_id: str, doc_id: str,
                                  segment_id: str | None = None,
                                  char_start: int = 0, char_end: int = 0,
                                  content_hash: str | None = None,
                                  fetched_at: str | None = None,
                                  published_at: str | None = None,
                                  model_id: str | None = None,
                                  prompt_template_hash: str | None = None,
                                  schema_version: str | None = None,
                                  preprocess_code_version: str | None = None) -> str:
        """§8.2 extraction_record 영속 — element_id → extraction_id 결정적 매핑.

        extraction_id 는 element_id 로부터 결정적 생성 → 동일 element 재영속은 동일
        extraction_id (ON CONFLICT no-op, 불변식 §3-6). element 1건에 추출 기록 1개.
        """
        import hashlib

        extraction_id = "ext-" + hashlib.sha256(element_id.encode()).hexdigest()[:24]
        self._conn.execute(
            """
            INSERT INTO extraction_records
                (extraction_id, element_id, doc_id, segment_id, char_start, char_end,
                 content_hash, fetched_at, published_at, model_id,
                 prompt_template_hash, schema_version, preprocess_code_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (extraction_id) DO NOTHING
            """,
            [extraction_id, element_id, doc_id, segment_id, char_start, char_end,
             content_hash, fetched_at, published_at, model_id,
             prompt_template_hash, schema_version, preprocess_code_version],
        )
        return extraction_id

    def extraction_records(self) -> list:
        """전체 extraction_record 조회 (추적·provenance 왕복용)."""
        rows = self._conn.execute(
            "SELECT * FROM extraction_records ORDER BY extraction_id"
        ).fetchall()
        cols = [d[0] for d in self._conn.execute("DESCRIBE extraction_records").fetchall()]
        return [dict(zip(cols, r)) for r in rows]

    def has_extraction_record(self, element_id: str) -> bool:
        """element_id 소유 추출 기록 존재 — ADR-305 게이트 근거."""
        row = self._conn.execute(
            "SELECT 1 FROM extraction_records WHERE element_id = ? LIMIT 1",
            [element_id],
        ).fetchone()
        return row is not None

    def persist_canonical(self, cc) -> None:
        """CanonicalClaim 1건 upsert + MEMBER_OF 엣지 (02 §2.4·§3.1, 정본 소속)."""
        from .canonicalize import CanonicalClaim

        assert isinstance(cc, CanonicalClaim), "expected CanonicalClaim"
        self._conn.execute(
            """
            INSERT INTO canonical_claims
                (canonical_claim_id, subject_id, predicate, object_id,
                 canonical_text, member_claim_ids)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (canonical_claim_id) DO NOTHING
            """,
            [cc.canonical_claim_id, cc.subject_id, cc.predicate, cc.object_id,
             cc.canonical_text, list(cc.member_claim_ids)],
        )
        for cid in cc.member_claim_ids:
            self._conn.execute(
                """
                INSERT INTO member_of (claim_id, canonical_claim_id)
                VALUES (?, ?) ON CONFLICT DO NOTHING
                """,
                [cid, cc.canonical_claim_id],
            )

    def set_claim_canonical(self, claim_id: str, canonical_claim_id: str | None) -> None:
        """claim_candidates.canonical_claim_id 반영 (파생 표현, 02 §3.1)."""
        self._conn.execute(
            "UPDATE claim_candidates SET canonical_claim_id=? WHERE claim_candidate_id=?",
            [canonical_claim_id, claim_id],
        )

    def persist_conflict(self, cc) -> None:
        """conflict_candidates 1건 upsert (결정적 쌍 → ON CONFLICT no-op)."""
        self._conn.execute(
            """
            INSERT INTO conflict_candidates
                (claim_id_a, claim_id_b, conflict_type, rationale, judged_by)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (claim_id_a, claim_id_b) DO UPDATE SET
                conflict_type=excluded.conflict_type, rationale=excluded.rationale,
                judged_by=excluded.judged_by
            """,
            [cc.claim_id_a, cc.claim_id_b, cc.conflict_type, cc.rationale, cc.judged_by],
        )

    def persist_canonical_llm_record(
        self, claim_id_a: str, claim_id_b: str, relation: str,
        canonical_text: str, confidence: float, rationale: str,
        version_tuple: dict, judged_by: str = "llm",
    ) -> None:
        """canonicalization LLM 판정 근거 upsert (결정적 (a,b) → idempotent, 05 §4.2).

        version_tuple은 03 §7.1 5축 JSON으로 보존 — 재실행·모델 교체 추적.
        """
        self._conn.execute(
            """
            INSERT INTO canonical_llm_records
                (claim_id_a, claim_id_b, relation, canonical_text, confidence,
                 rationale, judged_by, version_tuple)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (claim_id_a, claim_id_b) DO UPDATE SET
                relation=excluded.relation, canonical_text=excluded.canonical_text,
                confidence=excluded.confidence, rationale=excluded.rationale,
                judged_by=excluded.judged_by, version_tuple=excluded.version_tuple
            """,
            [claim_id_a, claim_id_b, relation, canonical_text, confidence,
             rationale, judged_by, json.dumps(version_tuple, ensure_ascii=False)],
        )

    def persist_conflict_verdict(
        self, claim_id_a: str, claim_id_b: str, verdict: str,
        conflict_type: str | None, rationale: str, confidence: float,
        version_tuple: dict, judged_by: str = "llm",
    ) -> None:
        """contradiction LLM verdict upsert (05 §5.2) — version tuple 함께 영속."""
        self._conn.execute(
            """
            INSERT INTO conflict_verdicts
                (claim_id_a, claim_id_b, verdict, conflict_type, rationale,
                 confidence, judged_by, version_tuple)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (claim_id_a, claim_id_b) DO UPDATE SET
                verdict=excluded.verdict, conflict_type=excluded.conflict_type,
                rationale=excluded.rationale, confidence=excluded.confidence,
                judged_by=excluded.judged_by, version_tuple=excluded.version_tuple
            """,
            [claim_id_a, claim_id_b, verdict, conflict_type, rationale,
             confidence, judged_by, json.dumps(version_tuple, ensure_ascii=False)],
        )

    def canonical_llm_records(self) -> list[dict]:
        cols = ["claim_id_a", "claim_id_b", "relation", "canonical_text",
                "confidence", "rationale", "judged_by", "version_tuple"]
        rows = self._conn.execute(
            f'SELECT {", ".join(cols)} FROM canonical_llm_records'
        ).fetchall()
        out = []
        for r in rows:
            d = dict(zip(cols, r))
            try:
                d["version_tuple"] = json.loads(d["version_tuple"])
            except (TypeError, ValueError):
                d["version_tuple"] = {}
            out.append(d)
        return out

    def conflict_verdicts(self) -> list[dict]:
        cols = ["claim_id_a", "claim_id_b", "verdict", "conflict_type",
                "rationale", "confidence", "judged_by", "version_tuple"]
        rows = self._conn.execute(
            f'SELECT {", ".join(cols)} FROM conflict_verdicts'
        ).fetchall()
        out = []
        for r in rows:
            d = dict(zip(cols, r))
            try:
                d["version_tuple"] = json.loads(d["version_tuple"])
            except (TypeError, ValueError):
                d["version_tuple"] = {}
            out.append(d)
        return out

    def assertions_as_of(self, valid_at=None, tx_at=None) -> list[dict]:
        """bitemporal AS-OF 질의 (설계 06 §8.2, ADR-606).

        Assertion valid/tx 두 축으로 시간 여행:
        - valid: `valid_from ≤ T_v < valid_to` (open lower/upper bound, time_precision 경계).
        - tx:   `tx_from ≤ T_t < (tx_to ?? ∞)` — tx_to null(현재) 또는 tx_to 이후.
        인자 없으면 현재 tx(tx_to null)의 모든 어세션 (현재 그래프).
        superseded 버전은 삭제하지 않으므로 과거 상태 그대로 조회된다 (03 §6.3).
        """
        # SQL 비교 — datetime 파라미터는 DuckDB TIMESTAMP로 일관 바인딩 (문자열 변환 금지:
        # aware-datetime 저장 시 local offset이 섞여 경계 비교가 어긋남).
        clauses, params = [], []
        if valid_at is not None:
            clauses.append("(valid_from IS NULL OR valid_from <= ?)")
            params.append(valid_at)
            clauses.append("(valid_to IS NULL OR ? < valid_to)")
            params.append(valid_at)
        if tx_at is not None:
            clauses.append("(tx_from <= ?)")
            params.append(tx_at)
            clauses.append("(tx_to IS NULL OR ? < tx_to)")
            params.append(tx_at)
        else:
            clauses.append("tx_to IS NULL")
        where = " AND ".join(clauses) if clauses else "1=1"
        cols = ["assertion_id", "claim_id", "subject_id", "predicate", "object_id",
                "object_literal", "valid_from", "valid_to", "time_precision",
                "tx_from", "tx_to", "supersedes_id", "mutation_id", "provenance_ref",
                "ontology_version"]
        rows = self._conn.execute(
            f'SELECT {", ".join(cols)} FROM assertions WHERE {where} '
            f'ORDER BY assertion_id', params
        ).fetchall()
        return [dict(zip(cols, r)) for r in rows]

    def persist_assertion(self, a) -> None:
        """Assertion 1건 upsert (결정적 asr- id → ON CONFLICT no-op, 03 §6.2)."""
        from .assertions import Assertion

        assert isinstance(a, Assertion), "expected Assertion"
        self._conn.execute(
            """
            INSERT INTO assertions
                (assertion_id, claim_id, subject_id, predicate, object_id,
                 object_literal, valid_from, valid_to, time_precision, tx_from,
                 tx_to, supersedes_id, mutation_id, provenance_ref, ontology_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (assertion_id) DO NOTHING
            """,
            [a.assertion_id, a.claim_id, a.subject_id, a.predicate, a.object_id,
             a.object_literal, a.valid_from, a.valid_to, a.time_precision, a.tx_from,
             a.tx_to, a.supersedes_id, a.mutation_id, list(a.provenance_ref),
             a.ontology_version],
        )

    def persist_edge(self, e) -> None:
        """authoritative_edges 1건 upsert (결정적 edge_id → ON CONFLICT do nothing)."""
        from .edges import PossiblySameAsEdge

        assert isinstance(e, PossiblySameAsEdge), "expected PossiblySameAsEdge"
        row = e.to_row()
        self._conn.execute(
            """
            INSERT INTO authoritative_edges
                (edge_id, entity_a_id, entity_b_id, relation, score,
                 blocking_key, resolution_ref, judged_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (edge_id) DO NOTHING
            """,
            [row["edge_id"], row["entity_a_id"], row["entity_b_id"], row["relation"],
             row["score"], row["blocking_key"], row["resolution_ref"], row["judged_by"]],
        )

    def authoritative_edges(self) -> list[dict]:
        cols = ["edge_id", "entity_a_id", "entity_b_id", "relation", "score",
                "blocking_key", "resolution_ref", "judged_by"]
        rows = self._conn.execute(
            f'SELECT {", ".join(cols)} FROM authoritative_edges'
        ).fetchall()
        return [dict(zip(cols, r)) for r in rows]

    def assertions(self) -> list[dict]:
        cols = ["assertion_id", "claim_id", "subject_id", "predicate", "object_id",
                "object_literal", "valid_from", "valid_to", "time_precision",
                "tx_from", "tx_to", "supersedes_id", "mutation_id", "provenance_ref",
                "ontology_version"]
        rows = self._conn.execute(
            f'SELECT {", ".join(cols)} FROM assertions'
        ).fetchall()
        return [dict(zip(cols, r)) for r in rows]

    def conflict_candidates(self) -> list[dict]:
        cols = ["claim_id_a", "claim_id_b", "conflict_type", "rationale", "judged_by"]
        rows = self._conn.execute(
            f'SELECT {", ".join(cols)} FROM conflict_candidates'
        ).fetchall()
        return [dict(zip(cols, r)) for r in rows]

    def canonical_claims(self) -> list[dict]:
        cols = ["canonical_claim_id", "subject_id", "predicate", "object_id",
                "canonical_text", "member_claim_ids"]
        rows = self._conn.execute(
            f'SELECT {", ".join(cols)} FROM canonical_claims'
        ).fetchall()
        return [dict(zip(cols, r)) for r in rows]

    def member_of(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT claim_id, canonical_claim_id FROM member_of"
        ).fetchall()
        return [dict(zip(["claim_id", "canonical_claim_id"], r)) for r in rows]

    def claims(self, doc_id: str | None = None) -> list[dict]:
        cols = ["claim_candidate_id", "doc_id", "predicate", "subject_id", "object_id",
                "object_literal", "modality", "polarity", "confidence", "seg_order",
                "char_start", "char_end", "surface_fragment", "event_type_hint",
                "status", "quarantine_reason", "canonical_claim_id",
                "ontology_version", "extraction_model"]
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

    def set_mention_authoritative(self, mention_id: str) -> None:
        """mention을 authoritative graph 노드로 표시 (게이트 통과 시, 05 §6)."""
        self._conn.execute(
            "UPDATE mentions SET authoritative=TRUE WHERE mention_id=?",
            [mention_id],
        )

    def mentions(self, doc_id: str | None = None) -> list[dict]:
        cols = ["mention_id", "doc_id", "segment_id", "surface_text", "mention_type",
                "char_start", "char_end", "context_window", "resolved_entity_id",
                "extraction_version", "authoritative"]
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

    def persist_golden_pair(
        self, claim_a: str, claim_b: str, label: str, split: str,
        gold_version: str, labeled_by: str | None = None,
        labeled_at: str | None = None, rationale: str | None = None,
        original_prediction: str | None = None,
    ) -> None:
        """골든 claim pair 1건 upsert (결정적 golden_id → ON CONFLICT no-op, 10 §2.3).

        결정적 ID: (claim_a, claim_b, label, split, gold_version) 기반 — 재실행 중복 없음
        (03 §5). split은 ADR-1007(dev/test). original_prediction은 원 모델 출력 보존
        (design 10 §2.2 human review as data — 회귀 대조용).
        """
        hashlib = __import__("hashlib")
        key = "|".join([claim_a, claim_b, label, split, gold_version])
        golden_id = "gold-" + hashlib.sha256(key.encode()).hexdigest()[:24]
        self._conn.execute(
            """
            INSERT INTO golden_pairs
                (golden_id, claim_a, claim_b, label, split, gold_version,
                 labeled_by, labeled_at, rationale, original_prediction)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (golden_id) DO NOTHING
            """,
            [golden_id, claim_a, claim_b, label, split, gold_version,
             labeled_by, labeled_at, rationale, original_prediction],
        )

    def golden_pairs(self) -> list[dict]:
        cols = ["golden_id", "claim_a", "claim_b", "label", "split",
                "gold_version", "labeled_by", "labeled_at", "rationale",
                "original_prediction"]
        rows = self._conn.execute(
            f'SELECT {", ".join(cols)} FROM golden_pairs').fetchall()
        return [dict(zip(cols, r)) for r in rows]

    def persist_golden_entity_pair(
        self, entity_key_a: str, entity_key_b: str, label: str, split: str,
        gold_version: str, labeled_by: str | None = None,
        labeled_at: str | None = None, rationale: str | None = None,
    ) -> None:
        """골든 entity pair 1건 upsert (결정적 golden_id → ON CONFLICT no-op, 10 §2.3).

        entity_key: 결정적 외부식별자(식별자 있으면 id, 없으면 (type, surface)).
        label ∈ {same, not_same, uncertain} — ER/오병합률 게이트(ADR-1001 precision-first:
        P ≥ 0.97, 오병합률 ≤ 0.02)의 ground truth. split은 ADR-1007(dev/test).
        """
        hashlib = __import__("hashlib")
        key = "|".join([entity_key_a, entity_key_b, label, split, gold_version])
        golden_id = "gold-" + hashlib.sha256(key.encode()).hexdigest()[:24]
        self._conn.execute(
            """
            INSERT INTO golden_entity_pairs
                (golden_id, entity_key_a, entity_key_b, label, split,
                 gold_version, labeled_by, labeled_at, rationale)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (golden_id) DO NOTHING
            """,
            [golden_id, entity_key_a, entity_key_b, label, split, gold_version,
             labeled_by, labeled_at, rationale],
        )

    def golden_entity_pairs(self) -> list[dict]:
        cols = ["golden_id", "entity_key_a", "entity_key_b", "label", "split",
                "gold_version", "labeled_by", "labeled_at", "rationale"]
        rows = self._conn.execute(
            f'SELECT {", ".join(cols)} FROM golden_entity_pairs').fetchall()
        return [dict(zip(cols, r)) for r in rows]

    def persist_golden_lineage_pair(
        self, doc_a: str, doc_b: str, label: str, split: str,
        gold_version: str, labeled_by: str | None = None,
        labeled_at: str | None = None, rationale: str | None = None,
    ) -> None:
        """골든 계보 쌍 1건 upsert (결정적 golden_id → ON CONFLICT no-op, 10 §2.3).

        label ∈ {dup, independent} — 출처 계보(design 04 §4)의 ground truth:
        두 doc 이 같은 dup_clusters 클러스터로 축소돼야 하는지(dup) 아닌지(independent).
        split은 ADR-1007(dev/test), gold_version·labeled_by/at — §3-7.
        """
        hashlib = __import__("hashlib")
        key = "|".join([doc_a, doc_b, label, split, gold_version])
        golden_id = "gold-" + hashlib.sha256(key.encode()).hexdigest()[:24]
        self._conn.execute(
            """
            INSERT INTO golden_lineage_pairs
                (golden_id, doc_a, doc_b, label, split,
                 gold_version, labeled_by, labeled_at, rationale)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (golden_id) DO NOTHING
            """,
            [golden_id, doc_a, doc_b, label, split, gold_version,
             labeled_by, labeled_at, rationale],
        )

    def golden_lineage_pairs(self) -> list[dict]:
        cols = ["golden_id", "doc_a", "doc_b", "label", "split",
                "gold_version", "labeled_by", "labeled_at", "rationale"]
        rows = self._conn.execute(
            f'SELECT {", ".join(cols)} FROM golden_lineage_pairs').fetchall()
        return [dict(zip(cols, r)) for r in rows]

    def persist_promotion_baseline(self, version: str, metrics: dict,
                                   promoted_by: str = "pipeline",
                                   ontology: str | None = None) -> str:
        """last-promoted baseline 1건 upsert (결정적 baseline_id, 10 §3.1/ADR-1003).

        같은 version 재영속은 no-op (idempotent). 승격 시 신규 version은 새 active로.
        baseline_id는 version 기반 결정적 — 재실행 중복 없음 (03 §5).
        ontology는 5축 version-aware 승격(S40)의 major bump 비교용 (02 §6.3).
        """
        hashlib = __import__("hashlib")
        baseline_id = "base-" + hashlib.sha256(
            ("promo|" + version).encode()).hexdigest()[:24]
        self._conn.execute(
            """
            INSERT INTO promotion_baselines
                (baseline_id, version, metrics, ontology, promoted_at, promoted_by,
                 status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (baseline_id) DO NOTHING
            """,
            [baseline_id, version, self._safe_json(metrics), ontology,
             None, promoted_by, "active"],
        )
        return baseline_id

    @staticmethod
    def _safe_json(v) -> str:
        try:
            return json.dumps(v, ensure_ascii=False)
        except TypeError:
            return json.dumps(str(v), ensure_ascii=False)

    def mark_baseline_superseded(self, version: str) -> None:
        """승격 시 기존 active baseline을 superseded로 (승격 이력 보존)."""
        self._conn.execute(
            "UPDATE promotion_baselines SET status='superseded' WHERE version=?",
            [version],
        )

    def promotion_baselines(self) -> list[dict]:
        cols = ["baseline_id", "version", "metrics", "ontology", "promoted_at",
                "promoted_by", "status"]
        rows = self._conn.execute(
            f'SELECT {", ".join(cols)} FROM promotion_baselines').fetchall()
        out = []
        for r in rows:
            d = dict(zip(cols, r))
            try:
                d["metrics"] = json.loads(d["metrics"])
            except (TypeError, ValueError):
                d["metrics"] = {}
            out.append(d)
        return out

    def active_baseline(self) -> dict | None:
        rows = self._conn.execute(
            "SELECT baseline_id, version, metrics, ontology, promoted_at, "
            "promoted_by, status FROM promotion_baselines "
            "WHERE status='active' ORDER BY version DESC LIMIT 1").fetchall()
        if not rows:
            return None
        cols = ["baseline_id", "version", "metrics", "ontology", "promoted_at",
                "promoted_by", "status"]
        d = dict(zip(cols, rows[0]))
        try:
            d["metrics"] = json.loads(d["metrics"])
        except (TypeError, ValueError):
            d["metrics"] = {}
        return d

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
            f"COPY canonical_claims TO '{p / 'canonical_claims.parquet'}' (FORMAT PARQUET)"
        )
        self._conn.execute(
            f"COPY member_of TO '{p / 'member_of.parquet'}' (FORMAT PARQUET)"
        )
        self._conn.execute(
            f"COPY conflict_candidates TO '{p / 'conflict_candidates.parquet'}' (FORMAT PARQUET)"
        )
        self._conn.execute(
            f"COPY assertions TO '{p / 'assertions.parquet'}' (FORMAT PARQUET)"
        )
        self._conn.execute(
            f"COPY authoritative_edges TO '{p / 'authoritative_edges.parquet'}' (FORMAT PARQUET)"
        )
        self._conn.execute(
            f"COPY canonical_llm_records TO '{p / 'canonical_llm_records.parquet'}' (FORMAT PARQUET)"
        )
        self._conn.execute(
            f"COPY conflict_verdicts TO '{p / 'conflict_verdicts.parquet'}' (FORMAT PARQUET)"
        )
        self._conn.execute(
            f"COPY dup_clusters TO '{p / 'dup_clusters.parquet'}' (FORMAT PARQUET)"
        )
        self._conn.execute(
            f"COPY golden_pairs TO '{p / 'golden_pairs.parquet'}' (FORMAT PARQUET)"
        )
        self._conn.execute(
            f"COPY promotion_baselines TO '{p / 'promotion_baselines.parquet'}' (FORMAT PARQUET)"
        )

    def close(self) -> None:
        self._root.close()
