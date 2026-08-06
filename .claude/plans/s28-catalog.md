# S28 API/출력 계층 — 검색 가능한 소비 카탈로그 (09 §1.4·§2.2)

> 권장안: 파이프라인 산출(어세션·그래프)을 **read-only** 소비 카탈로그로 노출한다.
> cursor 페이지네이션(09 §1.4) + subject/predicate 필터 + time-travel(as_of, §2.2) +
> 그래프 조회(subgraph, 06 §8 재사용).

## 배경·범위

결정적+LLM 파이프라인 결과를 UI·검색이 소비 가능한 형식으로 내보낸다.

| 결정 | 근거 |
| --- | --- |
| `Catalog.assertions(...)` — 필터+**cursor 페이지**+as_of | 09 §1.4(ULID 시간정렬)·§2.2(time-travel) |
| `CatalogGraph` — 노드/이웃/subgraph 재사용 | 06 §8 · S25/S26 |
| **read-only** — mutation API 미노출 | 불변식 §3-3, 09 §2.2 그래프 직접 write 금지 |
| cursor는 opaque(hex 인코딩, 클라이언트 미파싱) | 09 §1.4 |
| 소비 형식 `{items[], page{next_cursor,limit}}` | 09 §1.4 |

## 구현 계획

- **catalog.py**: `Catalog(zone)` — assertions(filters+page+as_of, assertions_as_of 재사용,
  assertion_id 축 고정 정렬, opaque cursor) / `CatalogGraph(graph)` — read-only 조회 래퍼.
- **TDD**: Red→Green — cursor 페이징(다음 위치)·subject/predicate 필터·time-travel
  (미관측 제외)·그래프 조회·read-only(mutation 미노출).
- **Smoke**: 395문서 카탈로그 — 페이지 전체 합계=29, 필터·predicate 분포 확인.

## DoD

- 어세션 카탈로그: cursor 페이지(마지막 next_cursor=null), 필터, as_of time-travel
- 그래프 카탈로그 read-only (apply/create_node 미노출)
- 실데이터 스모크로 소비 형식 확인, 전체 테스트 통과, code-only 커밋

## 한계 (문서화)

- 실제 REST/FastAPI 앱은 후속 — 여기선 계약형 쿼리 계층(facade) 확정
- 페이지네이션의 ULID 역순(최신 우선) 최적화는 수집 ULID 도입 후 — 지금은 asc 고정
