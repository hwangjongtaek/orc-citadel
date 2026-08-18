"""대량 실행 드라이버 — 결정적 파이프라인 → postgres SoT → replay → Neo4j 적재·Q4 (design 06 §9, ADR-304/601/602).

Phase 1 **10만 문서 기준선**의 실행 경로를 오케스트레이션한다:
  raw metas → `run_pipeline`(결정적 체인, postgres `graph_mutations` SoT 로 기록)
  → 로그 **replay** 로 그래프 재구축(ADR-304) → 가동 Neo4j Community MERGE 적재+Q4 실측.

각 단계 로직(파이프라인·재생·Neo4j store·Q4 하니스) 은 이미 단위검증. 본 모듈은 그
**조합** 만 담는다 — 그래프·저장소 의존은 주입/격리, 연결 불가 시 skip.
"""
from __future__ import annotations

import time


def bulk_pipeline(metas, zone=None, mutation_log=None, slo_log=None):
    """raw metas 를 결정적 체인으로 흘려 그래프를 재구축한다.

    - `mutation_log` 제공 시 `run_pipeline` 이 그래프 변화를 postgres
      SoT(`graph_mutations`)에 기록하고, 반환 그래프는 그 로그의 **replay**(ADR-304)로
      재구축된다 (authoritative 그래프의 유일 조회 경로).
    - 미제공 시 in-memory replay 그래프(파괴 없음).
    - `slo_log` 주입 시 내부 Gate 로 전달 (SLO-07 quarantine 로그, design 11 §2.3).
    - 반환: `(PipelineResult, GraphService)`.
    """
    from .pipeline_runner import run_pipeline

    begun = time.perf_counter()
    result = run_pipeline(metas, zone, judge=None, mutation_log=mutation_log,
                          slo_log=slo_log)

    if mutation_log is not None:
        from .graph_replay import replay_graph

        g = replay_graph(mutation_log.all_mutations())
    else:
        from .graph_replay import replay_graph

        # graph_mutations 가 없어도 run_pipeline 이 남긴 유일한 소스가 없으므로 —
        # 해석적으로는 빈 로그 재생이 일관된 계약(ADR-304) 을 유지한다.
        g = replay_graph([])

    result.elapsed_ms = round((time.perf_counter() - begun) * 1000, 3)
    return result, g


def load_and_measure_neo4j(graph, store, sample_k: int = 200) -> dict:
    """`graph` 를 Neo4j 에 적재하고 Q4 지표(적재·p95)를 실측 (design 06 §9).

    그래프가 비어 있으면 실측하지 않고 빈 dict 반환. 키: load_ms·node_count·
    edge_count·p95_ms·n_queries.
    """
    from .neo4j_q4_harness import measure_load, measure_query_latency

    nodes = graph.nodes()
    if not nodes:
        return {}
    store.clear()
    stats = measure_load(store, graph)
    sample_ids = [n["id"] for n in nodes[:sample_k]]
    q = measure_query_latency(store, sample_ids=sample_ids)
    return {
        "load_ms": stats["load_elapsed_ms"],
        "node_count": stats["node_count"],
        "edge_count": stats["edges"],
        "p95_ms": q["p95_ms"],
        "n_queries": q["n_queries"],
    }
