"""time-travel — 그래프 축 transaction-time AS-OF 재현 (design 03 §6.3, ADR-604).

`replay_graph_at_tx`가 `graph_mutations` 로그를 **특정 관측 시점 `tx_at`까지 잘라**
재생해 "그 시점 시스템이 믿던 그래프"(transaction-time AS-OF)를 재구축하는 것을 검증한다.

- assertion-축 time-travel(`CuratedZone.assertions_as_of`·`Catalog.as_of_tx`)은 이미 구현.
- 그래프(노드/엣지) 축은 `replay_graph`가 전부 재생만 하므로, tx 시점까지의 재현 read 경로가
  갭으로 남아 있다(03 §6.3 — "특정 관측 시점 기준, 특정 유효 시점의 상태를 재현", 불변식 §3-3:
  event log에서 materialized graph를 재구축 가능). 본 테스트가 그 read 경로를 TDD로 확정한다.
- superseded/삭제도 삭제하지 않고 로그에 남으므로 과거 시점 그래프가 그대로 조회된다 (§7.2).

순수 in-memory `Mutation`(tx_time 명시)로 필터·재생 로직을 검증 — db 연결 불필요.
"""
from __future__ import annotations

from datetime import datetime, timezone

from orc_citadel.graph_replay import replay_graph_at_tx
from orc_citadel.graph_service import GraphService
from orc_citadel.postgres_mutation_log import Mutation


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def _mut(mid: str, key: str, op: str, payload: dict, tx_time: datetime) -> Mutation:
    return Mutation(
        mutation_id=mid, idempotency_key=key, op=op, doc_id="d",
        source_span=("d#s", 0, 1), payload=payload, resolution_ref=None,
        actor="pipeline", correlation_id="c", tx_time=tx_time,
    )


def _log_with_three_nodes() -> list[Mutation]:
    """t1<t2<t3 간격으로 3개 노드 생성 로그. 시점에 따라 점진 확장되는 그래프."""
    return [
        _mut("mut-1", "k-n1", "create_node", {"id": "org-1", "props": {}},
             tx_time=_dt("2026-01-01T00:00:00")),
        _mut("mut-2", "k-n2", "create_node", {"id": "org-2", "props": {}},
             tx_time=_dt("2026-02-01T00:00:00")),
        _mut("mut-3", "k-e", "create_edge",
             {"type": "DEPENDS_ON", "from": "org-1", "to": "org-2"},
             tx_time=_dt("2026-03-01T00:00:00")),
    ]


def test_replay_at_tx_before_any_is_empty():
    """첫 이벤트 이전 시점 → 빈 그래프 (time-travel 상한 하한)."""
    g = replay_graph_at_tx(_log_with_three_nodes(), _dt("2025-12-01T00:00:00"))
    assert isinstance(g, GraphService)
    assert len(g.nodes()) == 0


def test_replay_at_tx_between_events_replays_observed_slice():
    """T_t=2026-02-15 → org-1/org-2 노드만(엣지는 03월 미관측)."""
    g = replay_graph_at_tx(_log_with_three_nodes(), _dt("2026-02-15T00:00:00"))
    got = {n["id"] for n in g.nodes()}
    assert got == {"org-1", "org-2"}
    assert g.edge_count("org-1") == 0  # DEPENDS_ON(03-01)은 아직 없음


def test_replay_at_tx_after_all_is_full_graph():
    """T_t=2026-04-01 (전부 이후) → 전체 그래프 (현재와 동일)."""
    g = replay_graph_at_tx(_log_with_three_nodes(), _dt("2026-04-01T00:00:00"))
    assert len(g.nodes()) == 2
    assert g.edge_count("org-1") == 1


def test_replay_at_tx_inclusive_tx_time_boundary():
    """T_t=2026-03-01 (엣지의 tx_time과 동일) → 포함 (inclusive 하한 경계)."""
    g = replay_graph_at_tx(_log_with_three_nodes(), _dt("2026-03-01T00:00:00"))
    assert g.edge_count("org-1") == 1


def test_replay_at_tx_invalid_mutations_ignored_after_but_before_not_applied():
    """지원하지 않는 op 는 해당 시점에 포함돼도 무시되고, 이후 아무 영향 없음."""
    log = [
        _mut("mut-1", "k-n1", "create_node", {"id": "org-1", "props": {}},
             tx_time=_dt("2026-01-01T00:00:00")),
        _mut("mut-2", "k-x", "unknown_op", {"id": "org-9", "props": {}},
             tx_time=_dt("2026-02-01T00:00:00")),
    ]
    g = replay_graph_at_tx(log, _dt("2026-03-01T00:00:00"))
    assert {n["id"] for n in g.nodes()} == {"org-1"}
