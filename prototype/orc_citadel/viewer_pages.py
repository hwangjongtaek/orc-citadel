"""뷰어 페이지 HTML 템플릿 (stdlib, read-only).

`viewer.py` 의 dispatch 는 라우트당 페이지 문자열을 이 모듈에서 가져와 서빙한다.
JS 는 각 페이지가 `viewer.py` 의 `/api/*` JSON 엔드포인트를 fetch 해 클라이언트 렌더
(기존 `_PAGE` 패턴). 공유 CSS·공유 내비(경량 기능 링크)를 여기서 집중한다.

장식·애니메이션·일러스트는 범위 밖 (handoff-viewer-pages.md §2-4). read-only·결정적.
"""
import html

# 공유 스타일 — DESIGN.md 토큰 + 목업 공유 셸 (docs/mockups/*.html 인라인 셸 재현).
# 외부 폰트(Cinzel/Space Grotesk/Inter/JetBrains)는 오프라인 stdlib 뷰어라
# --font-* 의 로컬 fallback 스택으로 대체 (목업 자체가 fallback 병기).
CSS = """
<style>
 :root{
   --citadel-void:#07111C; --citadel-night:#0D1B2A;
   --surface:#111820; --surface-variant:#26313A;
   --on-surface:#D6CCB8; --on-surface-muted:#59636A; --parchment:#C8B58E;
   --primary:#45E06F; --secondary:#20B85A; --ember:#E97824; --signal-amber:#FFB13B;
   --crimson:#7B2833; --error:#E05252; --uncertain:#A78BFA; --superseded:#59636A;
   --font-display:"Cinzel",Georgia,serif; --font-head:"Space Grotesk",system-ui,sans-serif;
   --font-body:"Inter",system-ui,sans-serif; --font-data:"JetBrains Mono",ui-monospace,monospace;
   --r-sm:4px; --r-md:8px; --r-lg:12px; --r-full:9999px;
   --sp-xs:4px; --sp-sm:8px; --sp-md:16px; --sp-lg:24px; --sp-xl:32px;
 }
 *{box-sizing:border-box;margin:0;padding:0}
 body{font-family:var(--font-body);background:var(--citadel-void);color:var(--on-surface);font-size:14px;line-height:1.55;-webkit-font-smoothing:antialiased}
 .app{min-height:100vh;background:var(--citadel-night)}
 main{max-width:1200px;margin:0 auto;padding:var(--sp-md) var(--sp-lg) var(--sp-xl)}
 .mono{font-family:var(--font-data)}
 a{color:var(--secondary);text-decoration:none} a:hover{color:var(--primary);text-decoration:underline}
 ::selection{background:rgba(69,224,111,.25)}
 h1{font-size:20px;margin:0 0 4px;font-family:var(--font-head)}
 .sub{color:var(--on-surface-muted);margin-bottom:20px}
 header{display:flex;align-items:center;gap:var(--sp-lg);padding:10px var(--sp-lg);background:var(--surface);border-bottom:1px solid var(--surface-variant)}
 .wordmark{font-family:var(--font-display);font-weight:700;font-size:18px;letter-spacing:.14em;color:var(--on-surface);display:flex;align-items:center;gap:10px;white-space:nowrap}
 .crest{width:22px;height:22px;flex:none;display:grid;place-items:center;color:var(--primary)}
 .space{display:flex;flex-direction:column;min-width:0;padding-left:var(--sp-lg);border-left:1px solid var(--surface-variant)}
 .space .eyebrow{font-family:var(--font-head);font-size:10px;font-weight:600;letter-spacing:.14em;text-transform:uppercase;color:var(--on-surface-muted)}
 .space .title{font-family:var(--font-head);font-size:15px;font-weight:600;color:var(--on-surface);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
 .grow{flex:1 1 auto}
 .search{display:flex;align-items:center;gap:8px;background:var(--surface-variant);border-radius:var(--r-md);padding:8px 12px;width:300px;max-width:32vw;color:var(--on-surface-muted)}
 .search svg{flex:none}
 .search input{background:none;border:none;outline:none;color:var(--on-surface);font-family:var(--font-body);font-size:13px;width:100%}
 .search input::placeholder{color:var(--on-surface-muted)}
 .spire{position:relative;display:flex;align-items:center;gap:8px;font-family:var(--font-head);font-size:12px;font-weight:600;color:var(--signal-amber);background:rgba(255,177,59,.08);border:1px solid rgba(255,177,59,.3);padding:8px 12px;border-radius:var(--r-md);cursor:pointer;white-space:nowrap}
 .spire .dot{width:7px;height:7px;border-radius:var(--r-full);background:var(--signal-amber);box-shadow:0 0 8px 1px var(--signal-amber)}
 .masthead{position:relative;height:108px;overflow:hidden;border-bottom:1px solid var(--surface-variant);display:flex;align-items:center;padding:0 var(--sp-lg);background:linear-gradient(90deg,rgba(7,17,28,.95) 0%,rgba(7,17,28,.72) 55%,rgba(13,27,42,.42) 100%),var(--citadel-night)}
 .masthead h1{font-family:var(--font-head);font-size:22px;font-weight:600;color:var(--on-surface);letter-spacing:-.01em;text-shadow:0 2px 14px rgba(7,17,28,.9)}
 .masthead p{font-family:var(--font-head);font-size:11px;font-weight:500;letter-spacing:.08em;text-transform:uppercase;color:var(--parchment);margin-top:5px;text-shadow:0 2px 14px rgba(7,17,28,.9)}
 .spaces{display:flex;flex-wrap:wrap;gap:2px;margin-bottom:var(--sp-lg)}
 .spaces a{padding:6px 12px;border-radius:var(--r-md);font-family:var(--font-head);font-size:12px;font-weight:600;color:var(--on-surface-muted)}
 .spaces a:hover{color:var(--on-surface);background:var(--surface-variant)}
 .spaces a.active{color:var(--primary);background:rgba(69,224,111,.08)}
 .panel,.card{background:var(--surface);border:1px solid var(--surface-variant);border-radius:var(--r-lg);overflow:hidden}
 .card{margin-bottom:var(--sp-md)}
 .card>.body,.panel-body{padding:var(--sp-md)}
 .panel-head{display:flex;align-items:center;justify-content:space-between;padding:12px var(--sp-md);border-bottom:1px solid var(--surface-variant)}
 .panel-head h2{font-family:var(--font-head);font-size:12px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--on-surface)}
 .panel-head .sub{font-family:var(--font-head);font-size:10px;letter-spacing:.08em;color:var(--on-surface-muted);text-transform:uppercase}
 h2.h{font-family:var(--font-head);font-size:12px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--on-surface);margin:var(--sp-md) 0 10px;display:flex;align-items:center;gap:8px}
 h2.h::after{content:"";flex:1;height:1px;background:var(--surface-variant)}
 table{border-collapse:collapse;width:100%;font-size:13px}
 th{font-family:var(--font-head);font-size:9.5px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--on-surface-muted);text-align:left;padding:8px 10px;border-bottom:1px solid var(--surface-variant);white-space:nowrap}
 td{padding:11px 10px;border-bottom:1px solid rgba(38,49,58,.5);vertical-align:middle}
 tr:last-child td{border-bottom:none}
 tbody tr:hover td{background:rgba(38,49,58,.28)}
 td.num,th.num{text-align:right;font-family:var(--font-data)}
 .badge{display:inline-block;font-family:var(--font-head);font-size:10px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;padding:3px 8px;border-radius:var(--r-sm);background:var(--surface-variant);color:var(--on-surface)}
 .badge.good{background:rgba(69,224,111,.14);color:var(--primary)}
 .badge.warn{background:rgba(255,177,59,.14);color:var(--signal-amber)}
 .badge.err{background:rgba(224,82,82,.14);color:var(--error)}
 .badge.uncert{background:rgba(167,139,250,.14);color:var(--uncertain)}
 .pill{display:inline-block;font-family:var(--font-head);font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;padding:3px 10px;border-radius:var(--r-md)}
 .pill.hi{background:rgba(69,224,111,.14);color:var(--primary)}
 .pill.normal{background:var(--surface-variant);color:var(--on-surface)}
 .pill.med{background:rgba(255,177,59,.14);color:var(--signal-amber)}
 .pill.lo{background:rgba(224,82,82,.14);color:var(--error)}
 .pill.contradicted{background:rgba(123,40,51,.55);color:var(--error)}
 .chip{display:inline-flex;align-items:center;gap:6px;font-family:var(--font-head);font-size:11px;font-weight:500;padding:5px 10px;border-radius:var(--r-full);border:1px solid var(--surface-variant);color:var(--on-surface);margin:0 6px 6px 0}
 .chip .sw{width:8px;height:8px;border-radius:var(--r-full);display:inline-block}
 .sec-label{font-family:var(--font-head);font-size:10px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:var(--on-surface-muted);display:flex;align-items:center;gap:8px;margin:var(--sp-md) 0 10px}
 .sec-label::after{content:"";flex:1;height:1px;background:var(--surface-variant)}
 .span{font-family:var(--font-data);font-size:11px;color:var(--parchment);background:var(--surface-variant);padding:8px 10px;border-radius:var(--r-sm)}
 .trail{display:flex;gap:6px;flex-wrap:wrap;font-family:var(--font-data);font-size:10px;color:var(--on-surface-muted)}
 .conf{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--surface-variant);border:1px solid var(--surface-variant);border-radius:var(--r-md);overflow:hidden}
 .conf .cell{background:var(--surface);padding:10px 12px}
 .conf .num{font-family:var(--font-head);font-size:20px;font-weight:600;color:var(--on-surface)}
 .conf .num.good{color:var(--primary)}
 .conf .cap{font-family:var(--font-head);font-size:9.5px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--on-surface-muted)}
 .btn{font-family:var(--font-head);font-size:11px;font-weight:600;padding:6px 12px;border-radius:var(--r-md);border:1px solid var(--surface-variant);color:var(--on-surface);background:none;cursor:pointer}
 .btn.primary{border-color:var(--primary);color:var(--primary);background:rgba(69,224,111,.06)}
 .btn.run{border:none;color:var(--citadel-void);background:var(--primary);box-shadow:0 0 0 1px rgba(69,224,111,.4),0 6px 18px -6px rgba(69,224,111,.5)}
 .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:var(--sp-md);margin-bottom:var(--sp-md)}
 .bar{background:var(--surface-variant);border-radius:6px;height:10px;width:140px;display:inline-block;vertical-align:middle;margin-right:8px;overflow:hidden}
 .bar>i{display:block;height:100%;background:var(--primary)}
 .dim{font-size:12px;color:var(--on-surface-muted)} .muted{color:var(--on-surface-muted)}
 .err{color:var(--error)} .na{color:var(--signal-amber)}
 code,pre{font-family:var(--font-data);font-size:12px;color:var(--parchment)}
 ::-webkit-scrollbar{width:8px;height:8px} ::-webkit-scrollbar-thumb{background:var(--surface-variant);border-radius:var(--r-full)}
</style>
"""


def nav(cur: str) -> str:
    """공간 전환 탭 (목업 .spaces 셸). `cur` 가 현재 페이지면 active."""
    links = [
        ("/", "Citadel Gate"),
        ("/table", "War Table · Council"),
        ("/watchtower", "Watchtower"),
        ("/archive", "Grand Archive"),
        ("/chronicle", "Chronicle Vault"),
        ("/spire", "Signal Spire"),
    ]
    tabs = "".join(
        f'<a class="{"active" if (r == cur) else ""}" href="{r}">{html.escape(t)}</a>'
        for r, t in links
    )
    return f'<nav class="spaces">{tabs}</nav>'


def _crest() -> str:
    """워드마크 쉴드(SVG) — 목업 .crest 재현."""
    return ('<span class="crest" aria-hidden="true">'
            '<svg width="22" height="22" viewBox="0 0 24 24" fill="none">'
            '<path d="M12 2 L20 6 V13 C20 18 12 22 12 22 C12 22 4 18 4 13 V6 Z" '
            'stroke="currentColor" stroke-width="1.6" fill="rgba(69,224,111,.07)"/>'
            '<path d="M9 9 Q12 12 15 9 M12 11 V15" stroke="currentColor" stroke-width="1.6" '
            'stroke-linecap="round"/><circle cx="12" cy="8" r="1.3" fill="currentColor"/>'
            '</svg></span>')


def _search_icon() -> str:
    return ('<svg width="15" height="15" viewBox="0 0 24 24" fill="none">'
            '<circle cx="11" cy="11" r="7" stroke="currentColor" stroke-width="2"/>'
            '<path d="M20 20 L16.5 16.5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
            '</svg>')


# 공간별 (라우트) 브레이드크럼 — (eyebrow EN·function, title KO).
_SPACE_META = {
    "/":         ("Citadel Gate · Home", "본부 · Home"),
    "/table":    ("War Table · Council Chamber", "조사 · 그래프"),
    "/watchtower": ("Watchtower · Ingestion", "수집 관제"),
    "/archive":  ("Grand Archive · Documents", "문서 탐색"),
    "/chronicle": ("Chronicle Vault · History", "시간 탐색"),
    "/spire":    ("Signal Spire · Alerts", "알림 센터"),
}


def shell(route: str, body: str, title: str) -> str:
    """목업 공유 셸로 페이지를 감싼 전체 HTML.

    header(워드마크+브레이드크럼+검색+Signal Spire 칩)·masthead 밴드·공간 탭을
    포함하고, `body`(페이지 본문+JS)를 main 에 넣는다. 히어로 PNG 는 오프라인이므로
    flat night 그라데이션으로 대체(목업 .masthead 의 fallback 조합).
    """
    eyebrow, app_title = _SPACE_META.get(route, _SPACE_META["/"])
    return (
        '<!doctype html><html lang="ko"><meta charset="utf-8">'
        f"<title>{html.escape(title)}</title>" + CSS +
        '<body><div class="app">'
        "<header>"
        f'<a class="wordmark" href="/">{_crest()}ORC&nbsp;CITADEL</a>'
        f'<div class="space"><span class="eyebrow">{html.escape(eyebrow)}</span>'
        f'<span class="title">{html.escape(app_title)}</span></div>'
        '<div class="grow"></div>'
        f'<label class="search">{_search_icon()}'
        '<input placeholder="entity · claim · source 검색" /></label>'
        '<a class="spire" href="/spire" title="Signal Spire · 결론·confidence 변화 알림">'
        '<span class="dot"></span> Signal Spire · 0</a>'
        "</header>"
        '<div class="masthead"><div class="mh-txt">'
        f"<h1>{html.escape(app_title)}</h1><p>{html.escape(eyebrow)}</p></div></div>"
        "<main>" + nav(route) + body + "</main>"
        "</div></body></html>"
    )


def _esc(v):
    return html.escape(str(v))


def _esc(v):
    return html.escape(str(v))


# --- 기존 개발 화면 (랭킹·보고서·조사·근거) — /table 에 서빙. ---
PAGE_TABLE = shell(
    "/table",
    """<h2>📊 Subject 신뢰도 랭킹 <span class="dim">(S31 · value 단일 게이지 금지 → 봉투 노출)</span></h2>
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
    """,
    "Orc Citadel — War Table · Council (실데이터 뷰어)")


# --- Citadel Gate — 홈/진입 대시보드 (`/`). ---
PAGE_GATE = shell(
    "/",
    """<h2>🗄️ 시스템 존 요약 <span class="dim">(raw / normalized / curated — 실측)</span></h2>
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
    """,
    "Orc Citadel — Citadel Gate (진입 대시보드)")


# --- Watchtower — 수집 관제 (`/watchtower`). ---
PAGE_WATCHTOWER = shell(
    "/watchtower",
    """<h2>📡 Source 상태 <span class="dim">(raw 존 · source × 문서 수 · source_type)</span></h2>
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
    """,
    "Orc Citadel — Watchtower · Ingestion Monitor (수집 관제)")


# --- Signal Spire — 알림 센터 (`/spire`). ---
PAGE_SPIRE = shell(
    "/spire",
    """<h2>🔔 5 종 트리거 카탈로그 <span class="dim">(정본 signal_spire.TRIGGER_TYPES)</span></h2>
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
    """,
    "Orc Citadel — Signal Spire · Alerts (알림 센터)")


# --- Grand Archive — 문서 탐색 (`/archive`). ---
PAGE_ARCHIVE = shell(
    "/archive",
    """<h2>📚 Normalized Documents <span class="dim">(oc.duckdb · read-only · segment 수 포함)</span></h2>
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
    """,
    "Orc Citadel — Grand Archive (문서 탐색)")


# --- Chronicle Vault — 시간 탐색 (`/chronicle`). ---
PAGE_CHRONICLE = shell(
    "/chronicle",
    """<h2>⏳ AS-OF 조회 <span class="dim">(valid_at · tx_at ISO datetime — 선택, 기본 현재 tx)</span></h2>
<div class="card">
  <form id="asof">
    <label>valid_at <input id="v" name="valid_at" placeholder="2026-08-01T00:00:00"></label>
    <label>tx_at &nbsp;<input id="t" name="tx_at" placeholder="2026-08-01T00:00:00"></label>
    <button type="submit">조회</button>
  </form>
</div>

<h2>📜 Assertions <span class="dim">(bitemporal 범위 + supersedes)</span></h2>
<div class="card"><table id="assertions"></table></div>

<h2>🔗 Supersedes 체인</h2>
<div class="card" id="chain"></div>

<h2>⏪ Graph Replay <span class="dim">(postgres `graph_mutations` SoT — ADR-304)</span></h2>
<div class="card" id="replay"></div>

<script>
const $=s=>document.querySelector(s);
function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML;}
function fmt(v){return v?esc(String(v).slice(0,10)):'<span class="na">—</span>';}

async function load(qs){
  const r=await (await fetch('/api/chronicle'+qs)).json();
  $('#assertions').innerHTML='<tr><th>assertion</th><th>subject</th><th>predicate</th><th>valid_from</th><th>valid_to</th><th>tx_from</th><th>tx_to</th><th>supersedes</th></tr>'+
    (r.assertions||[]).map(a=>`<tr>
      <td><code>${esc(a.assertion_id)}</code></td><td>${esc(a.subject_id)}</td><td>${esc(a.predicate)}</td>
      <td>${fmt(a.valid_from)}</td><td>${fmt(a.valid_to)}</td><td>${fmt(a.tx_from)}</td><td>${fmt(a.tx_to)}</td>
      <td>${a.supersedes_id?`<code>${esc(a.supersedes_id)}</code>`:'<span class="na">—</span>'}</td></tr>`).join('')||'<span class="muted">조회 결과 없음</span>';
  $('#chain').innerHTML=(r.supersedes_chain||[]).map(a=>'<p><code>'+esc(a.assertion_id)+'</code> supersedes <code>'+esc(a.supersedes_id)+'</code></p>').join('')||'<span class="muted">supersedes 체인 없음</span>';
  const rp=r.graph_replay||{};
  $('#replay').innerHTML=rp.available
    ? '<p>정상 — mutation 수 <b>'+rp.mutation_count+'</b></p>'
    : '<p class="na">unavailable</p><p class="dim">'+esc(rp.note)+'</p>';
}

load('');
$('#asof').onsubmit=e=>{
  e.preventDefault();
  const p=new URLSearchParams();
  if($('#v').value)p.set('valid_at',$('#v').value);
  if($('#t').value)p.set('tx_at',$('#t').value);
  load('?'+p.toString());
};
</script>
    """,
    "Orc Citadel — Chronicle Vault (시간 탐색)")
