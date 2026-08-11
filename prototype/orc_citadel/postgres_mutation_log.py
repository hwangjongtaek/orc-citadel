"""P1 저장 계층 키스톤 ① — PostgreSQL `graph_mutations` append-only event store (design 03 §7).

mutation_log.MutationLog 는 in-memory `list`에 이벤트를 두어 프로토타입에서 append-only
계약(불변식 §3-3)을 구형했다. 여기서는 그 SoT를 **postgres 16 컨테이너**에 영속화하고,
신규 인스턴스에서 **replay로 동일 materialized graph를 재구축**할 수 있게 한다 (ADR-304).

§7.1 `graph_mutations` 이벤트 계약:
- **Append-only** — 이벤트 수정·삭제 금지. rollback은 역이벤트(delete/supersede/unmerge)로.
- **Replay** — `tx_time`·기록 순서대로 적용 시 동일 결과 (§7.2, blueprint §21-2).
- **Idempotency** — 동일 `idempotency_key` 재수신 시 no-op, 기존 `mutation_id` 반환 (§3-6).
- **merge/unmerge 가역성** — `merge_entity`는 `unmerge`로 rollback 가능해야 함 (precision-first).

이 모듈은 postgres 드라이버(psycopg, pyproject dev 의존성)에만 의존한다. 연결이 없는
환경에서는 테스트가 importorskip으로 전체 skip 되어 기존 스위트 424를 보존한다.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from .identity import new_ulid

# §7.1 op enum — controlled vocabulary.
MUTATION_OPS = {
    "create_node", "create_edge", "merge_entity", "unmerge",
    "supersede", "delete", "quarantine",
}

@dataclass
class Mutation:
    """§7.1 `graph_mutations` 행 — 로그의 불변 append-only 이벤트."""

    mutation_id: str
    idempotency_key: str
    op: str
    doc_id: str
    source_span: tuple[str, int, int]
    payload: dict
    resolution_ref: str | None = None
    actor: str = "pipeline"
    version_tuple: dict = field(default_factory=dict)
    correlation_id: str | None = None
    tx_time: object | None = None


def build_dsn() -> str:
    """postgres 접속 DSN. .env(또는 환경)의 POSTGRES_* 값 사용 (docker-compose 스택).

    `.env`는 gitignore 되며 프로토타입 상위 디렉터리의 `.env`에 로컬 값이 채워져 있다.
    여기서는 환경변수(POSTGRES_HOST/PORT/USER/PASSWORD/DB)를 우선 읽고, 없으면 로컬 기본값.
    """
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    user = os.environ.get("POSTGRES_USER", "citadel")
    password = os.environ.get("POSTGRES_PASSWORD", "citadel-local-pg")
    db = os.environ.get("POSTGRES_DB", "citadel")
    return (
        f"host={host} port={port} dbname={db} "
        f"user={user} password={password}"
    )


def graph_mutations_ddl(table: str = "graph_mutations") -> str:
    """§7.1 `graph_mutations` 스키마 (DDL). 테이블명 주입 격리 테스트용."""
    return (
        f'CREATE TABLE "{table}" ('
        "  mutation_id     varchar PRIMARY KEY,"
        "  idempotency_key varchar UNIQUE NOT NULL,"
        "  op              varchar NOT NULL,"
        "  doc_id          varchar NOT NULL,"
        "  source_json     jsonb NOT NULL,"
        "  payload         jsonb NOT NULL,"
        "  resolution_ref  varchar,"
        "  actor           varchar NOT NULL,"
        "  version_tuple   jsonb NOT NULL,"
        "  correlation_id  varchar,"
        "  tx_time         timestamptz NOT NULL DEFAULT now()"
        ")"
    )


class PostgresMutationLog:
    """append-only `graph_mutations` SoT — postgres 영속 + replay (ADR-304).

    기존 `MutationLog`(in-memory)와 달리 이벤트를 관계형 로그에 기록하며, 동일
    append-only/idempotency 계약을 유지한다. 신규 인스턴스에서 `all_mutations()`로
    기록 순서 재조회(replay)가 가능하다.
    """

    def __init__(self, conn, table: str = "graph_mutations") -> None:
        self._conn = conn
        self._table = table

    def apply(
        self,
        doc_id: str,
        op: str,
        source_span: tuple[str, int, int],
        idempotency_key: str,
        payload: dict | None = None,
        resolution_ref: str | None = None,
        actor: str = "pipeline",
        version_tuple: dict | None = None,
        correlation_id: str | None = None,
    ) -> str:
        """mutation 적용. 동일 idempotency_key 재수신 시 no-op, 기존 id 반환 (§3-6).

        append-only: 기존 이벤트는 수정·삭제하지 않는다. payload는 jsonb에 저장.
        """
        if op not in MUTATION_OPS:
            raise ValueError(f"알 수 없는 op: {op} (허용: {sorted(MUTATION_OPS)})")

        # idempotency — 동일 key 재수신 no-op (ON CONFLICT DO NOTHING).
        mutation_id = new_ulid("mut")
        cur = self._conn.cursor()
        cur.execute(
            f"""
            INSERT INTO "{self._table}"
              (mutation_id, idempotency_key, op, doc_id, source_json, payload,
               resolution_ref, actor, version_tuple, correlation_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (idempotency_key) DO NOTHING
            """,
            (
                mutation_id,
                idempotency_key,
                op,
                doc_id,
                json.dumps(list(source_span)),
                json.dumps(payload or {}),
                resolution_ref,
                actor,
                json.dumps(version_tuple or {}),
                correlation_id,
            ),
        )
        if cur.rowcount == 0:
            # 이미 존재하는 key — 기존 mutation_id 반환 (no-op).
            cur.execute(
                f'SELECT mutation_id FROM "{self._table}" WHERE idempotency_key = %s',
                (idempotency_key,),
            )
            (existing_id,) = cur.fetchone()
            return existing_id
        return mutation_id

    def all_mutations(self) -> list[Mutation]:
        """기록 순서대로 전체 이벤트 재조회 — replay (ADR-304)."""
        cur = self._conn.cursor()
        cur.execute(
            f"""
            SELECT mutation_id, idempotency_key, op, doc_id, source_json, payload,
                   resolution_ref, actor, version_tuple, correlation_id, tx_time
            FROM "{self._table}"
            ORDER BY tx_time, mutation_id
            """
        )
        rows = cur.fetchall()
        return [
            Mutation(
                mutation_id=r[0],
                idempotency_key=r[1],
                op=r[2],
                doc_id=r[3],
                source_span=tuple(r[4]),
                payload=r[5],
                resolution_ref=r[6],
                actor=r[7],
                version_tuple=r[8],
                correlation_id=r[9],
                tx_time=r[10],
            )
            for r in rows
        ]
