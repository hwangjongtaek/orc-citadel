"""S16 Graph Service — Applier(replay) (설계 06 §3, 03 §7).

graph_mutations 이벤트를 **순서대로** 소비해 authoritative 노드-엣지 그래프를
재구축한다 (불변식 §3-3 append-only replay). 그래프의 유일한 쓰기 경로.

- idempotency (§3.1): 적용한 idempotency_key 기록, 중복 no-op (03 §7.2).
- create_node (§3.2): MERGE(id) + 속성 set + 게이트 라벨(:Authoritative).
- create_edge (§3.2): 양끝 노드 존재 확인(reference 무결성, 02 §4-3) → 관계 생성,
  미존재 시 quarantine 사유 기록(엣지 미생성).
- 조회: node(id)/nodes(label)/neighbors(id)/edge_count.
물리 Neo4j 아님 — prototype은 자체 in-memory 그래프. merge/unmerge/supersede/
delete(§3.2) · bitemporal AS-OF(§8)는 후속.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Node:
    id: str
    props: dict = field(default_factory=dict)
    label: str = "Authoritative"  # 게이트 라벨 (§3.2)


@dataclass
class Edge:
    edge_id: str
    etype: str
    fro: str
    to: str
    props: dict = field(default_factory=dict)


class GraphService:
    """append-only mutation 이벤트 → materialized graph 재구축 + 조회."""

    def __init__(self) -> None:
        self._nodes: dict[str, Node] = {}
        self._edges: list[Edge] = []
        self._applied: set[str] = set()  # idempotency_key (불변식 §3-6)
        self._edge_seq = 0
        self._quarantined_edges: list[dict] = []

    def apply(self, events: list[dict]) -> None:
        """이벤트를 순서대로 적용 (재구축). idempotent."""
        for evt in events:
            key = evt.get("idempotency_key", "")
            if key in self._applied:
                continue  # §3.1 no-op
            op = evt.get("op")
            payload = evt.get("payload", {})
            if op == "create_node":
                self._apply_create_node(payload)
            elif op == "create_edge":
                self._apply_create_edge(payload)
            else:
                continue  # 미지원 op는 무시 (후속: merge/supersede/...)
            self._applied.add(key)

    def _apply_create_node(self, payload: dict) -> None:
        nid = payload.get("id")
        if not nid:
            return
        if nid in self._nodes:
            self._nodes[nid].props.update(payload.get("props", {}))
        else:
            self._nodes[nid] = Node(id=nid, props=payload.get("props", {}))

    def _apply_create_edge(self, payload: dict) -> None:
        etype = payload.get("type")
        fro, to = payload.get("from"), payload.get("to")
        # reference 무결성 (02 §4-3) — 미존재 노드 참조는 quarantine, 엣지 미생성.
        if fro not in self._nodes or to not in self._nodes:
            self._quarantined_edges.append({"type": etype, "from": fro, "to": to,
                                            "reason": "dangling_ref"})
            return
        self._edge_seq += 1
        self._edges.append(Edge(
            edge_id=f"edge-{self._edge_seq:04d}", etype=etype, fro=fro, to=to,
            props=payload.get("props", {}),
        ))

    # --- 조회 ---------------------------------------------------------------

    def node(self, node_id: str) -> dict | None:
        n = self._nodes.get(node_id)
        return {"id": n.id, **n.props, "label": n.label} if n else None

    def nodes(self, label: str | None = None) -> list[dict]:
        out = [{"id": n.id, **n.props, "label": n.label} for n in self._nodes.values()]
        if label is not None:
            out = [n for n in out if n["label"] == label]
        return out

    def neighbors(self, node_id: str) -> list[dict]:
        nbrs = []
        for e in self._edges:
            if e.fro == node_id:
                nbrs.append({"id": e.to, "type": e.etype})
            elif e.to == node_id:
                nbrs.append({"id": e.fro, "type": e.etype})
        return nbrs

    def edge_count(self, node_id: str) -> int:
        return sum(1 for e in self._edges if e.fro == node_id or e.to == node_id)

    def edges(self) -> list[dict]:
        return [{"edge_id": e.edge_id, "type": e.etype, "from": e.fro, "to": e.to}
                for e in self._edges]

    def quarantined_edges(self) -> list[dict]:
        return list(self._quarantined_edges)
