"""실데이터를 브라우저로 직접 확인하는 prototype 개발 서버 (stdlib).

FastAPI·신규 런타임 의존 없이 `http.server`로 `09-api`의 prototype mapping을
제공한다. graph·curated zone은 읽기 전용이고, durable investigation의 운영
메타데이터와 report만 PostgreSQL에 쓴다.

실행:  .venv/bin/python -m orc_citadel.viewer     # http://127.0.0.1:8791
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from orc_citadel import component_status, viewer_static
from orc_citadel.collection_control import CollectionControl
from orc_citadel.investigation_job import build_read_facade
from orc_citadel.iceberg_zone import NormalizedZone
from orc_citadel.raw_shard import RawShardStore
from orc_citadel.versioning import extraction_version_tuple

# 컨테이너에서는 VIEWER_HOST=0.0.0.0 으로 외부 바인딩 (docker-compose.yml).
HOST, PORT = os.environ.get("VIEWER_HOST", "127.0.0.1"), int(os.environ.get("VIEWER_PORT", "8791"))
DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"
ICEBERG_ROOT = DATA_DIR / "iceberg"
RAW_DIR = DATA_DIR / "raw"          # raw zone flat files (design 03 §2.1)
NORM_ROOT = ICEBERG_ROOT            # shared normalized/curated Iceberg warehouse
_MAX_JSON_REQUEST_BYTES = 1024 * 1024


class _RequestTooLarge(ValueError):
    pass


def _investigation_json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)



# JSON serialization — datetime/tuple을 str로.
def _j(fn):
    def wrap(*a, **k):
        return json.dumps(fn(*a, **k), default=str, ensure_ascii=False)
    return wrap


def _raw_stamp(raw_dir) -> tuple:
    """raw 존 변경 지문 — `<source>` 디렉터리의 (mtime, size).

    샤드가 추가되면 그 디렉터리의 mtime 이 바뀐다. source 수만큼의 stat 이라
    요청당 비용이 사실상 없다. 캐시 키에 넣어 **수집이 돌면 재시작 없이**
    재스캔되게 한다 (2026-09-18 prod 실측: raw 127건 수집 후에도 뷰어가 0 을 표기).
    """
    root = pathlib.Path(raw_dir) if raw_dir else None
    if root is None or not root.is_dir():
        return ()
    out = []
    try:
        for src in sorted(p.name for p in root.iterdir() if p.is_dir()):
            try:
                st = (root / src).stat()
            except OSError:
                continue
            out.append((src, st.st_mtime_ns, st.st_size))
    except OSError:
        return ()
    return tuple(out)




def _count_raw(raw_dir: str) -> tuple[list[dict], int]:
    """raw 샤드에서 source×문서 수를 센다 (read-only·집계 쿼리).

    content 를 읽지 않는 `count_by_source` 한 번 — 옛 레이아웃의 문서 디렉터리
    전수 stat(10만+ 에서 요청당 0.3s)을 대체한다. 미존재 시 빈 목록.
    """
    cache = Handler._RAW_COUNT_CACHE
    key = (str(pathlib.Path(raw_dir).resolve()) if raw_dir else "", _raw_stamp(raw_dir))
    hit = cache.get(key)
    if hit is not None:
        return [dict(s) for s in hit[0]], hit[1]
    counts = RawShardStore(raw_dir).count_by_source() if raw_dir else {}
    out = [{"source_id": source, "doc_count": n} for source, n in sorted(counts.items())]
    total = sum(s["doc_count"] for s in out)
    cache[key] = (out, total)
    return [dict(s) for s in out], total


def _fetch_records(raw_dir: str) -> list[dict]:
    """raw 샤드의 수집 메타 조회 (1회·클래스 레벨 캐시 — 렌더마다 재조회 금지).

    content 컬럼을 읽지 않는 메타 전용 조회다. 캐시 키는 절대경로 + raw 지문.
    """
    cache = Handler._FETCH_CACHE
    key = (str(pathlib.Path(raw_dir).resolve()) if raw_dir else "", _raw_stamp(raw_dir))
    hit = cache.get(key)
    if hit is not None:
        return hit
    out = RawShardStore(raw_dir).fetch_records() if raw_dir else []
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


def _normalized(root):
    """Open a fresh catalog client for a thread-safe, snapshot-consistent read."""
    if not os.environ.get("ICEBERG_CATALOG_URI") and (
            not root or (str(root) != ":memory:" and not pathlib.Path(root).is_dir())):
        return None
    zone = NormalizedZone(root)
    zone.initialize()
    return zone


def _count_normalized(root) -> dict:
    zone = None
    try:
        zone = _normalized(root)
        return zone.counts() if zone else {"documents": 0, "segments": 0}
    except Exception:
        return {"documents": 0, "segments": 0}
    finally:
        if zone:
            zone.close()


# design 02 §2.3 — Source.source_type vocab (source_id 접두사에서 결정적 파생).
_SOURCE_TYPE_TOKENS = ("official", "press", "gov", "research", "exchange")


def _source_type(source_id: str) -> str:
    """source_id 의 접두사 → source_type. 미인식은 'source'(정직)."""
    head = source_id.split("-", 1)[0]
    return head if head in _SOURCE_TYPE_TOKENS else "source"


def _freshness(root) -> dict:
    zone = None
    try:
        zone = _normalized(root)
        return zone.freshness() if zone else {
            "measured": False,
            "note": "normalized Iceberg 미가동 (honest-gap §6.2)",
        }
    except Exception:
        return {"measured": False,
                "note": "normalized Iceberg 미가동 (honest-gap §6.2)"}
    finally:
        if zone:
            zone.close()


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


# 문서 전량(실측 10만+) 직렬화가 /archive 를 멈추게 했다 — 응답은 한 페이지로 제한한다.
ARCHIVE_LIMIT_DEFAULT, ARCHIVE_LIMIT_MAX = 50, 500
_ARCHIVE_SORTS = {"doc_id", "publication"}


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




def _archive_normalized(root, *, limit: int = ARCHIVE_LIMIT_DEFAULT,
                        offset: int = 0, source_type: str | None = None,
                        source: str | None = None, language: str | None = None,
                        q: str | None = None, doc_ids: list[str] | None = None,
                        sort: str = "doc_id") -> tuple[list[dict], dict, dict, dict]:
    counts = {"documents": 0, "segments": 0}
    chosen_sort = sort if sort in _ARCHIVE_SORTS else "doc_id"
    page = {"limit": limit, "offset": offset, "total": 0, "sort": chosen_sort}
    facets: dict[str, dict] = {"source_type": {}, "language": {}}
    zone = None
    try:
        zone = _normalized(root)
        if zone is None:
            return [], counts, page, facets
        return zone.archive_page(
            limit=limit, offset=offset, source_type=source_type, source=source,
            language=language, q=q, doc_ids=doc_ids, sort=chosen_sort)
    except Exception:
        return [], counts, page, facets
    finally:
        if zone:
            zone.close()


def _archive_facets(root) -> tuple[dict, list[dict]]:
    zone = None
    try:
        zone = _normalized(root)
        return zone.archive_facets() if zone else ({}, [])
    except Exception:
        return {}, []
    finally:
        if zone:
            zone.close()


def _search_documents(root, q: str) -> tuple[list[dict], int]:
    zone = None
    try:
        zone = _normalized(root)
        return zone.search_documents(q) if zone else ([], 0)
    except Exception:
        return [], 0
    finally:
        if zone:
            zone.close()


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
    return build_read_facade(ICEBERG_ROOT)


class Handler(BaseHTTPRequestHandler):
    facade = None  # class-level (한 번 로드)
    investigation_table_prefix = "investigation"
    # 정적 자산 루트 — 없으면 자산 없이 동작한다 (정직 갭).
    static_roots = viewer_static.default_roots()
    # raw fetch.json 전수 스캔 캐시 — 키는 (경로, raw 지문). 지문이 바뀌면
    # (= 수집이 돌면) 자동으로 재스캔된다.
    _FETCH_CACHE: dict[tuple, list[dict]] = {}
    # raw 존 source×문서 수 디렉터리 스캔 캐시 — 같은 키 규칙.
    _RAW_COUNT_CACHE: dict[tuple, tuple[list[dict], int]] = {}
    # Snapshot IDs change only after committed curated Iceberg writes.
    _facade_stamp: tuple | None = None

    def log_message(self, *a):  # 출력 간소화 (404 등만 남김)
        if self.path.startswith("/api/"):
            super().log_message(*a)

    def _send_json(self, status: int, payload: dict, *, headers: dict | None = None) -> None:
        body = json.dumps(
            payload, default=_investigation_json_default, ensure_ascii=False
        ).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(
        self,
        status: int,
        body: bytes,
        *,
        content_type: str,
        headers: dict | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    @classmethod
    def _ensure_facade(cls) -> None:
        """Rebuild the graph projection only after a committed Iceberg snapshot."""
        if cls.facade is not None:
            zone = getattr(cls.facade, "zone", None)
            if zone is None:
                return
            stamp = zone.snapshot_token()
            if cls._facade_stamp == stamp:
                return
        previous, cls.facade = cls.facade, None
        close = getattr(getattr(previous, "zone", None), "close", None)
        if callable(close):
            try:
                close()
            except Exception:  # pragma: no cover - closing failure must not block reads
                pass
        cls.facade = _build()
        cls._facade_stamp = cls.facade.zone.snapshot_token()

    def _investigation_store(self):
        import psycopg

        from orc_citadel.investigation_store import InvestigationStore
        from orc_citadel.postgres_mutation_log import build_dsn

        conn = psycopg.connect(build_dsn())
        conn.autocommit = True
        store = InvestigationStore(conn, table_prefix=self.investigation_table_prefix)
        store.ensure_tables()
        return store, conn

    def _collection_control(self):
        return CollectionControl(getattr(self, "collection_data_dir", DATA_DIR))

    def _serve_collection_get(self, path: str) -> bool:
        if path not in {"/api/collections/sources", "/api/collections/latest"}:
            return False
        control = self._collection_control()
        if path.endswith("/sources"):
            self._send_json(200, {"sources": control.sources()})
        else:
            self._send_json(200, control.status())
        return True

    @staticmethod
    def _investigation_error(code: str, message: str, **details) -> dict:
        return {"error": {"code": code, "message": message, "details": details}}

    def _request_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", ""))
        except (TypeError, ValueError):
            raise ValueError("JSON request body가 필요합니다") from None
        if length > _MAX_JSON_REQUEST_BYTES:
            raise _RequestTooLarge("JSON request body는 1 MiB를 초과할 수 없습니다")
        try:
            payload = json.loads(self.rfile.read(length))
        except (TypeError, ValueError, json.JSONDecodeError):
            raise ValueError("JSON request body가 필요합니다") from None
        if not isinstance(payload, dict):
            raise ValueError("JSON request body는 object여야 합니다")
        return payload

    @staticmethod
    def _investigation_list_query(query: str) -> tuple[str | None, int, str | None]:
        try:
            params = parse_qs(query, keep_blank_values=True, strict_parsing=True)
        except ValueError as exc:
            raise ValueError("query string 형식이 올바르지 않습니다") from exc
        unknown = set(params) - {"status", "limit", "cursor"}
        if unknown:
            raise ValueError(f"지원하지 않는 query parameter: {sorted(unknown)[0]}")
        if any(len(values) != 1 for values in params.values()):
            raise ValueError("query parameter는 한 번만 지정할 수 있습니다")

        status = params.get("status", [None])[0]
        if status not in {
            None, "queued", "running", "completed", "failed", "cancelled",
            "active", "unsuccessful",
        }:
            raise ValueError("지원하지 않는 status입니다")

        raw_limit = params.get("limit", ["25"])[0]
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            raise ValueError("limit은 정수여야 합니다") from None
        if not 1 <= limit <= 100:
            raise ValueError("limit은 1 이상 100 이하여야 합니다")

        cursor = params.get("cursor", [None])[0]
        if cursor == "":
            raise ValueError("cursor는 비어 있을 수 없습니다")
        return status, limit, cursor

    @staticmethod
    def _etag_matches(raw_header: str | None, etag: str) -> bool:
        if not raw_header:
            return False
        for candidate in raw_header.split(","):
            candidate = candidate.strip()
            if candidate == "*":
                return True
            if candidate.startswith("W/"):
                candidate = candidate[2:].strip()
            if candidate == etag:
                return True
        return False

    def _send_report_artifact(
        self,
        investigation: dict,
        artifact: dict | None,
        *,
        include_html: bool,
    ) -> None:
        investigation_id = investigation["investigation_id"]
        if investigation["status"] != "completed":
            headers = (
                {"Retry-After": "1"}
                if investigation["status"] in {"queued", "running"}
                else None
            )
            self._send_json(
                409,
                self._investigation_error(
                    "investigation_not_completed",
                    "조사가 아직 완료되지 않았습니다.",
                    investigation_id=investigation_id,
                ),
                headers=headers,
            )
            return
        if artifact is None:
            if investigation.get("report_profile") is not None:
                self._send_json(
                    500,
                    self._investigation_error(
                        "report_artifact_missing",
                        "완료된 조사에 report artifact가 없습니다.",
                        investigation_id=investigation_id,
                    ),
                )
            else:
                self._send_json(
                    404,
                    self._investigation_error(
                        "report_artifact_not_found",
                        "기존 JSON-only 조사에는 HTML report artifact가 없습니다.",
                        investigation_id=investigation_id,
                    ),
                )
            return

        if not include_html:
            metadata = dict(artifact)
            metadata.pop("html_bytes", None)
            self._send_json(200, metadata)
            return

        raw_html = artifact.get("html_bytes")
        if not isinstance(raw_html, (bytes, bytearray, memoryview)):
            self._send_report_integrity_error(investigation_id)
            return
        html_bytes = bytes(raw_html)
        actual_hash = f"sha256:{hashlib.sha256(html_bytes).hexdigest()}"
        if (
            artifact.get("media_type") != "text/html; charset=utf-8"
            or artifact.get("byte_length") != len(html_bytes)
            or artifact.get("content_hash") != actual_hash
            or len(html_bytes) > 1024 * 1024
        ):
            self._send_report_integrity_error(investigation_id)
            return

        try:
            from orc_citadel.investigation_report import style_csp_hash

            style_hash = style_csp_hash(artifact["template_version"])
        except (KeyError, TypeError, ValueError):
            self._send_report_integrity_error(investigation_id)
            return

        content_hash = artifact["content_hash"]
        etag = f'"{content_hash}"'
        safe_id = re.sub(r"[^A-Za-z0-9._-]", "-", investigation_id).strip(".-")
        safe_id = safe_id or "report"
        headers = {
            "Content-Security-Policy": (
                "default-src 'none'; "
                f"style-src 'sha256-{style_hash}'; "
                "img-src 'self' data:; base-uri 'none'; form-action 'none'; "
                "frame-ancestors 'self'"
            ),
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "ETag": etag,
            "Cache-Control": "private, no-cache",
            "Content-Disposition": (
                f'inline; filename="investigation-{safe_id}.html"'
            ),
        }
        if self._etag_matches(self.headers.get("If-None-Match"), etag):
            self._send_bytes(
                304, b"", content_type="text/html; charset=utf-8", headers=headers,
            )
            return
        self._send_bytes(
            200,
            html_bytes,
            content_type="text/html; charset=utf-8",
            headers=headers,
        )

    def _send_report_integrity_error(self, investigation_id: str) -> None:
        self._send_json(
            500,
            self._investigation_error(
                "report_artifact_integrity_error",
                "저장된 report artifact 무결성 검증에 실패했습니다.",
                investigation_id=investigation_id,
            ),
        )

    def _serve_durable_investigation_get(self, parsed) -> bool:
        """영속 investigation/job 조회 경로면 응답을 보내고 True를 반환한다."""
        parts = parsed.path.split("/")
        is_list = parts == ["", "api", "investigations"]
        is_job = len(parts) == 4 and parts[:3] == ["", "api", "jobs"]
        is_investigation = (
            len(parts) in (4, 5)
            and parts[:3] == ["", "api", "investigations"]
            and (
                len(parts) == 4
                or parts[4] in {"status", "report", "report-artifact", "report.html"}
            )
        )
        if not is_list and not is_job and not is_investigation:
            return False

        if is_list:
            try:
                status, limit, cursor = self._investigation_list_query(parsed.query)
            except ValueError as exc:
                self._send_json(
                    400,
                    self._investigation_error(
                        "invalid_investigation_query", str(exc),
                    ),
                )
                return True

        try:
            store, conn = self._investigation_store()
            try:
                if is_list:
                    try:
                        result = store.list_investigations(
                            status=status, limit=limit, cursor=cursor,
                        )
                    except ValueError as exc:
                        self._send_json(
                            400,
                            self._investigation_error(
                                "invalid_investigation_query", str(exc),
                            ),
                        )
                        return True
                    for item in result["items"]:
                        artifact = item.get("artifact")
                        if artifact is not None:
                            artifact.pop("html_bytes", None)
                        if (
                            item.get("status") == "completed"
                            and item.get("report_profile") is not None
                            and artifact is None
                        ):
                            self._send_json(
                                500,
                                self._investigation_error(
                                    "report_artifact_missing",
                                    "완료된 조사에 report artifact가 없습니다.",
                                    investigation_id=item["investigation_id"],
                                ),
                            )
                            return True
                    headers = (
                        {"Retry-After": "1"}
                        if any(
                            item.get("status") in {"queued", "running"}
                            for item in result["items"]
                        )
                        else None
                    )
                    self._send_json(200, result, headers=headers)
                    return True

                if is_job:
                    job = store.get_job(unquote(parts[3]))
                    if job is None:
                        self._send_json(
                            404,
                            self._investigation_error(
                                "job_not_found", "job을 찾을 수 없습니다.",
                                job_id=unquote(parts[3]),
                            ),
                        )
                    else:
                        self._send_json(200, job, headers={"Retry-After": "1"})
                    return True

                investigation_id = unquote(parts[3])
                investigation = store.get_investigation(investigation_id)
                if investigation is None:
                    self._send_json(
                        404,
                        self._investigation_error(
                            "investigation_not_found", "조사를 찾을 수 없습니다.",
                            investigation_id=investigation_id,
                        ),
                    )
                    return True
                if len(parts) == 4:
                    self._send_json(200, investigation)
                    return True
                if parts[4] == "status":
                    step = store.get_latest_step(investigation_id)
                    self._send_json(200, {
                        "investigation_id": investigation_id,
                        "status": investigation["status"],
                        "current_step": step,
                        "evidence_coverage": investigation["coverage"],
                    }, headers={"Retry-After": "1"})
                    return True
                if parts[4] == "report":
                    report = store.get_report(investigation_id)
                    if report is None:
                        self._send_json(
                            409,
                            self._investigation_error(
                                "investigation_not_completed",
                                "완료된 조사 report가 아직 없습니다.",
                                investigation_id=investigation_id,
                            ),
                        )
                    else:
                        self._send_json(200, report)
                    return True
                artifact = store.get_report_artifact(
                    investigation_id, include_html=parts[4] == "report.html",
                )
            finally:
                conn.close()
        except Exception:
            self._send_json(
                503,
                self._investigation_error(
                    "investigation_store_unavailable",
                    "investigation PostgreSQL 저장소에 연결할 수 없습니다.",
                ),
            )
            return True

        self._send_report_artifact(
            investigation,
            artifact,
            include_html=parts[4] == "report.html",
        )
        return True

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
        docs, document_count = _search_documents(
            getattr(self, "normalized_root", NORM_ROOT), q)
        out["counts"] = {"entities": len(out["entities"]),
                         "claims": len(out["claims"]),
                         "documents": document_count}
        # 고정 정렬 축: id. 결정적.
        out["entities"].sort(key=lambda x: x["entity_id"])
        out["claims"].sort(key=lambda x: x["claim_id"])
        out["entities"] = out["entities"][:10]
        out["claims"] = out["claims"][:10]
        out["documents"] = docs
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
    def _api_gate(self, qs):
        """Citadel Gate — 존 카운트(raw/normalized/curated)·랭킹 top N·신호 분포."""
        raw_dir = getattr(self, "raw_dir", RAW_DIR)
        norm_root = getattr(self, "normalized_root", NORM_ROOT)
        z = self.facade.zone
        top = [{
            "subject_id": r.subject_id, "rank": r.rank, "signal": r.signal,
            "value": r.confidence["value"],
            "evidence_count": r.confidence["evidence_count"],
            "independent_source_count": r.confidence["independent_source_count"],
        } for r in self.facade._ranking.ranked(limit=5)]
        raw_sources, raw_total = _count_raw(raw_dir)
        norm = _count_normalized(norm_root)
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
        norm_root = getattr(self, "normalized_root", NORM_ROOT)
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
        return {"sources": sources, "freshness": _freshness(norm_root),
                "intake": intake, "slo": _slo_panel(),
                # 표시용 run 메트릭 요약 (TS-6) — drill-down 은 Grafana 몫.
                "run_metrics": _recent_run_metrics(
                    getattr(self, "metrics_connect", None)),
                # 동반 구성요소 접속 패널 — 도달성 TCP 실측 (component_status).
                "components": component_status.probe_components()}

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
        norm_root = getattr(self, "normalized_root", NORM_ROOT)
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
            norm_root, limit=limit, offset=offset, source_type=source_type,
            source=source, language=language, q=q, doc_ids=doc_ids, sort=sort)
        for d in docs:
            d["cluster_role"] = role_map.get(d.get("doc_id"))
        facets["cluster_role"] = role_counts
        page |= {"source_type": source_type or "", "source": source or "",
                 "language": language or "", "role": role or "", "q": q or "",
                 "doc_ids": ",".join(want)}
        raw_sources, raw_total = _count_raw(raw_dir)
        segment_kinds, url_groups = _archive_facets(norm_root)
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
        """normalized Iceberg segments for source-span round trips."""
        doc_id = unquote(qs.get("doc", ""))
        zone = None
        try:
            zone = _normalized(getattr(self, "normalized_root", NORM_ROOT))
            if zone is None:
                raise RuntimeError("catalog unavailable")
            return zone.document(doc_id)
        except Exception:
            return {"doc_id": doc_id, "available": False, "segments": [],
                    "note": "normalized Iceberg 미가동 (honest-gap §6.2)"}
        finally:
            if zone:
                zone.close()

    @_j
    def _api_council(self, qs):
        """Council — 기존 보고서를 조회하고 durable 비동기 실행 가능성을 노출한다."""
        subj = unquote(qs.get("subject", ""))
        rep = self.facade.get_investigation_report(subj)
        if rep is None:
            return {"error": "not_found"}
        rep["execution"] = {
            "available": True,
            "note": "조사는 PostgreSQL-backed 비동기 job으로 실행·영속한다. "
                    "graph·curated evidence는 read-only다.",
        }
        return rep



    def do_POST(self):
        parsed = urlparse(self.path)
        cancel_prefix = "/api/investigations/"
        if (parsed.path.startswith(cancel_prefix)
                and parsed.path.endswith(":cancel")):
            investigation_id = parsed.path[len(cancel_prefix):-len(":cancel")]
            try:
                store, conn = self._investigation_store()
                try:
                    cancelled = store.cancel(investigation_id)
                finally:
                    conn.close()
            except Exception:
                self._send_json(
                    503,
                    self._investigation_error(
                        "investigation_store_unavailable",
                        "investigation PostgreSQL 저장소에 연결할 수 없습니다.",
                    ),
                )
                return
            if cancelled is None:
                self._send_json(
                    404,
                    self._investigation_error(
                        "investigation_not_found", "조사를 찾을 수 없습니다.",
                        investigation_id=investigation_id,
                    ),
                )
                return
            self._send_json(200, cancelled)
            return

        if parsed.path == "/api/collections":
            try:
                payload = self._request_json()
                source_ids = payload.get("source_ids")
                if not isinstance(source_ids, list):
                    raise ValueError("source_ids는 array여야 합니다")
                created = self._collection_control().trigger(source_ids)
            except _RequestTooLarge as exc:
                self._send_json(413, self._investigation_error(
                    "request_too_large", str(exc)))
                return
            except ValueError as exc:
                self._send_json(400, self._investigation_error(
                    "invalid_collection_request", str(exc)))
                return
            except RuntimeError as exc:
                self._send_json(409, self._investigation_error(
                    "collection_already_running", str(exc)))
                return
            self._send_json(202, created, headers={"Retry-After": "2"})
            return

        if parsed.path != "/api/investigations":
            self._send_json(
                404,
                self._investigation_error("route_not_found", "요청 경로를 찾을 수 없습니다."),
            )
            return
        try:
            payload = self._request_json()
            idempotency_key = self.headers.get("Idempotency-Key", "")
            scope = payload.get("scope") or {}
            if not isinstance(scope, dict):
                raise ValueError("scope는 object여야 합니다")
            from orc_citadel.investigation_report import default_report_profile

            store, conn = self._investigation_store()
            try:
                created = store.create(
                    question=payload.get("question", ""),
                    subject_id=payload.get("subject_id"),
                    scope=scope,
                    mode=payload.get("mode", "deterministic"),
                    idempotency_key=idempotency_key,
                    version_tuple=extraction_version_tuple(),
                    report_profile=default_report_profile(),
                )
            finally:
                conn.close()
        except _RequestTooLarge as exc:
            self._send_json(
                413,
                self._investigation_error("request_too_large", str(exc)),
            )
            return
        except ValueError as exc:
            self._send_json(
                400,
                self._investigation_error("invalid_investigation_request", str(exc)),
            )
            return
        except Exception:
            self._send_json(
                503,
                self._investigation_error(
                    "investigation_store_unavailable",
                    "investigation PostgreSQL 저장소에 연결할 수 없습니다.",
                ),
            )
            return

        self._send_json(
            202,
            created,
            headers={
                "Location": f"/api/jobs/{created['job']['job_id']}",
                "Retry-After": "1",
            },
        )


    def do_GET(self):
        parsed = urlparse(self.path)
        if self._serve_durable_investigation_get(parsed):
            return
        if self._serve_collection_get(parsed.path):
            return
        Handler._ensure_facade()
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

        # canonical 라우트는 frontend dist 가 유일한 표시 계층이다 (TS-1 —
        # 인라인 페이지·/legacy/* 는 이관 완료로 제거, Step 15). dist 는 커밋
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


# canonical 라우트 → frontend dist 엔트리 (TS-1).
_MIGRATED = {
    "/": "gate.html",
    "/witnesses": "witnesses.html",
    "/table": "table.html",
    "/archive": "archive.html",
    "/spire": "spire.html",
    "/council": "council.html",
    "/reports": "reports.html",
    "/watchtower": "watchtower.html",
    "/chronicle": "chronicle.html",
    "/about": "about.html",
}


def main() -> None:
    Handler._ensure_facade()
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
