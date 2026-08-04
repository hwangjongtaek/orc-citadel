# S14 SEC EDGAR 커넥터 완성 (04 §1.3·§1.4 gov)

> 권장안 1 선택. 현재 스텁(`discover`→`iter(())`)인 SecEdgarConnector를 정식 구현해
> gov 소스를 추가한다. 대상: [04-ingestion-and-parsing](../../docs/design/04-ingestion-and-parsing.md) §1.3·§1.4,
> connector 계약(§1.2)·11 §5.4(allow_redistribute=false).

## 배경·범위

| 결정 | 근거 |
| --- | --- |
| **`data.sec.gov/submissions/{CIK}.json` discover** (`gov` filing index) | 04 §1.4 공식 API (no-key, 무료). filing index cursor + last_modified |
| **선언형 User-Agent 강제** (`Name ContactEmail`) | 04 §1.4: 필수, 기본 HTTP client 403 → UA 주입 |
| **≤10 req/s politeness** | 04 §1.4 최대 제한 |
| **robots_respect: true** | 04 §1.4.json/§1.3 — FetchFramework robots 평가 |
| **CIK 후보 상수 사전** | 04 §1.4 대상: 대형 반도체·데이터센터 (NVDA 1045810, TSM 1046179) |
| **idempotent 저장·allow_redistribute=false** | 03 §2.1 content-hash + 11 §5.4 |

## 구현 계획

- **`sec_edgar.py`** (수정): 
  - `discover`: CIK → `submissions/{CIK}.json` → filing index (accessionNumber·primaryDocument·reportDate) yield `DiscoveredRef` (last_modified=reportDate).
  - `fetch`: primaryDocument URL → 접근자 (UA 주입, filing 원문).
  - **선언 UA 헤더** 강제 (테스트에서 검증).
- **rate limit**: FetchFramework(rps≤10)로 — 커넥터는 파싱만 (04 §1.3 프레임워크 분리 유지).
- **`curated/collect`**: collect_large에 SEC 소스 추가 (gov → source_id `gov-sec-edgar`).
- **TDD**: UA 헤더 강제·filing index 파싱·last_modified→hint·idempotent 저장 (오프라인).
- 라이브: 소량 실증 (CIK 1·2개 → filings 몇 건) — 대량은 politeness 따라 사용자/러너.

## DoD

- SecEdgarConnector.discover가 CIK submissions에서 filing ref를 yield (URL·last_modified)
- fetch가 UA 주입 + filing 원문, idempotent (content-hash)
- rate limit ≤10 req/s, robots_respect=true, allow_redistribute=false
- TDD 오프라인 + 라이브 소량 실증, 전체 테스트 통과, code-only 커밋

## 한계 (문서화)

- **발생 실물은 PDF/XBRL** — content.bin에 원문 저장, parse(extract_html)는 HTML이 아니라
  여전히 PDF라 S3 본문 추출은 후속 (04 §1.4 filing → PDF)
- CIK 후보 사전은 소수 상수 + 확장 — SE의 EDGAR 회사 검색으로 완전화 후속
- SEC full-text(efts)는 require key 아님 — submissions API 우선
