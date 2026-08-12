"""실신호 본문 Q4 재현 러너 — 전용 반도체 언론 본문 → SoT → replay → Neo4j → Q4 (design 06 §9).

결정적 extractor 가 arXiv abstract 에서 신호가 희소(edges=0)하므로, Q4 판정의 실신호
재료는 **전용 반도체/공급망 언론 본문**(nvidianews·semiengineering RSS)에 집중한다
(메모리 확증). 본 모듈은 그 실신호 본문 소스를 선택해, 결정적 파이프라인 → postgres
`graph_mutations` SoT → 로그 **replay** → 가동 Neo4j 적재·Q4 실측을 **재현 가능**하게
오케스트레이션한다 (ADR-304/601/602 — SoT=로그·그래프=파생·조립은 조합으로 격리).

각 단계 로직(파이프라인·재생·Neo4j store·Q4 하니스)은 이미 단위검증. 본 모듈은 **실신호
소스 선택**과 그 **조합 실행** 만 담는다. 저장소/연결은 주입·격리, 미가동 시 skip.
"""

SIGNAL_SOURCE_IDS = ("official-nvidia-news", "press-semiengineering")
"""실신호가 집중된 전용 반도체/공급망 언론 raw 소스 id (메모리 확증)."""


def select_signal_metas(metas: list[dict]) -> list[dict]:
    """`metas` 중 실신호 소스(전용 반도체/공급망 언론 본문) 만 선택.

    파이프라인 입력 meta list({source_id, url, doc_id, content}) 에서
    `SIGNAL_SOURCE_IDS` 에 속한 것만 남긴다 — arXiv abstract(신호 0) 등 비신호 소스 제외.
    """
    allowed = set(SIGNAL_SOURCE_IDS)
    return [m for m in metas if m.get("source_id") in allowed]


def run_signal_q4(metas, zone_path=":memory:", mutation_log=None):
    """실신호 본문 metas 를 파이프라인→SoT→replay→Q4 로 흘린다 (재현 러너).

    - `metas`: 실행할 raw meta list (소스 선택은 호출자/CLI 가 `select_signal_metas` 로).
    - `zone_path`: curated zone 저장 경로 (기본 in-memory).
    - `mutation_log`: postgres SoT(①). 미제공 시 SoT 미사용(빈 replay, ADR-304 계약).
    - 반환 `(PipelineResult, GraphService)`: 여기서 그래프는 **로그 replay** 로 재구축된
      authoritative 그래프 (실신호 엣지 포함).
    - 빈 그래프(신호 0) 는 Q4 실측을 건너뛰고 빈 dict — 노이즈 없는 명시적 분기.
    """
    from orc_citadel.curated_zone import CuratedZone
    from orc_citadel.graph_replay import replay_graph
    from orc_citadel.pipeline_bulk_driver import bulk_pipeline

    zone = CuratedZone(zone_path)
    zone.initialize()
    result, _g = bulk_pipeline(metas, zone=zone, mutation_log=mutation_log)

    # authoritative 그래프 — 로그 replay (ADR-304). SoT 미제공 시 빈 로그 replay.
    mutations = mutation_log.all_mutations() if mutation_log is not None else []
    graph = replay_graph(mutations)

    if not graph.nodes():
        return result, graph  # Q4 실측 skip — 호출자가 {} dict 여부로 분기할 수 있게.
    return result, graph


def load_q4_report(graph, store, sample_k: int = 200) -> dict:
    """실신호 `graph` 를 Neo4j 에 적재하고 Q4 지표(p95)를 실측·반환.

    graph 가 비어 있으면 빈 dict (실측 없음). 키: load_ms·node_count·edge_count·
    p95_ms·n_queries. 조립은 pipeline_bulk_driver.load_and_measure_neo4j 에 위임.
    """
    from orc_citadel.pipeline_bulk_driver import load_and_measure_neo4j

    return load_and_measure_neo4j(graph, store, sample_k=sample_k)


def main() -> None:
    """CLI — 로컬 raw 의 실신호 본문 소스 전체를 실행·Q4 실측·요약 출력.

    재현 경로: `select_signal_metas`(load_raw_zone 결과) → postgres SoT → replay →
    Neo4j 적재·Q4. postgres/Neo4j 는 활성 시 실측, 미가동/빈 그래프는 요약에 기재.
    """
    import json
    import pathlib
    import time

    from orc_citadel.curated_zone import CuratedZone
    from orc_citadel.load_raw_zone import load_raw_zone
    from orc_citadel.neo4j_graph_store import Neo4jGraphStore

    RAW = pathlib.Path(__file__).resolve().parent.parent / "data" / "raw"
    _store, metas = load_raw_zone(RAW)
    signal = select_signal_metas(metas)
    print(f"[signal_source_runner] 실신호 본문 소스 {len(signal)}건 "
          f"({len(metas)} raw 중) — 선택 {SIGNAL_SOURCE_IDS}")
    if not signal:
        raise SystemExit("실신호 본문 소스 없음 — 전용 반도체 언론 RSS 수집 필요")

    # postgres SoT — 활성 시 isolated 테이블로 실행 (기존 로그 훼손 방지).
    try:
        import psycopg

        from orc_citadel.postgres_mutation_log import (
            PostgresMutationLog, build_dsn, graph_mutations_ddl,
        )

        conn = psycopg.connect(build_dsn())
        conn.autocommit = True
        table = "graph_mutations_signal_run"
        cur = conn.cursor()
        cur.execute(f'DROP TABLE IF EXISTS "{table}"')
        cur.execute(graph_mutations_ddl(table))
        log = PostgresMutationLog(conn, table=table)
    except Exception as exc:  # 오프라인/드라이버 부재 — SoT 없이 재현 불가하므로 중단.
        log = None
        print(f"  [SoT] postgres 연결 불가: {exc} — 그래프 재현(ADR-304) 위해 SoT 필요")

    from orc_citadel.curated_zone import CuratedZone

    begun = time.perf_counter()
    result, graph = run_signal_q4(signal, zone_path=":memory:", mutation_log=log)
    wall = round((time.perf_counter() - begun) * 1000, 1)

    print(f"  파이프라인: docs={result.docs} claims={result.claims} "
          f"promoted={result.promoted_claims} conflicts={result.conflicts} "
          f"wall={wall}ms")
    print(f"  그래프(replay): nodes={len(graph.nodes())} edges={len(graph.edges())} "
          f"quarantined={len(graph.quarantined_edges())}")

    if not graph.nodes():
        print("  Q4: 빈 그래프 — 실측 skip")
        return
    store = Neo4jGraphStore()
    report = load_q4_report(graph, store)
    print("  Q4(실신호, 가동 Neo4j): " + json.dumps(report, ensure_ascii=False))
    from orc_citadel.neo4j_q4_harness import evaluate_q4
    taken = {"nodes": report["node_count"], "p95_ms": report["p95_ms"],
             "rebuild_ratio": 0.0}
    verdict = evaluate_q4(taken)
    print(f"  Q4 판정: tripped={verdict['tripped']} reasons={verdict.get('reasons')}")


if __name__ == "__main__":
    main()
