# S4 Dedup — 출처 계보·복제 축소 (Phase 0, design 04 §4, 03 §4.3)

## 맥락 / 목표
정규화·영속화까지 갖췄다(S1→S3→저장). 이 단계는 **서로 다른 `doc_id` 사이의 복제·파생
관계**를 판정해 `dup_clusters`로 축소한다 — "복제 500건을 독립 500으로 세지 않음"
과대평가를 막는 출처 계보 (design 04 §4, blueprint §18).

**prototype 범위:** 3수준 판정 중 **① exact + ② MinHash near-dup** (순수 Python, LLM 없음).
③ semantic(LLM)은 고비용·후보 쌍 전용 → 문서화된 **스텁**(미구현 표시)으로 둔다.

## 설계 근거 (design 04 §4, 03 §4.3)
- **3수준 계단식(cascade)**: ① exact(content hash) → ② near(MinHash LSH → Jaccard)
  → ③ semantic(LLM). 상위에서 결론 나면 하위 호출 안 함 (§4.1).
- ①은 S2 `doc_id` 동일성으로 이미 흡수 — S4는 **다른 doc_id** 사이만 다룬다 (§4.1).
- **`dup_clusters` 산출** (03 §4.3): `cluster_id(clus-<ULID>)`, `root_doc_id`,
  `member_doc_ids[]`, `independent_addition_doc_ids[]`, `dedup_method`.
- **root 선정**: 가장 이른 `publication_time` + `source_type` 신뢰(official/gov 우선),
  동률은 `doc_id` 사전순 tie-break (결정적 재현 §4.2).
- **independent ⊆ member, root ∉ 둘 다** — 부분집합·disjoint 불변식 (§4.2).
- **idempotency**: `(doc_id, dedup_version)` 결정적 재생성. 같은 버전은 같은 cluster (§4.2).
- **distinct-shingle Jaccard** 기반 MinHash로 near-dup 판정. ADR-403 임계값 placeholder
  → prototype에서 실측 합리값(예: Jaccard ≥ 0.85). LLM 없이 결정적.

## 구현 범위 (prototype 확장, TDD)

### 1) Red — `tests/test_dedup.py` 실패 테스트
`Deduplicator` 계약:
- **exact(①)**: 동일 sha256 콘텐츠(다른 url로 재수집) → 같은 cluster, 같은 doc_id 생성 안 함
- **near(②)**: 텍스트가 거의 동일(한두 문장만 다름)한 두 doc → same cluster
- **다른 문서**: Jaccard 낮음 → 서로 다른 cluster
- **root 선정**: publication_time 이른 쪽이 root; 동률 시 doc_id 사전순 tie-break
- **불변식**: independent ⊆ member · root ∉ member/independent (03 §4.3)
- **deterministic**: 같은 입력 → 같은 cluster 결정 재생성 (dedup_version 바인딩)

### 2) Green — `orc_citadel/dedup.py` 신규 모듈
- `shingles(text, k)` + `minhash(shingles, perms)` (순수 Python, 결정적 seed)
- `jaccard(a, b)` (distinct-shingle)
- `Deduplicator`:
  - `dedup(docs)` → list[Cluster] — input: [(doc_id, text, publication_time, source_type)]
  - exact: sha256(text) 동일 그룹핑
  - near: MinHash LSH 후보 → 임계값 이상만 병합
  - 병합 시 root 선정 규칙 적용, member/independent 분류(prototype: independent는
    root span에 없는 추가 문장이 있는 doc — 최소 규칙)
  - `dedup_version` 상수 보유, 결정적 재현
- `Cluster` dataclass: cluster_id, root_doc_id, member_doc_ids[], independent_addition_doc_ids[], dedup_method

### 3) E2E — `orc_citadel/dedup_smoke.py`
실수집 문서 + **인위적 복제 사본**(한두 문장 수정)을 넣어 클러스터링 확인:
원본·복제가 한 cluster로, 독립 문서와 분리. root가 원본인지 검증.

## TDD / 성공 기준
- `test_dedup.py` Green (exact·near·분리·root 선정·불변식·결정성)
- dedup_smoke: 실데이터에서 복제 축소 동작 확인
- 기존 30개 포함 전체 Green
- 코드만 커밋 (데이터 gitignore)

## 작업 순서 (Tidy First)
1. **Red** — dedup 테스트 실패 작성
2. **Green** — `dedup.py` 최소 구현 (①② + 스텁 ③)
3. **E2E smoke** — 실데이터 + 복제 사본으로 축소 검증
4. **Refactor** — MinHash 파라미터·병합 로직 갈무리
5. **Commit** — 코드만

## 범위 밖 (이 단계 아님)
- ③ semantic(LLM) 파생·인용 판정 — 고비용, 후보 쌍 전용, 재작성·번역·인용 — 스텁
- `embedding` near-dup 보강 — ADR-403 실측 후
- per-claim `independent_evidence_count` 집계 — 설계가 11 §1.4에 위임
- curated zone(mentions/claims) 영속화 — S5 추출 후
