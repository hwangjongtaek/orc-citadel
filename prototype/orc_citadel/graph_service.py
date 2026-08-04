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
            res = evt.get("resolution_ref")
            if op == "create_node":
                self._apply_create_node(payload)
            elif op == "create_edge":
                self._apply_create_edge(payload)
            elif op == "merge_entity":
                self._apply_merge(payload, res)
            elif op == "unmerge":
                self._apply_unmerge(payload, res)
            elif op == "supersede":
                self._apply_supersede(payload)
            else:
                continue  # 미지원 op는 무시 (delete는 후속)
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

    def _apply_merge(self, payload: dict, res: str | None) -> None:
        """merge_entity — SAME_AS 동치류 collapse + canonical 대표 (06 §5.1).

        member→canonical `SAME_AS` 엣지 + member.canonical_id + :Merged.
        양쪽 노드 미존재 시 quarantine(오병합/미존재; 02 §4-3).
        """
        member, canonical = payload.get("member"), payload.get("canonical")
        if member not in self._nodes or canonical not in self._nodes:
            self._quarantined_edges.append(
                {"type": "SAME_AS", "from": member, "to": canonical,
                 "reason": "merge_missing_node"})
            return
        n = self._nodes[member]
        n.props["canonical_id"] = canonical
        n.props["merged"] = True
        self._edge_seq += 1
        self._edges.append(Edge(
            edge_id=f"edge-{self._edge_seq:04d}", etype="SAME_AS",
            fro=member, to=canonical,
            props={"resolution_ref": res or "", "decided_by": payload.get("actor", "pipeline")},
        ))

    def _apply_unmerge(self, payload: dict, res: str | None) -> None:
        """unmerge — merge_entity 역연산 (06 §5.3): SAME_AS 제거·canonical 원복.

        resolution_ref로 대상 병합을 특정해 제거 (오병합 복구, 실행 가역).
        """
        member, canonical = payload.get("member"), payload.get("canonical")
        if member not in self._nodes:
            return
        # resolution_ref(있으면)로 매칭되는 SAME_AS 엣지 제거.
        def _matches(e):
            same_direction = e.fro == member and e.to == canonical
            if res and e.etype == "SAME_AS":
                return same_direction and e.props.get("resolution_ref") == res
            return same_direction
        self._edges = [e for e in self._edges if not _matches(e)]
        n = self._nodes[member]
        if not any(e.fro == member and e.etype == "SAME_AS" for e in self._edges):
            n.props.pop("canonical_id", None)
            n.props.pop("merged", None)
            n.props["merged"] = False

    def _apply_supersede(self, payload: dict) -> None:
        """supersede — 신버전 SUPERSEDES 구버전 + 구버전 tx_to close (06 §6).

        구버전은 그래프에 남되 '현재 아님'(tx_to close); 신버전은 tx_to null 유지.
        """
        new_id, old_id = payload.get("new_id"), payload.get("superseded_id")
        at, reason = payload.get("superseded_at"), payload.get("reason", "")
        if new_id in self._nodes and old_id in self._nodes:
            self._edge_seq += 1
            self._edges.append(Edge(
                edge_id=f"edge-{self._edge_seq:04d}", etype="SUPERSEDES",
                fro=new_id, to=old_id, props={"reason": reason, "superseded_at": at},
            ))
            self._nodes[old_id].props["tx_to"] = at
        # 신버전 tx_to는 기본 null (현재 버전).

    def as_of(self, claim: str | None = None, valid_at: str | None = None) -> dict | None:
        """bitemporal AS-OF 질의 (03 §6.3).

        - transaction: tx_to=null인 '현재' 버전만. (필터: claim prop)
        - valid: 유효한 유효시간(valid_from ≤ T_v < valid_to, open 상한 허용).
        최신 버전 1개 반환.
        """
        candidates = []
        for n in self._nodes.values():
            nv = {"id": n.id, **n.props}
            if claim is not None and nv.get("claim") != claim:
                continue
            if nv.get("tx_to") is not None:
                continue  # transaction AS-OF: 현재 버전만
            if valid_at is not None:
                vf, vt = nv.get("valid_from"), nv.get("valid_to")
                if vf is not None and valid_at < vf:
                    continue
                if vt is not None and valid_at >= vt:
                    continue
            candidates.append(nv)
        return candidates[0] if candidates else None

    # --- 조회 ---------------------------------------------------------------

    def node(self, node_id: str) -> dict | None:
        n = self._nodes.get(node_id)
        if n is None:
            return None
        # 스키마 일관성: canonical/버전/merge 키는 디폴트를 항상 노출.
        return {
            "id": n.id, **n.props, "label": n.label,
            "canonical_id": n.props.get("canonical_id"),
            "tx_to": n.props.get("tx_to"),
            "merged": n.props.get("merged", False),
        }

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
