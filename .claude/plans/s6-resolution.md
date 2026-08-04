# S6 Entity Resolution (결정적 stage-1만, 설계 05 §2 + ADR-507)

> 권장안 선정. L1 mention(추출) 위에 **결정적 해소의 최소 단계**만 구현한다. LLM·
> embedding 의존 단계는 설계가 명시한 대로 자동 병합 금지 대상이라 스텁/후속.
> 대상 문서: [05-resolution-and-extraction.md](../../docs/design/05-resolution-and-extraction.md) §2,
> [02-ontology.md](../../docs/design/02-ontology.md) §2.2·§3, 03 §4.

## 배경·범위

| 결정 | 근거 |
| --- | --- |
| **캐스케이드 stage-1 (식별자 exact match)만 구현** — `shared_identifier(m,c)` → ACCEPT → SAME_AS 자동 병합 | 설계 §2.2 rule 1, **ADR-507**: 결정적 외부식별자 exact match는 **유일한 자동 `SAME_AS` 병합 경로**. LLM·점수·이름 고신뢰는 자동 병합 금지 |
| **blocking key `identifier`** (설계 §2.1) | ticker/URL 외부식별자 exact 매칭 — O(n²) 방지·결정적 |
| **lexical·embedding·rule·LLM은 스텁** | 비결정적 자동 병합 금지 (ADR-507, G4). POSSIBLY_SAME_AS는 후속 |
| **canonical 대표 1개** (SAME_AS 동치류) | 설계 02 §4-5·§3.1: SAME_AS 전이·무순환, 대표 1 |
| **resolution 근거 저장** (설계 §2.5 요약) | `resolution_decisions`(res-): stage/결정/근거 — audit·reversible |
| mention.resolved_entity_id 채움 | 설계 05 §1.2 (extract.Mention 필드), curated mentions에 영속 |
| curated `entities` 테이블 신설 | Organization/... 캐노니컬 엔터티 영속 (entity_id, canonical_name, identifiers) |

**제외(후속 스텁):** embedding rerank·rule score·LLM judge·POSSIBLY_SAME_AS 후보·quarantine·
human review — 전부 비결정적 병합 또는 LLM 의존.

## 핵심 계약

- `entity_id = "org-" + <결정적>: (mention_type, canonical_name, identifiers) hash` → 재실행 동일.
  (prototype — Organization에 한정. Person/Location은 후속.)
- **canonical_name** 선택 (설계 02 §2.2): 동치류 내 최빈 표면형, 동률 사전순(결정적).
- **명시적 ticker 부착**: gazetteer Organization(NVIDIA)에 `identifiers{ticker:NVDA}` 부여 →
  `NVDA`(ticker mention)와 NVIDIA(gazetteer mention)가 **shared identifier로 교량**되어 한 entity로.
- merge는 **SAME_AS 동치 collapse**(canonical 대표 1개)로 표현. reversible은 resolution 이벤트
  기록으로 뒷받침(불변식 §3-3, 프로토타입은 res- 레코드).
- 결정만 **결정적**: 동일 mention 입력 → 동일 entity·동일 resolved_entity_id.

## 구현 파일

| 파일 | 내용 |
| --- | --- |
| `extract.py` (수정) | GAZETTEER Organization에 `identifiers{ticker}` 부착 → mention.identifiers로 전달 (구조적) |
| `prototype/orc_citadel/resolve.py` | **신규** — `EntityResolver`: block(identifier) → stage1(SAME_AS collapse) → entity/mention resolved |
| `curated_zone.py` (수정) | `entities` 테이블 + mention.resolved_entity_id 영속·조회 |
| `prototype/orc_citadel/resolve_smoke.py` | **신규** — 실수집 mention → 해소 → curated 영속 |
| `prototype/tests/test_resolve.py` | **신규** — TDD |
| `s6-resolution.md` | 이 플랜 |

## 작업 순서 (TDD)

1. Red: `test_resolve.py` — shared identifier(ticker) exact → 동일 entity (SAME_AS), canonical 결정, 결정성
2. Green: `resolve.py` + extract GAZETTEER identifiers
3. Green: curated `entities` + resolved 영속
4. Smoke: 실수집 6건 → mention 해소(NVIDIA 23회→1 org, TSMC 3회→1 org) → 영속
5. 전체 pytest Green + 커밋 (code-only)

## DoD

- NVIDIA/TSMC가 각 1 entity로, GeForce NOW/RTX 각 1 entity로 해소
- ticker NVDA mention과 gazetteer NVIDIA가 한 entity (identifier 교량)
- 결정성·idempotency (동일 입력 동일 결과), span·멘션 무손실
- curated에 entities + resolved 영속, 전체 테스트 통과, code-only 커밋

## 한계 (문서화)

- Person/Location·lexical/embedding/LLM·POSSIBLY·quarantine·human review는 후속
- canonical 대표는 최빈 표면형 — 법인 표준명(legal_name) 정규화·jurisdiction은 후속
