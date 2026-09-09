"""S32 뷰어 — 실데이터를 브라우저로 직접 확인하는 read-only 개발 서버 (stdlib).

FastAPI·신규 의존 없이 `http.server`로 S32 API 파사드(09 §2/§3 wire 계약)를
서빙한다. 조회 전용(read-only, 불변식 §3-3) — 쓰기 엔드포인트 없음.

결정적·재현: 커리티드 존(curated.duckdb)을 읽어 subject 랭킹(S31)·조사 보고서(S30)·
claim 근거(S29)를 HTML로 렌더링한다.

실행:  .venv/bin/python -m orc_citadel.viewer     # http://127.0.0.1:8791
"""
from __future__ import annotations

import json
import os
import pathlib
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

from orc_citadel import viewer_static
from orc_citadel.api_facade import ApiFacade
from orc_citadel.curated_zone import CuratedZone
from orc_citadel.graph_service import GraphService

# 컨테이너에서는 VIEWER_HOST=0.0.0.0 으로 외부 바인딩 (docker-compose.yml).
HOST, PORT = os.environ.get("VIEWER_HOST", "127.0.0.1"), 8791
DB = pathlib.Path(__file__).resolve().parent.parent / "data" / "curated.duckdb"
RAW_DIR = DB.parent / "raw"          # raw zone flat 파일 (설계 03 §2.1)
NORM_DB = DB.parent / "oc.duckdb"    # normalized zone DuckDB (03 §3)

# JSON serialization — datetime/tuple을 str로.
def _j(fn):
    def wrap(*a, **k):
        return json.dumps(fn(*a, **k), default=str, ensure_ascii=False)
    return wrap


def _count_raw(raw_dir: str) -> tuple[list[dict], int]:
    """raw 존 파일 트리(source/doc/<doc_id>)에서 source×문서 수를 센다 (read-only).

    디렉터리 수로만 세어 파일 I/O·파싱 없이 결정적·가볍게. 미존재 시 빈 목록.
    10만+ 문서 디렉터리 stat 은 요청당 0.3s 라 `_fetch_records` 와 같은 클래스 레벨
    캐시를 쓴다 (페이지 이동마다 재스캔 금지 — 수집이 돌면 뷰어 재시작으로 갱신).
    """
    cache = Handler._RAW_COUNT_CACHE
    key = str(pathlib.Path(raw_dir).resolve()) if raw_dir else ""
    hit = cache.get(key)
    if hit is not None:
        return [dict(s) for s in hit[0]], hit[1]
    raw_dir = pathlib.Path(raw_dir)
    out: list[dict] = []
    if raw_dir.is_dir():
        for source in sorted(p.name for p in raw_dir.iterdir() if p.is_dir()):
            doc_dir = raw_dir / source / "doc"
            n = sum(1 for d in doc_dir.iterdir() if d.is_dir()) if doc_dir.is_dir() else 0
            out.append({"source_id": source, "doc_count": n})
    total = sum(s["doc_count"] for s in out)
    cache[key] = (out, total)
    return [dict(s) for s in out], total


def _fetch_records(raw_dir: str) -> list[dict]:
    """raw 존 fetch.json 전수 스캔 (1회·클래스 레벨 캐시 — 렌더마다 재스캔 금지).

    각 문서 디렉터리의 fetch.json 에서 실측된 키만 담는다 (fetched_at·http_status·
    robots_allowed). 파싱 실패·미존재는 정직 스킵. 캐시 키는 절대경로 문자열.
    """
    cache = Handler._FETCH_CACHE
    key = str(pathlib.Path(raw_dir).resolve()) if raw_dir else ""
    hit = cache.get(key)
    if hit is not None:
        return hit
    out: list[dict] = []
    root = pathlib.Path(raw_dir) if raw_dir else None
    if root is not None and root.is_dir():
        for source in sorted(p.name for p in root.iterdir() if p.is_dir()):
            doc_dir = root / source / "doc"
            if not doc_dir.is_dir():
                continue
            for doc in sorted(p.name for p in doc_dir.iterdir() if p.is_dir()):
                fj = doc_dir / doc / "fetch.json"
                try:
                    meta = json.loads(fj.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if not isinstance(meta, dict):
                    continue
                out.append({
                    "source_id": source,
                    "doc_id": meta.get("doc_id") or doc,
                    "url": meta.get("url"),
                    "fetched_at": meta.get("fetched_at"),
                    "http_status": meta.get("http_status"),
                    "robots_allowed": meta.get("robots_allowed"),
                })
    cache[key] = out
    return out


def _intake_panel(raw_dir: str, window_hours: int = 24) -> dict:
    """Watchtower intake — fetch.json 실측 도착 계측 (read-only·결정적).

    최근 fetched_at 기준 window_hours 시간 버킷(1시간 간격) 도착 수. fetched_at
    이 하나도 없으면 measured=False 정직 (honest-gap §6.2). 버킷 라벨은 UTC ISO.
    """
    import datetime as _dt
    recs = [r for r in _fetch_records(raw_dir) if r["fetched_at"]]
    parsed = []
    for r in recs:
        try:
            t = _dt.datetime.fromisoformat(r["fetched_at"])
        except ValueError:
            continue
        if t.tzinfo is None:
            t = t.replace(tzinfo=_dt.timezone.utc)
        parsed.append((t, r))
    per_source: dict[str, tuple[object, str]] = {}
    for t, r in parsed:
        prev = per_source.get(r["source_id"])
        if prev is None or t > prev[0]:
            per_source[r["source_id"]] = (t, r["fetched_at"])
    last_fetch_by_source = [
        {"source_id": s, "fetched_at": v[1]}
        for s, v in sorted(per_source.items())]
    if not parsed:
        return {"measured": False, "window_hours": window_hours,
                "arrivals_per_hour": [], "last_fetch_by_source": [],
                "note": "fetch.json 에 fetched_at 없음 → intake 미측정 (honest-gap §6.2)"}
    latest = max(t for t, _ in parsed)
    start = latest.replace(minute=0, second=0, microsecond=0) - \
        _dt.timedelta(hours=window_hours - 1)
    buckets = {}
    for t, _ in parsed:
        b = t.replace(minute=0, second=0, microsecond=0)
        if start <= b <= latest:
            buckets[b] = buckets.get(b, 0) + 1
    arrivals = [{"bucket": (start + _dt.timedelta(hours=i)).isoformat(),
                 "count": buckets.get(start + _dt.timedelta(hours=i), 0)}
                for i in range(window_hours)]
    return {"measured": True, "window_hours": window_hours,
            "arrivals_per_hour": arrivals,
            "last_fetch_by_source": last_fetch_by_source}


def _count_normalized(norm_db: str) -> dict:
    """normalized zone 문서·segment 수 (read-only 연결 — 잠금 충돌 회피).

    read_only=True 로 열어 수집 파이프라인과 동시 실행해도 잠금이 안 건다.
    DB 미존재 시 0 (honest-gap).
    """
    import duckdb
    try:
        c = duckdb.connect(str(norm_db), read_only=True)
    except Exception:
        return {"documents": 0, "segments": 0}
    try:
        docs = c.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        segs = c.execute("SELECT COUNT(*) FROM segments").fetchone()[0]
    except Exception:
        docs = segs = 0
    finally:
        c.close()
    return {"documents": docs, "segments": segs}


# design 02 §2.3 — Source.source_type vocab (source_id 접두사에서 결정적 파생).
_SOURCE_TYPE_TOKENS = ("official", "press", "gov", "research", "exchange")


def _source_type(source_id: str) -> str:
    """source_id 의 접두사 → source_type. 미인식은 'source'(정직)."""
    head = source_id.split("-", 1)[0]
    return head if head in _SOURCE_TYPE_TOKENS else "source"


def _freshness(norm_db: str) -> dict:
    """normalized 문서 publication_time 기준 실측 신선도 (분) — 없으면 not-measured.

    가짜 지연을 채우지 않는다: publication_time 이 하나도 없으면 measured=False.
    """
    import datetime as _dt
    import duckdb
    try:
        c = duckdb.connect(str(norm_db), read_only=True)
    except Exception:
        return {"measured": False, "note": "normalized DuckDB 미가동 (honest-gap §6.2)"}
    try:
        rows = c.execute(
            "SELECT publication_time FROM documents "
            "WHERE publication_time IS NOT NULL").fetchall()
    except Exception:
        rows = []
    finally:
        c.close()
    times = [r[0] for r in rows if r[0]]
    if not times:
        return {"measured": False, "note": "publication_time 없음 → 지연 미측정 (honest-gap §6.2)"}
    now = _dt.datetime.now(_dt.timezone.utc)
    ages = []
    for t in times:
        if t.tzinfo is None:
            t = t.replace(tzinfo=_dt.timezone.utc)
        ages.append((now - t).total_seconds() / 60.0)
    ages.sort()
    return {
        "measured": True, "n": len(ages),
        "min_age_min": round(ages[0], 1),
        "median_age_min": round(ages[len(ages) // 2], 1),
        "max_age_min": round(ages[-1], 1),
    }


def _slo_panel() -> dict:
    """Watchtower SLO 판정표 — 관측 없음(런 간 미누적)을 honest-gap 으로 노출.

    SLO 관측은 in-memory(영속 저장소 없음)라 런 간 누적되지 않는다. 이 뷰어는
    가짜 측정값을 채우지 않고 nightly 5 SLO 를 전부 `not-measured` 로 나열하고,
    error budget 은 `run_nightly_gate({})`(실측 없음)의 정직 결과를 쓴다.
    """
    from orc_citadel.slo_nightly_gate import NIGHTLY_SLOS, run_nightly_gate

    reason = "관측 없음(런 간 미누적, in-memory slo_log)"
    nightly = [{"slo_id": s, "measured": False, "classified": "not-measured",
                "reason": reason} for s in NIGHTLY_SLOS]
    gate = run_nightly_gate({})
    return {
        "nightly_slos": nightly,
        "error_budget": gate["error_budget"],
        "violations": gate["violations"],
    }


# Signal Spire trigger → 평가 함수 (정본 signature_spire.trigger_*).
_SPIRE_TRIGGER_FNS = {
    "contradicting_evidence": "trigger_contradicting_evidence",
    "claim_changed": "trigger_claim_changed",
    "plan_to_execution": "trigger_plan_to_execution",
    "new_independent_source": "trigger_new_independent_source",
    "confidence_threshold": "trigger_confidence_threshold",
}


def _spire_catalog() -> list[dict]:
    """Signal Spire 5 종 트리거 카탈로그 — 정본 모듈 docstring 을 설명으로.

    허위·가공 없이 `signal_spire.TRIGGER_TYPES` 순서와 각 평가 함수 docstring 첫
    줄을 사용한다 (read-only, 결정적).
    """
    from orc_citadel import signal_spire as ss

    out = []
    for t in ss.TRIGGER_TYPES:
        fn = getattr(ss, _SPIRE_TRIGGER_FNS[t], None)
        doc = (fn.__doc__ or "").strip().splitlines()[0] if fn else ""
        out.append({"trigger": t, "description": doc})
    return out


# Grand Archive — source_type 은 source_id 접두사에서 결정적 파생 (뷰어 표기와 동일 규칙).
ARCHIVE_TYPE_TOKENS = ("official", "press", "gov", "research", "exchange")
_STYPE_SQL = ("CASE WHEN split_part(source_id, '-', 1) IN ("
              + ", ".join(f"'{t}'" for t in ARCHIVE_TYPE_TOKENS)
              + ") THEN split_part(source_id, '-', 1) ELSE 'source' END")
# 문서 전량(실측 10만+) 직렬화가 /archive 를 멈추게 했다 — 응답은 한 페이지로 제한한다.
ARCHIVE_LIMIT_DEFAULT, ARCHIVE_LIMIT_MAX = 50, 500
_ARCHIVE_SORTS = {"doc_id": "doc_id",
                  "publication": "publication_time DESC NULLS LAST, doc_id"}


def _recent_run_metrics(connect=None, limit: int = 5) -> dict:
    """pipeline_run_metrics 최근 런 요약 (read-only 표시용 — TS-6).

    run 단위 drill-down 은 Grafana 몫 — 여기는 최근 런 스칼라 요약만.
    postgres 미가동/드라이버 부재는 정직 빈 (§6.2 — 가짜 런 없음).
    """
    tables = ["pipeline_run_metrics", "pipeline_slo_observations"]
    conn = None
    try:
        if connect is not None:
            conn = connect()
        else:
            import psycopg
            from orc_citadel.postgres_mutation_log import build_dsn
            conn = psycopg.connect(build_dsn())
        cur = conn.cursor()
        cur.execute(
            "SELECT run_id, job_id, MIN(recorded_at) AS started "
            "FROM pipeline_run_metrics GROUP BY run_id, job_id "
            "ORDER BY started DESC LIMIT %s", (limit,))
        heads = cur.fetchall()
        runs = []
        for run_id, job_id, started in heads:
            cur.execute(
                "SELECT run_id, metric, value FROM pipeline_run_metrics "
                "WHERE run_id = %s AND labels = '{}'::jsonb".replace("{}", "{" + "}"),
                (run_id,))
            metrics = {m: v for _, m, v in cur.fetchall()}
            runs.append({"run_id": run_id, "job_id": job_id,
                         "recorded_at": str(started), "metrics": metrics})
        return {"available": True, "runs": runs, "source_tables": tables}
    except Exception as exc:
        return {"available": False, "runs": [], "source_tables": tables,
                "note": f"run 메트릭 조회 불가 — postgres 미가동/미영속 "
                        f"(honest-gap §6.2): {exc}"}
    finally:
        if conn is not None and connect is None:
            try:
                conn.close()
            except Exception:
                pass


def _qs_int(raw, default: int, lo: int, hi: int) -> int:
    """쿼리 정수 파싱 — 비수치는 기본값, 범위 밖은 클램프 (결정적)."""
    try:
        v = int(str(raw))
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def _archive_filter(source_type: str | None = None, source: str | None = None,
                    language: str | None = None, q: str | None = None,
                    doc_ids: list[str] | None = None) -> tuple[str, list]:
    """documents 필터 축 → (WHERE 절, 파라미터). 미지정 축은 절을 만들지 않는다."""
    cl: list[str] = []
    p: list = []
    if source_type:
        cl.append(f"{_STYPE_SQL} = ?"); p.append(source_type)
    if source:
        cl.append("source_id = ?"); p.append(source)
    if language == "unknown":
        cl.append("(language IS NULL OR language = '')")
    elif language:
        cl.append("language = ?"); p.append(language)
    if q:
        cl.append("(title ILIKE ? OR url ILIKE ? OR doc_id ILIKE ?)")
        p += [f"%{q}%"] * 3
    if doc_ids is not None:
        if doc_ids:
            cl.append("doc_id IN (" + ", ".join(["?"] * len(doc_ids)) + ")")
            p += list(doc_ids)
        else:
            cl.append("1 = 0")   # 대상 doc_id 없음 → 정직 빈 (전량 반환 아님)
    return (" WHERE " + " AND ".join(cl)) if cl else "", p


def _archive_normalized(norm_db: str, *, limit: int = ARCHIVE_LIMIT_DEFAULT,
                        offset: int = 0, source_type: str | None = None,
                        source: str | None = None, language: str | None = None,
                        q: str | None = None, doc_ids: list[str] | None = None,
                        sort: str = "doc_id") -> tuple[list[dict], dict, dict, dict]:
    """normalized 존 documents 한 *페이지*(+segment 수)·집계·facet — read-only 연결.

    `normalized_zone.documents()`/`segments()` 와 동일 스키마를 read_only DuckDB
    로 직접 조회해, 수집 파이프라인과의 잠금 충돌을 피한다. 전량을 싣던 것을 SQL
    LIMIT/OFFSET 한 페이지로 좁히고, segment 수는 그 페이지 doc_id 에 한해 GROUP BY
    한다 (segments 전수 GROUP BY 금지). facet 카운트는 검색(q)·doc_ids 범위 안에서
    GROUP BY 실측이라 페이지 밖 문서도 반영한다 — facet 선택 자체로는 좁히지 않아
    선택 해제용 chip 이 사라지지 않는다. DB 미존재/오류는 빈(정직).

    반환: (docs, counts{documents,segments}, page{limit,offset,total,sort},
    facets{source_type,language}).
    """
    import duckdb

    counts = {"documents": 0, "segments": 0}
    page = {"limit": limit, "offset": offset, "total": 0, "sort": sort}
    facets: dict[str, dict] = {"source_type": {}, "language": {}}
    try:
        c = duckdb.connect(str(norm_db), read_only=True)
    except Exception:
        return [], counts, page, facets
    order = _ARCHIVE_SORTS.get(sort, _ARCHIVE_SORTS["doc_id"])
    page["sort"] = sort if sort in _ARCHIVE_SORTS else "doc_id"
    where, params = _archive_filter(source_type, source, language, q, doc_ids)
    fwhere, fparams = _archive_filter(q=q, doc_ids=doc_ids)
    try:
        counts["documents"] = c.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        counts["segments"] = c.execute("SELECT COUNT(*) FROM segments").fetchone()[0]
        page["total"] = c.execute(
            "SELECT COUNT(*) FROM documents" + where, params).fetchone()[0]
        facets["source_type"] = {t: n for t, n in c.execute(
            f"SELECT {_STYPE_SQL} AS t, COUNT(*) FROM documents{fwhere} "
            "GROUP BY t ORDER BY t", fparams).fetchall()}
        facets["language"] = {l: n for l, n in c.execute(
            "SELECT COALESCE(NULLIF(language, ''), 'unknown') AS l, COUNT(*) "
            f"FROM documents{fwhere} GROUP BY l ORDER BY l", fparams).fetchall()}
        rows = c.execute(
            "SELECT doc_id, source_id, url, title, language, publication_time, "
            f"revision_time, parser_version, char_len FROM documents{where} "
            f"ORDER BY {order} LIMIT ? OFFSET ?", params + [limit, offset]).fetchall()
        ids = [r[0] for r in rows]
        segmap = dict(c.execute(
            "SELECT doc_id, COUNT(*) FROM segments WHERE doc_id IN ("
            + ", ".join(["?"] * len(ids)) + ") GROUP BY doc_id", ids).fetchall()) if ids else {}
    except Exception:
        rows, segmap = [], {}
    finally:
        c.close()
    cols = ["doc_id", "source_id", "url", "title", "language",
            "publication_time", "revision_time", "parser_version", "char_len"]
    docs = [dict(zip(cols, r)) | {"segments": segmap.get(r[0], 0)} for r in rows]
    return docs, counts, page, facets


def _archive_facets(norm_db: str) -> tuple[dict, list[dict]]:
    """Archive facet 실측 — segment kinds GROUP BY count·동일 URL 그룹(≥2, ≤20).

    normalized 존 read_only DuckDB (잠금 회피). DB 미가동/미존재는 정직 빈.
    """
    import duckdb
    kinds: dict[str, int] = {}
    groups: list[dict] = []
    try:
        c = duckdb.connect(str(norm_db), read_only=True)
    except Exception:
        return kinds, groups
    try:
        kinds = {k: n for k, n in c.execute(
            "SELECT kind, COUNT(*) FROM segments GROUP BY kind").fetchall()}
        for url, n, ids in c.execute(
                "SELECT url, COUNT(*), LIST(doc_id) FROM documents "
                "GROUP BY url HAVING COUNT(*) >= 2 ORDER BY url LIMIT 20").fetchall():
            groups.append({"url": url, "count": n, "doc_ids": list(ids)[:5]})
    except Exception:
        pass
    finally:
        c.close()
    return kinds, groups


def _search_documents(norm_db: str, q: str) -> list[dict]:
    """normalized 존 documents 제목·URL ILIKE 검색 (read-only). 미가동은 정직 빈."""
    import duckdb
    try:
        c = duckdb.connect(str(norm_db), read_only=True)
    except Exception:
        return []
    try:
        rows = c.execute(
            "SELECT doc_id, title, source_id FROM documents "
            "WHERE title ILIKE ? OR url ILIKE ? ORDER BY doc_id",
            [f"%{q}%", f"%{q}%"]).fetchall()
    except Exception:
        rows = []
    finally:
        c.close()
    return [{"doc_id": d, "title": t, "source_id": s} for d, t, s in rows]


def _parse_dt(s: str | None):
    """ISO datetime 문자열 → datetime. 미지정/오류는 None (결정적)."""
    from datetime import datetime

    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _postgres_replay_status() -> dict:
    """postgres `graph_mutations` SoT 재생 가용성 (ADR-304) — 정직 탐지.

    접속 성공 시 mutation 수까지 보고, 실패(미가동·드라이버 미설치)는
    available=False 로 (honest-gap §6.2 — 재생 불가를 실측으로 오인 금지).
    """
    import os

    creds = dict(host=os.environ.get("POSTGRES_HOST", "localhost"),
                 port=os.environ.get("POSTGRES_PORT", "5432"),
                 user=os.environ.get("POSTGRES_USER"),
                 password=os.environ.get("POSTGRES_PASSWORD"),
                 dbname=os.environ.get("POSTGRES_DB"))
    try:
        import psycopg
        c = psycopg.connect(connect_timeout=1, **creds)
    except Exception:
        return {"available": False,
                "note": "postgres SoT 미가동 또는 드라이버 미설치 — graph_mutations replay 불가 (honest-gap §6.2)"}
    try:
        n = c.execute("SELECT COUNT(*) FROM graph_mutations").fetchone()[0]
        return {"available": True, "mutation_count": n}
    except Exception:
        return {"available": False,
                "note": "postgres 접속 성공했으나 graph_mutations 미존재 (honest-gap §6.2)"}
    finally:
        c.close()


def _build():
    z = CuratedZone(str(DB))
    z.initialize()
    g = GraphService()
    for a in z.assertions():
        for node, uid in ((a["subject_id"], f"n-{a['assertion_id']}"),
                          (a["claim_id"], f"n2-{a['assertion_id']}")):
            g.apply([{"mutation_id": uid, "idempotency_key": uid,
                      "op": "create_node", "payload": {"id": node, "props": {}, "labels": []}}])
        g.apply([{"mutation_id": f"e-{a['assertion_id']}", "idempotency_key": f"e-{a['assertion_id']}",
                  "op": "create_edge",
                  "payload": {"type": "ABOUT", "from": a["subject_id"], "to": a["claim_id"],
                              "props": {}}}])
    return ApiFacade(z, g)


class Handler(BaseHTTPRequestHandler):
    facade = None  # class-level (한 번 로드)
    # 정적 자산 루트 — 없으면 자산 없이 동작한다 (정직 갭).
    static_roots = viewer_static.default_roots()
    # raw fetch.json 전수 스캔은 1회만 (경로 → 레코드 목록). 렌더마다 재스캔 금지.
    _FETCH_CACHE: dict[str, list[dict]] = {}
    # raw 존 source×문서 수 디렉터리 스캔도 1회만 (경로 → (source 목록, 합계)).
    _RAW_COUNT_CACHE: dict[str, tuple[list[dict], int]] = {}

    def log_message(self, *a):  # 출력 간소화 (404 등만 남김)
        if self.path.startswith("/api/"):
            super().log_message(*a)

    # --- API (JSON) ---
    @_j
    def _api_report(self, qs):
        subj = unquote(qs.get("subject", ""))
        return self.facade.get_investigation_report(subj) or {"error": "not_found"}

    @_j
    def _api_search(self, qs):
        """Cross-zone search — entities·claims 인메모리 substring, documents ILIKE. 각 ≤10."""
        q = unquote(qs.get("q", "")).strip().lower()
        out = {"query": q, "entities": [], "claims": [], "documents": [],
               "counts": {"entities": 0, "claims": 0, "documents": 0}}
        if not q:
            return out
        for e in self.facade.zone.entities():
            name = (e.get("canonical_name") or "")
            if q in name.lower():
                out["entities"].append({"entity_id": e["entity_id"],
                                        "name": name,
                                        "mention_type": e.get("mention_type")})
        for cid, r in self.facade._claims_rows.items():
            hay = " ".join(str(r.get(k) or "") for k in
                           ("predicate", "object_literal", "subject_id",
                            "surface_fragment")).lower()
            if q in hay:
                out["claims"].append({"claim_id": cid,
                                      "predicate": r.get("predicate"),
                                      "object_literal": r.get("object_literal"),
                                      "subject_id": r.get("subject_id")})
        docs = _search_documents(getattr(self, "normalized_db", NORM_DB), q)
        out["counts"] = {"entities": len(out["entities"]),
                         "claims": len(out["claims"]),
                         "documents": len(docs)}
        # 고정 정렬 축: id. 결정적.
        out["entities"].sort(key=lambda x: x["entity_id"])
        out["claims"].sort(key=lambda x: x["claim_id"])
        out["entities"] = out["entities"][:10]
        out["claims"] = out["claims"][:10]
        out["documents"] = docs[:10]
        return out

    @_j
    def _api_claim(self, qs):
        """단일 claim 상세 — 파사드 get_claim + zone claims 행(surface_fragment 등) 병합."""
        claim = unquote(qs.get("claim", ""))
        base = self.facade.get_claim(claim)
        if base is None:
            return {"error": "not_found"}
        row = self.facade._claims_rows.get(claim) or {}
        merged = dict(base)
        for k in ("surface_fragment", "predicate", "object_literal",
                  "modality", "doc_id"):
            if k in row:
                merged[k] = row[k]
        merged["claim_id"] = claim
        return merged

    @_j
    def _api_evidence(self, qs):
        claim = unquote(qs.get("claim", ""))
        return self.facade.get_claim_evidence(claim)

    @_j
    def _api_rank(self, qs):
        return {"items": [{
            "subject_id": r.subject_id, "rank": r.rank, "signal": r.signal,
            "value": r.confidence["value"],
            "evidence_count": r.confidence["evidence_count"],
            "independent_source_count": r.confidence["independent_source_count"],
            "predicates": {k: v["count"] for k, v in r.predicates.items()},
        } for r in self.facade._ranking.ranked()]}

    @_j
    def _api_subject_claims(self, qs):
        subj = unquote(qs.get("subject", ""))
        rows = self.facade.zone.claims()
        out = []
        for r in rows:
            if r["subject_id"] == subj:
                out.append({"claim_id": r["claim_candidate_id"], "predicate": r["predicate"],
                            "object_literal": r["object_literal"], "object_id": r["object_id"],
                            "modality": r["modality"]})
        return {"subject_id": subj, "items": out}

    @_j
    def _api_investigate(self, qs):
        """조사 에이전트 end-to-end (S43–S47) — read-only, 결정적."""
        from orc_citadel.investigation import InvestigationCoverage, Subclaim
        from orc_citadel.investigation_runner import InvestigationRunner
        from orc_citadel.planner import InvestigationPlanner
        from orc_citadel.synthesis import Synthesizer, Audit
        from orc_citadel.graph_service import GraphService

        subj = unquote(qs.get("subject", ""))
        facade = self.facade
        z = facade.zone
        # ABOUT 그래프 재구축 (read-only 조회용).
        g = GraphService()
        for a in z.assertions():
            for node, uid in ((a["subject_id"], f"n-{a['assertion_id']}"),
                              (a["claim_id"], f"n2-{a['assertion_id']}")):
                g.apply([{"mutation_id": uid, "idempotency_key": uid,
                          "op": "create_node", "payload": {"id": node, "props": {}, "labels": []}}])
            g.apply([{"mutation_id": f"e-{a['assertion_id']}",
                      "idempotency_key": f"e-{a['assertion_id']}",
                      "op": "create_edge",
                      "payload": {"type": "ABOUT", "from": a["subject_id"],
                                  "to": a["claim_id"], "props": {}}}])
        # Planner — 질문 → subclaim 트리 분해 (07 §3.2), known/gap 라벨.
        planner = InvestigationPlanner(z)
        planned = planner.plan(subj)
        subclaims = [Subclaim(sc.id, sc.text, subject_id=sc.subject_id)
                     for sc in planned.subclaims]
        inv = InvestigationRunner(z, g).run(subclaims)
        rep = Synthesizer(z).synthesize(inv, subj)
        # War Table — 조사 subgraph(진행식 disclosure 시드, 06 §8.1) 노출.
        graph_view = facade.get_investigation_graph(subj, hops=1)
        # Planner 산출 — 지식/공백 구분된 subclaim 트리 노출 (07 §3.2).
        planned_view = [{"id": sc.id, "text": sc.text, "known": sc.known,
                         "gap_reason": sc.gap_reason} for sc in planned.subclaims]
        # Audit §3.9 — 문장 → claim → source span 역추적 trace 노출 (연결률 = 1.0).
        audit_trace = self.facade.zone and Audit().trace(rep.statements, z)
        # Investigation 대시보드 (11 §2.2 D8) — coverage·독립 증거·비용·latency.
        from orc_citadel.investigation_dashboard import investigation_dashboard, Coverage
        indep = inv.coverage and graph_view["independence_summary"].get(
            "independent_source_count", 0)
        dashboard = investigation_dashboard(
            investigation_id=f"inv-{subj[:16]}",
            coverage=Coverage(covered=int(round(inv.coverage * len(planned.subclaims))),
                              planned=len(planned.subclaims),
                              gaps=inv.gaps),
            independent_evidence=indep,
            elapsed_ms=0)
        return {
            "subject_id": subj,
            "computed": "on-request, non-persistent",
            "planned_subclaims": planned_view,
            "coverage": inv.coverage,
            "iterations": inv.iterations,
            "terminated_by": inv.terminated_by,
            "gaps": inv.gaps,
            # 확장: 반증 배열 그대로 (hypotheses·negative_queries) + 검색 결과 ≤10.
            "counter_evidence": list(inv.counter_evidence),
            "retrieved": list(inv.retrieved)[:10],
            "conclusion": rep.conclusion,
            "statements": rep.statements,
            "open_questions": rep.open_questions,
            "audit": rep.audit,
            # 확장: audit_trace {trace,blocked_statements,verifiable,linked,linkage_ratio}.
            "audit_trace": audit_trace,
            "dashboard": dashboard,
            "subgraph": graph_view["subgraph"],
            "relation_paths": graph_view["relation_paths"],
            "independence_summary": graph_view["independence_summary"],
        }

    @_j
    def _api_gate(self, qs):
        """Citadel Gate — 존 카운트(raw/normalized/curated)·랭킹 top N·신호 분포."""
        raw_dir = getattr(self, "raw_dir", RAW_DIR)
        norm_db = getattr(self, "normalized_db", NORM_DB)
        z = self.facade.zone
        top = [{
            "subject_id": r.subject_id, "rank": r.rank, "signal": r.signal,
            "value": r.confidence["value"],
            "evidence_count": r.confidence["evidence_count"],
            "independent_source_count": r.confidence["independent_source_count"],
        } for r in self.facade._ranking.ranked(limit=5)]
        raw_sources, raw_total = _count_raw(raw_dir)
        norm = _count_normalized(norm_db)
        return {
            "raw_sources": raw_sources,
            "raw_doc_count": raw_total,
            "normalized_counts": norm,
            "curated": {
                "assertions": len(z.assertions()),
                "entities": len(z.entities()),
                "mentions": len(z.mentions()),
                "claims": len(z.claims()),
                "dup_clusters": len(z.clusters()),
            },
            "ranking_top": top,
            "signal_distribution": {k: len(v) for k, v in self.facade._ranking.by_signal().items()},
        }

    @_j
    def _api_watchtower(self, qs):
        """Watchtower — source 수집 사실(실측) + 실측 freshness + SLO 판정표(honest-gap).

        확장: intake(fetch.json 전수 스캔 1회·클래스 캐시)·sources[].last_fetch·
        sources[].governance(fetch.json 표본 실측 — http_status·robots_allowed).
        """
        raw_dir = getattr(self, "raw_dir", RAW_DIR)
        norm_db = getattr(self, "normalized_db", NORM_DB)
        raw_sources, _ = _count_raw(raw_dir)
        recs = _fetch_records(raw_dir)
        intake = _intake_panel(raw_dir)
        per_source: dict[str, list[dict]] = {}
        for r in recs:
            per_source.setdefault(r["source_id"], []).append(r)
        sources = []
        for s in raw_sources:
            rows = per_source.get(s["source_id"], [])
            fetched = [r["fetched_at"] for r in rows if r["fetched_at"]]
            statuses = [r["http_status"] for r in rows if r["http_status"] is not None]
            robots = [r["robots_allowed"] for r in rows if r["robots_allowed"] is not None]
            sources.append({
                "source_id": s["source_id"],
                "source_type": _source_type(s["source_id"]),
                "doc_count": s["doc_count"],
                "last_fetch": max(fetched) if fetched else None,
                "governance": {
                    "http_status": (statuses[0] if statuses else None),
                    "robots_allowed": (robots[0] if robots else None),
                },
            })
        return {"sources": sources, "freshness": _freshness(norm_db),
                "intake": intake, "slo": _slo_panel(),
                # 표시용 run 메트릭 요약 (TS-6) — drill-down 은 Grafana 몫.
                "run_metrics": _recent_run_metrics(
                    getattr(self, "metrics_connect", None))}

    @_j
    def _api_spire(self, qs):
        """Signal Spire — 5 종 트리거 카탈로그 + fire-once 규칙 + 정직 빈 alert feed."""
        return {
            "trigger_catalog": _spire_catalog(),
            "fire_once_rule": "동일 (investigation_id, trigger_type, target) 은 1회 점화 (ADR-1104 — 재알림 없음)",
            "alerts": [],
            "note": "점화된 알림 없음 (honest-gap §6.2) — alert 는 in-memory fire-once 이며 "
                    "영속 저장소가 없어 런 간 유지되지 않음. 실제 mutation 이벤트에서 파생된 것만 렌더.",
        }

    @_j
    def _api_archive(self, qs):
        """Grand Archive — normalized documents 한 페이지·raw source 목록·dedup cluster 수.

        페이지네이션(`limit`≤500 기본 50·`offset`)과 서버측 필터(`source_type`·
        `source`·`language`·`role`·`q`·`doc_ids`)·정렬(`sort`=doc_id|publication).
        전량 직렬화(실측 10만+ 문서)가 페이지를 멈추게 해 SQL 로 내렸다.

        확장: documents[].cluster_role(root|derived|independent|null, dup_clusters
        매핑)·language·publication_time·revision_time·parser_version(기존 조회에 포함)
        + segment_kinds GROUP BY·url_groups(≥2 그룹 ≤20). `facets` 는 검색 범위 실측
        (source_type·language 는 normalized 존 GROUP BY, cluster_role 은 curated
        dup_clusters 전역 — 정규화 존 밖 축이라 검색 범위로 좁히지 않는다).
        """
        norm_db = getattr(self, "normalized_db", NORM_DB)
        raw_dir = getattr(self, "raw_dir", RAW_DIR)
        limit = _qs_int(qs.get("limit"), ARCHIVE_LIMIT_DEFAULT, 1, ARCHIVE_LIMIT_MAX)
        offset = _qs_int(qs.get("offset"), 0, 0, 10 ** 9)
        source_type = unquote(qs.get("source_type", "")) or None
        source = unquote(qs.get("source", "")) or None
        language = unquote(qs.get("language", "")) or None
        role = unquote(qs.get("role", "")) or None
        q = unquote(qs.get("q", "").replace("+", "%20")).strip() or None
        sort = qs.get("sort", "doc_id")
        want = [unquote(x) for x in qs.get("doc_ids", "").split(",") if x]

        clusters = getattr(self, "curated_clusters", None)
        cluster_rows = []
        if clusters is None:
            cluster_rows = self.facade.zone.clusters()
            clusters = len(cluster_rows)
        # 계보 역할: root > independent(추가 소속) > derived(클러스터 멤버) > null.
        role_map: dict[str, str] = {}
        for c in cluster_rows:
            indep = set(c.get("independent_addition_doc_ids") or [])
            for d in c.get("member_doc_ids") or []:
                role_map.setdefault(d, "independent" if d in indep else "derived")
            role_map[c["root_doc_id"]] = "root"
        role_counts: dict[str, int] = {}
        for r in role_map.values():
            role_counts[r] = role_counts.get(r, 0) + 1
        # role 은 curated 존 축이라 SQL 컬럼이 아니다 — doc_id 교집합으로 좁힌다.
        doc_ids = want or None
        if role:
            keep = set(want) if want else None
            doc_ids = [d for d, rr in sorted(role_map.items())
                       if rr == role and (keep is None or d in keep)]
        docs, counts, page, facets = _archive_normalized(
            norm_db, limit=limit, offset=offset, source_type=source_type,
            source=source, language=language, q=q, doc_ids=doc_ids, sort=sort)
        for d in docs:
            d["cluster_role"] = role_map.get(d.get("doc_id"))
        facets["cluster_role"] = role_counts
        page |= {"source_type": source_type or "", "source": source or "",
                 "language": language or "", "role": role or "", "q": q or "",
                 "doc_ids": ",".join(want)}
        raw_sources, raw_total = _count_raw(raw_dir)
        segment_kinds, url_groups = _archive_facets(norm_db)
        return {
            "normalized_documents": docs,
            "normalized_counts": counts,
            "normalized_page": page,
            "facets": facets,
            "raw_sources": raw_sources,
            "raw_doc_count": raw_total,
            "dedup_clusters": clusters,
            "segment_kinds": segment_kinds,
            "url_groups": url_groups,
            "page_note": "normalized_documents 는 한 페이지다 (limit/offset) — "
                         "normalized_counts.documents 는 존 전체, normalized_page.total "
                         "은 현재 필터 적중 수.",
            "format_note": "raw 존은 Atom meta/전체 page 두 형식이 공존(04 §2.2) — 서로 다른 "
                           "형식일 뿐 '중복'이 아님.",
        }

    @_j
    def _api_chronicle(self, qs):
        """Chronicle Vault — bitemporal assertions(as-of)·supersedes 체인·graph-replay 상태."""
        zone = self.facade.zone
        valid_at = _parse_dt(qs.get("valid_at"))
        tx_at = _parse_dt(qs.get("tx_at"))
        rows = zone.assertions_as_of(valid_at=valid_at, tx_at=tx_at)
        superseded = [r for r in rows if r.get("supersedes_id")]
        avail = getattr(self, "postgres_available", None)
        replay = (_postgres_replay_status() if avail is None else
                  {"available": avail,
                   "note": ("postgres SoT" if avail else
                            "postgres SoT 미가동 (honest-gap §6.2)")})
        # 확장: bitemporal bounds + 이벤트 타임라인 (tx_from→asserted,
        # tx_to→closed, supersedes_id→superseded). 전체 assertions 축 (as-of 아님).
        all_rows = zone.assertions()
        def _ts(v):
            return v.isoformat() if hasattr(v, "isoformat") else (None if v is None else str(v))
        def _bounds(lo_key, hi_key):
            los = [r[lo_key] for r in all_rows if r.get(lo_key) is not None]
            his = [r[hi_key] if r.get(hi_key) is not None else r[lo_key]
                   for r in all_rows if r.get(lo_key) is not None or r.get(hi_key) is not None]
            return (_ts(min(los)) if los else None, _ts(max(his)) if his else None)
        vmin, vmax = _bounds("valid_from", "valid_to")
        tmin, tmax = _bounds("tx_from", "tx_to")
        bounds = {"valid_min": vmin, "valid_max": vmax,
                  "tx_min": tmin, "tx_max": tmax}
        events: list[dict] = []
        for a in all_rows:
            base = {"assertion_id": a["assertion_id"], "claim_id": a["claim_id"],
                    "predicate": a["predicate"]}
            if a.get("tx_from") is not None:
                events.append(base | {"kind": "asserted", "at": a["tx_from"]})
            if a.get("tx_to") is not None:
                events.append(base | {"kind": "closed", "at": a["tx_to"]})
            if a.get("supersedes_id"):
                events.append(base | {"kind": "superseded", "at": a.get("tx_from")})
        events.sort(key=lambda e: (str(e["at"] or ""), e["assertion_id"], e["kind"]))
        return {
            "assertions": rows,
            "supersedes_chain": superseded,
            "graph_replay": replay,
            "bounds": bounds,
            "events": events,
            "as_of": {"valid_at": valid_at.isoformat() if valid_at else None,
                      "tx_at": tx_at.isoformat() if tx_at else None},
        }

    @_j
    def _api_table(self, qs):
        """War Table seed — Campaign Map(subjects) + entity type chips. read-only."""
        subjects = []
        for r in self.facade._ranking.ranked():
            d = r.confidence.get("dimensions") or {}
            subjects.append({
                "subject_id": r.subject_id, "rank": r.rank, "signal": r.signal,
                "value": r.confidence["value"],
                "evidence_count": r.confidence["evidence_count"],
                "independent_source_count": r.confidence["independent_source_count"],
                "coverage": d.get("coverage", 0),
                "predicates": {k: v["count"] for k, v in r.predicates.items()},
            })
        types: dict[str, int] = {}
        for e in self.facade.zone.entities():
            label = e.get("mention_type") or "Entity"
            types[label] = types.get(label, 0) + 1
        entity_types = [{"label": k, "count": n} for k, n in sorted(types.items())]
        entity_types.append({"label": "Claim", "count": len(self.facade.zone.claims())})
        entities = sorted(
            [{"entity_id": e["entity_id"],
              "name": e.get("canonical_name") or "",
              "mention_type": e.get("mention_type")}
             for e in self.facade.zone.entities()],
            key=lambda x: x["entity_id"])[:200]
        quarantined = sum(1 for r in self.facade.zone.claims()
                          if r.get("status") == "quarantined")
        q = 0
        graph = getattr(self.facade, "graph", None)
        if graph is not None and hasattr(graph, "quarantined_edges"):
            q = len(graph.quarantined_edges())
        entity_types.append({"label": "Quarantine", "count": q})
        return {
            "subjects": subjects,
            "entity_types": entity_types,
            "entities": entities,
            "quarantined": quarantined,
            "notes": {
                "contradicts": "contradicts 근거는 파사드 미확장 (honest-gap §6.2)",
                "seer": "Seer LLM inference 미영속 (honest-gap §6.2)",
            },
        }

    @_j
    def _api_graph(self, qs):
        """War Table subgraph seed — get_investigation_graph (09 §2.2). read-only.

        확장: 서브그래프 nodes[].label — entity는 /api/table.entities와 동일
        canonical_name, claim은 predicate (없으면 정직 빈 문자열).
        """
        subj = unquote(qs.get("subject", ""))
        view = self.facade.get_investigation_graph(subj, hops=1)
        sg = view.get("subgraph") or {}
        names = {e["entity_id"]: (e.get("canonical_name") or "")
                 for e in self.facade.zone.entities()}
        rows = getattr(self.facade, "_claims_rows", None) or {}
        nodes = []
        for ent in sg.get("entities", []):
            label = names.get(ent.get("id"), "")
            ent["label"] = label
            nodes.append({"id": ent.get("id"), "label": label})
        for cl in sg.get("claims", []):
            row = rows.get(cl.get("id")) or {}
            label = row.get("predicate") or ""
            cl["label"] = label
            nodes.append({"id": cl.get("id"), "label": label})
        nodes.sort(key=lambda n: str(n["id"]))
        sg["nodes"] = nodes
        view["subgraph"] = sg
        return view

    @_j
    def _api_graph_node(self, qs):
        """단일 노드 상세 (09 §2.2). 미존재는 not_found."""
        nid = unquote(qs.get("id", ""))
        return self.facade.get_graph_node(nid) or {"error": "not_found"}

    @_j
    def _api_graph_expand(self, qs):
        """인접 확장 + opaque cursor (09 §1.4·§2.2). 클라이언트 미파싱."""
        nid = unquote(qs.get("id", ""))
        raw = qs.get("cursor")
        cursor = unquote(raw) if raw else None
        return self.facade.get_graph_expand(nid, cursor=cursor)

    @_j
    def _api_provenance(self, qs):
        """Evidence provenance trail (09 §2.3). 미존재는 not_found."""
        evid = unquote(qs.get("evidence", ""))
        return self.facade.get_evidence_provenance(evid) or {"error": "not_found"}

    @_j
    def _api_document(self, qs):
        """normalized 존 세그먼트 read-only — 원문 왕복(§3-2). DB 미가동/미존재는 정직 빈."""
        doc_id = unquote(qs.get("doc", ""))
        import duckdb
        db = getattr(self, "normalized_db", NORM_DB)
        try:
            c = duckdb.connect(str(db), read_only=True)
        except Exception:
            return {"doc_id": doc_id, "available": False, "segments": [],
                    "note": "normalized DuckDB 미가동 (honest-gap §6.2)"}
        try:
            drows = c.execute(
                "SELECT doc_id, source_id, url, title, language, publication_time, "
                "parser_version FROM documents WHERE doc_id=?", [doc_id]).fetchall()
            srows = c.execute(
                "SELECT segment_id, ord, kind, text, char_start, char_end "
                "FROM segments WHERE doc_id=? ORDER BY ord", [doc_id]).fetchall()
        except Exception:
            drows, srows = [], []
        finally:
            c.close()
        dcols = ["doc_id", "source_id", "url", "title", "language",
                 "publication_time", "parser_version"]
        scols = ["segment_id", "ord", "kind", "text", "char_start", "char_end"]
        return {"doc_id": doc_id, "available": True,
                "documents": [dict(zip(dcols, r)) for r in drows],
                "segments": [dict(zip(scols, r)) for r in srows]}

    @_j
    def _api_council(self, qs):
        """Council — 기존 조사 보고서 조회만. 실행(쓰기)은 범위 밖 정직 노출."""
        subj = unquote(qs.get("subject", ""))
        rep = self.facade.get_investigation_report(subj)
        if rep is None:
            return {"error": "not_found"}
        rep["execution"] = {
            "available": False,
            "note": "조사 실행(Planner+Runner 쓰기 루프)은 read-only 범위 밖 — "
                    "기존 결론·predicate·open_questions 조회만 (honest-gap §6.2)",
        }
        return rep



    def do_GET(self):
        if Handler.facade is None:
            Handler.facade = _build()
        parsed = urlparse(self.path)
        qs = {k: v for k, v in (p.split("=", 1) for p in parsed.query.split("&") if p)}

        if parsed.path == "/api/report":
            body = self._api_report(qs).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        if parsed.path == "/api/evidence":
            body = self._api_evidence(qs).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        if parsed.path == "/api/rank":
            body = self._api_rank(qs).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        if parsed.path == "/api/subject_claims":
            body = self._api_subject_claims(qs).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        if parsed.path == "/api/investigate":
            body = self._api_investigate(qs).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        if parsed.path == "/api/search":
            body = self._api_search(qs).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        if parsed.path == "/api/claim":
            body = self._api_claim(qs).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        if parsed.path == "/api/gate":
            body = self._api_gate(qs).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        if parsed.path == "/api/watchtower":
            body = self._api_watchtower(qs).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        if parsed.path == "/api/spire":
            body = self._api_spire(qs).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        if parsed.path == "/api/archive":
            body = self._api_archive(qs).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        if parsed.path == "/api/chronicle":
            body = self._api_chronicle(qs).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        if parsed.path == "/api/table":
            body = self._api_table(qs).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        if parsed.path == "/api/graph":
            body = self._api_graph(qs).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        if parsed.path == "/api/graph_node":
            body = self._api_graph_node(qs).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        if parsed.path == "/api/graph_expand":
            body = self._api_graph_expand(qs).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        if parsed.path == "/api/provenance":
            body = self._api_provenance(qs).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        if parsed.path == "/api/document":
            body = self._api_document(qs).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        if parsed.path == "/api/council":
            body = self._api_council(qs).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return


        if parsed.path.startswith("/assets/") or parsed.path.startswith("/app/"):
            self._serve_asset(parsed.path); return

        # 공간 라우트는 frontend dist 가 유일한 표시 계층이다 (TS-1 — 인라인
        # 페이지·/legacy/* 는 8공간 이관 완료로 제거, Step 15). dist 는 커밋
        # 대상이라 부재는 빌드/배포 결손 — 조용한 대체 화면 없이 정직 503.
        dist_entry = _MIGRATED.get(parsed.path)
        if dist_entry is not None:
            # 인스턴스 → 클래스 속성 순 (테스트가 인스턴스에 roots 를 주입한다)
            roots = getattr(self, "static_roots", None)
            if roots is not None and roots.resolve(f"/app/{dist_entry}") is not None:
                self._serve_asset(f"/app/{dist_entry}"); return
            body = ("503: frontend dist 없음 — frontend 에서 `npm run build` "
                    "후 커밋한다 (frontend/dist 는 커밋 대상)").encode()
            self.send_response(503)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers(); self.wfile.write(body); return

        # 미지정 경로가 Gate HTML 200 을 돌려주던 것을 바로잡는다 —
        # 오타 링크·없는 자산이 조용히 성공하면 디버깅이 어렵다.
        body = b"404 Not Found"
        self.send_response(404)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def _serve_asset(self, url_path: str) -> None:
        """`/assets/*` — 리포의 자산을 참조 서빙한다 (복제하지 않음)."""
        roots = Handler.static_roots
        hit = roots.resolve(url_path) if roots else None
        if hit is None:
            body = b"404 Not Found"
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers(); self.wfile.write(body); return
        path, mime = hit
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        # dist 번들(/app/*)은 청크 이름이 안정(해시 없음)이라, 캐시된 구 공유
        # 청크 + 새 엔트리 혼합이 빈 화면을 만든다 (재배포마다 실측 재발) —
        # no-cache 로 매 요청 재검증한다. 공용 자산은 짧게 캐시 유지.
        if url_path.startswith("/app/"):
            self.send_header("Cache-Control", "no-cache")
        else:
            self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        self.wfile.write(data)


# canonical 라우트 → frontend dist 엔트리 (8공간 이관 완료 — TS-1).
_MIGRATED = {
    "/": "gate.html",
    "/witnesses": "witnesses.html",
    "/table": "table.html",
    "/archive": "archive.html",
    "/spire": "spire.html",
    "/council": "council.html",
    "/watchtower": "watchtower.html",
    "/chronicle": "chronicle.html",
}


def main() -> None:
    Handler.facade = _build()
    # 조용한 로그 로거로 교체 (404 이외 억제).
    quiet = type("Q", (BaseHTTPRequestHandler,),
                  {"log_message": lambda self, *a: None,
                   "log_error": lambda self, *a: None})
    Handler.log_message = quiet.log_message
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://{HOST}:{PORT}/"
    print(f"Orc Citadel viewer: {url}  (Ctrl-C로 종료)")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
