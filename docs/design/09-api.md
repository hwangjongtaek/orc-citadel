# 09 · API 계약

> **상태:** ✅ Stable · **Spec:** 1.2.0 · **Blueprint 매핑:** §5
> 상위 규약: [README](./README.md) · 관련: [01-architecture](./01-architecture.md), [06-graph](./06-graph-service.md), [07-llm](./07-llm-and-agents.md), [03-storage](./03-storage-and-data-model.md)

Citadel의 외부 계약(API Gateway = **Citadel Gate**, FastAPI)을 확정한다. blueprint §5(조사 요청/결과/지속 관찰)의 사용자 경험을 REST 리소스와 응답 스키마로 번역하며, 그래프·조사·저장 계층의 내부 세부는 각 정본 문서([`06`](./06-graph-service.md), [`07`](./07-llm-and-agents.md), [`03`](./03-storage-and-data-model.md))가 소유한다. 본 문서는 **client ↔ services 경계의 wire contract**만 확정한다 (컴포넌트 경계는 [`01`](./01-architecture.md) §3).

---

## 1. 규약 (Conventions)

### 1.1 프로토콜·직렬화

- **REST over HTTPS.** 리소스 지향 경로 + 표준 HTTP 메서드(`GET`/`POST`/`PATCH`/`DELETE`). RPC-style 동사 경로는 상태 전이(`:cancel` 등)에만 제한적으로 허용한다.
- **JSON** 요청·응답 본문(`application/json; charset=utf-8`). 이진 원문(raw bytes)은 provenance 링크(presigned URL)로만 제공하고 API 본문에 싣지 않는다.
- **모든 timestamp는 UTC ISO-8601** (`2025-02-15T09:00:00Z`). 로컬타임·offset 표기를 받지 않는다 ([`README`](./README.md) §2.4).
- **ID는 `<prefix>-<body>` 문자열** 그대로 노출한다 ([`README`](./README.md) §2.2). 경로 파라미터·본문 모두 prefix 포함 ID를 사용한다 (`inv-01J9…`, `clm-01J9…`).

### 1.2 버저닝

- 경로 prefix `/{v}/` 로 major 버전을 고정한다. 현재 `/v1`.
- 응답 헤더 `X-Citadel-Spec-Version`, `X-Ontology-Version`으로 스펙·온톨로지 버전을 함께 통지한다 ([`02`](./02-ontology.md) §6.3 호환성 계약).

### 1.3 URL 명명 — 기술 용어 우선

경로·필드에는 **기술 용어를 우선**하고 세계관(UI) 명칭은 주석으로 병기한다 ([`README`](./README.md) §2.1, blueprint §1.4 반응형 원칙).

| 기술 경로 (canonical) | UI 표시명 | 세계관 |
| --- | --- | --- |
| `/v1/investigations` | 조사 · Campaign | Campaign |
| `/v1/investigations/{id}/graph` | War Table · Graph | War Table |
| `/v1/claims/{id}/evidence` | Evidence Inspector | Hall of Witnesses |
| `/v1/documents`, `/v1/sources` | 문서 탐색 | Grand Archive |
| `/v1/chronicle` | Chronicle · History | Chronicle |
| `/v1/alerts` | 알림 센터 | Signal Spire |
| `/v1/health/sources` | 수집 관제 | Watchtower |

> 계약 규칙: 클라이언트는 세계관 명칭을 **표시 레이어에서만** 사용하고, 경로·필드 키·ID는 기술 용어를 신뢰한다. UI 명칭 변경이 API를 깨뜨리지 않는다.

> **프로토타입 mapping (W3, 2026-09-10):** stdlib viewer는 외부 `/v1` 계약을 `/api`로 구현한다: `POST /api/investigations`, `GET /api/investigations/{inv_id}`, `GET /api/investigations/{inv_id}/status`, `GET /api/investigations/{inv_id}/report`, `GET /api/jobs/{job_id}`, `POST /api/investigations/{inv_id}:cancel`. 생성은 `Idempotency-Key`와 JSON body를 요구하고 `202` + `Location` + `Retry-After`를 반환한다. PostgreSQL 미가동은 가짜 job 없이 구조화 `503`이다. 구 `/api/investigate` 비영속 경로는 제거했다. 표시는 `frontend/dist`가 맡으며 graph·curated zone은 read-only, PostgreSQL investigation 운영 메타데이터만 write 허용이다.

### 1.4 페이지네이션 — Cursor 기반

목록 응답은 **opaque cursor** 방식을 사용한다. offset 페이지네이션은 대량 그래프·이벤트에서 불안정하므로 채택하지 않는다.

- 요청: `?limit=<1..200>&cursor=<opaque>` (default `limit=50`).
- 응답: `{ "items": [...], "page": { "next_cursor": <string|null>, "limit": 50 } }`.
- cursor는 ULID 시간 정렬성([`README`](./README.md) §2.2)을 활용한 불투명 토큰이며 클라이언트가 파싱하지 않는다. `next_cursor=null`이면 마지막 페이지.
- **정렬 키는 collection별로 고정**된다(클라이언트 미지정): 시계열 성격 목록(chronicle 이벤트·alert)은 `mutation_id`/`alert_id`의 ULID 역순(최신 우선), 리소스 목록(investigations·documents·segments)은 생성 ULID 순. cursor는 이 고정 정렬 축 위의 위치만 인코딩하므로 페이지 간 정렬 키를 바꿀 수 없다.

### 1.5 표준 에러 모델

모든 4xx/5xx는 동일 봉투를 사용한다. `correlation_id`는 파이프라인 공통 추적 ID와 연결된다 (blueprint §14, [`11`](./11-observability-and-governance.md)).

```json
{
  "error": {
    "code": "investigation_not_found",
    "message": "inv-01J9XYZ… 를 찾을 수 없습니다.",
    "correlation_id": "corr-01J9…",
    "details": { "investigation_id": "inv-01J9XYZ…" }
  }
}
```

| 필드 | 필수 | 설명 |
| --- | --- | --- |
| `code` | ✓ | 안정적 machine-readable 코드 (snake_case). HTTP status와 별개로 세분화 |
| `message` | ✓ | 사람이 읽는 설명 (한국어). UI 노출 가능 |
| `correlation_id` | ✓ | end-to-end 추적 키. 지원 문의·로그 상관에 사용 |
| `details` | — | 코드별 구조화 컨텍스트 |

표준 코드(발췌): `validation_error`(400), `unauthorized`(401), `forbidden`(403), `*_not_found`(404), `conflict`(409), `rate_limited`(429), `budget_exceeded`(422), `internal_error`(500). 상태 색·아이콘 매핑은 표시 레이어 책임이며 API는 색상을 규정하지 않는다.

**Rate limiting (429):** `rate_limited`(429) 응답은 `Retry-After`(초) 헤더로 재시도 대기 시간을 통지하며, 클라이언트는 이를 존중해 backoff한다. 임계치·윈도우 정책의 정본은 [`11`](./11-observability-and-governance.md) governance이며, 본 스펙은 응답 계약(코드+`Retry-After`)만 고정한다.

### 1.6 인증 (개요)

- **Bearer 토큰** — `Authorization: Bearer <token>`. 토큰 발급·회전 상세는 본 스펙 범위 밖이며 [`11`](./11-observability-and-governance.md) governance에 위임한다.
- **Idempotency-Key 헤더** — 리소스를 **새로 생성**하는 비멱등(`POST`) 요청은 `Idempotency-Key: <client-uuid>`를 받는다. 동일 키 재수신 시 최초 결과를 반환(no-op)한다 (불변식 §3-6, [`03`](./03-storage-and-data-model.md) §7.2). 상태 전이(`:cancel` 등 이미 존재하는 리소스의 idempotent transition)에는 필수가 아니다 — 전이 자체가 멱등이므로 재요청은 현재 상태를 그대로 반환한다.
- **Webhook 서명** — 비동기 콜백은 `X-Citadel-Signature`(HMAC)로 검증한다 (§5.2).

### 1.7 인가(Authorization)·테넌시

인증(§1.6)이 "누구인지"를 확인한다면, 인가는 "무엇에 접근·조작할 수 있는지"를 결정한다. 세부 정책(role 정의·권한 매트릭스·감사)의 정본은 [`11`](./11-observability-and-governance.md) governance이며, 본 스펙은 wire 계약에 필요한 최소 모델만 고정한다.

- **Scope 토큰** — Bearer 토큰은 하나 이상의 scope를 담는다: `investigations:read` / `investigations:write` / `graph:read` / `alerts:write` 등 리소스×동작 조합. scope 부족은 `403 forbidden`(§1.5 표준 코드).
- **Resource ownership** — investigation은 생성 주체(`owner`)에 귀속된다. 다음 조작은 `owner` 본인 또는 관리 role만 가능하다: `POST …:cancel`, `GET …/report`, `POST …:register-continuous`, alert 구독 생성/해제(§2.6). 타 소유 리소스 접근은 `403 forbidden`, 존재 자체를 숨겨야 하는 경우 `404 *_not_found`.
- **`?owner=` 필터** — 목록 질의(§2.1 `GET /v1/investigations`)의 `owner` 파라미터는 인가 범위 안에서만 유효하다. 요청자 scope를 벗어난 owner 지정은 결과를 확장하지 않는다(권한 상승 금지).
- **테넌시** — 토큰은 단일 테넌트에 바인딩되며 모든 리소스 조회·조작은 토큰 테넌트로 암묵 필터된다. cross-tenant ID를 경로에 넣어도 `404`로 처리하고 존재를 노출하지 않는다. role·권한 매트릭스 상세는 [`11`](./11-observability-and-governance.md).

---

## 2. 리소스 엔드포인트

각 표: `METHOD PATH · 설명 · 주요 파라미터 · 응답 개요`.

### 2.1 Investigations (조사 · Campaign)

blueprint §5.1(요청)·§5.2(결과)·§5.3(지속 관찰). 자연어 `question` + `scope`로 조사를 생성하고, 장시간 실행은 §5 job 패턴을 따른다.

| METHOD PATH | 설명 | 주요 파라미터 | 응답 개요 |
| --- | --- | --- | --- |
| `POST /v1/investigations` | 자연어 조사 생성 | body: `question`, `scope{time,region,source_type,depth}` | `202` + `inv-…` + `job-…` (§5) |
| `GET /v1/investigations/{id}` | 조사 메타·현재 상태 | — | Investigation 객체 |
| `GET /v1/investigations` | 조사 목록 | `?status=&owner=&cursor=&limit=` | cursor 페이지 |
| `POST /v1/investigations/{id}:cancel` | 실행 중 조사 취소 | — | `status=cancelled` |
| `GET /v1/investigations/{id}/status` | 조사 과정·비용·evidence coverage 진행률 | — | Progress 객체 (아래) |
| `GET /v1/investigations/{id}/report` | 조사 결과 보고서 | `?as_of_tx=` (bitemporal 재현) | Report 객체 (§3) |
| `POST /v1/investigations/{id}:register-continuous` | 지속 관찰 Campaign 등록 | body: `alert_thresholds{}` | Campaign 구독 객체 |

**`scope` 계약** — `depth`는 조사 budget·종료 조건과 연동된다 ([`07`](./07-llm-and-agents.md) 조사 루프).

```json
{
  "question": "2024년 이후 A사의 AI 가속기 공급망 다변화가 실제로 진행되었는지 조사하라. 공식 발표와 실제 계약·공시를 구분하고 반대 증거도 포함하라.",
  "scope": {
    "time": { "from": "2024-01-01", "to": null },
    "region": ["US", "KR", "TW"],
    "source_type": ["official", "exchange", "press", "gov"],
    "depth": "standard"
  }
}
```

- `depth` ∈ `quick` / `standard` / `deep`. `deep`일수록 반증 탐색·독립 출처 확인 반복이 늘고 비용·latency budget이 커진다.
- `source_type` 값은 온톨로지 `Source.source_type`([`02`](./02-ontology.md) §2.3)과 동일 vocabulary: `official`/`press`/`gov`/`research`/`exchange`.

**Progress 객체** (`GET …/status`) — 조사 과정·비용·evidence coverage를 노출한다 (blueprint §5.2, §12.4).

```json
{
  "investigation_id": "inv-01J9…",
  "status": "running",
  "current_step": { "agent": "counter_evidence", "subquestion": "복수 공급처 계약의 실제 집행 증거", "step_id": "step-014" },
  "evidence_coverage": { "subclaims_total": 8, "subclaims_covered": 5, "ratio": 0.63 },
  "cost": { "llm_usd": 2.41, "tokens_in": 812000, "tokens_out": 61000, "tool_calls": 47 },
  "budget": { "usd_limit": 8.0, "usd_used": 2.41, "time_limit_s": 1800, "time_used_s": 640 },
  "updated_at": "2026-08-03T04:12:00Z"
}
```

> 진행 표현 원칙: Agent 작업을 "신비한 예언"이 아니라 현재 하위 질문·탐색 경로·비용으로 투명하게 노출한다 (blueprint §1.4 피해야 할 방향).

### 2.2 Graph (War Table)

Knowledge Graph 조회. 스키마·라벨은 [`06`](./06-graph-service.md), 온톨로지는 [`02`](./02-ontology.md)가 정본. **read-only** — 그래프 변경은 API로 직접 하지 않는다 (불변식 §3-3, [`01`](./01-architecture.md) 경계 규칙).

| METHOD PATH | 설명 | 주요 파라미터 | 응답 개요 |
| --- | --- | --- | --- |
| `GET /v1/investigations/{id}/graph` | 조사 subgraph (progressive disclosure 시드) | `?focus=<node-id>&depth=1&as_of_valid=&as_of_tx=` | `{nodes[], edges[]}` + `truncated` |
| `GET /v1/graph/nodes/{node_id}` | 단일 노드 상세 | `?as_of_valid=&as_of_tx=` | Node 객체 |
| `GET /v1/graph/nodes/{node_id}/expand` | 인접 확장 (progressive disclosure) | `?edge_type=&direction=&limit=&cursor=` | 인접 `{nodes[],edges[]}` cursor |
| `GET /v1/graph/time-travel` | AS-OF 시간 질의 | `?as_of_valid=<ts>&as_of_tx=<ts>&focus=<node-id>&depth=` | 시점 재현 subgraph |

**Time-travel 계약** ([`03`](./03-storage-and-data-model.md) §6.3) — 두 시간 축을 독립 지정한다.

- `as_of_valid = T_v` → `valid_from ≤ T_v < valid_to` 인 assertion만 포함.
- `as_of_tx = T_t` → `tx_from ≤ T_t < (tx_to ?? ∞)` 인 버전만 포함.
- 두 파라미터 조합으로 "특정 관찰 시점(`T_t`) 기준, 특정 유효 시점(`T_v`)의 War Table 상태"를 재현한다. 노드를 삭제하지 않고 `valid`/`superseded` 상태를 edge에 표기한다 (시간 슬라이더 UI 계약, blueprint §6.4).

**Progressive disclosure 계약** — 대규모 그래프를 한 번에 반환하지 않는다 (blueprint §1.4 War Table 설계). subgraph 응답은 `focus` 노드 중심 `depth` 홉으로 제한되고, `truncated=true` + `expand` 링크로 점진 확장한다. 노드 `weight`는 조사 내 중요도·evidence coverage를 반영한다(시각적 인기가 아님).

### 2.3 Evidence (Hall of Witnesses)

claim → 근거(지지/반박), 원문 span·provenance trail. **결과 문장에서 원문까지 3회 이내 상호작용** 목표를 API 왕복 수로 보장한다 (blueprint §1.4 완료 기준 3).

| METHOD PATH | 설명 | 주요 파라미터 | 응답 개요 |
| --- | --- | --- | --- |
| `GET /v1/claims/{id}` | claim 상세 + confidence 다차원 | — | Claim + Confidence 객체 |
| `GET /v1/claims/{id}/evidence` | claim의 지지·반박 근거 | `?relation=supports\|contradicts&cursor=` | Evidence 목록(관계별) |
| `GET /v1/evidence/{id}/source-span` | 근거의 원문 구절 (1회 왕복) | — | source span + 문맥 |
| `GET /v1/evidence/{id}/provenance` | provenance trail (원문 왕복) | — | Trail 객체 (아래) |

**왕복 3회 계약 (blueprint §1.4-3):**

```text
1) GET /v1/investigations/{id}/report      → 결과 문장 + claim_ref
2) GET /v1/claims/{clm}/evidence           → 지지/반박 근거 목록 + evidence_ref
3) GET /v1/evidence/{evd}/provenance        → 원문 span·문서 버전·추출 모델까지
```

**Trail 객체** ([`03`](./03-storage-and-data-model.md) §8.1 provenance chain) — 그래프 요소 → 추출 기록 → 문서 버전 → source span → 원본 raw → source URL.

```json
{
  "evidence_id": "evd-01J9…",
  "relation": "supports",
  "strength": 0.8,
  "trail": [
    { "step": "extraction_record", "extraction_id": "ext-01J9…", "model_id": "claude-sonnet-5", "prompt_template_hash": "sha256:…", "schema_version": "0.1.0" },
    { "step": "document_version", "doc_id": "doc-2291…", "parser_version": "p-3", "publication_time": "2025-02-14T00:00:00Z" },
    { "step": "source_span", "segment_id": "doc-2291…#p42.s3", "char_start": 1180, "char_end": 1244, "text": "…substantially all of our AI accelerator components are sourced from a single supplier…" },
    { "step": "raw_document", "content_hash": "sha256:…", "raw_ref": "s3-presigned://…" },
    { "step": "source", "source_id": "src-01J9…", "url": "https://…", "fetched_at": "2025-02-15T09:00:00Z" }
  ]
}
```

### 2.4 Documents / Sources (Grand Archive)

문서 버전·출처 차원. 원문 bytes는 provenance presigned link로만 제공한다 (§1.1).

| METHOD PATH | 설명 | 주요 파라미터 | 응답 개요 |
| --- | --- | --- | --- |
| `GET /v1/documents/{doc_id}` | 문서 버전 메타 | — | Document 객체([`03`](./03-storage-and-data-model.md) §3.1) |
| `GET /v1/documents/{doc_id}/segments` | 문단·문장 segment | `?kind=&cursor=` | segment 목록(offset 포함) |
| `GET /v1/documents/{doc_id}/lineage` | 출처 계보(dup cluster) | — | root/derived/independent 분해 |
| `GET /v1/sources/{src_id}` | 출처 차원·독립성 | — | Source 객체 + `dimensions{}` |

- `dimensions{}`는 신뢰도를 단일 점수로 환원하지 않고 차원별로 노출한다 (blueprint §11): 직접 당사자 여부·1차/2차·인용 여부·정정 이력·이해관계·데이터 공개·독립 취득. 정본 정의는 [`11`](./11-observability-and-governance.md).
- `…/lineage`는 `dup_clusters`([`03`](./03-storage-and-data-model.md) §4.3)를 반환해 "복제 500건 = 독립 증거 2건" 보정의 근거를 제공한다.
- `independent_source_count`의 per-claim 보정 공식은 [`11`](./11-observability-and-governance.md) §1.4가 정본이며, prototype 구현(`assertion_evidence`)은 그 두 항(distinct root + 독립 추가)을 그대로 계산한다.
- provenance trail 의 claim step 은 authoritative claim 의 `ontology_version`(02 §2, MVP #3)을 함께 노출한다 — 검증 가능 문장이 원문 span·온톨로지 버전까지 감사되는 trail 완결.

### 2.5 Chronicle (Bitemporal Event Timeline)

사건·주장·시스템 인식의 변경 이력. bitemporal 두 축을 질의한다 ([`03`](./03-storage-and-data-model.md) §6).

| METHOD PATH | 설명 | 주요 파라미터 | 응답 개요 |
| --- | --- | --- | --- |
| `GET /v1/chronicle` | 이벤트 타임라인 질의 | `?subject=<node-id>&valid_from=&valid_to=&tx_from=&tx_to=&op=&cursor=` (`op` enum은 [`03`](./03-storage-and-data-model.md) §7.1: create_node/create_edge/merge_entity/unmerge/supersede/delete/quarantine) | 시간순 이벤트 목록 |
| `GET /v1/chronicle/{mutation_id}` | 단일 mutation 이벤트 | — | `graph_mutations` row([`03`](./03-storage-and-data-model.md) §7.1) |

- `op` 필터는 `create_node`/`create_edge`/`merge_entity`/`unmerge`/`supersede`/`delete`/`quarantine` ([`03`](./03-storage-and-data-model.md) §7.1 전 op 열거와 동일). `unmerge`는 merge_entity의 역이벤트로 감사·되돌림 추적에 포함된다 ([`06`](./06-graph-service.md) §3).
- 각 이벤트는 `actor`(`pipeline`/`llm:<model>`/`human:<user>`), `version_tuple`, `correlation_id`를 포함해 감사 가능하다.

### 2.6 Signal Spire (Alerts)

결론·confidence의 중요한 변화 알림. 등록된 지속 관찰 Campaign(§2.1 `:register-continuous`)이 트리거 소스다.

| METHOD PATH | 설명 | 주요 파라미터 | 응답 개요 |
| --- | --- | --- | --- |
| `GET /v1/alerts` | 알림 목록 | `?investigation=&severity=&unread=&cursor=` | Alert 목록 |
| `POST /v1/alerts/subscriptions` | 구독 생성(채널·임계값) | body: `investigation_id`, `channel{type,target}`, `triggers[]` | Subscription 객체 |
| `DELETE /v1/alerts/subscriptions/{sub_id}` | 구독 해제 | — | `204` |

**트리거 vocabulary** — 정본 enum은 [`11`](./11-observability-and-governance.md) §4.1(Signal Spire)이 소유한다. 값(blueprint §5.3): `contradicting_evidence`(기존 결론 반박 증거) / `claim_changed`(기존 주장 변경) / `plan_to_execution`(계획→실행 증거) / `new_independent_source`(독립 출처 추가) / `confidence_threshold`(confidence 임계값 이상 변동). `channel.type` ∈ `webhook`/`email`/`in_app`.

### 2.7 Watchtower / Health

source 신선도·backlog. **상세 지표·SLO·대시보드는 [`11`](./11-observability-and-governance.md)에 위임**하고, 본 API는 조사 UI가 필요로 하는 최소 상태만 노출한다.

| METHOD PATH | 설명 | 주요 파라미터 | 응답 개요 |
| --- | --- | --- | --- |
| `GET /v1/health` | 서비스 liveness/readiness | — | `{status, spec_version}` |
| `GET /v1/health/sources` | source 신선도·ingestion backlog 요약 | `?source_id=` | freshness·backlog 요약 (상세 → [`11`](./11-observability-and-governance.md)) |

---

## 3. 조사 결과 응답 스키마 (blueprint §5.2)

`GET /v1/investigations/{id}/report`의 계약. blueprint §5.2의 8개 결과 영역을 1:1로 담는다. **Evidence-first** 원칙(불변식 §3-5)에 따라 검증된 subgraph 범위 안의 문장만 포함한다.

| 영역 (blueprint §5.2) | 응답 필드 |
| --- | --- |
| 현재 결론 + confidence | `conclusion`, `confidence`(다차원, §4) |
| 사실·주장·추론·예측 구분 보고서 | `report.sections[].statements[].modality` |
| 주장별 지지·반박 증거 | `report.statements[].claim_ref` → §2.3 |
| 사건·주장 변화 타임라인 | `timeline[]` (bitemporal ref) |
| 출처 계보·독립성 | `source_independence` |
| 탐색 가능한 Evidence Graph | `evidence_graph_ref` |
| 아직 증거 부족한 질문 | `open_questions[]` |
| Agent 조사 과정·비용 | `agent_process`, `cost` |

```json
{
  "investigation_id": "inv-01J9…",
  "question": "2024년 이후 A사의 AI 가속기 공급망 다변화가 실제로 진행되었는지…",
  "as_of_tx": "2026-08-03T04:20:00Z",
  "conclusion": {
    "text": "A사의 공급망 다변화는 공식 발표 수준에서는 진행되었으나, 확인된 계약·공시로 뒷받침되는 실제 집행 증거는 제한적이다.",
    "confidence": {
      "value": 0.61,
      "evidence_count": 7,
      "independent_source_count": 2,
      "basis": "지지 근거 5건 중 4건이 동일 보도자료 파생 → 독립 출처 2건으로 집계. 반박 근거 1차 자료(공시) 1건 존재.",
      "dimensions": { "support": 0.72, "contradiction": 0.44, "coverage": 0.63 }
    }
  },
  "report": {
    "sections": [
      {
        "title": "공식 발표",
        "statements": [
          { "text": "A사는 2024-05 복수 공급처 확보를 발표했다.", "modality": "asserted", "claim_ref": "clm-01J9A…", "speaker_id": "org-01J9A…" }
        ]
      },
      {
        "title": "실제 집행",
        "statements": [
          { "text": "동일 기간 10-K는 '단일 공급자'에 사실상 전량 의존한다고 적시한다.", "modality": "fact", "claim_ref": "clm-01J9B…" },
          { "text": "다변화가 조달 안정성으로 이어질지는 추가 분기 공시로 확인이 필요하다.", "modality": "prediction", "claim_ref": null }
        ]
      }
    ]
  },
  "timeline": [
    { "valid_time": "2024-05-01", "observed_at": "2024-05-02T00:00:00Z", "claim_ref": "clm-01J9A…", "change": "asserted", "supersedes": null },
    { "valid_time": "2025-01-01", "observed_at": "2025-02-15T09:00:00Z", "claim_ref": "clm-01J9B…", "change": "contradicts", "supersedes": null }
  ],
  "source_independence": {
    "total_documents": 500,
    "root_clusters": 1,
    "independent_sources": 2,
    "note": "복제 기사 498건이 단일 보도자료에서 파생됨 (dup_cluster 근거)."
  },
  "evidence_graph_ref": "/v1/investigations/inv-01J9…/graph",
  "open_questions": [
    { "subquestion": "2025-H2 조달 계약의 실제 인도 실적", "reason": "공시 미확인", "coverage": 0.0 }
  ],
  "agent_process": {
    "steps": 21,
    "agents": ["planner", "graph_explorer", "retrieval", "evidence_extractor", "counter_evidence", "source_independence_judge", "synthesis", "audit"],
    "counter_evidence_searched": true,
    "stopping_reason": "coverage_and_diminishing_returns"
  },
  "cost": { "llm_usd": 3.02, "tokens_in": 940000, "tokens_out": 72000, "tool_calls": 51 },
  "version_tuple": { "ontology_version": "1.0.0", "schema_version": "0.1.0", "model_id": "claude-sonnet-5", "prompt_template_hash": "sha256:…" }
}
```

계약 세부:

- `report.sections[].statements[].modality`는 온톨로지 `Claim.modality`([`02`](./02-ontology.md) §5.3)와 동일 vocabulary(`fact`/`asserted`/`opinion`/`prediction`)로, **사실·주장·의견·예측을 명시적으로 분리**한다 (blueprint §5.2, §9.3 Synthesis/Audit). 모델 자체의 추론(inference)은 `modality` 값으로 신설하지 않는다 — evidence-first 원칙상 모델 추론은 별도 modality가 아니라 근거 구조(model_prior 플래그)로 처리하며, 4개 값 외 확장이 필요하면 [`02`](./02-ontology.md) §5.3 정본을 먼저 개정한다.
- `report.sections[].statements[].speaker_id`는 해당 문장의 발화 주체(node ID, 예: `org-…`)를 가리키는 선택 필드로, 보고서가 "누가 주장했는가"를 화자에 귀속시킬 때 채워진다. 화자 미상·시스템 종합 문장은 생략(부재)한다. 참조 대상은 그래프 노드(§2.2)다.
- 무출처 문장은 `claim_ref=null`이면서 `modality`가 `prediction`/`opinion`인 경우로만 허용되며, `fact`/`asserted`는 반드시 `claim_ref`(→ provenance)를 가진다 (Audit Agent 계약, blueprint §9.3, 불변식 §3-2).
- `timeline[].change`는 해당 시점 변화의 종류를 나타내는 enum: `asserted`(주장 최초 등장) / `contradicts`(반박 증거 등장) / `superseded`(이전 주장 대체) / `retracted`(철회). `supersedes`는 대체된 이전 claim ref(없으면 `null`). 시간축 의미는 [`03`](./03-storage-and-data-model.md) §6 bitemporal 정본을 따른다.
- `evidence_graph_ref`는 문서를 인라인하지 않고 War Table subgraph API(§2.2)를 가리켜 progressive disclosure를 유지한다.

---

## 4. Confidence 표현 계약 (다차원)

**단일 색 게이지를 금지**한다 (blueprint §1.4 접근성, §5.2, mockup `never a lone gauge`). confidence는 항상 다음을 함께 제공한다.

| 필드 | 필수 | 의미 |
| --- | --- | --- |
| `value` | ✓ | 집계 신뢰도 값 ∈ [0,1] |
| `evidence_count` | ✓ | 전체 근거 수 (지지+반박) |
| `independent_source_count` | ✓ | dup cluster 보정 후 독립 출처 수 |
| `basis` | ✓ | 계산 근거의 사람 읽는 설명 (독립성 보정·반박 존재 등) |
| `dimensions` | — | `support`/`contradiction`/`coverage` 등 분해 축 |

- 클라이언트는 `value` 하나만으로 UI를 구성해서는 안 된다. 최소 `value` + `evidence_count` + `independent_source_count` + `basis`를 함께 표시한다 (mockup의 3-cell + 독립성 보정 문구가 참조 구현).
- `value`는 source reputation이 아니라 **claim별 증거 구조**로 계산한다 (blueprint §11). 모델 자체 confidence 값만으로 사실을 확정하지 않는다 (blueprint §3.2 비목표).
- `confidence`(집계)와 개별 `Claim.confidence`(추출 모델 신뢰도)·`Claim.certainty`(화자 확실성)는 별개 축이다 ([`02`](./02-ontology.md) ADR-202).

---

## 5. 비동기 작업 (Job 패턴)

장시간 investigation·재처리는 동기 응답으로 기다리지 않는다 ([`01`](./01-architecture.md) S9, blueprint §5.2 "조사 과정" 노출).

### 5.1 흐름

```text
POST /v1/investigations           → 202 Accepted
  body: { investigation_id, job }
  header: Location: /v1/jobs/job-01J9…

GET  /v1/jobs/{job_id}            → 폴링 (status: queued|running|succeeded|failed|cancelled)
GET  /v1/investigations/{id}/status → 도메인 진행률(coverage·cost, §2.1)
```

```json
{
  "investigation_id": "inv-01J9…",
  "job": {
    "job_id": "job-01J9…",
    "status": "queued",
    "kind": "investigation",
    "poll_url": "/v1/jobs/job-01J9…",
    "result_url": "/v1/investigations/inv-01J9…/report",
    "created_at": "2026-08-03T04:05:00Z"
  }
}
```

### 5.2 완료 통지

- **Polling** — `GET /v1/jobs/{job_id}`. 응답에 `Retry-After` 힌트를 포함한다.
- **Webhook** — 조사 생성 시 `callback_url` 지정 시 완료·실패에 서명된 POST 콜백. `X-Citadel-Signature`(HMAC-SHA256) 검증 필수(§1.6).
- Job과 도메인 상태를 분리한다: `job.status`는 실행 수명주기, `investigation.status`+`Progress`(§2.1)는 조사 의미론(coverage·cost). 두 축은 독립 조회한다.
- Job 자체도 idempotent: 동일 `Idempotency-Key`의 재요청은 기존 `job_id`를 반환한다(중복 조사 생성 방지).

---

## 6. 의사결정 로그 (ADR-9xx)

| ID | 결정 | 근거 | 상태 |
| --- | --- | --- | --- |
| ADR-901 | 외부 계약을 **REST + JSON**으로 채택(GraphQL/RPC 아님) | 리소스 지향·캐시·페이지네이션 표준화, FastAPI 기본 정합([`01`](./01-architecture.md)); 그래프 조회는 subgraph+expand로 과대질의 통제 | Accepted |
| ADR-902 | 장시간 investigation은 **202 + job id + polling/webhook** 패턴 | 동기 대기 회피, 조사 과정·비용 투명 노출(blueprint §5.2), Agent 루프 latency 수용([`07`](./07-llm-and-agents.md)) | Accepted |
| ADR-903 | 경로·필드는 **기술 용어 우선**, 세계관 명칭은 표시 레이어 | UI 명칭 변경이 API를 깨지 않게 함([`README`](./README.md) §2.1, blueprint §1.4) | Accepted |
| ADR-904 | **Cursor 페이지네이션** 채택(offset 불가) | 대량 그래프·bitemporal 이벤트에서 안정 페이징, ULID 시간정렬 활용([`README`](./README.md) §2.2) | Accepted |
| ADR-905 | Confidence는 **다차원 봉투 필수**(단일 게이지 금지) | 신뢰도 과대평가·오해 방지(blueprint §1.4·§5.2·§11), mockup `never a lone gauge` | Accepted |
| ADR-906 | Graph API는 **read-only**, mutation 미노출 | event-driven mutation 불변식 §3-3, Agent·클라이언트의 직접 그래프 변경 차단([`01`](./01-architecture.md) 경계 규칙) | Accepted · **구현(P1 B)**: `ApiFacade.get_investigation_graph`가 investigation subgraph(§2.2 seed)+relation_paths+independence_summary 노출 (`prototype/orc_citadel/api_facade.py`, 2026-08-11) |
| ADR-907 | 원문 span→provenance를 **≤3 왕복**으로 보장하는 전용 엔드포인트 | 감사 가능성 완료 기준(blueprint §1.4-3), Hall of Witnesses UX | Accepted |
| ADR-908 | prototype은 `/api` mapping으로 durable investigation/job/cancel/polling을 제공하고 FastAPI를 도입하지 않는다 | 기존 stdlib runtime 유지 + 외부 `/v1` wire 계약의 수직 검증 | Accepted |
