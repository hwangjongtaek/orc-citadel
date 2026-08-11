"""P1 저장 계층 키스톤 ⑤ — postgres SoT 로그 재생 → 그래프 재구축 (ADR-304).

`PostgresMutationLog`(①)가 영속한 append-only `graph_mutations` SoT 를 `GraphService`
(Applier/replay, design 06 §3)로 **순서대로 재생**해 동일 materialized graph 를 재구축한다
(불변식 §3-3, blueprint §21-2: "graph_mutations 를 순서대로 적용하면 동일 그래프").

payload 는 jsonb 로 원형 보존되므로 재생 시 그대로 전달한다. GraphService.apply 는
`idempotency_key` 를 기록해 중복(불변식 §3-6)과 미지원 op 를 무시한다.

이 모듈은 순수 변환/재생 — db 연결·GraphService 를 조합만 한다.
"""
from __future__ import annotations

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
