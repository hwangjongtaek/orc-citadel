# S44 · Graph Explorer (설계 07 §3.3)

## 목표

조사 루프의 Graph Explorer — subclaim → 관련 subgraph + relation_paths + independence_summary를 **read-only**로 산출 (07 §3.3, tier L3·graph:read).

## 출력 계약 (07 §3.3)

```json
{
  "subclaim": "...",
  "subgraph": {            // S26 investigation_subgraph (canonical view-rewrite)
    "entity", "entities", "claims", "evidence", "relationships", "truncated"
  },
  "relation_paths": [...],   // entity → ABOUT claim → SUPPORTS|CONTRADICTS evidence 경로
  "independence_summary": {  // S29 독립 출처 보정
    "evidence_count", "independent_source_count", "dedup_ratio", "note"
  }
}
```

## module·API

`prototype/orc_citadel/graph_explorer.py`:
```python
class GraphExplorer:
    """조사 루프의 read-only 그래프 탐색 (07 §3.3, S26·S29 재사용)."""
    def __init__(self, zone, graph): ...
    def explore(self, subclaim_id, subject_id, hops=1) -> dict
    def independence_summary(self, subject_id) -> dict
```
read-only — graph mutation 미노출.

## TDD (Red→Green→Refactor)
`test_graph_explorer.py`: subgraph 재사용, relation_paths, independence_summary(독립 보정), read-only, 그리기.

## 커밋
code-only behavioral, main 직접 머지.
