"""Council Chamber remaining-gaps 확장 (조회 전용 · stdlib · read-only · 오프라인).

`viewer_pages.PAGE_COUNCIL` 에 병합되는 본문 HTML 조각(PAGE_COUNCIL_EXT_BODY)과
JS 문 블록(PAGE_COUNCIL_EXT_JS)만 export 한다. 셸 래퍼·병합은 오케스트레이터 책임.

불변식:
- honest-gap — live 실행·비용·turn 로그·라우팅 판정·모델 ID·timestamp 는 wire 에
  미영속이므로 렌더하지 않고 'not-run'/'미영속'으로 정직 표시. 목업 예시 수치는
  일절 하드코딩하지 않는다.
- '실시간' 문구 금지 — 모든 trace 는 `computed:"on-request, non-persistent"` 주석.
- fetch 규율: subject 선택 시 /api/council 1회(기존 페이지 소유) + 이 확장에서는
  '조사 trace' 버튼 클릭 시 /api/investigate 1회. 로드 시 자동 fetch 없음.
- 딥링크는 URL 생성만: statements[].claim_ref → /witnesses?claim=,
  subject → /table?subject= (대상 페이지 bootstrap 은 이미 파라미터 파싱 존재).

JS 는 병합 후 viewer_pages 전역 헬퍼($·esc·empty·api)만 사용하고 재정의하지 않는다.
"""
from __future__ import annotations

# /api/investigate 응답에서 이 확장이 읽는 키 (테스트가 wire 계약으로 봉인).
WIRE_KEYS = (
    "computed", "planned_subclaims", "coverage", "gaps", "retrieved",
    "counter_evidence", "statements", "audit_trace", "iterations",
    "terminated_by", "subgraph", "conclusion",
)

# 8역할 카탈로그 — 순서 고정. executed/not-run 판정은 JS 쪽 wire 필드 존재 여부.
AGENT_ROLES = (
    "Planner", "GraphExplorer", "Retrieval", "CounterEvidence",
    "Synthesizer", "Audit", "route_llm", "Evidence Extractor",
)


def build() -> tuple[str, str]:
    """(본문 HTML 조각, JS 문 블록) 반환 — integration 시점 테스트용."""
    return PAGE_COUNCIL_EXT_BODY, PAGE_COUNCIL_EXT_JS


PAGE_COUNCIL_EXT_BODY = """<h2>조사 Trace <span class="dim">(on-request — 위 요약과 달리 실행 시점 실측값)</span></h2>
<div class="cncl-grid" id="council-ext">
  <section class="panel">
    <div class="panel-head"><h2>Agent Catalog</h2><span class="sub" id="ce-agents-sub">not-run · trace 미실행</span></div>
    <div class="panel-body" id="ce-agents"></div>
  </section>
  <section class="panel">
    <div class="panel-head"><h2>Investigation Trace</h2><span class="sub">on-request · read-only</span></div>
    <div class="panel-body">
      <div id="ce-loop"></div>
      <div id="ce-subclaims"></div>
      <div id="ce-retrieved"></div>
      <div id="ce-counter"></div>
      <div id="ce-statements"></div>
    </div>
  </section>
  <section class="panel">
    <div class="panel-head"><h2>Stopping · Audit 실측</h2><button class="btn primary" id="ce-trace-btn" type="button">조사 trace</button></div>
    <div class="panel-body">
      <div id="ce-stop"></div>
      <div id="ce-audit"></div>
    </div>
  </section>
</div>
"""

PAGE_COUNCIL_EXT_JS = """(function(){
/* Council ext — 조회 전용 trace 렌더. wire 계약: audit_trace·counter_evidence·
   computed:'on-request, non-persistent' — 실행 로그 아님, 버튼 클릭 시점 재계산 결과만. */
const URL_INVESTIGATE='/api/investigate';
const CX_ROLES=[
 ['Planner',r=>(r.planned_subclaims||[]).length>0,'질문 → subclaim 분해 · known/gap 라벨'],
 ['GraphExplorer',r=>!!r.subgraph&&!((r.subgraph.relationships||[]).length===0&&!r.subgraph.entity),'ABOUT subgraph 조회 · read-only'],
 ['Retrieval',r=>(r.retrieved||[]).length>0,'gap → 후보 span 검색 · ≤10 반환'],
 ['CounterEvidence',r=>(r.counter_evidence||[]).length>0,'반증 가설·부정 질의 · 결정적 규칙 산출'],
 ['Synthesizer',r=>(r.statements||[]).length>0,'결론 반영 asserted 문장 생성'],
 ['Audit',r=>!!r.audit_trace&&typeof r.audit_trace==='object','문장 → claim → source span 역추적'],
 ['route_llm',null,'tier 라우팅 — 판정 미영속 · wire 신호 없음 (honest-gap)'],
 ['Evidence Extractor',null,'span → claim 추출 — 쓰기 경로 범위 밖 · wire 신호 없음 (honest-gap)'],
];

function cxBadge(executed){return executed===null
  ?'<span class="badge warn">not-run</span>'
  :(executed?'<span class="badge good">executed</span>':'<span class="badge warn">not-run</span>');}

function cxCurrent(){return (typeof current==='string'&&current)?current:'';}

function renderAgents(r){
  $('#ce-agents-sub').textContent='computed: '+esc(r.computed||'on-request, non-persistent');
  $('#ce-agents').innerHTML=CX_ROLES.map(a=>{
    const ex=a[1]===null?null:!!a[1](r);
    return '<div class="subq"><div class="q">'+esc(a[0])+' '+cxBadge(ex)+'</div>'
      +'<div class="meta"><span>'+esc(a[2])+'</span></div></div>';
  }).join('');
}

/* Loop stepper — coverage→gaps→retrieved→counter_evidence→statements→audit
   순서의 read-only 결과 trace (실행 순서/로그 아님). */
function renderLoop(r){
  const cov=(typeof r.coverage==='number')?(r.coverage*100).toFixed(0)+'%':'—';
  const at=r.audit_trace||{};
  const steps=[['coverage',cov],['gaps',(r.gaps||[]).length],
    ['retrieved',(r.retrieved||[]).length],['counter_evidence',(r.counter_evidence||[]).length],
    ['statements',(r.statements||[]).length],
    ['audit',(r.audit_trace?((at.linked||0)+'/'+(at.verifiable||0)):'—')]];
  $('#ce-loop').innerHTML='<div class="sec-label">Investigation Loop · 결과 trace</div>'
    +steps.map((s,i)=>'<div class="subq"><div class="q"><span class="badge">'+(i+1)+' · '+esc(s[0])
      +'</span> <b>'+esc(s[1])+'</b></div></div>').join('')
    +'<p class="dim">computed: on-request, non-persistent — 저장·재생 없는 조회 결과 순서 (실행 로그 아님)</p>';
}

function renderSubclaims(r){
  const rows=(r.planned_subclaims||[]).map(sc=>'<div class="subq"><div class="q">'+esc(sc.id)+' · '
    +esc(sc.text)+(sc.known?' <span class="badge good">known</span>':' <span class="badge err">gap</span>')
    +'</div>'+(sc.known?'':'<div class="meta"><span>gap_reason · '+esc(sc.gap_reason||'미기록')+'</span></div>')+'</div>').join('');
  $('#ce-subclaims').innerHTML='<div class="sec-label">planned_subclaims · Planner 분해</div>'
    +(rows||empty('분해 없음','planned_subclaims 가 비어 있습니다 (subject 미분해).'));
}

function renderRetrieved(r){
  const cards=(r.retrieved||[]).slice(0,10).map(x=>'<div class="ev support"><div class="top">'
    +'<span class="rel">span</span><span class="src">'+esc(x.doc_id||'')+(x.segment_id?' · '+esc(x.segment_id):'')+'</span></div>'
    +'<div class="span">'+esc(x.span||'')+'</div>'
    +'<div class="trail"><span>score '+(typeof x.score==='number'?x.score:'—')+'</span><span>'+esc(x.retrieval_path||'')+'</span></div></div>').join('');
  $('#ce-retrieved').innerHTML='<div class="sec-label">Retrieved · 후보 span ≤10</div>'
    +(cards||empty('회수 span 없음','gap 미발생 또는 무매칭 (honest-gap).'));
}

function renderCounter(r){
  const cards=(r.counter_evidence||[]).map(c=>'<div class="seer"><div class="hd">반증 카드 · '
    +esc(c.id||c.subject_id||'—')+' · 결정적 규칙 산출 (모델 생성 아님)</div><div class="body">'
    +((c.hypotheses||[]).map(h=>'H · '+esc(h)).join('<br>')||'hypotheses 없음')+'</div>'
    +(c.negative_queries||[]).map(q=>'<div class="trail" style="margin-top:6px"><span>negative_query</span><span>'+esc(q)+'</span></div>').join('')
    +'</div>').join('');
  $('#ce-counter').innerHTML='<div class="sec-label">Counter-Evidence · 가설/부정 질의</div>'
    +(cards||empty('반증 없음','gap subclaim 에 대한 규칙 산출 반증이 없습니다.'));
}

/* Stopping A/B/C — evaluate_stop 의 실제 입력·결정만. 임계 상수는 wire 미노출이라
   충족/미충족 판정을 그리지 않는다 (hardcode 금지). */
function renderStop(r){
  const cov=(typeof r.coverage==='number')?r.coverage:null;
  const ce=(r.counter_evidence||[]).length;
  const rows=[['A','evidence coverage · gaps '+((r.gaps||[]).length)+'건',
      cov===null?'—':('<span class="bar"><i style="width:'+Math.max(2,Math.round(cov*100))+'%;background:var(--signal-amber)"></i></span>'+(cov*100).toFixed(0)+'%')],
    ['B','신규 독립 증거 유입 · read-only 루프 — 반복에서 새 근거 불가','iterations '+esc(String(r.iterations))],
    ['C','미해결 반증 후보 (결정적 규칙 입력)',ce+'건'],
    ['D','budget hard stop',r.terminated_by==='budget'?'terminated_by = budget':'미발동']];
  $('#ce-stop').innerHTML='<div class="sec-label">종료 조건 · Stopping (A ∧ B ∧ C) ∨ D</div>'
    +'<div class="formula">evaluate_stop 임계 상수는 wire 미노출 · <span class="muted">아래는 실제 입력·결정 텍스트만</span></div>'
    +rows.map(x=>'<div class="cond"><div class="ct"><span class="ck">'+x[0]+'</span><span class="cn">'+esc(x[1])
      +'</span><span class="cv">'+x[2]+'</span></div></div>').join('')
    +'<p class="dim">종료 결정 · terminated_by = <b>'+esc(r.terminated_by||'—')+'</b> — 계산 시점 재현 가능, 실행 로그는 미영속.</p>';
}

/* Audit — 분모 0 은 PASS 과장 금지: '검증가능 문장 없음'으로 정직 표시. */
function renderAudit(r){
  if(!r.audit_trace||typeof r.audit_trace!=='object'){$('#ce-audit').innerHTML=empty('audit 없음','audit_trace 미노출 (honest-gap).');return;}
  const a=r.audit_trace,v=a.verifiable||0,l=a.linked||0;
  const ratio=(typeof a.linkage_ratio==='number')?(a.linkage_ratio*100).toFixed(0)+'%':'—';
  const verdict=v===0?'<span class="badge warn">검증가능 문장 없음 — PASS 표시 불가 (분모 0)</span>'
    :(l===v?'<span class="badge good">전 문장 claim+span 역추적</span>'
      :'<span class="badge err">역추적 미완 '+(v-l)+'건</span>');
  const blocked=(a.blocked_statements||[]).map(b=>'<div class="arow"><div class="al"><span class="pill lo">blocked</span> '
    +esc(b.text||'')+'<span class="as">'+esc(b.reason||'')+'</span></div></div>').join('');
  $('#ce-audit').innerHTML='<div class="sec-label">Audit · 역추적 감사</div>'+verdict
    +'<div class="conf" style="margin-top:8px"><div class="cell"><div class="num">'+esc(String(v))+'</div><div class="cap">verifiable</div></div>'
    +'<div class="cell"><div class="num'+(v&&l===v?' good':'')+'">'+esc(String(l))+'</div><div class="cap">linked</div></div>'
    +'<div class="cell"><div class="num">'+esc(ratio)+'</div><div class="cap">linkage</div></div></div>'
    +(blocked?'<div class="sec-label">차단 문장</div>'+blocked:'');
}

function renderStatements(r){
  const subj=cxCurrent()||r.subject_id||'';
  const links=subj?'<div class="trail"><a href="/table?subject='+encodeURIComponent(subj)+'">War Table · subject ›</a></div>':'';
  const rows=(r.statements||[]).map(st=>'<div class="subq"><div class="q">'+esc(st.text||'')+'</div>'
    +'<div class="meta"><span>'+esc(st.modality||'')+'</span>'
    +(st.claim_ref?'<a href="/witnesses?claim='+encodeURIComponent(st.claim_ref)+'">'+esc(st.claim_ref)+' · 증거 검사 ›</a>'
      :'<span>claim_ref 없음 (prediction/opinion)</span>')+'</div></div>').join('');
  $('#ce-statements').innerHTML='<div class="sec-label">Statements · evidence-first</div>'+links
    +(rows||empty('문장 없음','결론 미산출 — Synthesizer 산출 문장이 없습니다.'));
}

async function runTrace(){
  const subj=cxCurrent();
  if(!subj){$('#ce-loop').innerHTML=empty('subject 미선택','Subjects 에서 대상을 고른 뒤 [조사 trace] 를 누르세요.');return;}
  const btn=$('#ce-trace-btn'); if(btn)btn.disabled=true;
  try{
    const r=await (await fetch(URL_INVESTIGATE+'?subject='+encodeURIComponent(subj))).json();
    if(r.error){$('#ce-loop').innerHTML=empty('trace 실패',esc(r.error));return;}
    renderAgents(r);renderLoop(r);renderSubclaims(r);renderRetrieved(r);
    renderCounter(r);renderStop(r);renderAudit(r);renderStatements(r);
  }finally{if(btn)btn.disabled=false;}
}

/* 자기초기화 — 로드 시 fetch 없음 (조회는 버튼 클릭 시에만). */
$('#ce-agents').innerHTML=empty('trace 대기','[조사 trace] 클릭 시 8역할 실행 여부를 wire 필드 존재로 판정합니다.');
$('#ce-loop').innerHTML=empty('trace 대기','coverage→gaps→retrieved→counter_evidence→statements→audit 결과 순서 (on-request).');
$('#ce-stop').innerHTML=empty('판정 대기','Stopping A/B/C — 종료 결정과 실제 입력만 표시됩니다.');
$('#ce-audit').innerHTML=empty('감사 대기','audit_trace — 검증가능 문장 역추적률 (분모 0 시 PASS 과장 없음).');
const cxBtn=$('#ce-trace-btn'); if(cxBtn)cxBtn.onclick=runTrace;
})();
"""
