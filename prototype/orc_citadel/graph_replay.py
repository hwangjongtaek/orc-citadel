"""P1 저장 계층 키스톤 ⑤ — postgres SoT 로그 재생 → 그래프 재구축 (ADR-304).

`PostgresMutationLog`(①)가 영속한 append-only `graph_mutations` SoT 를 `GraphService`
(Applier/replay, design 06 §3)로 **순서대로 재생**해 동일 materialized graph 를 재구축한다
(불변식 §3-3, blueprint §21-2: "graph_mutations 를 순서대로 적용하면 동일 그래프").

payload 는 jsonb 로 원형 보존되므로 재생 시 그대로 전달한다. GraphService.apply 는
`idempotency_key` 를 기록해 중복(불변식 §3-6)과 미지원 op 를 무시한다.

이 모듈은 순수 변환/재생 — db 연결·GraphService 를 조합만 한다.
"""
from __future__ import annotations

from datetime import datetime

from .graph_service import GraphService
from .postgres_mutation_log import Mutation


def events_from_mutations(mutations: list[Mutation]) -> list[dict]:
    """postgres Mutation → GraphService.apply 이벤트 dict 변환 (payload 원형 전달).

    GraphService.apply 가 읽는 필드(idempotency_key, op, payload, resolution_ref)를
    보존한다. mutation_id 는 디버그 추적용으로 함께 담는다.
    """
    return [
        {
            "mutation_id": m.mutation_id,
            "idempotency_key": m.idempotency_key,
            "op": m.op,
            "payload": m.payload,
            "resolution_ref": m.resolution_ref,
        }
        for m in mutations
    ]


def replay_graph(mutations: list[Mutation]) -> GraphService:
    """postgres `graph_mutations` 로그 → materialized graph 재구축 (ADR-304).

    events 를 기록 순서대로 GraphService 에 적용한다. 반환된 GraphService 는
    authoritative 노드-엣지 그래프의 유일 조회 경로다.
    """
    g = GraphService()
    g.apply(events_from_mutations(mutations))
    return g


def replay_graph_at_tx(mutations: list[Mutation], tx_at: datetime) -> GraphService:
    """time-travel — `tx_at` 이전(포함) 관측 그래프 재현 (03 §6.3, ADR-604).

    `replay_graph`의 transaction-time AS-OF 변형. 관측 시점 `tx_at`까지 기록된
    mutation(`tx_time ≤ tx_at`)만 순서대로 재생해 "그 시점 시스템이 믿던 그래프"를
    재구축한다. superseded/delete 도 로그에 남으므로 과거 시점 상태를 그대로 조회
    (불변식 §3-3: event log 에서 materialized graph 재구축 가능).

    - tx_time 이 없는 mutation 은 항상 포함(현재 그래프와 동일)한다.
    - assertion-축 time-travel(`CuratedZone.assertions_as_of`)과 병행 사용 시
      "특정 관측 시점 기준, 특정 유효 시점" 의 상태를 재현한다 (06 §7.2 계약).
    """
    if tx_at is None:
        # 명시 안 하면 전체 재생 — replay_graph 와 동일.
        return replay_graph(mutations)
    live = [
        m for m in mutations
        if m.tx_time is None or m.tx_time <= tx_at
    ]
    g = GraphService()
    g.apply(events_from_mutations(live))
    return g
