"""Full rebuild vs partial recomputation benchmark (설계 10 §1.4·§4.5) — read-only.

Phase 4 완료조건 — "증분(partial recomputation)이 full rebuild 대비 유의미 절감".
`neo4j_q4_harness.measure_rebuild`(06 §9 3항 재구축/증분 비율)의 벤치 계약을
**store 측정 훅**으로 추상화해 순수 함수로 계량한다.

- full_vs_incremental(store, base, delta): {full_ms, incremental_ms, ratio}
  — ratio = full/incremental (증분 대비 full 비용 배수, 10 §4.5).
  store 는 측정 훅(`full_rebuild_ms`·`incremental_rebuild_ms`)을 제공 —
  실측(Neo4j load)과 mock(대리 벽시계)을 격리.
- evaluate_recompute_bench(bench): 완료조건 게이트 ratio > REBUILD_RATIO_GATE(10×,
  06 §9 3항) + **slo-gate** 분류(10 §1.4 — 성능 nightly 경보, CI 비차단).

**read-only** (불변식 §3-3): 측정 훅 대조만 — 영속·graph mutation 미노출. 결정적.
"""
from __future__ import annotations

REBUILD_RATIO_GATE = 10.0  # 06 §9 3항 — 재구축/증분 비율 게이트.


def full_vs_incremental(store, base_nodes: int, delta_nodes: int,
                        edges_per_node: int = 3) -> dict:
    """full rebuild vs 증분 partial 재계산 벽시계 비율 (10 §4.5 완료조건).

    `measure_rebuild` 시맨틱 — full(빈 상태 전체) vs incremental(base 위 delta).
    store 가 각 방식의 벽시계를 측정 훅으로 제공 (실측·mock 격리, read-only 대조).
    """
    full_ms = store.full_rebuild_ms(base_nodes, delta_nodes, edges_per_node)
    incr_ms = store.incremental_rebuild_ms(base_nodes, delta_nodes, edges_per_node)
    ratio = (full_ms / incr_ms) if incr_ms > 0 else float("inf")
    return {"full_ms": round(full_ms, 3), "incremental_ms": round(incr_ms, 3),
            "ratio": round(ratio, 3)}


def neo4j_rebuild_bench(store, base_nodes: int, delta_nodes: int,
                        edges_per_node: int = 3) -> dict:
    """가동 Neo4j 실측 벤치 — `measure_rebuild`(06 §9 3항)를 랜핑.

    `full_vs_incremental` 의 store 훅을 실측(Neo4j MERGE 적재 벽시계)으로 충족하는
    adapter. `neo4j_q4_harness.measure_rebuild`(재구축/증분 비율)가 이미 동일
    `{full_ms, incremental_ms, ratio}` 를 산출하므로 이를 그대로 벤치 shape 로 노출.
    가동 Neo4j 가 없으면 오프라인(integration·skip) — 순수 함수 게이트만 단위 봉인.
    """
    from orc_citadel.neo4j_q4_harness import measure_rebuild
    return measure_rebuild(store, base_nodes, delta_nodes,
                           edges_per_node=edges_per_node)


def evaluate_recompute_bench(bench: dict) -> dict:
    """완료조건 게이트 — 증분이 full 대비 유의미 절감 (ratio > 10×) + slo-gate.

    `saving_meaningful` = ratio > REBUILD_RATIO_GATE. 10 §1.4 원칙 — 성능은 부하·
    운영 SLO로 검증, `slo_gate=True` 로 CI 차단 없이 nightly 경보로 라우팅.
    """
    ratio = bench.get("ratio")
    meaningful = ratio is not None and ratio > REBUILD_RATIO_GATE
    return {
        "ratio": ratio,
        "saving_meaningful": meaningful,
        "gate": {"threshold": REBUILD_RATIO_GATE, "pass": meaningful},
        "slo_gate": True,  # 10 §1.4 — 성능 차단 게이트 아닌 nightly 경보.
    }
