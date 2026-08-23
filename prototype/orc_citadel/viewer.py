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

from orc_citadel.api_facade import ApiFacade
from orc_citadel.curated_zone import CuratedZone
from orc_citadel.graph_service import GraphService
from orc_citadel.viewer_pages import PAGE_GATE, PAGE_TABLE

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
    """
    raw_dir = pathlib.Path(raw_dir)
    out: list[dict] = []
    if raw_dir.is_dir():
        for source in sorted(p.name for p in raw_dir.iterdir() if p.is_dir()):
            doc_dir = raw_dir / source / "doc"
            n = sum(1 for d in doc_dir.iterdir() if d.is_dir()) if doc_dir.is_dir() else 0
            out.append({"source_id": source, "doc_count": n})
    return out, sum(s["doc_count"] for s in out)


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

    def log_message(self, *a):  # 출력 간소화 (404 등만 남김)
        if self.path.startswith("/api/"):
            super().log_message(*a)

    # --- API (JSON) ---
    @_j
    def _api_report(self, qs):
        subj = unquote(qs.get("subject", ""))
        return self.facade.get_investigation_report(subj) or {"error": "not_found"}

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
            "planned_subclaims": planned_view,
            "coverage": inv.coverage,
            "terminated_by": inv.terminated_by,
            "gaps": inv.gaps,
            "counter_evidence": len(inv.counter_evidence),
            "retrieved": inv.retrieved,
            "conclusion": rep.conclusion,
            "statements": rep.statements,
            "open_questions": rep.open_questions,
            "audit": rep.audit,
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
        if parsed.path == "/api/gate":
            body = self._api_gate(qs).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        body = _page_for(parsed.path).encode()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


_PAGES = {
    "/": PAGE_GATE,        # Citadel Gate (진입 대시보드)
    "/table": PAGE_TABLE,  # 기존 개발 화면 (랭킹·보고서·조사·근거)
}  # watchtower/spire/archive/chronicle 는 각 스텝에서 추가.


def _page_for(path: str) -> str:
    """라우트 → 페이지 HTML. 미지정 경로는 기본('/')을 사용한다."""
    return _PAGES.get(path, _PAGES["/"])

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
