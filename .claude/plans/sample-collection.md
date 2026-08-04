# 1만 문서 샘플 확보 계획 — Scout 커넥터 (Phase 0, design 04)

## 목표
prototype에 Scout 커넥터를 얹어 실제 소스를 일부 수집해 **Phase 0 "1만 문서 샘플" 경로를 검증**한다.
- 범위: **커넥터 구현(TDD) + 소량 실수집**(신호 검증). 전량 1만 건은 별도 실행.
- 저장: **prototype raw 3-zone** 확장(설계 03 §2 immutable raw + fetch.json, DuckDB/Parquet 메타).

## 대상 소스 (Scout 5종, 04 §1.4)
1. SEC EDGAR (`gov`) — 공식 API `efts.sec.gov` + `data.sec.gov`
2. arXiv (`research`) — `export.arxiv.org/api/query`
3. CHIPS/NIST (`gov`) — `nist.gov/news-events/electronics/rss.xml`
4. NVIDIA Newsroom (`official`) — `nvidianews.nvidia.com/rss.xml`
5. SemiEngineering (`press`) — `semiengineering.com/feed/`

## 구현 (prototype 확장)
```
prototype/orc_citadel/
  connectors/
    __init__.py
    base.py            # DiscoveredRef/FetchResult/SourceConnector 추상 (04 §1.2)
    sec_edgar.py       # full-text search API discover+fetch
    arxiv.py           # api query discover+fetch
    rss.py             # 공용 RSS discover+fetch (CHIPS/NVIDIA/SemiEngineering 재사용)
  fetch.py             # robots·rate limit·backoff 공통 프레임워크 (04 §1.2)
tests/
  test_connectors.py   # 모의 응답으로 discover→fetch 계약 검증 (TDD)
```

## 검증 가능한 목표 (TDD)
1. **discover→fetch 계약** — 각 커넥터가 설계 04 §1.2 `DiscoveredRef`/`FetchResult` 계약 준수 (모의 응답)
2. **idempotent 저장** — 동일 문서 재수집 시 중복 raw/doc_id 없음 (기존 raw_store 재사용)
3. **robots·rate limit 준수** — fetch 프레임워크가 politeness 적용 (모의)
4. **소량 실수집** — 각 소스 최소 1건 fetch 성공, raw 3-zone 저장 확인

## 작업 순서 (TDD)
1. **Red** — `test_connectors.py` 실패 테스트 (모의 응답, 계약 검증)
2. **Green** — 커넥터 + fetch 프레임워크 최소 구현
3. **Refactor** — 구조 갈무리
4. **소량 실수집 검증** — 실제 네트워크에서 각 소스 1~n건 수집, raw 저장 확인(금지: 전량)

## 도구/제약
- 네트워크 수집은 **소량만** (rate limit·robots 준수, politeness)
- 의존성: `requests`(HTTP) 추가 필요 (uv로 설치), 기존 duckdb·pytest 유지
- SEC는 UA 필수(10 req/s), arXiv 1 req/3s — politeness 보장

## 성공 기준
- 커넥터 계약 테스트 Green
- 각 소스 최소 1건 실수집 → raw 3-zone 저장 검증
- 로컬 샘플은 .gitignore 대상이므로 커밋 제외(코드만 커밋)
