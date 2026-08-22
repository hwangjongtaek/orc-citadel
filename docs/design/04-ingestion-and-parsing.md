# 04 · 수집·파싱 (Scouts · Archivists)

> **상태:** ✅ Stable · **Spec:** 1.0.0 · **Blueprint 매핑:** §8.1–§8.3
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
    "allow_store_raw": true,
    "allow_redistribute": false
  },
  "schedule": { "cron": "0 */6 * * *", "priority": "normal" },
  "enabled": true
}
```

- `source_type` ∈ `official`/`press`/`gov`/`research`/`exchange`. 초기 도메인(AI 반도체·데이터센터 공급망, [`README`](./README.md) §4)의 발행 주체 분류다.
- `compliance.license`는 수집 정책이자 [`03`](./03-storage-and-data-model.md) `fetch.json.license`로 전파된다. 재배포 게이트는 `compliance.allow_redistribute`(bool, 기본 `false`)로 선언하며, retention·재배포 강제는 [`11`](./11-observability-and-governance.md) §5.4 governance가 이 필드명을 인용해 수행한다. `allow_store_raw`는 raw bytes 저장 허용 여부, `allow_redistribute`는 원문·발췌의 외부 재배포 허용 여부로 분리한다.
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
| `gov` | **SEC EDGAR**, **CHIPS/NIST** 공시 | API(구조화 filing) → download(PDF/XBRL) | filing index cursor + `last_modified` | `gov-public` |
| `official` | 기업 IR·공식 블로그·보도자료 (초기: **NVIDIA Newsroom**) | RSS → sitemap → HTML | feed entry id + `content_hash` | `proprietary`(요약·인용 한정) |
| `press` | 뉴스·전문 매체 (초기: **SemiEngineering**) | RSS → sitemap | RSS pubDate + `content_hash` | `proprietary` |
| `research` | 논문·프리프린트 (**arXiv**) | API(메타+PDF) → download | API updated 필드 | `cc-by` 등 소스별 |
| `exchange` | 거래소·가격·시세 데이터 | API | API cursor/timestamp | 소스별(재배포 제한 주의) |

- **초기 Scout 5종**은 Phase 0에서 선정·확정된 세부 표를 §1.4에 둔다 (source config 구체 스키마·라이선스·접근 방식).
- 어떤 전략이든 `politeness`를 우회할 수 없다. rate limit 초과·`429`/`503`은 `backoff`(exponential + jitter)로 물러난 뒤 재시도한다(§6).
- **`sitemap` 1급 kind (2026-08-19, Spec 1.1.0):** RSS 를 노출하지 않는 정부 정책 사이트(예: **BIS 수출통제**)는 API·RSS 가 없어도 **sitemap.xml(정적 XML, robots `Allow`) 으로 수집 대상 URL 을 정적 열거**할 수 있다. §1.3 표의 "sitemap"(fallback) 을 1급 `SOURCES` kind 로 승격 — `SitemapConnector`(04 §1.2 discover/fetch 계약) + `collect_sitemap`. 변경 탐지는 sitemap `<lastmod>` + `content_hash`. robots 개방 확인 시 **headless·비용 불필요**, 기존 `_get`/`_save_zone`·URL-skip(S1)·content-hash(S2) 재사용.
- `download`(PDF/바이너리)는 원본 bytes를 그대로 S2에 저장하고 파싱은 S3로 미룬다. 수집 단계에서 본문을 재작성하지 않는다.

### 1.4 초기 Scout 5종 (Phase 0 선정)

미국 중심 AI 반도체·데이터센터 공급망 도메인의 최초 커넥터 세트. 전 source가 공식 API/RSS로 수집 가능하며(Easy), 라이선스 재배포는 전 source에서 제한한다(`allow_redistribute=false`, [`11`](./11-observability-and-governance.md) §5.4 정합). 구체·보류(候補)·추가 후보는 ROADMAP §6 Q1 해소 기록 참조.

| # | Source | `source_type` | 접근 | 라이선스 자세 | 변경 탐지 |
| --- | --- | --- | --- | --- | --- |
| 1 | **SEC EDGAR** | `gov` | 공식 API `efts.sec.gov`(full-text)·`data.sec.gov/submissions/{CIK}.json`(무료, no-key) | store·paraphrase 안전, 재배포 제한 | filing index cursor + `last_modified` |
| 2 | **arXiv** | `research` | 공식 API `export.arxiv.org/api/query` + **S3 bulk mirror** (metadata) | metadata **CC0**(재배포 가능), PDF는 연구용 저장만·재배포 제한 | API updated 필드 |
| 3 | **CHIPS/NIST** | `gov` | 공식 RSS `nist.gov/news-events/electronics/rss.xml` | `gov-public` | RSS pubDate + `content_hash` |
| 4 | **NVIDIA Newsroom** | `official` | 공식 RSS `nvidianews.nvidia.com/rss.xml` | store 허용, 재배포 제한 | RSS pubDate + `content_hash` |
| 5 | **SemiEngineering** | `press` | RSS `semiengineering.com/feed/` | store 허용, 재배포 제한(라이선스 문구 미검증) | RSS pubDate + `content_hash` |
| 6 | **AMD IR** | `official` | 공식 RSS `ir.amd.com/news-events/press-releases/rss` | store 허용, 재배포 제한(라이선스 문구 미검증) | RSS pubDate + `content_hash` |
| 8 | **Tom's Hardware** | `press` | RSS `tomshardware.com/feeds/all` | store 허용, 재배포 제한(라이선스 문구 미검증) | RSS pubDate + `content_hash` |

- **수집 제한 요약 (Phase 0 확인):**
  - SEC: **최대 10 req/sec**, 선언형 User-Agent 필수(`Name ContactEmail`), default HTTP client(WebFetch 포함)는 403 차단 → **curl + UA 사용**.
  - arXiv: **1 req/3초**, 단일 연결. metadata는 S3 bulk로 본문 제한 회피 가능.
  - 상업 테크 프레스(EE Times·The Register·TechCrunch)는 robots.txt가 **AI 크롤러(`anthropic-ai`/`ClaudeBot`)를 명시 차단** → Phase 0 초기 세트에서 제외. SemiEngineering만 개방.
  - **Tom's Hardware 개방 확인 (2026-08-22, A25):** robots `User-agent:*` 에서 아티클 본문 경로(`/tech-industry/`, `/pc-components/` 등) 크롤링 **허용**, 특정 AI 크롤러(bytespider·mistralai 등)만 별도 BLOCK — SemiEngineering 과 동류로 크롤러 UA 로 개방. The Register 는 **default-deny**(AI scraping licence 요구) 로 기각 유지.
  - TSMC 프로미스룸(`pr.tsmc.com`)은 Cloudflare 403 → 1차 세트 제외.
- **미확정 항목:** SEC 필링 내용의 정확한 법적 public-domain 프레이밍(SEC 저작권 페이지 404) · SemiEngineering/EE Times/TechCrunch 공식 라이선스 문구 — 실무상 store-only로 취급하고, 확정 시 `compliance.license`·`license_url` 갱신.
- **추가 후보(Phase 1+):** (AMD IR RSS는 2026-08-12 실신호 확장으로 **#6 정식 소스 승격** — robotics 열려있음, 결정적 extractor 공급망 신호 고밀도: 10건 수집 → claims +59·엣지 +21 실측, `signal_source_runner` `SIGNAL_SOURCE_IDS` 포함.)
- **BIS 수출통제 — sitemap 커넥터로 정식 채택 (2026-08-19, Spec 1.1.0, #7):** 이전 "RSS 없어 scraping Medium" 으로 유보됐으나, 실측로 **robots `Allow: /`(개방)·sitemap.xml(정적 37 URL) 존재** → RSS 없이도 sitemap 1급 kind 로 **수집 불가가 아님** 것으로 재평가. `gov-bis-exportcontrol`(`sitemap`, `https://www.bis.gov/sitemap.xml`) 등록·`SitemapConnector` 개발·`collect_sitemap` 배선. **실측 (A18, 2026-08-19):** sitemap 37 `<loc>` 전부 수집(정책·가이드 — country guidance·compliance·deemed exports 등), raw +37. **신호 수율 실측:** `signal_density` **0.000**(claims 0) — 정책 문서는 결정적 extractor 신호 희소, **`SIGNAL_SOURCE_IDS` 미포함**(A10 원칙 정합). **raw 수집 소스로 유효**(쿼리·조사 재료 정책 컨텍스트, 무중복 URL-skip). `sitemap.connecter` 계약은 §1.3·2.1 반영.
- **Tom's Hardware — 독립 언론 원문 소스 정식 채택 (2026-08-22, A25, Spec 1.1.0, #8):** 기존 소스셋(arXiv 논문 · 벤더 자사 공식 블로그 · BIS 정책 · SemiEngineering)의 공통 근본 한계는 **"상호 모순될 수 있는 관점이 없다"** — #4 contradiction·SLO-07 의 deferred 근본 원인. 같은 사건을 **벤더 자사와 독립·때로 비판적 관점**으로 보도하는 복수 뉴스/분석 소스를 추가해 모순 자연발생 경로를 연다 (A10 신호 밀도 원칙 정합, §6.2 빈 소스 노이즈 수집 억제). The Register 는 default-deny(AI scraping licence)로 기각, **Tom's Hardware 를 robots-개방 확인 후 채택**. `press-tomshardware`(`rss`, `https://www.tomshardware.com/feeds/all`) 등록 · 기존 `collect_rss` 계약 재사용(RSS → `_get` 본문 fetch → `_save_zone` content-hash). **실측 (A25):** TDD Green(스위트 1040→1041), raw 104,915→**104,920(+5)**(S1 URL-skip 45건 skip + 신규 5 저장, errors 0) · 누적 50건 `robots_allowed` 전부 True. **신호 밀도 실측:** 50건 중 ①수출통제/제재 5건(smic 가격인상·H200 중국수출 허가·Nvidia LPU 부인·Supermicro 밀수·Pixel 제조이전) + ②반도체 산업 13건 + ③AI인프라/DC 13건 — 절반 이상이 도메인 신호, **공식 nvidia(38건)와 URL 겹침 0 완전 독립**. → **#4 contradiction·SLO-07 실측 전환의 모순 재료 확보**(경로 해소 시작). `signals` 부착(벤더 자사 프레이밍 대비 관점)은 `SIGNAL_SOURCE_IDS` 판정 별도 — 신호 source 집합은 결정적 extractor 신호 기반이므로(RSS press semiengineering 등) 분류는 추후 실측. 계약·스키마 추가 없음(기존 RSS kind) → **Spec 1.1.0 유지**.
- **배선 상태 (2026-08-18, A9→A11 정정; 2026-08-22 A25 갱신):** `collect_large.SOURCES` 에 구현된 초기 소스는 NVIDIA(#4)·AMD(#6)·SemiEngineering(#5)·arXiv(#2)·SEC(#1) 이고 **#3 CHIPS/NIST 는 미배선 유지** (보류). **A18: `gov-bis-exportcontrol`(#7 sitemap) 추가 배선 — 정부 정책 소스** · **A25: `press-tomshardware`(#8 rss) 추가 배선 — 독립 언론 관점 소스**. **A9 런으로 #3 를 임시 배선했으나 A11 추적 검증으로 **content-hash dedup 결함** 발견 → **미배선 복귀·보류**. 근본 원인: `_save_zone` 의 doc_id 가 **content sha256** 이고(Hash 기반, 03 §7), **NIST 동적 페이지 본문이 매 요청 달라져** 매 런 hash 가 새로 발급 → 같은 URL이 doc_id 2개로 **중복 저장**(A11 실측: gov 80건 = 고유 40×2). A9"A9 의 "gov 신규 +40" 은 **중복 허수**였다(실은 40 고유 문서 2번 저장). 처리: 40 간 중복 doc 정리(80→40 고유) + `SOURCES` 제거. **근본 해결은 URL 기반 idempotency 키**(04 §2.1 `hash(source_id,url,fetch_window)`) 전환 — 계약·Spec 번프 수반, 별도 작업 전까지 **gov 보류**. Gov 는 raw 성장 잠재력이 있으나(gov-public·CHIPS법 정책 문서 40 고유 확보) dedup 미해결로 **현재 수집 불가**. **signal 스코프 (2026-08-18, A10, 그대로 유효):** `signal_density` — gov 40건 claims 1·density 0.025(=비신호 arXiv 수준) vs signal 3종 0.63~5.9 → **`SIGNAL_SOURCE_IDS` 미포함 유지**. details: ROADMAP §5 A9·A10.

## 2. Fetch stage (S1) 계약

blueprint §8.1. 입력은 `source config` + `DiscoveredRef`, 출력은 S2로 넘길 원본 bytes와 `fetch.json` 필드다.

### 2.1 Idempotency

- **idempotency key:** `hash(source_id, url, fetch_window)`([`01`](./01-architecture.md) §4 S1). 동일 소스·URL·수집 창(window)의 재실행은 동일 key로 중복 작업을 만들지 않는다(불변식 §3-6).
- `fetch_window`는 `discovery.fetch_window`에서 파생한 결정적 값이다. `incremental`은 커서 구간(예: `2025-02-15/2025-02-16`), `full`은 상수 토큰을 쓴다.
- S1의 idempotency는 "같은 창을 다시 긁지 않는다"를, S2의 idempotency(`doc_id`)는 "같은 bytes를 다시 저장하지 않는다"를 보장한다. 두 계층은 독립적이다.
- **구현 완료 (2026-08-19, A15 — Spec 1.0.0 유지):** S1 재수집 방지를 `collect_large` 에 전면 적용. `_stored_urls(source_id)` — 해당 소스의 기존 저장 URL 집합(read-only) · `collect_rss(..., known_urls=None)` — 제공 시 이미 저장된 URL 은 **재수집(fetch) 자체를 하지 않고 skip**(`counts["skipped"]++`, SLO-05 `record_collect` 미기록 — skip 은 fetch 아님, 성공률 분모 부적절). `main()` RSS 루프가 `known_urls=_stored_urls(source_id)` 로 배선. **실측 (A15):** nvidia known 37→skip 20·amd 10→skip 10·semi 41→skip 10, raw +0 (신규 없음, 중복 재수집 완전 차단) — 이전 A-runs 의 "saved:20" 이 실제로 같은 URL 재-fetch 였음을 확정. 2-tier 계약(S1 URL skip + S2 content-hash) 정합. arXiv 창-쿼리는 과거 연대 소진으로 URL-skip 보다는 기존 S2 dedup + 최신 windows 로 운용.

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
- 비교 기준이 되는 **직전 저장본의 `content_hash`·ETag**는 `url`별 최신 fetch 상태로 보관한다. 저장위치는 [`03`](./03-storage-and-data-model.md) §2.2 `fetch.json`(최신 `doc_id`) 및 소스 수집 상태(PostgreSQL, [`01`](./01-architecture.md) §5)이며, 조건부 GET 헤더 주입과 hash 비교의 입력이 된다.

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
- `table_cell`은 소속 표를 식별하는 **table anchor**(문서 내 표 순번 기반)와 셀의 **(row, col) 좌표**를 함께 보존해, 셀 값을 표 구조로 왕복 복원할 수 있게 한다(round-trip). 좌표·anchor의 물리 컬럼은 [`03`](./03-storage-and-data-model.md) §3.2가 정본이다.
- 각주 참조(본문의 상첨자)와 각주 본문은 문서 내에서 유일한 **footnote marker key**(각주 표식 + 문서 내 등장 순번)로 연결한다. `order` 단독이 아니라 이 key로 참조↔본문을 결합해 다중 각주·재사용 표식에서도 provenance 왕복을 깨지 않는다.

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
- ②는 shingle 기반 MinHash(또는 SimHash) LSH로 후보 쌍을 좁힌 뒤, 애매 구간만 embedding cosine으로 보강한다. 구체 임계값(shingle k·MinHash perm·LSH band/row·Jaccard cutoff·embedding cosine)과 방법 선택은 ADR-403(초기 placeholder, 실측 조정).
- ③은 ②가 "가깝지만 동일하지 않다"고 남긴 후보 쌍에만 LLM을 호출해 **문서↔문서** 파생/인용/독립 관계를 판정한다. LLM 호출은 version tuple([`README`](./README.md) §2.3)을 부착한다. 여기서 판정하는 것은 dedup 목적의 doc-level 계보뿐이며, claim 단위 인용(citation) 추출은 [`11`](./11-observability-and-governance.md) cite-extractor가 소유한다(S4 level③ ≠ claim-level citation).

### 4.2 dup_clusters 산출

blueprint §8.3의 `root source`/`derived sources`/`independent additions`를 [`03`](./03-storage-and-data-model.md) §4.3 컬럼으로 매핑한다. 각 cluster는 `cluster_id`(`clus-<ULID>`, [`README`](./README.md) §2.2, [`03`](./03-storage-and-data-model.md) §4.3)로 식별된다.

| 개념(blueprint) | `dup_clusters` 컬럼(03) | 의미 |
| --- | --- | --- |
| (cluster 식별자) | `cluster_id` | `clus-<ULID>` (출처 계보 클러스터 ID) |
| root source | `root_doc_id` | 근원 문서(가장 이른 공개 시각·원 발행 주체 우선) |
| derived sources | `member_doc_ids[]` | 근원에서 파생된 복제·재작성 문서 |
| independent additions | `independent_addition_doc_ids[]` | 파생이지만 **독립적 추가 정보**를 가진 문서 |

- **root 선정 규칙:** 최선의 `publication_time`(가장 이른) + `source_type` 신뢰(official/gov 우선). 동률은 결정적 tie-break(`doc_id` 사전순)로 재현성을 보장한다.
- **independent_addition_doc_ids 분류 기준:** cluster 멤버(파생) 문서 중 root_source의 span에 **없는 새 claim/span**을 담거나, 별도 root_source 계보로 **독립 취득**된(재인용이 아닌 자체 취재·자체 데이터) 정보를 귀속시키는 문서만 이 배열에 넣는다. 단순 재작성·번역·전재는 파생일 뿐 독립 추가가 아니다. 이 판정은 S4 dedup 산출물이므로 `dedup_version`에 바인딩되고 `doc_id+dedup_version` idempotency key(§4, [`01`](./01-architecture.md) §4 S4) 하에 결정적으로 재생성된다.
- **member vs independent 관계:** `independent_addition_doc_ids[]` ⊆ `member_doc_ids[]`(독립 추가 정보를 가진 파생 문서의 **부분집합**)이며, `root_doc_id`는 두 배열 어디에도 포함하지 않는다(disjoint).
- **"복제 500건을 독립 500으로 세지 않음"(축소만 담당):** S4는 각 cluster를 **root_source 기여 단위**(1개 root_source + 독립 추가 기여)로 **축소**하는 것까지만 소유한다. 04는 per-claim 독립 증거 공식을 자체 정의하지 않는다 — `independent_evidence_count`의 per-claim 집계와 "새 증거를 더하는지(adds new evidence)" 한정자는 [`11`](./11-observability-and-governance.md) §1.4가 정본이며, API 노출 필드명은 `independent_source_count`([`09`](./09-api.md))다. cluster 축소 결과(root + `independent_addition_doc_ids[]`)가 그 집계의 입력이 된다.
- 새 문서가 기존 cluster에 편입되면 `dedup_version` 하에 cluster를 **재계산(recompute)**한다. `doc_id`·raw bytes는 불변([`03`](./03-storage-and-data-model.md) §2)이지만 `dup_clusters` 자체는 append-only가 아니라 `dedup_version` 하에서 재생성되는 curated 산출물이다(같은 `dedup_version`은 동일 cluster를 결정적으로 재생성).

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
- **version 구성·bump 트리거:** `parser_version`은 문단/문장 분할 규칙·분할기 pin·정규화(offset 매핑) 로직의 조합을 식별하며, 그중 어느 하나라도 바뀌면 상향한다(→ 재파싱, §3.3). `dedup_version`은 3수준 판정 파라미터(ADR-403 임계값·MinHash/LSH 설정·LLM 판정 프롬프트/모델)의 조합을 식별하며, 어느 하나라도 바뀌면 상향한다(→ cluster 재생성, §4.2). 두 버전은 결정적이어서 동일 버전은 동일 산출물을 낸다.
- **Backoff:** 일시 오류(네트워크·`429`/`5xx`)는 exponential backoff + jitter(`politeness.backoff`)로 재시도한다. rate limit은 소스별 토큰버킷을 넘지 않는다.
- **Dead-letter:** 재시도 예산 소진, 영구 오류(파싱 불가·인코딩 판정 실패·`4xx` non-retryable)는 원본 bytes·오류 컨텍스트·correlation ID와 함께 dead-letter로 보낸다. **원본은 절대 유실하지 않으며**(raw는 immutable, [`03`](./03-storage-and-data-model.md) §2), 재처리는 `parser_version`/`dedup_version` 상향 후 동일 key로 안전하게 재실행한다.
- 실패한 문서는 authoritative graph로 진입하지 않는다. provenance/파싱이 불완전한 element는 quarantine 경로([`03`](./03-storage-and-data-model.md) §8.3, [`05`](./05-resolution-and-extraction.md))로 격리한다.

## 7. 의사결정 로그

| ID | 결정 | 근거 | 상태 |
| --- | --- | --- | --- |
| ADR-401 | `doc_id`는 내용 기반 `sha256(raw_bytes)[:24]`, 변경분은 새 `doc_id`로 전부 보존 | S2 idempotency + 버전 추적([`README`](./README.md) §2.2, [`03`](./03-storage-and-data-model.md) ADR-301) | Accepted |
| ADR-402 | S1 idempotency key = `hash(source_id, url, fetch_window)`, S2 idempotency(`doc_id`)와 분리 | 수집 창 중복 방지와 bytes 중복 저장 방지를 독립 계층으로(불변식 §3-6) | Accepted |
| ADR-403 | near-dup은 MinHash/SimHash LSH로 후보 축소 후 애매 구간만 embedding 보강. 초기 임계값은 아래 placeholder로 고정하고 golden set 실측으로 조정 | LLM 없이 저비용 정밀, 임계값 튜닝 가능(blueprint §8.3) | Accepted · **구현(P1 A)**: `Deduplicator`를 `run_pipeline`에 배선해 `dup_clusters` 영속 + 결정적 cluster_id(`sorted(members)+dedup_version`) (`prototype/orc_citadel/dedup.py`·`pipeline_runner.py`, 2026-08-11) |
| ADR-404 | LLM 의미적 파생 판정은 near-dup이 남긴 후보 쌍에만 계단식 호출(S4 수준 ③) | LLM 비용 통제 + 재현성(version tuple 부착) | Accepted |
| ADR-405 | 파싱 실패·인코딩 판정 실패는 dead-letter로 보내되 raw bytes는 유실 없이 보존, 버전 상향 후 재처리 | immutable raw 불변식·재현성([`03`](./03-storage-and-data-model.md) §2, 불변식 §3-1) | Accepted |

### ADR-403 near-dup 파라미터 (초기값 · 실측 조정)

아래 값은 **placeholder(초기 기본값)**이며 golden dedup set 기준 precision/recall 실측으로 조정한다. 확정 시 `dedup_version`을 상향한다(§6). 값 변경은 재현성상 반드시 `dedup_version`에 반영된다.

| 파라미터 | 초기값(placeholder) | 역할 |
| --- | --- | --- |
| shingle k (word n-gram) | `k = 5` | 문서 표면을 shingle 집합으로 변환하는 토큰 창 크기 |
| MinHash 순열 수 (perm) | `128` | Jaccard 추정 정밀도 ↔ 비용 트레이드오프 |
| LSH band × row | `b = 16`, `r = 8` (`b·r = 128`) | 후보 쌍 recall 튜닝(작은 r = 높은 recall·많은 후보) |
| Jaccard cutoff | `≥ 0.80` | LSH 후보 중 near-dup으로 승인하는 표면 유사도 하한 |
| embedding cosine (보강 확정) | `≥ 0.90` | 애매 구간에서 near-dup 확정 임계 |
| embedding cosine (③ LLM 회부) | `[0.82, 0.90)` | 확정도 배제도 아닌 구간 → 수준 ③(LLM) 후보로 전달 |

- 위 값은 초기 도메인(§1.3)·언어(§3.5)별로 달라질 수 있으므로 source_type·language 축으로 별도 튜닝할 수 있다. 최종값은 [`10`](./10-evaluation-and-testing.md) golden set 회귀로 검증한다.

> **Q2 실측(2026-08-03) 근거:** 초기 수집 395문서의 MinHash Jaccard 분포를 측정한 결과, intra-source·inter-source 모두 **0.5~0.7 구간에 겹쳐 첨두**(각 median ≈0.63/0.61)를 이루고 진짜 복제만 0.9+ (근접 쌍 J=1.0이 실제 중복)였다. 즉 단일 MinHash 임계로는 0.80~0.90 애매 구간에서 near-dup 독립성을 신뢰 판정할 수 없다. prototype은 **minhash-only 병합 회선을 0.90**(위 표의 "embedding cosine 보강 확정"에 해당)으로 사용해 확실한 복제만 병합하고, 애매 구간은 수준 ③(embedding/LLM)로 위임한다 — 위 3-tier 설계와 정합. (구) 0.6 임계는 동 데이터에서 오결합 후보 5152쌍을 유발함을 확인. 최종 확정은 [`10`](./10-evaluation-and-testing.md) golden dedup 회귀로 갱신한다.

> **구현 메모 (Phase 5 — signal source adaptive scheduling, 2026-08-12):** `signal_scheduler.py` — 10M Challenge 수집 병목에서 **신호 수율 기반 예산 배분**을 봉인 (수확 근거 = `signal_source_runner` 메모리 — arXiv abstract 에 비해 전용 반도체/공급망 언론 본문이 신호 고밀도). **수율 지표(§1.3 정합):** `signal_density(docs, claims, edges) = (claims+edges)/docs`, `trailing_signal_density` = 과거 run 누적(문서 수 가중). **예산 배분(핵심, read-only·결정적):** `allocate_signal_budget` — 각 소스 **floor(min_docs, 기본 `DEFAULT_MIN_DOCS=1`) 피보장**(§5 freshness — 어느 소스도 멸종 방지), 잉여만 수율 비례 배분, 예산 희소 시 floor 비례 축소(전체 보존). **미측정 소스는 잉여 제외(min 만)/전 미측정은 균등**(honest-gap §6.2, 신호 근거 부재 오판 방지). **freshness(§5 지표):** `freshness_lag` = 최신 수집 vs 기대 주기 → lag·overdue, 수집 이력/기대 주기 부재는 None(미측정). **주기 우선순위(§1.1 `schedule.priority`):** `cadence_priority` — density ≥ `HIGH_DENSITY_THRESHOLD=2.0` → high, < `LOW_DENSITY_THRESHOLD=0.2` → low, 미측정 → normal(보수적). `adaptive_schedule` — 히스토리 → trailing 수율 → 배분 + priority·lag 부착 일괄 산출. **스케줄은 산출물일 뿐 — 실제 수집 실행·큐 기록은 호출자 몫(read-only §3-3).** 임계는 placeholder(golden set 실측 조정, §1.1 정합). **스키마·계약 변경 없음 → Spec 그대로(0.1.9).** TDD — `test_signal_scheduler` 신규 38개(수율·배분 floor/비례/희소/미측정·freshness·주기·오케스트레이션·read-only·결정성) — 스위트 747→**785개 통과**(회귀 0). 다음: Phase 5 는 hot/cold graph 분리(06).
