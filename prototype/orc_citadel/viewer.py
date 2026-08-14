"""S32 뷰어 — 실데이터를 브라우저로 직접 확인하는 read-only 개발 서버 (stdlib).

FastAPI·신규 의존 없이 `http.server`로 S32 API 파사드(09 §2/§3 wire 계약)를
서빙한다. 조회 전용(read-only, 불변식 §3-3) — 쓰기 엔드포인트 없음.

결정적·재현: 커리티드 존(curated.duckdb)을 읽어 subject 랭킹(S31)·조사 보고서(S30)·
claim 근거(S29)를 HTML로 렌더링한다.

실행:  .venv/bin/python -m orc_citadel.viewer     # http://127.0.0.1:8791
"""
from __future__ import annotations

import html
import json
import os
import pathlib
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

from orc_citadel.api_facade import ApiFacade
from orc_citadel.curated_zone import CuratedZone
from orc_citadel.graph_service import GraphService

# 컨테이너에서는 VIEWER_HOST=0.0.0.0 으로 외부 바인딩 (docker-compose.yml).
HOST, PORT = os.environ.get("VIEWER_HOST", "127.0.0.1"), 8791
DB = pathlib.Path(__file__).resolve().parent.parent / "data" / "curated.duckdb"

# JSON serialization — datetime/tuple을 str로.
def _j(fn):
    def wrap(*a, **k):
        return json.dumps(fn(*a, **k), default=str, ensure_ascii=False)
    return wrap


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


def _esc(v): return html.escape(str(v))


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
        from orc_citadel.investigation import Subclaim, InvestigationCoverage
        from orc_citadel.investigation_runner import InvestigationRunner
        from orc_citadel.synthesis import Synthesizer
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
        subclaims = [Subclaim("s1", "announces?", subject_id=subj)]
        inv = InvestigationRunner(z, g).run(subclaims)
        rep = Synthesizer(z).synthesize(inv, subj)
        # War Table — 조사 subgraph(진행식 disclosure 시드, 06 §8.1) 노출.
        graph_view = facade.get_investigation_graph(subj, hops=1)
        return {
            "subject_id": subj,
            "coverage": inv.coverage,
            "terminated_by": inv.terminated_by,
            "gaps": inv.gaps,
            "counter_evidence": len(inv.counter_evidence),
            "retrieved": inv.retrieved,
            "conclusion": rep.conclusion,
            "statements": rep.statements,
            "open_questions": rep.open_questions,
            "audit": rep.audit,
            "subgraph": graph_view["subgraph"],
            "relation_paths": graph_view["relation_paths"],
            "independence_summary": graph_view["independence_summary"],
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

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        body = _PAGE.encode()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


_PAGE = """<!doctype html><html lang="ko"><meta charset="utf-8">
<title>Orc Citadel — 실데이터 뷰어 (09 §2/§3)</title>
<style>
 :root{--bg:#0f1419;--panel:#1a2230;--line:#2a3444;--txt:#e6edf3;--mut:#8b98a9;
   --hi:#4ade80;--md:#fbbf24;--lo:#f87171;--acc:#60a5fa;}
 *{box-sizing:border-box} body{margin:0;font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;
   background:var(--bg);color:var(--txt);padding:28px}
 h1{font-size:20px;margin:0 0 4px} .sub{color:var(--mut);margin-bottom:24px}
 h2{font-size:15px;margin:28px 0 10px;border-bottom:1px solid var(--line);padding-bottom:6px}
 .card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px;margin-bottom:14px}
 table{border-collapse:collapse;width:100%} th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line);vertical-align:top}
 th{color:var(--mut);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.5px}
 .pill{display:inline-block;padding:1px 9px;border-radius:20px;font-size:12px;font-weight:600}
 .hi{background:#14532d;color:var(--hi)} .normal{background:#1e3a5f;color:var(--acc)}
 .med{background:#713f12;color:var(--md)} .lo{background:#7f1d1d;color:var(--lo)}
 .contradicted{background:#701a1a;color:#fca5a5}
 .bar{background:#0a0e14;border-radius:6px;height:10px;width:140px;display:inline-block;vertical-align:middle;margin-right:8px;overflow:hidden}
 .bar>i{display:block;height:100%;background:var(--acc)}
 a{color:var(--acc);text-decoration:none;cursor:pointer} a:hover{text-decoration:underline}
 .dim{font-size:12px;color:var(--mut)} .muted{color:var(--mut)}
 .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}
 .badge{display:inline-block;background:#0a0e14;border:1px solid var(--line);border-radius:6px;padding:1px 7px;margin:2px;font-size:12px}
 .err{color:var(--lo)}
</style>
<body>
<h1>🏰 Orc Citadel — 실데이터 뷰어</h1>
<div class="sub">Phase 0 · 커리티드 존(curated.duckdb) · read-only (09 §2 / §3 wire 계약) · 파이프라인 → 어세션 → 근거 신뢰도</div>

<h2>📊 Subject 신뢰도 랭킹 <span class="dim">(S31 · value 단일 게이지 금지 → 봉투 노출)</span></h2>
<div class="card"><table id="rank"></table></div>

<h2>🔍 Subject 조사 보고서 <span class="dim">(S30 · 09 §3 conclusion</span></h2>
<div class="grid" id="reports"></div>

<h2>🔁 조사 에이전트 <span class="dim">(S43–S47 · coverage→explorer→counter-evidence→report)</span></h2>
<div class="card"><div id="investigation"><span class="muted">subject 보고서에서 "조사 실행"을 누르면 end-to-end 조사가 렌더링됩니다.</span></div></div>

<h2>🧾 Claim 근거 <span class="dim">(S29 · 09 §2.3 evidence)</span></h2>
<div class="card"><div id="evidence"><span class="muted">subject를 선택한 뒤 근거를 로드하세요.</span></div></div>

<script>
const $=s=>document.querySelector(s);
const dark=b=>{const w=Math.max(2,Math.round(b*140));const x=Math.min(255,Math.round(b*60+40));
  return `linear-gradient(90deg,#0b3a2e 0%,rgb(${x},${Math.round(180*b+40)},${Math.round(120*b+40)}) ${w}%)`};
const pill=s=>s==='high_confidence'?'<span class="pill hi">high</span>':s==='contradicted'
  ?'<span class="pill contradicted">contradicted</span>':s==='low_evidence'?'<span class="pill lo">low evidence</span>'
  :'<span class="pill normal">normal</span>';
const valBar=v=>'<span class="bar"><i style="width:'+Math.max(2,v*100)+'%;background:'+dark(v)+'"></i></span>'+(v*100).toFixed(0)+'%';
function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML;}

async function loadRank(){
  const r=await (await fetch('/api/rank')).json();
  $('#rank').innerHTML='<tr><th>#</th><th>Subject</th><th>신호</th><th>value</th><th>근거</th><th>독립출처</th><th>predicate</th><th></th></tr>'+
    r.items.map(x=>`<tr><td>#${x.rank}</td><td>${esc(x.subject_id)}</td><td>${pill(x.signal)}</td>
    <td>${valBar(x.value)}</td><td>${x.evidence_count}</td><td>${x.independent_source_count}</td>
    <td>${Object.entries(x.predicates).map(([p,c])=>`<span class="badge">${esc(p)}×${c}</span>`).join(' ')}</td>
    <td><a data-subj="${esc(x.subject_id)}" class="pick">보고서</a></td></tr>`).join('');
  document.querySelectorAll('.pick').forEach(a=>a.onclick=e=>{selectSubject(e.target.dataset.subj);});
}

async function selectSubject(subj){
  const r=await (await fetch('/api/report?subject='+encodeURIComponent(subj))).json();
  if(r.error){$('#evidence').innerHTML='<span class="err">not found</span>';return;}
  const c=r.confidence,d=c.dimensions;
  const openQ=Array.isArray(r.open_questions)&&r.open_questions.length;
  $('#reports').innerHTML=`
    <div class="card"><div style="font-size:15px;font-weight:700;margin-bottom:6px">${esc(subj)}</div>
      ${pill(r.signal)} <span class="muted">· ${esc(r.id.slice(0,18))}…</span>
      <p style="margin:10px 0 0">결론 신뢰도 <b>${valBar(c.value)}</b></p>
      <p class="dim">근거 ${c.evidence_count}건 · 독립출처 ${c.independent_source_count}건</p>
      <p class="dim">support ${d.support.toFixed(2)} · contradiction ${d.contradiction.toFixed(2)} · coverage ${d.coverage.toFixed(2)}</p>
      <p class="dim">${esc(c.basis)}</p>
      <p><b>predicate</b>: ${Object.entries(r.by_predicate).map(([p,v])=>esc(p)+' ('+v.count+')').join(', ')}</p>
      ${openQ?`<p class="err"><b>미결 질문</b>: ${r.open_questions.map(q=>esc(q.predicate)+'('+esc(q.reason)+')').join(', ')}</p>`:''}
      <p style="margin:12px 0 0"><a data-subj="${esc(subj)}" class="loadClaims">근거 조회</a> ·
        <a data-subj="${esc(subj)}" class="loadInvest">🔁 조사 실행</a></p>
    </div>`;
  const a=document.querySelector('.loadClaims');
  if(a) a.onclick=e=>loadClaims(e.target.dataset.subj);
  const b=document.querySelector('.loadInvest');
  if(b) b.onclick=e=>loadInvestigation(e.target.dataset.subj);
}

async function loadClaims(subj){
  const r=await (await fetch('/api/subject_claims?subject='+encodeURIComponent(subj))).json();
  $('#evidence').innerHTML='<p class="dim">subject '+esc(subj)+' — claims '+r.items.length+'건</p>'+
    r.items.map(c=>`<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid var(--line)">
      <span>${esc(c.predicate)} · ${esc(c.object_literal||c.object_id||'—')} <span class="dim">(${esc(c.modality)})</span></span>
      <a data-c="${esc(c.claim_id)}" class="loadEv">근거 ${c.claim_id.slice(0,12)}…</a></div>`).join('');
  document.querySelectorAll('.loadEv').forEach(x=>x.onclick=e=>loadOneEvidence(e.target.dataset.c));
}

async function loadOneEvidence(claim){
  const r=await (await fetch('/api/evidence?claim='+encodeURIComponent(claim))).json();
  const inner=r.items.map(it=>`<div style="padding:6px 0;border-bottom:1px solid var(--line)">
    <b>${esc(it.relation)}</b> · strength ${+it.strength.toFixed(2)} · doc <code>${esc(it.source_doc)}</code>
    <span class="dim">${esc(it.evidence_id.slice(0,16))}…</span></div>`).join('');
  $('#evidence').innerHTML=`<p class="dim">claim ${esc(claim)} — evidence ${r.items.length}건 (next_cursor: ${r.page.next_cursor?'있음':'null'})</p>`+
    (inner||'<span class="muted">근거 없음</span>');
}

async function loadInvestigation(subj){
  $('#investigation').innerHTML='<span class="muted">🔁 조사 실행 중…</span>';
  const r=await (await fetch('/api/investigate?subject='+encodeURIComponent(subj))).json();
  const c=r.conclusion,d=c.dimensions;
  const sg=r.subgraph||{entities:[],relationships:[]};
  const nodes=[...new Set([sg.entity,...sg.entities.map(e=>e.id),...sg.relationships.map(rl=>rl.from),...sg.relationships.map(rl=>rl.to)])].filter(Boolean);
  $('#investigation').innerHTML=`
    <p class="dim">subject ${esc(subj)} — <b>조사 루프 (S43–S47)</b></p>
    <p>coverage <b>${esc(r.coverage)}</b> · terminated_by <code>${esc(r.terminated_by)}</code>
      · gaps ${Array.isArray(r.gaps)?r.gaps.length:0} · counter_evidence ${esc(r.counter_evidence)}건</p>
    <p>결론 신뢰도 <b>${valBar(c.value)}</b> · 근거 ${c.evidence_count} · 독립 ${c.independent_source_count}
      <span class="dim">(support ${d.support.toFixed(2)} · contradiction ${d.contradiction.toFixed(2)} · coverage ${d.coverage.toFixed(2)})</span></p>
    <div id="wargraph" style="border:1px solid var(--line);border-radius:8px;padding:10px;margin:10px 0">
      <p class="dim"><b>War Table</b> — 조사 subgraph (노드 ${nodes.length} · 관계 ${sg.relationships.length})</p>
      <p class="dim">노드: ${nodes.map(n=>`<code>${esc(n)}</code>`).join(' ')}</p>
      <p class="dim">관계: ${(sg.relationships||[]).map(rl=>`<code>${esc(rl.from)} <span style="color:#8ab">—${esc(rl.type)}→</span> ${esc(rl.to)}</code>`).join(' ')}</p>
      ${r.relation_paths&&r.relation_paths.length?`<p class="dim">경로: ${r.relation_paths.map(p=>`<code>${esc(p)}</code>`).join(' · ')}</p>`:''}
      <p class="dim">독립출처: <b>${r.independence_summary?r.independence_summary.independent_source_count:0}</b>
        / 근거 ${r.independence_summary?r.independence_summary.evidence_count:0}
        (dedup_ratio ${r.independence_summary?r.independence_summary.dedup_ratio.toFixed(2):0})</p>
    </div>
    <p><b>statements (evidence-first)</b>:</p>
    ${(r.statements||[]).map(s=>`<div style="padding:4px 0;border-bottom:1px solid var(--line)">
      [${esc(s.modality)}] ${esc(s.text)} <span class="dim">(claim_ref ${esc((s.claim_ref||'').slice(0,14))})</span></div>`).join('')||'<span class="muted">문장 없음</span>'}
    ${(r.open_questions&&r.open_questions.length)?`<p class="err"><b>open_questions</b>: ${r.open_questions.map(q=>esc(q.subquestion)).join(', ')}</p>`:''}
    <p>Audit: ${r.audit&&r.audit.passed?'<span class="pill hi">PASS</span>':'<span class="pill lo">FAIL</span>'}
      <span class="dim">(${r.audit?r.audit.violations.length:0} violations)</span></p>`;
}
</script>
<script>
(async()=>{await loadRank();
  const first=document.querySelector('.pick');
  if(first) selectSubject(first.dataset.subj);
})();
</script>
</body></html>
"""


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
