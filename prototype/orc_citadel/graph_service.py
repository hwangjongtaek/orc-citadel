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
            elif op == "delete":
                self._apply_delete(payload)
            else:
                continue  # 미지원 op는 무시
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

    # --- merge 감사·rollback (DoD ②, 06 §5.3) ------------------------------

    def merge_audit(self, entity_id: str) -> dict:
        """특정 entity 의 병합 이력 감사 조회 (read-only, 06 §5.3).

        member→canonical `SAME_AS` 병합 이력 + 현재 rewrite 상태를 노출 — 누가(actor)·
        언제(resolution_ref)·어디로(canonical) 병합했는지 감사 가능하도록. 불변식 §3-3
        조회만 — 그래프 상태를 변경하지 않는다.
        """
        n = self._nodes.get(entity_id)
        if n is None:
            return {"entity_id": entity_id, "canonical_id": None, "merges": []}
        merges = []
        for e in self._edges:
            if e.etype == "SAME_AS" and e.fro == entity_id:
                merges.append({
                    "to": e.to,
                    "resolution_ref": e.props.get("resolution_ref", ""),
                    "decided_by": e.props.get("decided_by", "pipeline"),
                })
        return {
            "entity_id": entity_id,
            "canonical_id": n.props.get("canonical_id"),
            "merged": n.props.get("merged", False),
            "merges": merges,
        }

    def audit_rollback(self, entity_id: str, resolution_ref: str) -> bool:
        """오병합 판정 시 해당 resolution 의 병합을 unmerge 로 revert (06 §5.3).

        감사로 찾은 `resolution_ref` 를 가진 SAME_AS 병합에 대해 canonical 로 unmerge
        역연산을 실행(가역) — 그 뒤 노드는 원래 canonical rewrite 를 잃는다.
        실패(병합 미존재·미매칭 ref) 시 no-op 이고 False 반환 (정확한 복구, ADR-507
        precision-first — 오병합만 revert).
        """
        if entity_id not in self._nodes:
            return False
        for e in self._edges:
            if (e.etype == "SAME_AS" and e.fro == entity_id
                    and e.props.get("resolution_ref") == resolution_ref):
                self._apply_unmerge(
                    {"member": entity_id, "canonical": e.to}, resolution_ref)
                return True
        return False

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

    def _apply_delete(self, payload: dict) -> None:
        """delete — soft delete (06 §3.2·§4.1): :Deleted + deleted_at.

        원장 append-only이므로 물리 삭제 금지 — 노드에 deleted 표시, 엣지 제거.
        기본 조회에서 :Deleted 제외. rollback(역이벤트) 가능 (06 §7.4).
        """
        nid = payload.get("id")
        n = self._nodes.get(nid)
        if n is None:
            return  # 안전 no-op
        n.props["deleted"] = True
        n.props["deleted_at"] = payload.get("deleted_at")
        n.label = "Deleted"
        # 관련 엣지 제거.
        self._edges = [e for e in self._edges if e.fro != nid and e.to != nid]

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

    def restore(self, nodes: list[dict], edges: list[dict],
                quarantined: list[dict]) -> None:
        """저장된 materialized 상태로 그래프 재구축 (03 §7 repload).

        노드/엣지/quarantine을 직접 복원 — merge/supersede 후의 최종 상태 보존.
        """
        self._nodes.clear()
        self._edges.clear()
        self._quarantined_edges.clear()
        for n in nodes:
            nid = n["id"]
            # 저장 상태는 props가 평평화(flattened) → id/label 외 키를 props로.
            props = {k: v for k, v in n.items() if k not in ("id", "label")}
            self._nodes[nid] = Node(
                id=nid, props=props, label=n.get("label", "Authoritative"))
        for e in edges:
            self._edges.append(Edge(
                edge_id=e.get("edge_id", f"edge-{len(self._edges) + 1:04d}"),
                etype=e["type"], fro=e["from"], to=e["to"],
                props=dict(e.get("props", {})),
            ))
        self._quarantined_edges = list(quarantined)

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

    def nodes(self, label: str | None = None,
              include_deleted: bool = False) -> list[dict]:
        out = [{"id": n.id, **n.props, "label": n.label} for n in self._nodes.values()]
        if label is not None:
            out = [n for n in out if n["label"] == label]
        if not include_deleted:
            out = [n for n in out if not n.get("deleted")]  # 06 §4.1 기본 제외
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
        return [{"edge_id": e.edge_id, "type": e.etype, "from": e.fro, "to": e.to,
                 "props": e.props} for e in self._edges]

    def quarantined_edges(self) -> list[dict]:
        return list(self._quarantined_edges)

    # --- Investigation subgraph (06 §8.1·§8.3) -----------------------------

    def _canonical_of(self, node_id: str) -> str | None:
        """SAME_AS 동치류 대표 해석 (이동: member→canonical). 미해석이면 self."""
        node = self._nodes.get(node_id)
        if node is None:
            return None
        seen = set()
        cur = node_id
        while cur in self._nodes:
            n = self._nodes[cur]
            canon = n.props.get("canonical_id")
            if not canon or n.props.get("merged") is not True:
                break
            if canon in seen:  # 사이클 가드
                break
            seen.add(canon)
            cur = canon
        return cur

    def _equivalence_class(self, node_id: str) -> list[str]:
        """SAME_AS*0.. 동치류 전체 (자기 포함, §8.1 view-rewrite fold 대상)."""
        canon = self._canonical_of(node_id) or node_id
        members = []
        for nid, n in self._nodes.items():
            if self._canonical_of(nid) == canon and not n.props.get("deleted"):
                members.append(nid)
        return members

    def investigation_subgraph(self, seed: str, hops: int = 1,
                               limit: int = 100, include: str | None = None) -> dict:
        """Investigation subgraph 조회 (06 §8.1·§8.3).

        - **canonical view-rewrite**(§5.2 필수): seed → canonical 대표, 동치류(SAME_AS*0..)
          전체 fold. merged-away member를 별도 엔터티로 노출하지 않는다.
        - hop 제한 BFS: entity 동치류 → ABOUT claim → (SUPPORTS|CONTRADICTS) evidence.
        - 기본 필터(§4.1): :Authoritative만, :Deleted 제외.
        - 프로그래시브(§8.3): limit 초과 시 `truncated=True` (요약 축약 신호,
          relationship 타입 필터 `include`는 콤마 구분 ABOUT,SUPPORTS,CONTRADICTS).
        """
        include_set = set((include or "").split(",")) if include else None

        def _allowed(etype: str) -> bool:
            return include_set is None or etype in include_set

        # 1) scope 엔터티 동치류 (canonical 후 rewrite).
        canon = self._canonical_of(seed)
        if canon is None:
            return {"entity": None, "claims": [], "evidence": [], "relationships": [],
                    "entities": [], "truncated": False}
        members = self._equivalence_class(seed)

        entity_ids = {canon}          # 노출 entity: canonical 대표만 (§8.1 fold).
        claim_ids: set[str] = set()
        evidence_ids: set[str] = set()
        relationships: list[dict] = []

        def _live(nid: str) -> bool:
            n = self._nodes.get(nid)
            return n is not None and not n.props.get("deleted")

        # 2) 1-hop: 동치류 entity → ABOUT claim.
        member_set = set(members)
        for e in self._edges:
            if not _allowed(e.etype):
                continue
            # direction: (member) --ABOUT--> (claim), 또는 역.
            ent_side, other = None, None
            if e.fro in member_set and e.etype == "ABOUT":
                ent_side, other = e.fro, e.to
            elif e.to in member_set and e.etype == "ABOUT":
                ent_side, other = e.to, e.fro
            if ent_side is None:
                continue
            if other in claim_ids or not _live(other):
                continue
            if len(claim_ids) >= limit:
                break
            claim_ids.add(other)
            relationships.append({"from": ent_side, "to": other, "type": e.etype,
                                  "props": e.props})

        # 3) 2-hop: claim → SUPPORTS|CONTRADICTS evidence.
        for e in self._edges:
            if e.etype not in ("SUPPORTS", "CONTRADICTS") or not _allowed(e.etype):
                continue
            if e.to in claim_ids and _live(e.fro) and e.fro not in evidence_ids:
                evidence_ids.add(e.fro)
                relationships.append({"from": e.fro, "to": e.to, "type": e.etype,
                                      "props": e.props})
            elif e.fro in claim_ids and _live(e.to) and e.to not in evidence_ids:
                evidence_ids.add(e.to)
                relationships.append({"from": e.to, "to": e.fro, "type": e.etype,
                                      "props": e.props})

        truncated = len(claim_ids) >= limit and len(members) + len(claim_ids) > limit

        return {
            "entity": canon,
            "entities": [{"id": cid} for cid in sorted(entity_ids)],
            "claims": [{"id": cid} for cid in sorted(claim_ids)],
            "evidence": [{"id": eid} for eid in sorted(evidence_ids)],
            "relationships": relationships,
            "truncated": truncated,
        }
