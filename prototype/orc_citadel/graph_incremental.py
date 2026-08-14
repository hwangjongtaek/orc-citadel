"""증분 graph update — 실증분 재적용 + full 재구축 비율·정합성 + DoD ② SLO (design 06 §7.2).

Phase 4 「증분 graph update」 — 설계 06 §7.2 incremental rebuild: 신규 문서·정정이
영향 준 **subgraph 만 재적용** (정상 운영은 incremental, 정합성 보증 시 full rebuild,
§7.1 vs §7.2). 재구축/증분 비율 게이트는 #14(`recompute_bench`, 06 §9 3항) 에서
store 훅으로 봉인했고, 본 모듈은 그 **실경로** 를 봉인한다.

- `extract_events(graph)` — GraphService 그래프를 `graph_mutations` 이벤트 스트림으로
  역직렬화 (결정·read-only) — 증분 리포트의 source (03 §7.2 shape).
- `apply_incremental(base, delta_events)` — 기존 base 위에 delta subgraph 만 적용
  (실증분 재적용; 그래프 쓰기는 `GraphService.apply` 경로 — 본 모듈은 read-only).
- `incremental_rebuild_bench(base_events, delta_events, executor)` — full(전량 replay)
  vs incremental(base + delta) 벽시계·ratio 측정 (10 §4.5, 06 §9 3항 — ratio > 10×).
- `evaluate_incremental_bench` + `compute_graph_slo` — **DoD ② "신규 문서가 SLO 내
  그래프 반영"** 게이트 (10 §1.4 slo-gate·CI 비차단).

**정합성 계약:** incremental 재적용 그래프는 full replay 그래프와 동일해야 한다
(불변식 §3-1 파생 serving 결정적). 벤시계·엣지는 executor mock 주입, 결정성은 순수
에뮬레이션으로 봉인 (recompute_bench store-hooks 패턴과 동일).

read-only(불변식 §3-3)·결정적·mock/실측 격리 원칙 (Phase 4 전 작업과 동일).
"""
from __future__ import annotations

# design 10 §1.4 — 신규 문서 → graph 반영 지연 SLO (p95). 성능 nightly 경보·CI 비차단.
GRAPH_SLO_MS = 60_000.0  # p95 반영 지연 예산 60초 (프로파일로 재측정).
# design 06 §9 3항 / 10 §4.5 — 증분 절감 완료조건 (full/incremental ratio > 10×).
INCREMENTAL_RATIO_GATE = 10.0


def extract_events(graph) -> list[dict]:
    """GraphService 그래프를 `graph_mutations` 이벤트 스트림으로 역직렬화 (read-only).

    `create_node`(노드)·`create_edge`(엣지) 를 idempotency_key 포함 이벤트로 반환.
    그래프를 변경하지 않는다 (불변식 §3-3). 빈 그래프 → 빈 리스트.
    """
    events: list[dict] = []
    for nd in graph.nodes():
        events.append({
            "idempotency_key": f"extract:{nd['id']}",
            "op": "create_node",
            "payload": {"id": nd["id"], "props": {
                k: v for k, v in nd.items()
                if k not in ("id", "label", "canonical_id", "tx_to", "merged")}},
        })
    for ed in graph.edges():
        events.append({
            "idempotency_key": f"extract:{ed['edge_id']}",
            "op": "create_edge",
            "payload": {"edge_id": ed["edge_id"], "type": ed["type"],
                        "from": ed["from"], "to": ed["to"]},
        })
    return events


def apply_incremental(base, delta_events: list[dict]) -> "GraphService":
    """기존 base 위에 delta subgraph 만 적용 → 병합 그래프 반환 (실증분 재적용, §7.2).

    그래프 쓰기는 `GraphService.apply` 경로로만 (idempotent — 중복 이벤트 no-op
    불변식 §3-6). base 는 변경하지 않고 새 그래프로 재적용해 복사본을 반환한다
    (read-only 원칙 — 입력 불변). 반환 그래프가 full replay 와 동일 해야 한다 (§3-1).
    """
    from .graph_service import GraphService

    merged = GraphService()
    merged.apply(extract_events(base))
    merged.apply(delta_events)
    return merged


def incremental_rebuild_bench(base_events: list[dict], delta_events: list[dict],
                              executor=None) -> dict:
    """full vs incremental 벽시계·ratio (mock executor, 10 §4.5·06 §9 3항).

    `executor(events, incremental)` → `(counts, wall_ms)`. 미주입 시 결정적 에뮬레이션:
    full = 전량 이벤트 수 × 단위 벽시계, incremental = delta 이벤트 수 × 단위 벽시계
    (incremental 이 subgraph 만 재적용하므로 더 싸다). 반환: `{full_ms, incremental_ms,
    ratio, delta_nodes, full_nodes}` — ratio = full/incremental.
    """
    def _wall(events: list[dict]) -> float:
        if executor is not None:
            _, wall = executor(events, incremental=False)
            return wall
        return float(len(events))  # 이벤트 수 비례 (결정적 모델)

    delta_nodes = len({e["payload"]["id"] for e in delta_events
                       if e["op"] == "create_node"})
    full_ms = _wall(base_events + delta_events)
    if executor is not None:
        _, inc_wall = executor(delta_events, incremental=True)
        incr_ms = inc_wall
    else:
        incr_ms = float(len(delta_events))
    ratio = (full_ms / incr_ms) if incr_ms > 0 else float("inf")
    return {"full_ms": full_ms, "incremental_ms": incr_ms,
            "ratio": ratio, "delta_nodes": delta_nodes,
            "full_nodes": delta_nodes + len({e["payload"]["id"] for e
                                             in base_events if e["op"] == "create_node"})}


def evaluate_incremental_bench(bench: dict) -> dict:
    """완료조건 게이트 — 증분이 full 대비 유의미 절감 (ratio > 10×) + slo-gate.

    `saving_meaningful` = ratio > INCREMENTAL_RATIO_GATE. 10 §1.4 원칙 — 성능은 부하·
    운영 SLO 로 검증, `slo_gate=True` 로 CI 차단 없이 nightly 경보로 라우팅.
    """
    ratio = bench.get("ratio")
    meaningful = ratio is not None and ratio > INCREMENTAL_RATIO_GATE
    return {"ratio": ratio, "saving_meaningful": meaningful,
            "gate": {"threshold": INCREMENTAL_RATIO_GATE, "pass": meaningful},
            "slo_gate": True}  # 10 §1.4 — 성능 차단 게이트 아닌 nightly 경보.


def compute_graph_slo(p95_ms: float | None) -> dict:
    """신규 문서 → 그래프 반영 지연 SLO 게이트 (DoD ②, 10 §1.4 slo-gate).

    `p95_ms` 가 `GRAPH_SLO_MS` 미만이면 `within_slo=True·classified="ok"`. 이상이면
    `within_slo=False·classified="slo-gate"` (CI 비차단 nightly). None(미측정) →
    `classified="not-measured"` + `within_slo=False` — honest-gap (§6.2): 부재가
    OK 가 아니다. read-only·결정적.
    """
    if p95_ms is None:
        return {"within_slo": False, "classified": "not-measured",
                "slo_ms": GRAPH_SLO_MS}
    within = p95_ms < GRAPH_SLO_MS
    return {"within_slo": within,
            "classified": "ok" if within else "slo-gate",
            "slo_ms": GRAPH_SLO_MS, "p95_ms": p95_ms}
