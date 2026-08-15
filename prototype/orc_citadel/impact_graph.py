"""impact graph 부분 재계산 — 영향 하류 재계산 범위 도출·절감 게이트 (design 06 §7.2·§5.2, 10 §4.5, Phase 5).

Phase 5 「impact graph 부분 재계산」 — 엔터티/claim 변경 시 **영향 하류 subgraph 를
도출**해 full 재계산 대신 **부분 재계산만 수행**하도록 범위를 봉인한다.

설계 근거:
- design 06 **§7.2** — 신규 문서·정정이 영향 준 `subgraph 만 재적용`.
- design 06 **§5.2** — 엔터티/claim 재지정은 독립 증거 수·모순 판정에 파급 → 영향
  **subgraph 의 재평가를 트리거**한다 (연결된 증거 클러스터는 상호 영향).
- design 10 **§4.5** — partial recomputation 이 full rebuild 대비 유의미 절감.

프로파게이션 모델: **전파 엣지**(ABOUT/SUPPORTS/CONTRADICTS/SUPERSEDES/SAME_AS) 로
연결된 **연결 클러스터는 상호 영향**(양방향) — 한 원소 변경이 클러스터 전체 재평가로
퍼진다(§5.2 재지정 파급). hops·include_types 로 범위를 한정한다.

원칙 (Phase 4/5 전 작업과 동일):
- **결정적** — 범위·부분 재계산이 순수 그래프 함수.
- **read-only** (불변식 §3-3) — 영향 범위·부분 재계산 이벤트는 **산출물**일 뿐, 실제
  재적용은 `GraphService.apply` 경로만 사용(호출자 몫).
- **honest-gap** (§6.2) — 영향 범위 비어 있음(partial=0) 을 유의미 절감으로 오판하지
  않음 (ratio None + empty_scope).
"""
from __future__ import annotations

# design 06 §7.2·§5.2 — 영향 전파 엣지 (변경이 하류로 퍼지는 관계 타입).
PROPAGATION_TYPES = frozenset(
    {"ABOUT", "SUPPORTS", "CONTRADICTS", "SUPERSEDES", "SAME_AS"})

# design 10 §4.5 / 06 §9 — 부분 재계산 절감 완료조건 (full/partial ratio > gate).
PARTIAL_RATIO_GATE = 5.0


def impact_scope(graph, targets: list[str],
                 hops: int | None = None,
                 include_types: tuple[str, ...] | None = None) -> list[str]:
    """변경 target 에서 도달 가능한 **영향 노드 집합** (read-only·결정적, BFS).

    - 전파 엣지(§7.2·§5.2) 로 연결된 하류를 양방향으로 탐색 — 연결 클러스터는 상호 영향.
    - `hops` 指定 시 그 깊이까지만 (범위 상한), `include_types` 로 전파 엣지 제한.
    - target 미존재·빈 input 은 건너뛰고 반환. 반환 순서는 BFS 도달 순(결정적).
    - 그래프를 변경하지 않는다 (불변식 §3-3).
    """
    if not targets:
        return []
    allowed = set(include_types) if include_types else set(PROPAGATION_TYPES)
    nodes = {n["id"] for n in graph.nodes()}
    visited: list[str] = []
    seen: set[str] = set()
    # 초기 target (존재하는 것만).
    frontier = [t for t in targets if t in nodes]
    for t in frontier:
        seen.add(t)
        visited.append(t)

    # BFS — 양방향 전파 엣지 탐색.
    while frontier and (hops is None or hops > 0):
        if hops is not None:
            hops -= 1
        nxt: list[str] = []
        for cur in frontier:
            for e in graph.edges():
                if e["type"] not in allowed:
                    continue
                nbr = None
                if e["from"] == cur:
                    nbr = e["to"]
                elif e["to"] == cur:
                    nbr = e["from"]
                if nbr is not None and nbr not in seen and nbr in nodes:
                    seen.add(nbr)
                    visited.append(nbr)
                    nxt.append(nbr)
        frontier = nxt
    return visited


def impact_subgraph(graph, targets: list[str],
                    hops: int | None = None,
                    include_types: tuple[str, ...] | None = None) -> dict:
    """영향 범위를 **materialized subgraph** 로 노출 (read-only·결정적).

    반환 `{node_ids, nodes, edges}`:
    - `node_ids` = 영향 노드 (BFS 도달 순), `nodes` = 노드 dict 목록.
    - `edges` = **양끝이 모두 scope 인 내부 엣지만** (부분 재계산 섬 — 경계 엣지 제외).
    - 빈 target → 빈 subgraph.
    """
    scope = impact_scope(graph, targets, hops=hops, include_types=include_types)
    scope_set = set(scope)
    node_map = {n["id"]: n for n in graph.nodes()}
    nodes_out = [node_map[nid] for nid in scope if nid in node_map]
    edges_out = [e for e in graph.edges()
                 if e["from"] in scope_set and e["to"] in scope_set]
    return {"node_ids": scope, "nodes": nodes_out, "edges": edges_out}


def partial_recompute_events(graph, full_events: list[dict],
                             targets: list[str],
                             hops: int | None = None) -> list[dict]:
    """full 이벤트 중 **영향 범위 내 노드·내부 엣지만** 추려 반환 (부분 재계산 집합).

    - 노드 이벤트: scope 에 속한 `create_node` 만.
    - 엣지 이벤트: 양끝이 모두 scope 인 `create_edge` 만.
    - 순서는 full 의 원순서 보존 (노드 먼저 — replay 정합성). read-only·결정적.
    """
    scope = set(impact_scope(graph, targets, hops=hops))
    out = []
    for e in full_events:
        pay = e.get("payload", {})
        if e.get("op") == "create_node":
            if pay.get("id") in scope:
                out.append(e)
        elif e.get("op") == "create_edge":
            if pay.get("from") in scope and pay.get("to") in scope:
                out.append(e)
    return out


def partial_vs_full(graph, full_events: list[dict], targets: list[str],
                    hops: int | None = None) -> dict:
    """full vs partial 이벤트 수·ratio (부분 절감 계량, read-only·결정적).

    - `full_events` = 전체 이벤트 수, `partial_events` = 영향 scope 내 이벤트 수.
    - `ratio` = full/partial. **partial=0** (영향 범위 없음) → ratio None + `empty_scope=True`
      (honest-gap §6.2 — "아무것도 재계산 안 함" 이 유의미 절감의 근거가 아님).
    - full 이벤트 없음 → ratio None (측정 불가).
    """
    partial = partial_recompute_events(graph, full_events, targets, hops=hops)
    full_n = len(full_events)
    part_n = len(partial)
    ratio = (full_n / part_n) if (full_n > 0 and part_n > 0) else None
    return {
        "full_events": full_n,
        "partial_events": part_n,
        "ratio": ratio,
        "empty_scope": full_n > 0 and part_n == 0,
    }


def evaluate_partial_recompute(brief: dict, gate: float = PARTIAL_RATIO_GATE) -> dict:
    """완료조건 게이트 — 부분 재계산이 full 대비 유의미 절감 (ratio > gate) + slo-gate.

    - `ratio > gate` → `saving_meaningful=True` + `classified="slo-gate"` (10 §1.4 —
      성능은 부하·운영 SLO 로 검증, CI 차단 아닌 **nightly 경보** 라우팅).
    - ratio None·empty_scope → `saving_meaningful=False` + `classified="empty-scope"`
      (honest §6.2). ratio ≥ gate 이하 → 절감 미인정 (`classified="no-saving"`).
    """
    ratio = brief.get("ratio")
    if brief.get("empty_scope") or ratio is None:
        return {"ratio": ratio, "saving_meaningful": False,
                "classified": "empty-scope" if brief.get("empty_scope") else "not-measured",
                "gate": gate}
    meaningful = ratio > gate
    return {"ratio": ratio, "saving_meaningful": meaningful,
            "classified": "slo-gate" if meaningful else "no-saving",
            "gate": gate}
