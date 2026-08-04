"""S18 그래프 영속 — GraphService 노드·엣지·quarantine을 DuckDB/Parquet에 저장·재구축 (06 §2, 03 §7).

저장 계약은 curated_zone 패턴 재사용 — DuckDB + Parquet export, 결정적 PK, idempotent upsert.
materialized 그래프(노드·엣지·merge/supersede 후 상태)를 영속하고 load로 재구축한다
(replay 대신 저장 스냅샷 — 03 §7 단순화).

- `graph_nodes`   : node_id PK, props(JSON), label — 06 §2 공통 속성.
- `graph_edges`   : edge_id PK, type, from, to, props(JSON) — 관계 타입.
- `graph_quarantine`: edge_id PK, type/from/to, reason.
"""
from __future__ import annotations

import json

import duckdb

from .graph_service import GraphService


class GraphStorage:
    """DuckDB 백엔드 그래프 저장·로드·Parquet."""

    def __init__(self, path: str = ":memory:") -> None:
        self._conn = duckdb.connect(path)

    def initialize(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS graph_nodes (
                node_id VARCHAR PRIMARY KEY,
                props   VARCHAR,
                label   VARCHAR NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS graph_edges (
                edge_id VARCHAR PRIMARY KEY,
                type    VARCHAR NOT NULL,
                from_id VARCHAR NOT NULL,
                to_id   VARCHAR NOT NULL,
                props   VARCHAR
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS graph_quarantine (
                edge_id VARCHAR PRIMARY KEY,
                type    VARCHAR,
                from_id VARCHAR,
                to_id   VARCHAR,
                reason  VARCHAR
            )
            """
        )

    def persist_graph(self, g: GraphService) -> None:
        """GraphService materialized 상태를 영속 (idempotent upsert)."""
        # 노드: node() 는 평평한 dict — id/label 분리, 나머지 props.
        for n in g.nodes():
            node_id = n["id"]
            label = n.get("label", "Authoritative")
            props = {k: v for k, v in n.items() if k not in ("id", "label")}
            self._conn.execute(
                """INSERT INTO graph_nodes (node_id, props, label) VALUES (?, ?, ?)
                   ON CONFLICT (node_id) DO UPDATE SET props=excluded.props,
                   label=excluded.label""",
                [node_id, json.dumps(props, ensure_ascii=False, default=str), label],
            )
        # 엣지.
        for e in g.edges():
            self._conn.execute(
                """INSERT INTO graph_edges (edge_id, type, from_id, to_id, props)
                   VALUES (?, ?, ?, ?, ?) ON CONFLICT (edge_id) DO NOTHING""",
                [e["edge_id"], e["type"], e["from"], e["to"],
                 json.dumps(e.get("props", {}), ensure_ascii=False, default=str)],
            )
        # quarantine.
        for q in (g.quarantined_edges() if hasattr(g, "quarantined_edges") else []):
            self._conn.execute(
                """INSERT INTO graph_quarantine (edge_id, type, from_id, to_id, reason)
                   VALUES (?, ?, ?, ?, ?) ON CONFLICT (edge_id) DO UPDATE SET reason=excluded.reason""",
                [q.get("edge_id", q.get("type", "")), q.get("type"), q.get("from"),
                 q.get("to"), q.get("reason")],
            )

    def load_graph(self) -> GraphService:
        """저장 상태 → GraphService 재구축 (materialized 복원)."""
        g = GraphService()
        nodes = []
        for nid, props, label in self._conn.execute(
                "SELECT node_id, props, label FROM graph_nodes").fetchall():
            p = json.loads(props) if props else {}
            nodes.append({"id": nid, **p, "label": label})
        edges = []
        for eid, etype, fro, to, props in self._conn.execute(
                "SELECT edge_id, type, from_id, to_id, props FROM graph_edges").fetchall():
            edges.append({"edge_id": eid, "type": etype, "from": fro, "to": to,
                          "props": json.loads(props) if props else {}})
        quarantined = [{"edge_id": r[0], "type": r[1], "from": r[2], "to": r[3],
                        "reason": r[4]} for r in self._conn.execute(
                            "SELECT edge_id, type, from_id, to_id, reason "
                            "FROM graph_quarantine").fetchall()]
        g.restore(nodes, edges, quarantined)
        return g

    def nodes(self) -> list[dict]:
        return [{"id": r[0], "label": r[2]} for r in self._conn.execute(
            "SELECT node_id, props, label FROM graph_nodes").fetchall()]

    def edges(self) -> list[dict]:
        return [{"edge_id": r[0], "type": r[1], "from": r[2], "to": r[3]} for r in
                self._conn.execute(
                    "SELECT edge_id, type, from_id, to_id FROM graph_edges").fetchall()]

    def export_parquet(self, out_dir: str) -> None:
        import pathlib

        p = pathlib.Path(out_dir)
        p.mkdir(parents=True, exist_ok=True)
        self._conn.execute(f"COPY graph_nodes TO '{p / 'graph_nodes.parquet'}' (FORMAT PARQUET)")
        self._conn.execute(f"COPY graph_edges TO '{p / 'graph_edges.parquet'}' (FORMAT PARQUET)")

    def close(self) -> None:
        self._conn.close()
