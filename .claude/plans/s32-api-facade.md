# S32 · 조사/근거/그래프 API 파사드 (설계 09 §2·§3)

## 목표

**read-only 프로젝션 4종**(S28 Catalog, S29 evidence, S30 conclusion, S31 ranking)을 설계 09 §2 조사 중심 **엔드포인트 wire 계약**으로 노출하는 **API 파사드 계층**을 추가한다.

FastAPI 서버를 세우지 않는다(신규 의존 금지, 결정성·TDD). 대신 **순수 핸들러 함수**(`(zone, graph, **params) -> dict`)가 09 §2·§3의 **응답 JSON 스키마**를 그대로 생성하고, 단위 테스트로 검증한다. 후속에서 FastAPI 라우터는 이 핸들러를 1:1 감싸기만 하면 된다 (09 §1.1 REST+JSON 계약).

**read-only** (불변식 §3-3): 모든 핸들러는 조회 전용 — 쓰기·영속·그래프 mutation 미노출. 09 §2.2 "그래프 변경은 mutation 이벤트로만".

## 핸들러 (09 §2·§3)

| 핸들러 | 09 엔드포인트 | 동작 |
| --- | --- | --- |
| `get_claim(claim_id)` | `GET /v1/claims/{id}` | claim 상세 + 09 §4 confidence 봉투 (S29) |
| `get_claim_evidence(claim_id, relation)` | `GET /v1/claims/{id}/evidence` | 지지/반박 근거 + cursor (09 §2.3) |
| `get_evidence_provenance(evidence_id)` | `GET /v1/evidence/{id}/provenance` | Trail 객체 (09 §2.3) |
| `get_investigation_report(subject_id)` | `GET /v1/investigations/{id}/report` | 09 §3 결론 봉투 + by_predicate + open_questions (S30) |
| `get_graph_node(node_id)` | `GET /v1/graph/nodes/{id}` | 노드 상세 (06 §8, S28 Catalogue) |
| `get_graph_expand(node_id, limit, cursor)` | `GET /v1/graph/nodes/{id}/expand` | 인접 확장 cursor (09 §2.2 progressive disclosure) |

각 핸들러는 **응답 JSON 스키마**를 dict로 Return (09 §1.1 JSON, §1.4 cursor).

### aport 응답 shape (input로 추상체)

`get_claim_evidence` → `{items:[{evidence_id, relation, strength, claim_id, source_doc}], page:{next_cursor, limit}}`.
`get_evidence_provenance` → `{evidence_id, relation, strength, trail:[{step, doc_id, segment_id, text}]}` (09 §2.3 trail).
`get_investigation_report` → `{subject_id, confidence:{...09 §4 봉투}, by_predicate, open_questions:[]}` (09 §3).
`get_graph_expand` → `{items:[{id, type}], page:{next_cursor, limit}}`.

**근거(strength) mapping**: claim의 근거는 **같은 (subject,predicate,object) 주장의 서로 다른 문서**로 식별됨 (S29 supporting_docs). `strength`는 해당 claim의 S29 support 성분. provenance trail은 supporting_claim → claim → doc 참조.

## module·API

`prototype/orc_citadel/api_facade.py`:

```python
class ApiFacade:
    """09 §2·§3 wire 계약을 노출하는 read-only API 파사드 (FastAPI 라우터의 백엔드)."""
    def __init__(self, zone, graph, low_confidence=0.4, high_confidence=0.8): ...
    def get_claim(self, claim_id) -> dict | None
    def get_claim_evidence(self, claim_id, relation=None, cursor=None, limit=30) -> dict
    def get_evidence_provenance(self, evidence_id) -> dict | None
    def get_investigation_report(self, subject_id) -> dict | None
    def get_graph_node(self, node_id) -> dict | None
    def get_graph_expand(self, node_id, cursor=None, limit=30) -> dict
```

내부에서 S28 Catalog·S29·S30·S31 재사용. **read-only** — `_` 쓰기 없음, zone/graph 참조만.

## TDD (Red→Green→Refactor)

`test_api_facade.py` — 기존 zone 픽스처(catalog/conclusion 패턴) 재사용.

1. **Red**:
   - `get_claim` — claim 존재 시 상세+봉투, 미존재 시 None.
   - `get_claim_evidence` — 지지 근거 항목 + cursor 페이지, relation 필터.
   - `get_evidence_provenance` — trail: evidence→claim→doc (step 포함).
   - `get_investigation_report` — 09 §3 결론 봉투 + open_questions.
   - `get_graph_node` / `get_graph_expand` — 노드·인접 cursor.
   - read-only — `apply`/`persist`/`create_*` 미노출; zone/graph 상태 불변.
2. **Green** — 최소 구현.
3. **Refactor** — 중복 없음.

## 실데이터 스모크

curated.duckdb + graph — 조사 보고서·근거·provenance·그래프 확장 방출.

## 커밋

**code-only (behavioral)**: `feat(S32): API facade for investigation/evidence/graph read endpoints (09 §2·§3)`.

## 완료 기준

- [ ] Red→Green→Refactor, 전체 테스트 통과 (기존 260 + 신규).
- [ ] 결정성 — 동일 zone+graph → 동일 응답.
- [ ] read-only — 쓰기 경로 미노출, 상태 불변.
- [ ] 실데이터 스모크 — 09 §2·§3 wire shape pad.
