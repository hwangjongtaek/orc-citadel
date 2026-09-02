# P1 · Viewer 목업 충실 — War Table·Witnesses·Council·page-4

선행: `docs/handoff-viewer-fidelity.md`. 한 페이지씩. 본 문서는 **War Table** 갭 분석 + 완료 체크리스트.

## 갭 분석 (목업 `war-table.html` vs 현재 `/table`)

현재 `/table` 은 랭킹·보고서·조사 실행·근거 조회 개발 화면. 목업 핵심은 **3+1 패널**.

| 목업 블록 | 분류 | 실데이터 경로 | 비고 |
| --- | --- | --- | --- |
| Campaign Map · subject 목록 | 실데이터 가능 | `ConclusionRanking.ranked()` → `/api/table` | Campaign 등록은 쓰기·범위 밖. subject 를 Campaign 대용 |
| Campaign Map · predicate / open_questions | 실데이터 가능 | `get_investigation_report` `by_predicate`·`open_questions` | 조사 실행(Planner+Runner) 없이 기존 결론만 |
| Entities · Filters 칩 | 실데이터 가능 | `zone.entities().mention_type` + claims 수 + quarantine | 라벨 없는 그래프 노드 → zone 차원으로 정직 집계 |
| War Table 캔버스 (노드·엣지) | 실데이터 가능 | `get_investigation_graph` + `get_graph_node` / `get_graph_expand`(cursor) | 외부 lib 없이 SVG + 목록형. `_build()` 그래프는 ABOUT 만 |
| 관계 범례 (supports/contradicts/…) | 구현됨 (정적) | — | 그래프에 해당 엣지 없으면 캔버스에 안 그림 |
| Valid-time 슬라이더 | 실데이터 가능 | `/api/chronicle?valid_at=` | TX time = now (정직) |
| Evidence Inspector · claim 카드 | 실데이터 가능 | `get_claim` + report 봉투 | value 단독 게이지 금지 |
| 독립성 보정 문구 | 실데이터 가능 | `confidence.basis` | |
| Supporting Evidence | 실데이터 가능 | `get_claim_evidence` | |
| Provenance trail | 실데이터 가능 | `get_evidence_provenance` | claim → extraction_record → document |
| Contradicting Evidence | 데이터 없음 | — | 파사드 supports-only. 정직 빈 |
| Seer · LLM Inference | 데이터 없음 | — | 미영속. 정직 빈 |
| 하단 Chronicle 레일 | 실데이터 가능 | `/api/chronicle` subject 필터 | |
| 헤더 검색 | 실데이터 가능 | 클라이언트 subject 필터 | 기존 `/api/*` fetch |
| 조사 실행 버튼 | 범위 밖 | `_api_investigate` 유지·페이지 미노출 | 쓰기 개념. API 는 기존 테스트 회귀용으로 존치 |

## 완료 체크리스트 (handoff §4-3)

| 블록 | 상태 |
| --- | --- |
| Campaign Map (subjects + predicate/open_questions) | ✅ |
| Entity type 칩 | ✅ |
| 그래프 캔버스 + 클릭 확장 (cursor) | ✅ |
| Evidence Inspector (claim·봉투·supports·trail) | ✅ |
| Contradicts / Seer 정직 빈 | ✅ |
| Chronicle 레일 + valid-time | ✅ |
| 빈 상태 (조사 미선택 / claim 미선택 / 이력 없음) | ✅ |
| 조사 실행 UI 제거 (API 존치) | ✅ |

**검증 (2026-09-02):** `test_viewer_table.py` 6 Green · `test_viewer_graph.py` 회귀 0 · 전체 스위트 **1068 passed**, 22 skipped. pre-existing `test_claude_cost`/`test_claude_judge` 2 실패는 base 와 동일·본 작업 무관. Spec 1.1.0 유지.

## Hall of Witnesses (`/witnesses`) — 우선 2

목업 3-column: 좌=Claim 목록(modality facet)·중=Evidence·Provenance Trail·우=원문 하이라이트. **결과→원문 3-hop 왕복**(§2.3).

| 목업 블록 | 분류 | 구현 |
| --- | --- | --- |
| Claim 목록 + modality 칩 | 실데이터 | `/api/table`+`/api/subject_claims`+`/api/report` |
| Evidence & confidence 봉투 | 실데이터 | `/api/evidence`+`/api/report` |
| Supporting Evidence | 실데이터 | `/api/evidence` |
| Contradicting Evidence | 데이터 없음 | 정직 빈 (`notes.contradicts`) |
| Provenance Trail (complete) | 실데이터 | `/api/provenance` claim→extraction_record→document |
| 원문 문서 뷰·span 하이라이트 | 실데이터 | `/api/document` normalized 세그먼트 — `ord` 대응(char는 세그 clean-text 축) |
| Round-trip 힌트바 | 구현 | 정적 3-hop 안내 |

**완료:** ✅ 전 블록. 검증: `/witnesses` 라이브 3-hop 왕복 — "will host a conference call"supports 하이라이트 렌더 실측.

## Council Chamber (`/council`) — 우선 3

| 목업 블록 | 분류 | 구현 |
| --- | --- | --- |
| Subjects 랭킹 (좌) | 실데이터 | `/api/table` |
| 결론·by_predicate·open_questions (중) | 실데이터 | `/api/council`(=`get_investigation_report`) |
| Stopping A/B/C bars (우) | 실데이터 | confidence.dimensions (coverage·support·contradiction) |
| Cost·Audit (우) | 데이터 없음 | runtime 미영속 → `—`·범위 밖 정직 |
| 8-agent roster·조사 실행 | 범위 밖 | 쓰기. `execution.available=False` |

**완료:** ✅ 조회 전용. 조사 실행 미노출.

## page-4 보조 블록 (Gate·Watchtower·Archive·Chronicle·Spire) — 우선 4

| 페이지 | 추가 블록 | 상태 |
| --- | --- | --- |
| `/` | Campaign 카드(coverage·value·독립·predicate)·8 공간 quick-enter | ✅ |
| `/watchtower` | 3 타일 — Sources active·**normalized publication_time 실측** freshness·Documents | ✅ |
| `/archive` | source_type facet 칩·Codex 문서 상세(세그·char_len·딥링크) | ✅ |
| `/chronicle` | as-of 상태 분해(현재 믿음 vs tx 닫힘)·War Table bitemporal 딥링크(`/table?subject&as_of_*`) | ✅ |
| `/spire` | 5 트리거 필터행(not-fired)·정직 빈 피드 유지 | ✅ |
| `/table` | 딥링크 수신: URL `subject`·`as_of_valid` 부트스트랩 | ✅ |

**발견·수정 (라이브 스모크):** witnesses `||` 연산자 우선순위로 trail 컨테이너(`#prov-steps`) 소실 → 괄로 수정. chronicle `qs` 재선언 SyntaxError(as-of 필드와 이름 충돌) → `dlp` 리네임. 둘다 인라인 JS `node --check` 문법 가드(`test_viewer_aux.py`·8 페이지)로 봉인.

**검증 (2026-09-02):** `test_viewer_witnesses.py` 4 + `test_viewer_aux.py` 8(+문법가드 8 parametrized)·`test_viewer_table.py` 6 Green. 전체 스위트 **1086 passed**, 22 skipped. 8 라우트 라이브 스모크 실데이터 렌더 확인. Spec 1.1.0 유지.
