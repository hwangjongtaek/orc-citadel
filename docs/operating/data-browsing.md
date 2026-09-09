# 데이터 존 브라우징 가이드 (TS-7 · FR-7)

> 존 계층별 저장 형식을 **그대로** 들여다보는 체험 도구 안내. 뷰어(8791)가
> 브리핑 UI라면, 여기 도구들은 저장 계층을 원형으로 만지는 쪽이다.

## 1. 존 계층 → 저장 형식 → 도구 매핑

| 존 (design 01 §5) | 저장 형식 | 브라우징 도구 | 포트 |
|---|---|---|---|
| raw | MinIO 오브젝트 (`raw/<source>/...`) + 로컬 미러 `prototype/data/raw/` | **MinIO Console** (내장) | 9001 |
| normalized (`oc.duckdb`) | DuckDB → **parquet 스냅샷** | **DuckDB UI** 사이드카 | 4213 |
| curated (`curated.duckdb`) | DuckDB → **parquet 스냅샷** | **DuckDB UI** 사이드카 | 4213 |
| SoT 운영 로그·런 메트릭 | PostgreSQL (`graph_mutations`·`pipeline_run_metrics`…) | **Grafana** Explore (read-only 계정) | 3000 |
| 그래프 투영 | Neo4j | **Neo4j Browser** (내장) | 7474 |
| 검색 인덱스 | OpenSearch | **OpenSearch API/Dashboards** (내장) | 9200 |

접근 정책은 전부 viewer 와 동일 — **loopback 바인딩 + SSH 터널**. 인증 신설 없음.

> 뷰어 **Watchtower(`/watchtower`)의 Components 패널**이 위 도구들의 도달성
> (뷰어 프로세스 TCP 연결 실측)과 접속 링크를 한곳에 제공한다 — 링크는 접속
> host 로 런타임 조립되며, DuckDB UI 만 `localhost` 강제(§3 Origin 함정).

## 2. ⚠ 규칙: `.duckdb` 직접 attach 금지

외부 도구(DuckDB CLI·UI·DBeaver 등)로 `oc.duckdb`·`curated.duckdb` 를 **직접
열지 않는다.** 뷰어가 curated 를 RW 로 상시 점유하고(`viewer._build`), DuckDB
는 프로세스 간 단일 writer XOR 다중 reader 라 잠금 충돌이 실측으로 재현된다
(뷰어 500 또는 도구 열기 실패 — arXiv 수집기 운영에서 이미 겪은 함정).

대신 **parquet 스냅샷**(`prototype/data/parquet/<zone>/`)만 읽는다:

- 스냅샷은 nightly 수집 런 종료 시 자동 갱신 (`scheduler_runner` 훅, 16a).
- 원자 교체(`<zone>.new` → live, 직전은 `.bak`) — 읽는 중 반쯤 교체 없음.
- 즉시 재수출이 필요하면 수동 1회 (105k 문서 전량 ~1초):

```bash
# 로컬
prototype/.venv/bin/python -m orc_citadel.parquet_snapshot
# prod (컨테이너)
docker compose ... exec scheduler python -m orc_citadel.parquet_snapshot
```

DuckDB UI 사이드카도 같은 규칙으로 지어졌다 — 컨테이너에는 parquet 디렉터리만
read-only 마운트라 `.duckdb` 는 **볼 수조차 없다** (§3-3 존 오염 불가).

## 3. DuckDB UI (normalized·curated 존)

```bash
docker compose up -d duckdb-ui        # 로컬 — 이미지 빌드 시 1회 네트워크
```

접속: **`http://localhost:4213`** — 반드시 `localhost` 로. ui 확장이 Origin 을
검증해 `127.0.0.1` 로 열면 모든 쿼리가 401 이 난다 (실측).

왼쪽 `browse` DB 아래 존별 스키마(`normalized`·`curated`)로 뷰가 떠 있다.
뷰는 `read_parquet()` 경유라 스냅샷이 갱신되면 다음 쿼리부터 새 내용을 본다
(새 테이블·존이 *추가*된 경우만 `docker compose restart duckdb-ui`).

> 정직 표기: 이 사이드카의 UI 프런트 자산은 확장이 원격(ui.duckdb.org)에서
> 가져온다 — **런타임 네트워크 필요**. "외부 CDN 금지"는 뷰어 프런트 불변식이고,
> 이 도구는 운영 편의 사이드카라 예외다. 또한 구버전 duckdb CLI 는 최신 프런트와
> 프로토콜이 어긋나 Initialization Error 가 난다(v1.3.2 실측) — Dockerfile 핀을
> 낮추지 말 것.

### 복붙 예제 쿼리 (전부 실측 검증됨)

**① 원문 왕복 — 소스별 문서·세그먼트 분해 (segments 조인)**

```sql
SELECT d.source_id, count(DISTINCT d.doc_id) AS docs, count(*) AS segments
FROM normalized.documents d
JOIN normalized.segments s ON s.doc_id = d.doc_id
GROUP BY 1 ORDER BY docs DESC;
```

**② dedup cluster — 같은 사건을 말하는 문서 스택**

```sql
SELECT c.cluster_id, c.dedup_method, c.root_doc_id,
       len(c.member_doc_ids) AS members,
       len(c.independent_addition_doc_ids) AS independent
FROM curated.dup_clusters c
ORDER BY members DESC LIMIT 20;
```

**③ assertion → 근거 문장 drill-down (provenance lineage)**

```sql
SELECT a.assertion_id, a.predicate, a.tx_from,
       cc.doc_id, cc.surface_fragment, cc.extraction_model
FROM curated.assertions a
JOIN curated.claim_candidates cc ON cc.claim_candidate_id = a.claim_id
WHERE a.predicate = 'supplies'
LIMIT 20;
```

**④ bitemporal as-of 재료 — 현재 믿음 집계**

```sql
SELECT predicate, count(*) AS assertions,
       count(*) FILTER (WHERE tx_to IS NULL) AS current_belief
FROM curated.assertions
GROUP BY 1 ORDER BY assertions DESC;
```

## 4. MinIO Console (raw 존)

```bash
open http://localhost:9001            # 로컬 — 로그인: .env 의 MINIO_ROOT_USER/PASSWORD
```

버킷 → `raw/<source_id>/...` 오브젝트를 직접 열람. 수집 원문(HTML)과
`fetch.json` governance 메타가 그대로 있다.

## 5. Grafana Explore (SoT 운영 로그·메트릭)

`http://localhost:3000` → Explore → `Citadel Postgres` datasource. 계정이
read-only(`grafana_reader`)라 메트릭 테이블 SELECT 만 가능 — 그래프 SoT
테이블은 권한 자체가 없다. 대시보드·접근 절차는 [deployment.md](deployment.md) §3.4.

## 6. Neo4j Browser / OpenSearch (내장 UI)

- Neo4j Browser: `http://localhost:7474` (bolt 7687, 로그인 `.env` 의 `NEO4J_PASSWORD`).
- OpenSearch: `http://localhost:9200` REST 직접 조회 (`GET /_cat/indices?v`).

둘 다 컨테이너 내장 — 별도 구축 없음. prod 는 포트 publish 가 제거돼 있어
(§deployment) `docker compose exec` 또는 터널로만.

## 7. prod 접근 (SSH 터널)

prod 는 전 서비스 loopback — 필요한 포트만 터널로 끌어온다:

```bash
ssh -N -L 4213:127.0.0.1:4213 orchwang-macbookpro   # DuckDB UI → http://localhost:4213
ssh -N -L 3000:127.0.0.1:3000 orchwang-macbookpro   # Grafana   → http://localhost:3000
ssh -N -L 9001:127.0.0.1:9001 orchwang-macbookpro   # MinIO Console (publish 없음 — 필요 시 compose 조정)
```

DuckDB UI 는 터널이어도 브라우저 주소가 `localhost` 라 Origin 검증을 그대로
통과한다. prod 사이드카는 proddata 볼륨의 `parquet` subpath 만 read-only
마운트 — 첫 스냅샷(nightly 런 또는 수동 1회)이 만들어진 뒤 기동해야 한다.
