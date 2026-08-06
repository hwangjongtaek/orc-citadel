"""S28 API/출력 계층 — 검색 가능한 소비 카탈로그 (설계 09 §1.4·§2.2).

파이프라인 산출(어세션·그래프)을 **read-only** 쿼리 계층으로 노출한다 (불변식 §3-3,
그래프 직접 write 금지, 09 §2.2 — 그래프 변경은 mutation 이벤트로만, API는 조회 전용).

- `Catalog.assertions(...)` — 어세션 카탈로그: 필터(subject/predicate) + **cursor
  페이지네이션**(09 §1.4, opaque cursor, 마지막 어세션 위치 인코딩) + 선택적 time-travel
  (as_of, 09 §2.2 — assertions_as_of 재사용).
- `CatalogGraph` — 그래프 카탈로그(06 §8, S25/S26 재사용): 노드/이웃/조사 subgraph.
  read-only — mutation API 미노출 (불변식 §3-3).

소비 형식: `{items:[...], page:{next_cursor, limit}}` (09 §1.4).
"""
from __future__ import annotations

from .curated_zone import CuratedZone
from .graph_service import GraphService


class Catalog:
    """어세션 중심 소비 카탈로그 — cursor 페이지된 조회."""

    def __init__(self, zone: CuratedZone) -> None:
        self._zone = zone

    def assertions(self, subject_id: str | None = None,
                   predicate: str | None = None, as_of_tx=None, as_of_valid=None,
                   limit: int = 50, cursor: str | None = None) -> dict:
        """어세션 질의 — 필터 + cursor 페이지네이션 (09 §1.4).

        - 필터: subject_id / predicate (AND). as_of_tx/valid 지정 시 time-travel
          (assertions_as_of 재사용, 09 §2.2 — time-travel 함수는 AS-OF 양축 필터).
        - cursor: opaque 토큰 — 마지막 반환 어세션의 assertion_id 를 URL-safe 인코딩.
          ULID 시간정렬 축 위 고정 정렬(assertion_id asc)의 위치만 인코딩 (09 §1.4).
        - 반환: {items:[...], page:{next_cursor, limit}} — next_cursor=null 이면 마지막.
        """
        # time-travel 지정 시 AS-OF 양축 재사용, 아니면 전체 현재 어세션.
        if as_of_tx is not None or as_of_valid is not None:
            rows = self._zone.assertions_as_of(valid_at=as_of_valid, tx_at=as_of_tx)
        else:
            rows = self._zone.assertions_as_of()  # 현재(tx_to null).

        # 필터 (AND).
        if subject_id is not None:
            rows = [r for r in rows if r["subject_id"] == subject_id]
        if predicate is not None:
            rows = [r for r in rows if r["predicate"] == predicate]

        # 고정 정렬 축: assertion_id (ULID 시간정렬, 09 §1.4). 결정적.
        rows.sort(key=lambda r: r["assertion_id"])

        # cursor 재개 — 마지막으로 본 assertion_id 이후부터.
        start = 0
        if cursor is not None:
            for i, r in enumerate(rows):
                if r["assertion_id"] > _decode_cursor(cursor):
                    start = i
                    break
        page = rows[start:start + limit]
        has_more = start + limit < len(rows)
        return {
            "items": page,
            "page": {
                "next_cursor": _encode_cursor(page[-1]["assertion_id"]) if has_more
                else None,
                "limit": limit,
            },
        }


class CatalogGraph:
    """그래프 카탈로그 — read-only 조회 (06 §8, S25/S26 재사용).

    create_node/create_edge 등 mutation API를 **노출하지 않는다** (불변식 §3-3 —
    그래프 변경은 mutation 이벤트 소비(Applier)로만, 09 §2.2 read-only).
    """

    def __init__(self, graph: GraphService) -> None:
        self._graph = graph

    def node(self, node_id: str) -> dict | None:
        return self._graph.node(node_id)

    def nodes(self, label: str | None = None) -> list[dict]:
        return self._graph.nodes(label=label)

    def neighbors(self, node_id: str) -> list[dict]:
        return self._graph.neighbors(node_id)

    def investigation_subgraph(self, seed: str, hops: int = 1, limit: int = 100,
                               include: str | None = None) -> dict:
        return self._graph.investigation_subgraph(seed, hops=hops, limit=limit,
                                                  include=include)


def _encode_cursor(assertion_id: str) -> str:
    """opaque cursor — assertion_id(ascii)를 hex 인코딩 (클라이언트 미파싱, 09 §1.4)."""
    return assertion_id.encode("ascii").hex()


def _decode_cursor(cursor: str) -> str:
    """opaque cursor 복호 — last_seen assertion_id."""
    try:
        return bytes.fromhex(cursor).decode("ascii")
    except (ValueError, UnicodeDecodeError):
        return ""
