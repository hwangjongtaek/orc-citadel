# P1 · 저장 계층 키스톤 ⑤ — postgres SoT 로그 재생 → 그래프 재구축 (ADR-304)

## 배경

저장 계층 키스톤 ①~③ 완료(18b5d0e·19edad2·78244c2):
- ① `PostgresMutationLog` — `graph_mutations`를 postgres에 SoT 영속, replay 조회 가능.
- ② `MinioRawStore` — raw zone 객체 스토어.
- ③ `extraction_records` + provenance 게이트 (ADR-305).

①의 SoT 로그는 영속됐지만 **아무도 소비하지 않는다**. `GraphService`(문서 헤더: Applier/replay, design 06 §3)는
이미 mutation 이벤트 sequence를 순서대로 재생해 authoritative 그래프를 재구축하는 in-memory Applier다.
⑤는 **postgres 로그 → GraphService 재생** 브릿지를 추가해 ADR-304의 DoD("graph_mutations를 순서대로 적용하면
동일 materialized graph 재구축, blueprint §21-2")를 실제로 달성한다.

## 대상 계약

### postgres `Mutation` (①, `postgres_mutation_log.Mutation`)
```python
Mutation(mutation_id, idempotency_key, op, doc_id, source_span, payload,
         resolution_ref, actor, version_tuple, correlation_id, tx_time)
```
`payload` 는 jsonb 로 원형 보존 (그래프 재생에 그대로 사용).

### GraphService.apply(events) — 기대 이벤트 dict
| op | payload 형태 | GraphService 반응 |
| --- | --- | --- |
| `create_node` | `{"id":..., "props":{}}` | 노드 생성/MERGE (§3.2) |
| `create_edge` | `{"type":..., "from":..., "to":...}` | 양끝 존재 시 엣지, 미존재 시 quarantine(dangling_ref) |
| `merge_entity` | `{"member":..., "canonical":...}` | SAME_AS collapse (§6 §5.1) |
| `unmerge` | `{"member":..., "canonical":...}` | 역연산 (§6 §5.3) |
| `supersede` | — | 실행 (후속) |
| `delete` | — | 실행 (후속) |

이벤트 필드: `idempotency_key`, `op`, `payload`, `resolution_ref` (GraphService가 읽음).

## 구현 (TDD)

### 신규 모듈 `graph_replay.py`
```python
def events_from_mutations(mutations: list[Mutation]) -> list[dict]:
    """postgres Mutation → GraphService.apply 이벤트 변환 (payload 원형 전달)."""
    return [{
        "mutation_id": m.mutation_id,
        "idempotency_key": m.idempotency_key,
        "op": m.op,
        "payload": m.payload,
        "resolution_ref": m.resolution_ref,
    } for m in mutations]

def replay_graph(mutations: list[Mutation]) -> GraphService:
    """postgres 로그 → GraphService 재생으로 materialized graph 재구축 (ADR-304)."""
    g = GraphService()
    g.apply(events_from_mutations(mutations))
    return g
```

**Step 1 (Red)** — `tests/test_graph_replay.py`:
- 전용 postgres 테이블명 격리(① 패턴), 연결 불가 시 skip.
- postgres에 `create_node` 2개(`{id:"org-1"}`, `{id:"org-2"}`) + `create_edge`(`{from:"org-1",to:"org-2",type:"DEPENDS_ON"}`) 저장.
- `replay_graph(all_mutations())` → `GraphService` 에 node 2·edge 1, `node("org-1")` 존재 (ADR-304 재구축).
- idempotency_key 중복 이벤트 저장 적용 시 중복 노드 없음 (불변식 §3-6 유지).

**Step 2 (Green)** — `graph_replay.py` 구현.

**Step 3 — 문서 3단계 규칙:** design 03 ADR-304에 실제 재생 경로 구현 표기 + ROADMAP Changelog + design README(version 유지 확인).

**Step 4 — 회귀:** 전체 스위트(442) Green 유지.

## 앤티-골(하지 않음)
- 실제 pipeline을 postgres 로그로 배선 (파이프라인은 여전히 in-memory Gate 소비) — 후속.
- Neo4j 적재 / merge·supersede·delete 실행 확장 / GraphService 개선.

## 성공 기준
1. `test_graph_replay.py` 통과.
2. 전체 스위트 442 회귀 0.
3. postgres 라이브 데모: create_node/edge 저장 → replay → GraphService node·edge 재구축.
4. 3단계 문서 반영.

## 테스트 격리 주의
- postgres 전용 테이블명(① `graph_mutations_test` 재사용)에 DROP+CREATE — 운영 테이블과 분리.
- 연결 불가(오프라인) 시 `importorskip`·커넥션 예외 skip → 기존 442 유지.
