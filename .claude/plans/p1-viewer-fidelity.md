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

---

# Remaining-gaps 전수 소진 (2026-09-02 · workflowz)

scout 4종 병렬 갭분석(war-table/witnesses-council/aux/backend-residual) → 58 feasible·39 blocked. Wave 1(백엔드 API) → Wave 2(프런트 4 워커 파일-배타 병렬) → 오케스트레이터 병합.

## 구현됨 (실데이터)

| 영역 | 블록 |
| --- | --- |
| API | `/api/search`(text contains)·`/api/claim` 신설 · table(entities/quarantined)·graph(label)·archive(cluster_role/segment_kinds/url_groups)·chronicle(bounds/events)·watchtower(intake/governance)·investigate(counter_evidence[]/audit_trace/iterations/terminated_by) 확장 |
| War Table | subclaim known/gap 카드·entity chip 토글·SVG zoom/pan/fit/reset·edge 타입 색+incident 강조·expand more(opaque cursor)·claim 상세+excerpt 발췌·bitemporal dual-slider 레일·이벤트→loadClaim |
| Witnesses | claim 카드 실문장+per-claim confidence·bitemporal join·독립성/clusters 정직·인용 char-span·trail 전개·toolbar 딥링크·legend·`?claim`/`?doc` 부트스트랩 |
| Council | 8역할 executed/not-run(wire 필드 판정)·loop 결과 trace·subclaims 트리·retrieved≤10·반증(결정적 후보)·Stopping 실제 입력·audit 분모0 과장금지·딥링크 (버튼 클릭 시만 on-request) |
| Aux | Gate mini-watchtower+전역 검색 드롭다운 · Watchtower 24h intake SVG+governance · Archive facet/stacks/contains+`?doc` · Chronicle bitemporal plane/preset/events rail |

## 영구 blocked (honest-gap — 데이터·불변식 근거)

- **subclaim 연속 coverage %** — per-subclaim 실측 없음 (known/gap 배지만)
- **확정 CONTRADICTS·Seer inference** — conflict_candidates·canonical_llm_records 영속 0
- **graph as-of 과거 스냅샷·과거 시점 confidence 봉투** — as-of는 `/api/chronicle` 뿐, evidence 프로젝터는 현재축
- **ingest 이벤트 타입** — assertion tx之外 수집 타임스탬프 없음
- **1차자료/당사자 라벨** — source 신뢰 메타 스키마 없음
- **live agent 상태·turn 로그·tier·Cost/token/latency 영속** — 실행 이벤트 미저장 (on-request trace로 대체)
- **Campaign 등록·조사 실행·Spire alert/subscription/ack** — read-only 불변식 (§2-1)
- **Watchtower schedule 분모·stage backlog·DLQ·retry** — queue/registry/attempt 저장소 없음
- **BM25 전문 검색** — FTS 인덱스·오프라인 확장 설치 불가 (text contains로 대체·UI에 명시)
- **Quarantine/POSSIBLY_SAME_AS 그래프 상세** — authoritative_edges 0

## 병합 봉인 (오케스트레이터)

- `viewer_pages.py` 하단 `_inject`: CSS/본문/JS 3조각 주입, `<script>` 앵커 1회 assert. ext 모듈은 viewer_pages 를 import 하지 않아 사이클 0.
- base **edge-label `NaN` 우선순위 버그**(`(a[1]+b[1])/2-4` 문자열화) 수정 — table_ext 의 ensureEdgeLayer 구제 불필요화, 이중렌더 자동 해제 경로로 무력화.
- `test_viewer_ext_merge.py` 13: 앵커 병합·헬퍼(esc/empty/api/$) 재정의 금지·node --check 8페이지·NaN 회귀 봉인·Spire 정직 유지.

**검증 (2026-09-02):** 전체 스위트 **1174 passed**, 22 skipped (pre-existing `test_claude_*` 2 무관). live 8791(기구현 curated 실데이터) 스모크: War Table edge 25·label 'NVIDIA/announces'·subclaim 카드·claim 상세 conf 0.92·chronicle 레일 30이벤트 / Witnesses 29 claim 카드·trail·`?claim` 미스 정직·`?doc` hl 1 / Council trace executed·audit 분모0 과장없음 / Gate 검색 'nvidia' entity1+doc3 / Watchtower intake 24버킷+governance 200·ALLOW / Archive facet en·6+stacks 정직 0+preset as-of 29. Spec 1.1.0 유지.
