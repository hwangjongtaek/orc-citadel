"""뷰어 페이지 HTML 템플릿 (stdlib, read-only).

`viewer.py` 의 dispatch 는 라우트당 페이지 문자열을 이 모듈에서 가져와 서빙한다.
JS 는 각 페이지가 `viewer.py` 의 `/api/*` JSON 엔드포인트를 fetch 해 클라이언트 렌더
(기존 `_PAGE` 패턴). 공유 CSS·공유 내비(경량 기능 링크)를 여기서 집중한다.

장식·애니메이션·일러스트는 범위 밖 (handoff-viewer-pages.md §2-4). read-only·결정적.
"""
import html

# 공유 스타일 — 모든 페이지가 사용 (dark 토큰, DESIGN.md).
CSS = """
 <style>
 :root{--bg:#0f1419;--panel:#1a2230;--line:#2a3444;--txt:#e6edf3;--mut:#8b98a9;
   --hi:#4ade80;--md:#fbbf24;--lo:#f87171;--acc:#60a5fa;}
 *{box-sizing:border-box} body{margin:0;font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;
   background:var(--bg);color:var(--txt);padding:28px}
 h1{font-size:20px;margin:0 0 4px} .sub{color:var(--mut);margin-bottom:20px}
 h2{font-size:15px;margin:26px 0 10px;border-bottom:1px solid var(--line);padding-bottom:6px}
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
 .err{color:var(--lo)} .na{color:var(--md)}
 .nav{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:22px;align-items:baseline}
 .nav a{color:var(--mut);border:1px solid var(--line);padding:4px 12px;border-radius:7px;font-size:13px}
 .nav a:hover{color:var(--txt);border-color:var(--acc)}
 .nav a.cur{color:var(--txt);background:#1e3a5f;border-color:var(--acc)}
 .nav .word{font-weight:700;color:var(--txt);margin-right:6px}
 </style>
"""


def nav(cur: str | None = None) -> str:
    """공간 내비 바 (경량 기능 링크). `cur` 가 현재 페이지면 강조."""
    links = [
        ("/", "Citadel Gate"),
        ("/table", "War Table · Council"),
        ("/watchtower", "Watchtower"),
        ("/archive", "Grand Archive"),
        ("/chronicle", "Chronicle Vault"),
        ("/spire", "Signal Spire"),
    ]
    body = "".join(
        f'<a class="{"cur" if (r == cur) else "normal"}" href="{r}">'
        f"{html.escape(t)}</a>" for r, t in links
    )
    return (
        '<div class="nav"><span class="word">🏰 Orc Citadel</span>' + body + "</div>"
    )


def _esc(v):
    return html.escape(str(v))


# --- 기존 개발 화면 (랭킹·보고서·조사·근거) — /table 에 서빙. ---
PAGE_TABLE = """<!doctype html><html lang="ko"><meta charset="utf-8">
<title>Orc Citadel — War Table · Council (실데이터 뷰어)</title>
""" + CSS + """
<body>
<h1>🏰 Orc Citadel — War Table · Council <span class="dim">(실데이터 뷰어)</span></h1>
<div class="sub">Phase 0 · 커리티드 존(curated.duckdb) · read-only (09 §2 / §3 wire 계약) · 파이프라인 → 어세션 → 근거 신뢰도</div>
""" + nav("/table") + """

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


# --- Citadel Gate — 홈/진입 대시보드 (`/`). ---
PAGE_GATE = """<!doctype html><html lang="ko"><meta charset="utf-8">
<title>Orc Citadel — Citadel Gate (진입 대시보드)</title>
""" + CSS + """
<body>
<h1>🏰 Orc Citadel — Citadel Gate <span class="dim">(홈 · 진입 대시보드)</span></h1>
<div class="sub">Temporal Evidence Intelligence · 시스템 상태 · 존 카운트 · 랭킹 top N · read-only</div>
""" + nav("/") + """

<h2>🗄️ 시스템 존 요약 <span class="dim">(raw / normalized / curated — 실측)</span></h2>
<div class="grid" id="zones"></div>

<h2>📊 Subject 랭킹 top 5 <span class="dim">(S31 · value + 근거 + 독립출처 봉투)</span></h2>
<div class="card"><table id="rank"></table></div>

<h2>🚦 신호 분포 <span class="dim">(contradicted · low_evidence · high_confidence · normal)</span></h2>
<div class="card" id="signals"></div>

<script>
const $=s=>document.querySelector(s);
const dark=b=>{const w=Math.max(2,Math.round(b*140));const x=Math.min(255,Math.round(b*60+40));
  return `linear-gradient(90deg,#0b3a2e 0%,rgb(${x},${Math.round(180*b+40)},${Math.round(120*b+40)}) ${w}%)`};
const pill=s=>s==='high_confidence'?'<span class="pill hi">high</span>':s==='contradicted'
  ?'<span class="pill contradicted">contradicted</span>':s==='low_evidence'?'<span class="pill lo">low evidence</span>'
  :'<span class="pill normal">normal</span>';
const valBar=v=>'<span class="bar"><i style="width:'+Math.max(2,v*100)+'%;background:'+dark(v)+'"></i></span>'+(v*100).toFixed(0)+'%';
function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML;}

(async()=>{
  const r=await (await fetch('/api/gate')).json();
  $('#zones').innerHTML=[
    ['raw', r.raw_doc_count+' docs', (r.raw_sources||[]).length+' source'],
    ['normalized', r.normalized_counts.documents+' docs', r.normalized_counts.segments+' segments'],
    ['curated', r.curated.assertions+' assertions', r.curated.entities+' entities · '+r.curated.mentions+' mentions'],
    ['dedup', r.curated.dup_clusters+' clusters', ''],
  ].map(z=>`<div class="card"><div style="font-size:15px;font-weight:700">${esc(z[0])}</div>
    <div style="font-size:13px;margin-top:4px">${esc(z[1])}</div><div class="dim">${esc(z[2])}</div></div>`).join('');

  const rows=(r.ranking_top||[]).map(x=>`<tr><td>#${x.rank}</td><td>${esc(x.subject_id)}</td>${pill(x.signal)}
    <td>${valBar(x.value)}</td><td>${x.evidence_count}</td><td>${x.independent_source_count}</td>
    <td><a href="/table">상세</a></td></tr>`).join('');
  $('#rank').innerHTML='<tr><th>#</th><th>Subject</th><th>신호</th><th>value</th><th>근거</th><th>독립출처</th><th></th></tr>'+rows;

  const sig=Object.entries(r.signal_distribution||{}).map(([k,v])=>`<span class="badge">${pill(k)} ${esc(k)} <b>${v}</b></span>`).join(' ')||'<span class="muted">정보 없음</span>';
  $('#signals').innerHTML=sig;
})();
</script>
</body></html>
"""


# --- Watchtower — 수집 관제 (`/watchtower`). ---
PAGE_WATCHTOWER = """<!doctype html><html lang="ko"><meta charset="utf-8">
<title>Orc Citadel — Watchtower · Ingestion Monitor (수집 관제)</title>
""" + CSS + """
<body>
<h1>🏰 Orc Citadel — Watchtower · Ingestion Monitor <span class="dim">(수집 관제)</span></h1>
<div class="sub">source 수집 사실(실측) · SLO 판정표(honest-gap §6.2) · read-only</div>
""" + nav("/watchtower") + """

<h2>📡 Source 상태 <span class="dim">(raw 존 · source × 문서 수 · source_type)</span></h2>
<div class="card"><table id="sources"></table></div>

<h2>🛎️ SLO 판정표 <span class="dim">(nightly 5 — 관측 미누적 → 전항 not-measured, 정직)</span></h2>
<div class="card"><table id="slo"></table></div>

<h2>📈 Error Budget <span class="dim">(위반/측정 — 측정 없음이면 ratio None)</span></h2>
<div class="card" id="budget"></div>

<script>
const $=s=>document.querySelector(s);
function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML;}

(async()=>{
  const r=await (await fetch('/api/watchtower')).json();
  $('#sources').innerHTML='<tr><th>Source</th><th>type</th><th>문서 수</th></tr>'+
    (r.sources||[]).map(s=>`<tr><td>${esc(s.source_id)}</td><td><span class="badge">${esc(s.source_type)}</span></td>
      <td>${s.doc_count}</td></tr>`).join('')||'<span class="muted">source 없음</span>';

  const sl=(r.slo.nightly_slos||[]).map(x=>`<tr><td>${esc(x.slo_id)}</td>
    <td><span class="pill lo">${esc(x.classified)}</span></td><td class="dim">${esc(x.reason)}</td></tr>`).join('');
  $('#slo').innerHTML='<tr><th>SLO</th><th>판정</th><th>이유</th></tr>'+sl;

  const eb=r.slo.error_budget||{};
  $('#budget').innerHTML=`<p>violations <b>${eb.violations}</b> · measured <b>${eb.measured_count}</b>
    · violation_ratio <b>${eb.violation_ratio===null?'<span class="na">not-measured (분모 제외)</span>':eb.violation_ratio}</b></p>`;
})();
</script>
</body></html>
"""


# --- Signal Spire — 알림 센터 (`/spire`). ---
PAGE_SPIRE = """<!doctype html><html lang="ko"><meta charset="utf-8">
<title>Orc Citadel — Signal Spire · Alerts (알림 센터)</title>
""" + CSS + """
<body>
<h1>🏰 Orc Citadel — Signal Spire · Alerts <span class="dim">(알림 센터)</span></h1>
<div class="sub">결론·confidence 의 중요 변화 한정 알림 · fire-once (11 §4, ADR-1104) · read-only</div>
""" + nav("/spire") + """

<h2>🔔 5 종 트리거 카탈로그 <span class="dim">(정본 signal_spire.TRIGGER_TYPES)</span></h2>
<div class="card"><table id="triggers"></table></div>

<h2>🕯️ 알림 피드 <span class="dim">(실 점화 없음 → 정직 빈 상태, §6.2)</span></h2>
<div class="card" id="feed"><span class="muted">새 알림 없음 — 아직 점화된 알림이 없습니다.</span></div>

<script>
const $=s=>document.querySelector(s);
function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML;}

(async()=>{
  const r=await (await fetch('/api/spire')).json();
  $('#triggers').innerHTML='<tr><th>Trigger</th><th>의미</th></tr>'+
    (r.trigger_catalog||[]).map(t=>`<tr><td><code>${esc(t.trigger)}</code></td><td>${esc(t.description)}</td></tr>`).join('');
  $('#feed').innerHTML='<p class="muted">'+esc(r.note)+'</p><p class="dim">'+esc(r.fire_once_rule)+'</p>';
})();
</script>
</body></html>
"""


# --- Grand Archive — 문서 탐색 (`/archive`). ---
PAGE_ARCHIVE = """<!doctype html><html lang="ko"><meta charset="utf-8">
<title>Orc Citadel — Grand Archive (문서 탐색)</title>
""" + CSS + """
<body>
<h1>🏰 Orc Citadel — Grand Archive <span class="dim">(문서 탐색)</span></h1>
<div class="sub">normalized documents · raw source 목록 · dedup lineage · read-only</div>
""" + nav("/archive") + """

<h2>📚 Normalized Documents <span class="dim">(oc.duckdb · read-only · segment 수 포함)</span></h2>
<div class="card"><table id="docs"></table></div>

<h2>📦 Raw 존 <span class="dim">(source × 문서 수 — Atom meta/전체 page 두 형식 공존)</span></h2>
<div class="card"><table id="raw"></table></div>

<h2>♻️ Dedup Cluster <span class="dim">(curated clusters)</span></h2>
<div class="card" id="clusters"></div>

<script>
const $=s=>document.querySelector(s);
function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML;}

(async()=>{
  const r=await (await fetch('/api/archive')).json();
  $('#docs').innerHTML='<tr><th>doc_id</th><th>source</th><th>title</th><th>segments</th><th>char_len</th><th>parser</th></tr>'+
    (r.normalized_documents||[]).map(d=>`<tr>
      <td><code>${esc(d.doc_id)}</code></td><td>${esc(d.source_id)}</td><td>${esc(d.title||'')}</td>
      <td>${d.segments}</td><td>${d.char_len}</td><td><span class="badge">${esc(d.parser_version)}</span></td></tr>`).join('')||'<span class="muted">문서 없음</span>';

  $('#raw').innerHTML='<tr><th>source</th><th>문서 수</th></tr>'+
    (r.raw_sources||[]).map(s=>`<tr><td>${esc(s.source_id)}</td><td>${s.doc_count}</td></tr>`).join('')||'<span class="muted">raw 없음</span>';

  $('#clusters').innerHTML='<p>dedup clusters <b>'+r.dedup_clusters+'</b></p><p class="dim">'+esc(r.format_note)+'</p>';
})();
</script>
</body></html>
"""
