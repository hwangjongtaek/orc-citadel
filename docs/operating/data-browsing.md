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

prod 는 전 서비스 loopback 이고, **minio·neo4j·opensearch·postgres 는 호스트
publish 자체가 없다** (docker-compose.prod.yml `ports: !override []`).
`scripts/tunnel.sh` 가 두 경우를 함께 처리한다 — publish 있는 것은 원격 loopback
으로, 없는 것은 **컨테이너 IP** 로 포워딩한다 (원격이 Linux+bridge 라 호스트에서
컨테이너 IP 가 라우팅된다 — 실측). 컨테이너 IP 는 재생성마다 바뀌므로 접속할
때마다 원격에서 조회한다.

```bash
scripts/tunnel.sh hwangjongtaek@10.0.0.11                 # 전체, 포그라운드 (Ctrl-C 종료)
scripts/tunnel.sh hwangjongtaek@10.0.0.11 duckdb minio    # 지정 타깃만
scripts/tunnel.sh hwangjongtaek@10.0.0.11 all --daemon    # 백그라운드 (PID 파일)
scripts/tunnel.sh --status                                # 열린 포트 실측
scripts/tunnel.sh --stop
```

| 타깃 | 로컬 포트 | 접속 |
|---|---|---|
| `viewer` | 18791 | http://127.0.0.1:18791 |
| `grafana` | 3000 | http://localhost:3000 |
| `duckdb` | 4213 | http://localhost:4213 — **반드시 localhost·4213** (§3 Origin 함정) |
| `minio` / `minio-api` | 9001 / 9000 | http://localhost:9001 (로그인은 원격 `.env`) |
| `neo4j` / `neo4j-bolt` | 7474 / 7687 | http://localhost:7474 — 브라우저가 bolt 로 붙으므로 둘 다 필요 |
| `opensearch` | 9200 | http://localhost:9200/_cat/indices?v |
| `postgres` | 15432 | `psql -h 127.0.0.1 -p 15432` (로컬 5432 와 충돌 회피) |

이미 점유된 로컬 포트는 건너뛴다 — 수동으로 띄워둔 뷰어 터널과 공존한다.
자격증명은 스크립트가 다루지 않는다 (SoT 는 원격 `.env`).

> 정직 표기 (2026-09-18 prod 실측): **MinIO 는 비어 있다.** nightly 수집은
> raw 를 파일시스템 미러(`/app/data/raw`, proddata 볼륨)에만 쓴다 —
> `collect_large._store()` 의 `minio_store` 주입이 nightly 경로에 없다. MinIO
> Console 터널은 열리지만 버킷에 오브젝트가 없다. raw 원형을 지금 보려면
> `docker compose exec prototype ls /app/data/raw/<source_id>/doc` 쪽이다.
