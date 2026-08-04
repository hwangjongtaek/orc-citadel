# S5 추출 + curated zone 영속화 (deterministic-first 최소 구현)

> 소량 수집 6건 실데이터 상에서 S5(설계 05)의 **결정적 출처 계보·mention 추출** 최소
> 구현 + curated zone DuckDB 영속(설계 03 §4)을 검증한다. LLM 의존 단계는 스텁/후속.
> 대상 문서: [05-resolution-and-extraction.md](../../docs/design/05-resolution-and-extraction.md),
> 03 §4.1 `mentions` · §4.3 `dup_clusters`.

## 배경과 범위

| 결정 | 근거 |
| --- | --- |
| **§2 Entity Resolution·§3 Claim·§4 Canonicalization은 스텁** | 전부 LLM/embedding 의존. 설계 §5·§6 "deterministic-first" 원칙: 규칙·사전으로 판정 가능한 것만 먼저 |
| **L1 (gazetteer·식별자 정규식) mention 추출만 구현** (설계 05 §1.1 L1) | ticker/URL/대문자 조직명 등 **강한 식별자** mention — 해소·claim의 입력 신호, 결정적 |
| 캐스케이드의 **ˍ2·L3(LLM NER)은 미구현** (스텁 문서화) | prototype 비용 통제, span 없는 mention 폐기 원칙(§1.1)은 지킴 |
| **mentions + dup_clusters DuckDB 영속·조회·Parquet export** | 설계 03 §4 curated zone 물질화 — S4 dedup 산출물도 같은 zone에 영속 |
| LLM 스텁은 호출 가능 경계만 정의 (sentry) | 실제 LLM 투입은 후속(1만 문서/평가 이후) |

## 핵심 계약 (설계 정합)

- **span 축**: `char_start/char_end`는 **clean text** 기준 (설계 03 §3.2·04 §3.4와 동일 축,
  segment offset과 정합). raw HTML 축 역매핑은 일반 케이스에서 후속 (04 §3.4).
- `mention_id = "men-" + <결정적>: (doc_id, segment_id, char_start/end, surface_text) hash`
  → 재실행 동일 mention이 동일 ID (idempotency, 03 §5).
- `extraction_version = { model_id: "rule-l1-1", schema_version: "0.1.0", extraction_code_version: "git:..." }`.
- touch rule: `extract` header docstring에서 L1 규칙·파라미터 식별 — 변경 시 bump.
- **curated zone 파생 파일은 gitignore** (`prototype/data/`, `*.duckdb`) — code-only 커밋 (기존와 동일).

## L1 추출 전략 (설계 05 §1.1)

L1 deterministic parser는 진입 순서대로, 각 규칙에 대해 결정적 mention 생성:

| 규칙 | 신호 | mention_type | 예 |
| --- | --- | --- | --- |
| **ticker** | `(NYSE|NASDAQ|OTC):[A-Z]{1,5}` | Organization | NASDAQ:NVDA |
| **URL 도메인** | `https?://(?:www\.)?([a-z0-9-]+\.)+[a-z]{2,}` | Organization(resolver hook) | nvidia.com |
| **gazetteer** (도메인 사전) | 대문자 표면형 + positiveset | Organization | NVIDIA, TSMC, SEMI |
| **대문자 연속 토큰** | `[A-Z][A-Z]+(?:\s[A-Z][A-Z]+)*` (≥2 token) | Technology/Org(약한) | GeForce NOW, RTX |

- gazetteer는 `extract.GAZETTEER: dict[surface, type]`으로, 도메인 전문화 가능 (prototype 배정).
- **span 문맥**: mention 주위 ±N chars `context_window` (설계 05 §1.2 `context_window`).
- **중복 제거**: span 겹침 시 가장 긴(또는 타입 우선) mention만 유지 — 결정적.

## 구현 파일

| 파일 | 내용 |
| --- | --- |
| `prototype/orc_citadel/extract.py` | **신규** — L1 mention 추출 (`extract_mentions(doc_id, doc, segs) → list[Mention]`) |
| `prototype/orc_citadel/curated_zone.py` | **신규** — `CuratedZone` DuckDB: `mentions`(§4.1) + `dup_clusters`(§4.3) 테이블, `initialize/persist_mention(s)/persist_cluster(s)/mentions()/clusters()/export_parquet/close` |
| `prototype/orc_citadel/extract_smoke.py` | **신규** — 실수집 6건 → 추출 → curated 영속·조회 스모크 |
| `prototype/tests/test_extract.py` | **신규** — TDD: ticker/URL/gazetteer/대문자/span·문맥/중복제거/결정성/span 없는 폐기 |
| `prototype/tests/test_curated_zone.py` | **신규** — schema/persist/query/원자성 turn |
| `curated_s5.md` | 이 플랜 |

기존 `duckdb_zone.py`(normalized)는 **수정하지 않음** — curated는 별도 zone으로 독립 영속.
실수집 경로는 `persist_smoke.py` 패턴 재사용 (raw→extract→parse→segment).

## 작업 순서 (TDD: Red → Green → Refactor)

1. `test_extract.py` Red — ticker mention 추출 실패 확인
2. `extract.py` Green — L1 규칙 구현
3. `test_extract.py` 확장 → gazetteer/대문자/URL/중복제거/결정성/span 폐기 전부 Green
4. `test_curated_zone.py` Red → `curated_zone.py` Green — mentions/dup_clusters 영속·조회
5. `extract_smoke.py` — 실수집 6건으로 E2E: 추출→mentions 영속→조회·offset 정합·Parquet export
6. 전체 `pytest` Green 확인
7. 커밋 (code-only, `git log`로 확인) — **curated_s5 플랜도 함께**

## 검증 기준 (Definition of Done)

- 전체 테스트 통과 (기존 38 + 신규)
- 실수집 6건 중 `official-nvidia-news`(3건)에서 NVIDIA/NVIDIA Jetson 등 **결정적 mention** 다수 추출, `press-semiengineering`(3건)도 본문/제목 기반 가동
- mention span으로 segment.text를 slice하면 surface_text 정합 (offset 왕복)
- mentions·dup_clusters가 DuckDB에 영속, Parquet export 가능
- code-only 커밋 (git status에 `data/`·`.duckdb` 미포함)

## 위험 / 한계 (문서화)

- 대문자 연속 토큰 규칙은 문장 시작·제목에서 오탐 가능 → 긍정 gazetteer로 상쇄 (precision 우선, 설계 §5)
- raw HTML 축 정확 역매핑은 미구현 — clean text 축으로 범위 확정 (04 §3.4와 동일)
- L2/L3(LLM NER)·resolution·claim·canonicalization은 후속 단계 (이번 범위 밖, 스텁)
