# 04 · 수집·파싱 (Scouts · Archivists)

> **상태:** Draft · **Spec:** 0.1.0 · **Blueprint 매핑:** §8.1–§8.3
> 상위 규약: [README](./README.md) · 관련: [01-architecture](./01-architecture.md), [03-storage](./03-storage-and-data-model.md), [05-resolution](./05-resolution-and-extraction.md)

허용된 소스에서 문서를 수집(Fetch)하고, 원문을 손실 없이 정규화(Parse/Normalize)하며, 복제·파생을 출처 계보로 축소(Dedup)하는 파이프라인 전반(stage S1·S3·S4)을 확정한다. 본 문서는 커넥터 모델과 세 stage의 계약을 소유하며, 저장 스키마·ID 체계는 [`03`](./03-storage-and-data-model.md)을, 추출·해소(S5–S6)는 [`05`](./05-resolution-and-extraction.md)를 정본으로 참조한다.

**stage 소유 범위:** S1(Fetch), S3(Parse/Normalize), S4(Dedup). S2(Store raw)의 객체 레이아웃·`fetch.json` 스키마는 [`03`](./03-storage-and-data-model.md) §2가 소유하며, 본 문서 S1이 그 필드를 채운다. 모든 stage는 `(input_ref, idempotency_key, version_tuple)` → `(output_ref, correlation_id)` 계약([`01`](./01-architecture.md) §4)을 따른다.

## 1. Scouts (Source connectors) 커넥터 모델

blueprint §8.1. Scouts는 외부 세계에서 자료를 가져오는 수집 주체다. 소스별 접근 방식·권한·rate limit 차이를 **선언적 source config**와 **단일 connector 인터페이스**로 흡수한다.

### 1.1 Source config 스키마

각 소스는 하나의 config 레코드로 등록되며, `source_id`(`src-<ULID>`, [`README`](./README.md) §2.2)로 식별된다. config는 curated 메타데이터가 아니라 수집 정책이므로 PostgreSQL 메타데이터에 둔다([`01`](./01-architecture.md) §5).

```json
{
  "source_id": "src-01J9...",
  "name": "SEC EDGAR",
  "source_type": "gov",
  "access": {
    "strategy": "api",
    "base_url": "https://data.sec.gov/",
    "auth": { "kind": "none | api_key | oauth", "secret_ref": "env:SEC_API_KEY" }
  },
  "discovery": {
    "mode": "api | rss | sitemap | download",
    "seeds": ["https://www.sec.gov/cgi-bin/browse-edgar?..."],
    "fetch_window": { "kind": "incremental | full", "cursor_field": "last_modified" }
  },
  "politeness": {
    "robots_respect": true,
    "rate_limit": { "rps": 5, "concurrency": 2 },
    "backoff": { "base_ms": 500, "max_ms": 60000, "jitter": true },
    "user_agent": "OrcCitadel-Scout/0.1 (+contact)"
  },
  "compliance": {
    "license": "gov-public | cc-by | proprietary",
    "license_url": "https://...",
    "allow_store_raw": true
  },
  "schedule": { "cron": "0 */6 * * *", "priority": "normal" },
  "enabled": true
}
```

- `source_type` ∈ `official`/`press`/`gov`/`research`/`exchange`. 초기 도메인(AI 반도체·데이터센터 공급망, [`README`](./README.md) §4)의 발행 주체 분류다.
- `compliance.license`는 수집 정책이자 [`03`](./03-storage-and-data-model.md) `fetch.json.license`로 전파되며, retention·재배포 게이트는 [`11`](./11-observability-and-governance.md) governance가 강제한다.
- `robots_respect: false`는 라이선스가 명시적으로 허용한 소스에 한해 ADR로만 승인한다. 수집 권한·라이선스 우회 크롤러는 명시적 비목표다(blueprint §비목표).

### 1.2 Connector 인터페이스 (Python 추상)

모든 커넥터는 아래 추상을 구현한다. `discover → fetch`의 2단계로, discover는 대상 URL을 열거하고 fetch는 단일 URL의 bytes를 가져온다. **네트워크 접근과 저장을 분리**해 fetch를 idempotent·재실행 가능하게 유지한다.

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Iterator, Mapping

@dataclass(frozen=True)
class DiscoveredRef:
    url: str
    hint_modified: datetime | None      # RSS/sitemap이 알려주는 변경 힌트 (없으면 조건부 GET로 확인)
    extra: Mapping[str, str]            # ETag, feed entry id 등

@dataclass(frozen=True)
class FetchResult:
    url: str
    content: bytes                      # 원본 bytes (수정 금지 대상)
    content_hash: str                   # "sha256:..."
    http_status: int
    response_headers: Mapping[str, str]
    fetched_at: datetime                # UTC
    unchanged: bool = False             # 304 또는 content_hash 불변 → 재저장 불필요

class SourceConnector(ABC):
    source_type: str                    # official | press | gov | research | exchange

    @abstractmethod
    def discover(self, config: "SourceConfig", cursor: str | None) -> Iterator[DiscoveredRef]:
        """API/RSS/sitemap을 우선 사용해 수집 대상 URL을 열거한다. robots·rate limit 준수는 프레임워크가 강제한다."""

    @abstractmethod
    def fetch(self, ref: DiscoveredRef, prior_etag: str | None) -> FetchResult:
        """단일 URL을 조건부 GET(If-None-Match/If-Modified-Since)으로 가져온다. 재시도 안전해야 한다."""

    def next_cursor(self, refs: Iterator[DiscoveredRef]) -> str | None:
        """incremental fetch_window를 위한 다음 커서(예: 최대 last_modified). 기본은 None(full)."""
        return None
```

- robots 파싱, rate limit 토큰버킷, backoff, `User-Agent` 주입은 **커넥터 밖의 공통 fetch 프레임워크**가 담당한다. 커넥터는 소스별 discover 규칙과 응답 파싱만 구현한다.
- `unchanged=True`면 S2는 no-op(동일 `doc_id`)이 되어 하위 stage를 트리거하지 않는다(§2.2).

### 1.3 source_type별 수집 전략

blueprint §8.1의 우선순위 **API › RSS › sitemap › download**를 source_type별로 구체화한다. 위 순서는 안정성·구조화도·서버 부하 순이며, 상위 수단이 없을 때만 하위로 내려간다.

| source_type | 대표 소스 | 우선 strategy | 변경 탐지 | 라이선스 기본값 |
| --- | --- | --- | --- | --- |
| `gov` | SEC/공정위/규제기관 공시 | API(구조화 filing) → download(PDF/XBRL) | filing index cursor + `last_modified` | `gov-public` |
| `official` | 기업 IR·공식 블로그·보도자료 | RSS → sitemap → HTML | feed entry id + `content_hash` | `proprietary`(요약·인용 한정) |
| `press` | 뉴스·전문 매체 | RSS → sitemap | RSS pubDate + `content_hash` | `proprietary` |
| `research` | 논문·프리프린트(arXiv 등) | API(메타+PDF) → download | API updated 필드 | `cc-by` 등 소스별 |
| `exchange` | 거래소·가격·시세 데이터 | API | API cursor/timestamp | 소스별(재배포 제한 주의) |

- 어떤 전략이든 `politeness`를 우회할 수 없다. rate limit 초과·`429`/`503`은 `backoff`(exponential + jitter)로 물러난 뒤 재시도한다(§6).
- `download`(PDF/바이너리)는 원본 bytes를 그대로 S2에 저장하고 파싱은 S3로 미룬다. 수집 단계에서 본문을 재작성하지 않는다.

## 2. Fetch stage (S1) 계약

blueprint §8.1. 입력은 `source config` + `DiscoveredRef`, 출력은 S2로 넘길 원본 bytes와 `fetch.json` 필드다.

### 2.1 Idempotency

- **idempotency key:** `hash(source_id, url, fetch_window)`([`01`](./01-architecture.md) §4 S1). 동일 소스·URL·수집 창(window)의 재실행은 동일 key로 중복 작업을 만들지 않는다(불변식 §3-6).
- `fetch_window`는 `discovery.fetch_window`에서 파생한 결정적 값이다. `incremental`은 커서 구간(예: `2025-02-15/2025-02-16`), `full`은 상수 토큰을 쓴다.
- S1의 idempotency는 "같은 창을 다시 긁지 않는다"를, S2의 idempotency(`doc_id`)는 "같은 bytes를 다시 저장하지 않는다"를 보장한다. 두 계층은 독립적이다.

### 2.2 Content hash 기반 변경 탐지 → 새 doc_id

```text
fetch(url) → content_hash 계산
   ├─ 직전 저장본과 동일 hash (또는 HTTP 304) → unchanged, 파이프라인 트리거 안 함
   └─ 다른 hash → 변경 감지
         └─ doc_id = "doc-" + sha256(raw_bytes)[:24]   ← 새 버전은 새 doc_id (03 §2.1)
               → S2가 raw/source_id=…/doc_id=…/ 에 content.bin + fetch.json 저장
               → S3(parse) 신규 트리거
```

- **새 버전 → 새 `doc_id`:** 동일 `url`의 변경분은 덮어쓰지 않고 새 `doc_id`로 **모두 보존**한다([`03`](./03-storage-and-data-model.md) §2.2 불변식, ADR-301). `doc_id`가 내용 기반([`README`](./README.md) §2.2, ADR-001)이므로 동일 bytes 재수집은 동일 객체 → S2 idempotent.
- 변경 탐지는 조건부 GET(ETag/Last-Modified)로 대역폭을 아끼고, 최종 판정은 항상 `content_hash`로 한다(헤더가 거짓말해도 hash가 진실).

### 2.3 `fetch.json` 필드 채움

S1은 [`03`](./03-storage-and-data-model.md) §2.2가 소유하는 `fetch.json` 스키마를 채운다. 채움 규칙만 아래에 고정하고 스키마 원본은 [`03`](./03-storage-and-data-model.md)이 정본이다.

| 필드 | 채움 규칙(S1) |
| --- | --- |
| `doc_id` | `"doc-" + sha256(content)[:24]` |
| `source_id` | source config에서 |
| `url` | `FetchResult.url` |
| `content_hash` | `FetchResult.content_hash` |
| `fetched_at` | `FetchResult.fetched_at`(UTC ISO-8601) |
| `http_status` / `response_headers` | HTTP 응답 그대로 |
| `license` | `config.compliance.license` 전파 |
| `robots_allowed` | discover 시점 robots 평가 결과 |
| `fetch_correlation_id` | S1 correlation ID([`11`](./11-observability-and-governance.md)) |

## 3. Parse/Normalize stage (S3)

blueprint §8.2. 입력은 raw `doc_id`, 출력은 normalized zone의 `documents`·`segments` row([`03`](./03-storage-and-data-model.md) §3)다. **idempotency key:** `doc_id + parser_version`([`01`](./01-architecture.md) §4 S3) — 파서가 바뀌면 재파싱하되 `segment_id`는 안정적으로 유지된다.

### 3.1 메타데이터 분리

- 본문·**제목**·**저자**·**공개 시각**(`publication_time`)·**수정 시각**(`revision_time`)을 분리해 `documents`에 채운다.
- 시각은 UTC ISO-8601로 정규화하고, 부분/미상은 `null` + `time_precision`으로 표현한다([`README`](./README.md) §2.4). 없는 값을 추정으로 채우지 않는다(허위 정밀도 금지).

### 3.2 표·각주 유실 금지

blueprint §8.2. 표와 각주는 본문에서 제거하지 않고 **구조를 보존한 segment**로 저장한다.

- `segments.kind` ∈ `paragraph`/`sentence`/`table_cell`/`footnote`([`03`](./03-storage-and-data-model.md) §3.2). 표는 `table_cell` 단위로, 각주는 `footnote`로 보존해 셀 값·각주 본문이 추출(S5) 대상 span이 될 수 있게 한다.
- 각주 참조(본문의 상첨자)와 각주 본문은 `order`로 연결해 provenance 왕복을 깨지 않는다.

### 3.3 문단·문장 ID 안정 생성 (segment_id 결정성)

- `segment_id = <doc_id>#p<par>.s<sent>` — **결정적**([`03`](./03-storage-and-data-model.md) §3.2). 문단 인덱스 `par`와 문장 인덱스 `sent`는 문서 내 순서(`order`)에서 파생하며, 동일 입력·동일 `parser_version`은 동일 `segment_id`를 낸다.
- 결정성 조건: (1) 문단 분할·문장 분할 규칙이 `parser_version`에 고정, (2) 언어별 문장 분할기가 버전 pin, (3) 인덱스는 0-base 순번. 이 성질은 offset mapping unit test 대상이다([`10`](./10-evaluation-and-testing.md)).
- `parser_version`이 오르면 인덱싱이 달라질 수 있으므로 `doc_id`와 함께 재파싱하며, 옛 버전 segment는 재현성을 위해 폐기하지 않는다.

### 3.4 원문↔정규화 offset 양방향 매핑

blueprint §8.2, ADR-302. 각 segment는 **원문(raw) 기준 offset**과 **정규화 텍스트 기준 offset**을 함께 보존한다([`03`](./03-storage-and-data-model.md) §3.2 `char_start`/`char_end`/`norm_char_start`).

```text
정규화 텍스트 span (norm_char_start..)  ⇄  원문 raw span (char_start..char_end)
```

- 왕복 보장: 추출된 claim/evidence의 정규화 span을 항상 원문 raw span으로 역매핑할 수 있어야 하며(provenance chain, [`03`](./03-storage-and-data-model.md) §8.1), 그 역도 성립한다.
- 정규화(공백 축약·엔티티 디코딩·유니코드 NFC)로 문자 수가 바뀌므로 단순 offset 이동이 아니라 **구간 매핑 테이블**을 유지한다. 매핑 손실은 해당 segment를 quarantine 사유로 본다.

### 3.5 언어·인코딩 감지

- 인코딩은 HTTP 헤더 → 문서 선언(meta charset/BOM) → 통계적 감지 순으로 확정하고, 실패 시 원문 bytes를 보존한 채 S3를 실패 처리(§6)한다. 원본은 절대 유실하지 않는다.
- 언어 감지 결과는 `documents.language`([`03`](./03-storage-and-data-model.md) §3.1)에 저장하며, 문장 분할기·near-dup 임베딩 모델 선택의 입력이 된다.

## 4. 중복·출처 계보 stage (S4)

blueprint §8.3. 입력은 normalized `doc_id`, 출력은 curated `dup_clusters` row([`03`](./03-storage-and-data-model.md) §4.3)다. **idempotency key:** `doc_id + dedup_version`([`01`](./01-architecture.md) §4 S4). 복제 문서를 하나의 근원으로 축소해 **독립 증거 수 과대평가를 막는다**(blueprint §18 위험표, 불변식 관련 원칙).

### 4.1 3수준 판정

비용·정밀도 순으로 계단식(cascade)으로 적용한다. 상위 수준에서 결론 나면 하위를 호출하지 않는다.

| 수준 | 방법 | 판정 | `dedup_method` | 근거 |
| --- | --- | --- | --- | --- |
| ① exact | content hash 완전 일치 | 동일 bytes = 동일 문서(사실상 재수집) | `content_hash` | 결정적, 무비용 |
| ② near | MinHash/SimHash **또는** embedding near-dup | 표면 거의 동일한 복제·미세수정 | `minhash` / `embedding` | 임계값 기반, LLM 미사용 |
| ③ semantic | LLM 의미적 파생·인용 관계 판정 | 재작성·번역·인용 등 의미적 파생 | `llm` | 고비용, 후보 쌍에만 |

- ①은 사실상 S2 단계에서 `doc_id` 동일성으로 이미 흡수된다. S4는 서로 다른 `doc_id` 사이의 관계를 다룬다.
- ②는 shingle 기반 MinHash(또는 SimHash) LSH로 후보 쌍을 좁힌 뒤, 애매 구간만 embedding cosine으로 보강한다. 임계값·방법 선택은 ADR-403.
- ③은 ②가 "가깝지만 동일하지 않다"고 남긴 후보 쌍에만 LLM을 호출해 파생/인용/독립을 판정한다. LLM 호출은 version tuple([`README`](./README.md) §2.3)을 부착한다.

### 4.2 dup_clusters 산출

blueprint §8.3의 `root source`/`derived sources`/`independent additions`를 [`03`](./03-storage-and-data-model.md) §4.3 컬럼으로 매핑한다.

| 개념(blueprint) | `dup_clusters` 컬럼(03) | 의미 |
| --- | --- | --- |
| root source | `root_doc_id` | 근원 문서(가장 이른 공개 시각·원 발행 주체 우선) |
| derived sources | `member_doc_ids[]` | 근원에서 파생된 복제·재작성 문서 |
| independent additions | `independent_addition_doc_ids[]` | 파생이지만 **독립적 추가 정보**를 가진 문서 |

- **root 선정 규칙:** 최선의 `publication_time`(가장 이른) + `source_type` 신뢰(official/gov 우선). 동률은 결정적 tie-break(`doc_id` 사전순)로 재현성을 보장한다.
- **"복제 500건을 독립 500으로 세지 않음":** 하나의 보도자료에서 파생된 복제 기사 500건은 **1개 근원 + N개 독립 추가**로 카운트한다([`03`](./03-storage-and-data-model.md) §4.3, blueprint §8.3·§11). 독립 증거 수 = 1(root) + |independent_addition_doc_ids|. 이 값이 하류 confidence·evidence 카운팅([`05`](./05-resolution-and-extraction.md), [`06`](./06-graph-service.md))의 근거다.
- 새 문서가 기존 cluster에 편입되면 `dedup_version` 하에 cluster를 재계산하되, cluster/`doc_id`는 불변 원칙을 지킨다(관계 갱신은 append 방식).

## 5. Watchtower (Ingestion monitor) 지표 개요

blueprint §11·§14. Scouts·S1–S4의 건전성을 감시한다. **지표 정의·SLO·대시보드·알림 라우팅의 정본은 [`11`](./11-observability-and-governance.md)**이며, 여기서는 수집·파싱이 배출하는 지표군만 명시한다.

| 지표군 | 의미 | 배출 stage |
| --- | --- | --- |
| freshness | source별 최신 수집 시각 vs 기대 주기(`schedule.cron`) 지연 | S1 |
| backlog | ingestion queue 적체·미처리 문서 수 | S1→S3→S4 |
| failure | fetch/parse/dedup 실패율, dead-letter 유입률 | S1·S3·S4 |

- 모든 stage 이벤트는 공통 correlation ID로 end-to-end 추적된다([`01`](./01-architecture.md) §1, [`11`](./11-observability-and-governance.md)). 상세·임계값은 [`11`](./11-observability-and-governance.md)에 위임한다.

## 6. 실패·재시도

불변식 §3-6(Idempotency). 모든 stage는 idempotency key로 재실행 안전하며, retry해도 동일 결과를 중복 생성하지 않는다.

- **Idempotent 재실행:** S1은 `hash(source_id,url,fetch_window)`, S3는 `doc_id+parser_version`, S4는 `doc_id+dedup_version`로 재실행을 흡수한다. 부분 실패 후 재시도는 이미 완료된 단위를 no-op 처리한다.
- **Backoff:** 일시 오류(네트워크·`429`/`5xx`)는 exponential backoff + jitter(`politeness.backoff`)로 재시도한다. rate limit은 소스별 토큰버킷을 넘지 않는다.
- **Dead-letter:** 재시도 예산 소진, 영구 오류(파싱 불가·인코딩 판정 실패·`4xx` non-retryable)는 원본 bytes·오류 컨텍스트·correlation ID와 함께 dead-letter로 보낸다. **원본은 절대 유실하지 않으며**(raw는 immutable, [`03`](./03-storage-and-data-model.md) §2), 재처리는 `parser_version`/`dedup_version` 상향 후 동일 key로 안전하게 재실행한다.
- 실패한 문서는 authoritative graph로 진입하지 않는다. provenance/파싱이 불완전한 element는 quarantine 경로([`03`](./03-storage-and-data-model.md) §8.3, [`05`](./05-resolution-and-extraction.md))로 격리한다.

## 7. 의사결정 로그

| ID | 결정 | 근거 | 상태 |
| --- | --- | --- | --- |
| ADR-401 | `doc_id`는 내용 기반 `sha256(raw_bytes)[:24]`, 변경분은 새 `doc_id`로 전부 보존 | S2 idempotency + 버전 추적([`README`](./README.md) §2.2, [`03`](./03-storage-and-data-model.md) ADR-301) | Accepted |
| ADR-402 | S1 idempotency key = `hash(source_id, url, fetch_window)`, S2 idempotency(`doc_id`)와 분리 | 수집 창 중복 방지와 bytes 중복 저장 방지를 독립 계층으로(불변식 §3-6) | Accepted |
| ADR-403 | near-dup은 MinHash/SimHash LSH로 후보 축소 후 애매 구간만 embedding 보강 | LLM 없이 저비용 정밀, 임계값 튜닝 가능(blueprint §8.3) | Accepted |
| ADR-404 | LLM 의미적 파생 판정은 near-dup이 남긴 후보 쌍에만 계단식 호출(S4 수준 ③) | LLM 비용 통제 + 재현성(version tuple 부착) | Accepted |
| ADR-405 | 파싱 실패·인코딩 판정 실패는 dead-letter로 보내되 raw bytes는 유실 없이 보존, 버전 상향 후 재처리 | immutable raw 불변식·재현성([`03`](./03-storage-and-data-model.md) §2, 불변식 §3-1) | Accepted |
