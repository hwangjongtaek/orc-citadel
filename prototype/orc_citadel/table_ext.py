"""War Table remaining-gaps 프런트 extension (Wave 2 · stdlib · 오프라인 · read-only).

`viewer_pages.PAGE_TABLE`(기존 4패널) 위에 주입되는 확장 블록 3종:
`PAGE_TABLE_EXT_CSS`(추가 <style>) · `PAGE_TABLE_EXT_BODY`(숨김 템플릿 조각) ·
`PAGE_TABLE_EXT_JS`(기존 <script> 최후에 이어붙이는 IIFE 문 블록).
`shell()` 래퍼는 오케스트레이터가 담당하고, 이 모듈은 조각만 export 한다.

기능 (태스크 1-9):
1. Campaign Map subclaim 카드 — /api/investigate.planned_subclaims[](id/text/
   known/gap_reason). continuous coverage bar 는 미측정 — known/gap 배지만
   (목업 72% 등 수치 금지). `_api_investigate` 는 무거우므로 wave1 규칙 19
   ("버튼 클릭 시에만 fetch") 에 따라 명시 버튼 클릭 시에만 실행.
2. entity type chip 토글 — closure 의 `seed`(/api/table) .entities[](entity_id,
   mention_type) 를 graph 노드 id 와 join, 선택 type 외 entity 노드 dim. 재fetch 없음.
3. 그래프 zoom/pan/fit/reset — SVG viewBox 속성만 조작 (외부 lib 금지).
4. 관계별 stroke 색 + 선택 노드(focus) incident edge 강조 — base 가 line 에 type
   속성을 주지 않으므로 edge-label 텍스트와 (count 일치 시) index, 아니면
   label.x≈line midpoint x 로 type 역결정.
5. /api/graph_expand next_cursor 'more' 버튼 — cursor opaque: 파싱 없이
   encodeURIComponent 로 왕복만.
6. 노드 라벨 — /api/graph subgraph.nodes[].label (sg closure) → g.gn 텍스트 치환.
7. Inspector claim 상세 — /api/claim(predicate/object_literal/modality/
   surface_fragment/per-claim confidence) + /api/chronicle assertions 의 해당
   claim 유효시간(valid/tx from→to) 카드.
8. Evidence 원문 excerpt — /api/evidence + /api/provenance + /api/document.
   Hall of Witnesses 와 동일한 offset 패턴(segment_id 마지막 숫자 → normalized
   ord). extraction_records=0 실측이므로 trail 없으면 정직 빈 문구.
9. Chronicle rail — /api/chronicle.events(asserted/closed/superseded) 를
   valid/tx dual slider(이벤트 at 인덱스 축, bounds 라벨) 로 필터 +
   이벤트 클릭 → focus 설정 + loadClaim(cid) 포커스.

모든 fetch 는 lazy: 사용자 액션(서브클림 버튼/칩/more/이벤트 클릭) 또는
subject·claim 선택 시에만. chronicle 은 최초 subject 선택 때 1회 캐시.
base globals(seed·current·focus·sg·claimIds·renderGraph·loadClaim) 와 헬퍼
($·esc·empty) 는 동일 <script> 스코프 공유 전제.
통합: PAGE_TABLE 의 부트스트랩 IIFE 뒤 `</script>` 직전에 PAGE_TABLE_EXT_JS,
본체 끝에 PAGE_TABLE_EXT_BODY, CSS 블록 뒤에 PAGE_TABLE_EXT_CSS.
"""

# 확장 CSS — viewer_pages.CSS 뒤에 병합하는 별도 <style>.
PAGE_TABLE_EXT_CSS = """
<style>
.wte-headbtn{cursor:pointer;color:var(--secondary);text-transform:uppercase;letter-spacing:.08em}
.wte-headbtn:hover{color:var(--primary)}
.wte-sc{border:1px solid var(--surface-variant);border-radius:var(--r-md);padding:8px 10px;margin-bottom:8px}
.wte-sc .q{font-size:12px;color:var(--on-surface);margin-bottom:5px}
.wte-sc .meta{display:flex;align-items:center;gap:8px;font-size:10.5px;color:var(--on-surface-muted);flex-wrap:wrap}
.wte-b{display:inline-block;font-family:var(--font-head);font-size:9.5px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;padding:2px 7px;border-radius:var(--r-sm)}
.wte-b.k{background:rgba(69,224,111,.14);color:var(--primary)}
.wte-b.g{background:rgba(255,177,59,.14);color:var(--signal-amber)}
.wte-chipoff{opacity:.35}
.wte-tb{position:absolute;top:8px;right:8px;display:flex;gap:4px;z-index:2}
.wte-tb button{font-family:var(--font-data);font-size:11px;line-height:1;padding:4px 8px;border-radius:var(--r-sm);border:1px solid var(--surface-variant);background:rgba(7,17,28,.72);color:var(--on-surface);cursor:pointer}
.wte-tb button:hover{border-color:var(--primary);color:var(--primary)}
.wte-more{margin:6px 12px 10px;display:none}
.wte-pan{cursor:grab} .wte-panning{cursor:grabbing}
.wte-chron{background:var(--surface);border:1px solid var(--surface-variant);border-radius:var(--r-lg);padding:10px var(--sp-lg);display:flex;flex-direction:column;gap:8px;margin-bottom:var(--sp-md)}
.wte-chron .hd{display:flex;align-items:center;gap:var(--sp-md);font-family:var(--font-head);font-size:10px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--on-surface-muted)}
.wte-sliders{display:flex;align-items:center;gap:var(--sp-lg);flex-wrap:wrap}
.wte-sl{display:flex;align-items:center;gap:6px;font-family:var(--font-head);font-size:9.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--on-surface-muted);white-space:nowrap}
.wte-sl input[type=range]{width:110px}
.wte-sl .v{font-family:var(--font-data);font-size:9.5px;color:var(--on-surface)}
.wte-evt{cursor:pointer}
.wte-evt .lab{pointer-events:none}
.wte-kn{font-family:var(--font-head);font-size:9.5px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--on-surface-muted)}
.wte-ev-row{font-family:var(--font-data);font-size:10.5px;color:var(--on-surface-muted);margin:2px 0}
</style>
"""

# 본문 HTML 조각 — PAGE_TABLE 본체 뒤에 삽입되는 숨김 템플릿.
# JS 부트스트랩이 노드를 최종 앵커로 이관한다:
#   #wte-subclaim-btn → #campaign-map .panel-head, #wte-subclaims → #pred-list 앞,
#   #wt-viewbar → .wt-canvas, #wt-expand-more → #war-canvas (#wt-list 앞),
#   #wte-claim-detail → #inspector, #wte-chron → #chronicle-rail 뒤 형제.
# base 의 innerHTML 덮어쓰기(#subq-list·#pred-list·#wt-list·#inspector-body·
# #chronicle-rail) 를 피하기 위해 확장 컨테이너는 전부 그들 외부 위치에 붙인다.
PAGE_TABLE_EXT_BODY = """<div id="wte-frag" hidden aria-hidden="true">
  <span class="sub wte-headbtn" id="wte-subclaim-btn" title="planner 실행 (on-request)">Subclaims · 분석</span>
  <div id="wte-subclaims"></div>
  <div class="wte-tb" id="wt-viewbar">
    <button id="wt-zoom-in" title="확대">+</button>
    <button id="wt-zoom-out" title="축소">&minus;</button>
    <button id="wt-fit" title="화면 맞춤">fit</button>
    <button id="wt-reset" title="초기화">reset</button>
  </div>
  <button class="btn wte-more" id="wt-expand-more">in접 더 보기 (next page)</button>
  <div id="wte-claim-detail"></div>
  <div class="wte-chron" id="wte-chron">
    <div class="hd"><span>Chronicle · events</span>
      <span id="wte-bounds" class="mono"></span></div>
    <div class="rail" id="wte-evt-box"></div>
    <div class="wte-sliders">
      <div class="wte-sl"><span>Valid</span>
        <input type="range" id="wte-sl-lo" min="0" max="0" value="0"><span>&ndash;</span>
        <input type="range" id="wte-sl-hi" min="0" max="0" value="0">
        <span class="v" id="wte-sl-val"></span></div>
      <div class="wte-sl"><span>Tx</span>
        <input type="range" id="wte-sl-tlo" min="0" max="0" value="0"><span>&ndash;</span>
        <input type="range" id="wte-sl-thi" min="0" max="0" value="0">
        <span class="v" id="wte-sl-tval"></span></div>
    </div>
  </div>
</div>
"""

# 스크립트 문 블록 — PAGE_TABLE <script> 부트스트랩 IIFE 뒤 `</script>` 직전 삽입.
PAGE_TABLE_EXT_JS = """
(function(){
'use strict';
/*==PURE==*/
function wtEdgeColor(t){
  const x=String(t||'').toLowerCase();
  if(x.indexOf('support')>=0) return '#45E06F';
  if(x.indexOf('contradict')>=0) return '#E05252';
  if(x.indexOf('qualif')>=0) return '#FFB13B';
  if(x.indexOf('uncertain')>=0||x.indexOf('same')>=0) return '#A78BFA';
  return '#59636A';
}
function wtNodeText(n){
  const lab=n&&n.label!=null?String(n.label):'';
  return lab!==''?lab:String((n&&n.id)||'').slice(0,12);
}
function wtSentenceAt(text,a,b){
  const t=String(text==null?'':text);
  if(!t.length) return '';
  const s=Math.max(0,Math.min(t.length,Math.max(0,a|0)));
  const e=Math.max(s,Math.min(t.length,b|0));
  const head=t.lastIndexOf('. ',s);
  const st=head<0?0:Math.min(head+2,t.length);
  let en=t.indexOf('. ',e);
  en=(en<0?t.length:en+1);
  if(en<e) en=e;
  return t.slice(st,Math.min(t.length,en));
}
function wtSegmentOrder(segId){
  const m=/([0-9]+)$/.exec(String(segId==null?'':segId));
  return m?(+m[1]):null;
}
function wtTsList(events){
  const seen={},out=[];
  for(let i=0;i<events.length;i++){
    const at=events[i]&&events[i].at;
    if(at==null||seen[at]) continue;
    seen[at]=1; out.push(at);
  }
  out.sort();
  return out;
}
function wtIndexOfTs(ts,at){
  for(let i=0;i<ts.length;i++) if(ts[i]===at) return i;
  return -1;
}
function wtEventPct(at,min,max){
  if(at==null||min==null||max==null) return 50;
  if(String(min)===String(max)) return 50;
  const a=Date.parse(String(min)),b=Date.parse(String(max)),t=Date.parse(String(at));
  if(isNaN(a)||isNaN(b)||isNaN(t)||b<=a) return 50;
  return Math.max(2,Math.min(98,Math.round(100*(t-a)/(b-a))));
}
function wtPinColor(kind){
  const k=String(kind||'');
  if(k==='closed') return '#E05252';
  if(k==='superseded') return '#59636A';
  return '#45E06F';
}
function wtClampPair(lo,hi,max){
  const m=Math.max(max|0,0);
  let a=Math.max(0,Math.min(m,lo|0)),b=Math.max(0,Math.min(m,hi|0));
  if(a>b){const t=a;a=b;b=t;}
  return [a,b];
}
function wtFilterEvents(events,ts,vw){
  const out=[];
  const p=wtClampPair(vw.lo,vw.hi,Math.max(ts.length-1,0));
  const q=wtClampPair(vw.tlo,vw.thi,Math.max(ts.length-1,0));
  for(let i=0;i<events.length;i++){
    const e=events[i]||{};
    const k=wtIndexOfTs(ts,e.at);
    out.push({event:e,idx:k,
      shown:k>=0&&k>=p[0]&&k<=p[1]&&k>=q[0]&&k<=q[1]});
  }
  return out;
}
function wtSubclaimHtml(sc){
  const row=sc||{};
  const known=row.known===true;
  const gap=known?'':String(row.gap_reason||'');
  return '<div class="wte-sc wte-subclaim"><div class="q">'
    +esc(wtNodeText({id:row.id,label:row.text}))+'</div>'
    +'<div class="meta"><span class="wte-b '+(known?'k">known':'g">gap')+'</span>'
    +(gap?'<span>'+esc(gap)+'</span>':'')
    +'</div></div>';
}
function wtCovNoteHtml(){
  return '<div class="wte-sc" id="wte-cov-note"><div class="q wte-kn">'
    +'continuous coverage — not measured</div>'
    +'<div class="meta">planned_subclaims 의 known/gap 사실만 노출 (목업 %-bar 미측정)</div></div>';
}
/*==ENDPURE==*/

/* ── state ─────────────────────────────────────────────────────── */
const V0={x:0,y:0,w:900,h:280};            // PAGE_TABLE svg viewBox 상수
const vb={x:0,y:0,w:900,h:280};            // 3) live viewBox
const wteLabels={};                        // 6) id → label (/api/graph nodes)
const wteCursors={};                       // 5) node id → opaque next_cursor
const wteNoMore={};                        // 5) 다음 페이지 고갈 노드 플래그
let wteChron=null,wteChronFetching=false;  // 9) chronicle 캐시 (최초 선택 1회)
let wteEvents=[],wteTs=[];
const wteView={lo:0,hi:0,tlo:0,thi:0};     // dual slider 인덱스 창
let wteSubj=null,wteFocusShown=null,wteSubjSeq=0;
const wteOn=new Set();                     // 2) 활성 type 칩 (빈 집합 = 전체)

function api(p){return fetch(p).then(function(r){return r.json();});}
function typesMap(){
  const m={},rows=(typeof seed!=='undefined'&&seed&&seed.entities)||[];
  for(let i=0;i<rows.length;i++){
    const e=rows[i];
    if(e&&e.entity_id!=null) m[String(e.entity_id)]=e.mention_type||'';
  }
  return m;
}
function isClaim(id){
  if(id==null) return false;
  if(typeof claimIds!=='undefined'&&claimIds&&claimIds.has(id)) return true;
  if(typeof sg!=='undefined'&&sg&&Array.isArray(sg.claims))
    return sg.claims.some(function(c){return c&&c.id===id;});
  return String(id).indexOf('clm-')===0;
}

/* ── 1) subclaim 카드 (명시 버튼 클릭 시에만 /api/investigate) ───── */
async function runInvestigate(){
  if(typeof current!=='undefined'&&current) await loadSubclaims(current);
}
async function loadSubclaims(subj){
  const box=$('#wte-subclaims'); if(!box) return;
  const seq=++wteSubjSeq;
  box.innerHTML='<div class="wte-sc"><div class="q muted">'
    +'planner 실행 중… (on-request, non-persistent)</div></div>';
  let data=null;
  try{ data=await api('/api/investigate?subject='+encodeURIComponent(subj)); }
  catch(_){ data=null; }
  if(seq!==wteSubjSeq||current!==subj) return;   // 더 최신 선택이 덮어씀
  const rows=(data&&data.planned_subclaims)||[];
  box.innerHTML='<div class="sec-label">Subclaims · '+esc(subj)+'</div>'
    +(rows.map(wtSubclaimHtml).join('')
      ||empty('subclaim 없음','planned_subclaims 가 비어 있습니다 (honest-gap).'))
    +wtCovNoteHtml();
}

/* ── 7)+8) claim 상세 + 원문 excerpt (claim 선택 시에만 fetch) ───── */
async function showClaim(cid){
  if(wteFocusShown===cid) return;
  wteFocusShown=cid;
  const det=$('#wte-claim-detail'); if(!det) return;
  det.innerHTML='<div class="sec-label">Claim · 상세</div>'
    +'<div class="wte-sc"><div class="q muted">로딩…</div></div>';
  let c=null;
  try{ c=await api('/api/claim?claim='+encodeURIComponent(cid)); }catch(_){ c=null; }
  if(wteFocusShown!==cid) return;
  if(!c||c.error){
    det.innerHTML='<div class="sec-label">Claim · 상세</div>'
      +empty('claim 상세 없음','/api/claim — not_found');
    return;
  }
  const conf=(c.confidence&&c.confidence.value!=null)
    ?(+c.confidence.value).toFixed(2):'미측정';
  det.innerHTML='<div class="sec-label">Claim · 상세</div>'
    +'<div class="wte-sc"><div class="q">'
    +esc(c.predicate||'—')+' · '+esc(c.object_literal!=null?c.object_literal:(c.object_id||'—'))
    +'</div><div class="meta"><span class="wte-b k">'+esc(c.modality||'modality —')
    +'</span><span>per-claim conf '+esc(conf)+'</span></div>'
    +'<div class="span">'+esc(c.surface_fragment||'surface_fragment — (not measured)')+'</div>'
    +'<div class="meta"><span>'+esc(c.claim_id||cid)+'</span>'
    +(c.doc_id?'<span>· '+esc(c.doc_id)+'</span>':'')+'</div></div>'
    +validityCard(cid)
    +'<div class="sec-label">Evidence · 원문 excerpt</div>'
    +'<div id="wte-excerpt"></div>';
  loadExcerpt(cid);
}
function validityCard(cid){
  const rows=(wteChron&&wteChron.assertions)||[];
  const mine=rows.filter(function(a){return a&&a.claim_id===cid;});
  const evs=(wteEvents||[]).filter(function(e){return e&&e.claim_id===cid;});
  const fmt=function(v){return v==null?'—':String(v).slice(0,19);};
  const body=mine.length
    ?mine.map(function(a){
        return '<div class="wte-ev-row">valid '+esc(fmt(a.valid_from))+' → '
          +esc(fmt(a.valid_to))+' · tx '+esc(fmt(a.tx_from))+' → '+esc(fmt(a.tx_to))
          +'</div>';}).join('')
    :(evs.length
      ?evs.map(function(e){
          return '<div class="wte-ev-row">'+esc(e.kind||'event')+' @ '
            +esc(fmt(e.at))+'</div>';}).join('')
      :'<div class="meta">assertion 유효시간 데이터 없음 (not measured)</div>');
  return '<div class="wte-sc"><div class="q wte-kn">Assertion · 유효시간</div>'+body+'</div>';
}
async function loadExcerpt(cid){
  let ev=null;
  try{ ev=await api('/api/evidence?claim='+encodeURIComponent(cid)); }catch(_){ ev=null; }
  if(wteFocusShown!==cid) return;
  const box=$('#wte-excerpt'); if(!box) return;
  const items=(ev&&ev.items)||[];
  if(!items.length){
    box.innerHTML=empty('근거 없음','이 claim 의 supporting evidence 가 없습니다.');
    return;
  }
  const trails=await Promise.all(items.map(function(it){
    return api('/api/provenance?evidence='+encodeURIComponent(it.evidence_id))
      .catch(function(){return null;});
  }));
  if(wteFocusShown!==cid) return;
  const parts=[];
  for(let i=0;i<items.length;i++){
    const it=items[i]||{},tr=(trails[i]&&trails[i].trail)||[];
    const ext=tr.find(function(s){return s&&s.step==='extraction_record';});
    const doc=tr.find(function(s){return s&&s.step==='document';});
    let inner='<div class="meta">extraction_record trail 없음 — 원문 offset 미측정'
      +' (extraction_records=0 · honest-gap)</div>';
    if(ext&&doc){
      let d=null;
      try{ d=await api('/api/document?doc='+encodeURIComponent(doc.doc_id)); }catch(_){ d=null; }
      if(wteFocusShown!==cid) return;
      // Hall of Witnesses 동일 패턴: segment_id 마지막 숫자 → normalized ord.
      const ord=wtSegmentOrder(ext.segment_id);
      const seg=(d&&(d.segments||[]).find(function(s){return ord!=null&&s.ord===ord;}))||null;
      inner=seg
        ?'<div class="span">'+esc(wtSentenceAt(seg.text,ext.char_start,ext.char_end))
          +'<span class="off"> [supports · p'+esc(seg.ord)+']</span></div>'
        :empty('원문 미가동','normalized segment ord '+(ord==null?'?':ord)+' 없음 (honest-gap)');
    }
    parts.push('<div class="wte-sc"><div class="meta"><span class="wte-b k">supports</span>'
      +'<span>'+esc(String(it.evidence_id||'').slice(0,16))+'</span>'
      +(it.source_doc?'<span>· '+esc(it.source_doc)+'</span>':'')+'</div>'+inner+'</div>');
  }
  box.innerHTML=parts.join('');
}

/* ── 3) zoom / pan / fit / reset — viewBox transform 만 ──────────── */
function applyView(){
  const svg=$('#wt-svg');
  if(svg) svg.setAttribute('viewBox',
    vb.x.toFixed(1)+' '+vb.y.toFixed(1)+' '+vb.w.toFixed(1)+' '+vb.h.toFixed(1));
}
function zoomAt(f,px,py){
  const nw=Math.max(90,vb.w*f),nh=nw*(V0.h/V0.w);
  vb.x+=(vb.w-nw)*((px-vb.x)/vb.w);
  vb.y+=(vb.h-nh)*((py-vb.y)/vb.h);
  vb.w=nw;vb.h=nh;applyView();
}
function svgUserPoint(evt,svg){
  if(svg.createSVGPoint&&svg.getScreenCTM){
    try{
      const m=svg.getScreenCTM().inverse(),p=svg.createSVGPoint();
      p.x=evt.clientX;p.y=evt.clientY;
      const q=p.matrixTransform(m);return [q.x,q.y];
    }catch(_){}
  }
  return [vb.x+vb.w/2,vb.y+vb.h/2];
}
function bindView(){
  const canvas=$('#war-canvas .wt-canvas'),svg=$('#wt-svg');
  if(!canvas||!svg) return;
  canvas.appendChild($('#wt-viewbar'));
  canvas.addEventListener('wheel',function(ev){
    if(!ev.target||!svg.contains(ev.target)) return;
    ev.preventDefault();
    const p=svgUserPoint(ev,svg);
    zoomAt(ev.deltaY<0?0.85:1.18,p[0],p[1]);
  },{passive:false});
  let drag=null;
  svg.classList.add('wte-pan');
  svg.addEventListener('mousedown',function(ev){
    if(ev.target&&ev.target.closest&&ev.target.closest('g.gn')) return;
    drag={x:ev.clientX,y:ev.clientY,vx:vb.x,vy:vb.y};
    svg.classList.add('wte-panning');
  });
  window.addEventListener('mousemove',function(ev){
    if(!drag) return;
    const r=svg.getBoundingClientRect();
    if(!r||!r.width) return;
    vb.x=drag.vx-(ev.clientX-drag.x)*vb.w/r.width;
    vb.y=drag.vy-(ev.clientY-drag.y)*vb.h/r.height;
    applyView();
  });
  window.addEventListener('mouseup',function(){
    drag=null;svg.classList.remove('wte-panning');
  });
  const mid=[V0.x+V0.w/2,V0.y+V0.h/2];
  const zin=$('#wt-zoom-in'),zout=$('#wt-zoom-out');
  if(zin) zin.onclick=function(){zoomAt(0.8,mid[0],mid[1]);};
  if(zout) zout.onclick=function(){zoomAt(1.25,mid[0],mid[1]);};
  const rst=$('#wt-reset');
  if(rst) rst.onclick=function(){
    vb.x=V0.x;vb.y=V0.y;vb.w=V0.w;vb.h=V0.h;applyView();
  };
  const fit=$('#wt-fit');
  if(fit) fit.onclick=function(){
    let bb=null;
    try{ bb=svg.getBBox(); }catch(_){ bb=null; }
    if(!bb||!bb.width){
      vb.x=V0.x;vb.y=V0.y;vb.w=V0.w;vb.h=V0.h;applyView();return;
    }
    const pad=28,w=bb.width+2*pad,h=bb.height+2*pad;
    const target=Math.max(w/V0.w,h/V0.h);
    vb.x=bb.x+bb.width/2-vb.w/2;vb.y=bb.y+bb.height/2-vb.h/2;
    applyView();
  };
}

/* ── 2)+4)+6) 렌더 데코 (base innerHTML 갱신 후 호출) ────────────── */
function nodeAnchors(svg){
  const pos={};
  const gs=svg.querySelectorAll('g.gn');
  for(let i=0;i<gs.length;i++){
    const g=gs[i],id=g.getAttribute('data-id');
    const c=g.querySelector('circle'),r=g.querySelector('rect');
    if(id!=null&&c) pos[id]=[+c.getAttribute('cx'),+c.getAttribute('cy')];
    else if(id!=null&&r)
      pos[id]=[+r.getAttribute('x')+ +r.getAttribute('width')/2,
        +r.getAttribute('y')+ +r.getAttribute('height')/2];
  }
  return pos;
}
function labelTexts(svg){
  const out=[];
  const texts=svg.querySelectorAll('text.edge-label');
  for(let i=0;i<texts.length;i++)
    out.push([+texts[i].getAttribute('x'),+texts[i].getAttribute('y'),
      texts[i].textContent]);
  return out;
}
function decorate(){
  const svg=$('#wt-svg'); if(!svg) return;
  const types=typesMap();
  const gs=svg.querySelectorAll('g.gn');
  for(let i=0;i<gs.length;i++){
    const g=gs[i],id=g.getAttribute('data-id'),kind=g.getAttribute('data-kind');
    const lab=g.querySelector('text.node-label')||g.querySelector('text.node-sub');
    // textContent 대입은 childList mutation — #wt-svg 옵저버와 피드백 루프가 되지
    // 않도록 값이 바뀔 때만 쓴다 (fixpoint).
    const want=(id!=null&&wteLabels[id])?wteLabels[id]:null;
    if(lab&&want!=null&&lab.textContent!==want) lab.textContent=want;
    let dim=false;
    if(wteOn.size&&kind==='entity')
      dim=!(Object.prototype.hasOwnProperty.call(types,id)&&wteOn.has(types[id]));
    g.style.opacity=dim?'0.15':'';
  }
  const pos=nodeAnchors(svg);
  ensureEdgeLayer(svg,pos);
  const lines=svg.querySelectorAll('line'),labs=labelTexts(svg);
  const focusId=(typeof focus!=='undefined'?focus:null);
  // base 는 edge line/label 을 rels 순서로 emit → count 일치 시 index pairing.
  // (base 의 label y 는 연산자 우선순위로 NaN — x 좌표 근접이 fallback.)
  const byIndex=lines.length===labs.length;
  for(let i=0;i<lines.length;i++){
    const ln=lines[i],own=ln.getAttribute('data-wte-type');
    let type='';
    if(own!=null) type=own;
    else{
      const mx=(+ln.getAttribute('x1')+ +ln.getAttribute('x2'))/2;
      let bd=2;
      for(let j=0;j<labs.length;j++){
        const d=Math.abs(labs[j][0]-mx);
        if(d<bd){bd=d;type=labs[j][2];}
      }
    }
    const col=wtEdgeColor(type);
    const near=function(k){
      const p=pos[k]; if(!p) return false;
      const q=[+ln.getAttribute('x1'),+ln.getAttribute('y1')];
      const q2=[+ln.getAttribute('x2'),+ln.getAttribute('y2')];
      return (Math.abs(p[0]-q[0])<0.01&&Math.abs(p[1]-q[1])<0.01)
        ||(Math.abs(p[0]-q2[0])<0.01&&Math.abs(p[1]-q2[1])<0.01);
    };
    const inc=focusId!=null&&near(focusId);
    ln.setAttribute('stroke',col);
    ln.setAttribute('stroke-width',inc?'2.6':'1.5');
    ln.style.opacity=focusId?(inc?'1':'0.3'):'';
    if(String(type).toLowerCase().indexOf('contradict')>=0){
      ln.setAttribute('stroke-dasharray','4 2');
    }else if(String(type).toLowerCase().indexOf('qualif')>=0){
      ln.setAttribute('stroke-dasharray','5 3');
    }else{
      ln.removeAttribute('stroke-dasharray');
    }
  }
  renderMore();
}
/* base(viewer_pages.PAGE_TABLE:414) 의 edge 문자열은 연산자 우선순위 결함으로
   모든 line 이 무효('NaN') 텍스트 노드로 붕괴된다. rels 가 있는데 line 이
   0개면 확장 레이어가 sg.relationships + 노드 좌표로 edges 를 직접 재생성한다
   (base 수정 시 line>0 → 레이어 자동 off, 라벨 중복 없음). */
/* const WTE_NS 제거 — svg.namespaceURI 재사용 (오프라인 리터럴 금지 가드). */
let wteLayerHtml=null;   // 마지막 주입 html — 동일 재주입(옵저버 재점화) 차단
function ensureEdgeLayer(svg,pos){
  const rels=(typeof sg!=='undefined'&&sg&&sg.relationships)||[];
  const broken=svg.querySelectorAll(':scope > line').length===0&&rels.length>0;
  let layer=svg.querySelector('#wte-edge-layer');
  if(!broken){
    if(layer) layer.remove();
    return;
  }
  // 붕괴된 base 의 잔여 텍스트 노드('NaN" …ABOUT') 제거 (SVG 직접 자식 텍스트는 미렌더).
  const kids=svg.childNodes;
  for(let i=kids.length-1;i>=0;i--){
    const n=kids[i];
    if(n.nodeType===3&&String(n.nodeValue).indexOf('NaN')>=0) svg.removeChild(n);
  }
  let html='';
  for(let i=0;i<rels.length;i++){
    const rl=rels[i]||{},a=pos[rl.from],b=pos[rl.to];
    if(!a||!b) continue;
    const type=String(rl.type==null?'':rl.type);
    html+='<line data-wte-type="'+esc(type)+'" x1="'+a[0]+'" y1="'+a[1]
      +'" x2="'+b[0]+'" y2="'+b[1]+'" stroke="'+wtEdgeColor(type)
      +'" stroke-width="1.5"/>'
      +'<text class="edge-label" x="'+((a[0]+b[0])/2)+'" y="'+((a[1]+b[1])/2-4)
      +'" text-anchor="middle">'+esc(type)+'</text>';
  }
  if(html===wteLayerHtml&&layer&&layer.parentNode===svg) return;
  wteLayerHtml=html;
  if(!layer){
    layer=document.createElementNS(svg.namespaceURI,'g');
    layer.setAttribute('id','wte-edge-layer');
  }
  if(layer.parentNode!==svg) svg.insertBefore(layer,svg.firstChild);
  layer.innerHTML=html;
}
function snapshotLabels(){
  const nodes=(typeof sg!=='undefined'&&sg&&sg.nodes)||[];
  for(let i=0;i<nodes.length;i++){
    const n=nodes[i];
    if(n&&n.id!=null) wteLabels[String(n.id)]=n.label==null?'':String(n.label);
  }
}
function renderMore(){
  const btn=$('#wt-expand-more'); if(!btn) return;
  const f=(typeof focus!=='undefined'?focus:null);
  btn.style.display=(f!=null&&!wteNoMore[f])?'block':'none';
}

/* ── 5) graph_expand 'more' — next_cursor opaque 유지 ────────────── */
async function expandMore(){
  const id=(typeof focus!=='undefined'?focus:null); if(!id) return;
  const cur=wteCursors[id];
  let url='/api/graph_expand?id='+encodeURIComponent(id);
  if(cur) url+='&cursor='+encodeURIComponent(cur);   // 파싱 없이 그대로 왕복
  let data=null;
  try{ data=await api(url); }catch(_){ return; }
  if(focus!==id) return;
  const items=(data&&data.items)||[];
  const nc=(data&&data.page&&data.page.next_cursor)||null;
  if(nc) wteCursors[id]=nc; else wteNoMore[id]=1;
  const seenIds={};
  const collect=function(arr){
    (arr||[]).forEach(function(x){if(x&&x.id!=null) seenIds[x.id]=1;});
  };
  if(typeof sg!=='undefined'&&sg){
    collect(sg.entities);collect(sg.claims);collect(sg.evidence);collect(sg.extra);
  }
  const rels=(sg&&sg.relationships)||[];
  let added=false;
  for(let i=0;i<items.length;i++){
    const it=items[i];
    if(!it||it.id==null||seenIds[it.id]===1||it.id===id) continue;
    seenIds[it.id]=1;added=true;
    if(it.label!=null) wteLabels[String(it.id)]=String(it.label);
    if(sg){
      sg.extra=sg.extra||[];
      sg.extra.push({id:it.id,kind:isClaim(it.id)?'claim':'entity'});
      if(!rels.some(function(r){
        return (r.from===id&&r.to===it.id)||(r.to===id&&r.from===it.id);}))
        rels.push({from:id,to:it.id,type:it.type});
    }
  }
  if(added&&typeof renderGraph==='function') renderGraph();
  decorate();
}

/* ── 2) type chip 토글 (칩 라벨 = "Type · n" 앞쪽) ──────────────── */
function chipLabel(el){
  return String(el.textContent||'').split('·')[0].trim();
}
function renderChips(){
  const chips=document.querySelectorAll('#type-chips .chip');
  for(let i=0;i<chips.length;i++)
    chips[i].classList.toggle('wte-chipoff',!!wteOn.size&&!wteOn.has(chipLabel(chips[i])));
}
function bindChips(){
  const box=$('#type-chips'); if(!box) return;
  box.addEventListener('click',function(ev){
    const chip=ev.target&&ev.target.closest?ev.target.closest('.chip'):null;
    if(!chip) return;
    const label=chipLabel(chip);
    if(wteOn.has(label)) wteOn.delete(label); else wteOn.add(label);
    renderChips(); decorate();
  });
}

/* ── 9) chronicle rail: events + valid/tx dual slider + 클릭 포커스 ── */
async function ensureChronicle(){
  if(wteChron||wteChronFetching) return;
  wteChronFetching=true;
  try{ wteChron=await api('/api/chronicle'); }
  catch(_){ wteChron={events:[],bounds:{}}; }
  wteChronFetching=false;
  wteEvents=(wteChron&&wteChron.events)||[];
  wteTs=wtTsList(wteEvents);
  const max=Math.max(wteTs.length-1,0);
  wteView.lo=0;wteView.hi=max;wteView.tlo=0;wteView.thi=max;
  renderBounds();renderRail();
}
function renderBounds(){
  const el=$('#wte-bounds'); if(!el) return;
  const b=(wteChron&&wteChron.bounds)||{};
  const f=function(v){return v==null?'—':String(v).slice(0,10);};
  el.textContent='valid '+f(b.valid_min)+'…'+f(b.valid_max)
    +' · tx '+f(b.tx_min)+'…'+f(b.tx_max);
}
function sliderMax(){return Math.max(wteTs.length-1,0);}
function renderRail(){
  const box=$('#wte-evt-box'); if(!box) return;
  const max=sliderMax();
  const specs=[['#wte-sl-lo','lo'],['#wte-sl-hi','hi'],
    ['#wte-sl-tlo','tlo'],['#wte-sl-thi','thi']];
  for(let i=0;i<specs.length;i++){
    const el=$(specs[i][0]); if(!el) continue;
    el.min='0';el.max=String(max);el.step='1';
    el.value=String(wteView[specs[i][1]]);
    el.oninput=onSlide;
  }
  const tmin=wteTs[0]||null,tmax=wteTs[wteTs.length-1]||null;
  let html='';
  const rows=wtFilterEvents(wteEvents,wteTs,wteView);
  for(let i=0;i<rows.length;i++){
    const r=rows[i]; if(!r.shown) continue;
    const e=r.event,pct=wtEventPct(e.at,tmin,tmax);
    html+='<div class="event wte-evt" style="left:'+pct+'%" data-claim="'
      +esc(e.claim_id||'')+'" title="'+esc(e.kind||'')+' · '+esc(String(e.at||''))+'">'
      +'<span class="lab">'+esc(e.kind||'')+'</span>'
      +'<span class="pin" style="background:'+wtPinColor(e.kind)+'"></span>'
      +'<span class="date">'+esc(String(e.at||'').slice(0,10))+'</span></div>';
  }
  box.innerHTML=wteEvents.length
    ?('<div class="line"></div>'+(html||'<div class="dim" style="padding:10px 0">선택 시간 창에 이벤트 없음</div>'))
    :empty('이력 없음','/api/chronicle events 가 없습니다 (honest-gap).');
  renderSliderVals();
}
function renderSliderVals(){
  const v=$('#wte-sl-val'),t=$('#wte-sl-tval');
  const fmt=function(k){return String(wteTs[k]||'—').slice(0,10);};
  if(v) v.textContent=fmt(wteView.lo)+' … '+fmt(wteView.hi);
  if(t) t.textContent=fmt(wteView.tlo)+' … '+fmt(wteView.thi);
}
function onSlide(){
  const g=function(id,key){
    const el=$(id); return el?+el.value:wteView[key];
  };
  const p=wtClampPair(g('#wte-sl-lo','lo'),g('#wte-sl-hi','hi'),sliderMax());
  const q=wtClampPair(g('#wte-sl-tlo','tlo'),g('#wte-sl-thi','thi'),sliderMax());
  wteView.lo=p[0];wteView.hi=p[1];wteView.tlo=q[0];wteView.thi=q[1];
  const pairs=[['#wte-sl-lo',p[0]],['#wte-sl-hi',p[1]],
    ['#wte-sl-tlo',q[0]],['#wte-sl-thi',q[1]]];
  for(let i=0;i<pairs.length;i++){
    const el=$(pairs[i][0]); if(el) el.value=String(pairs[i][1]);
  }
  renderRail();
}
function onEventClick(ev){
  const el=ev.target&&ev.target.closest?ev.target.closest('.wte-evt'):null;
  if(!el) return;
  const cid=el.getAttribute('data-claim'); if(!cid) return;
  if(typeof focus!=='undefined') focus=cid;
  if(typeof renderGraph==='function') renderGraph();
  wteFocusShown=null;
  showClaim(cid);
  if(typeof loadClaim==='function') loadClaim(cid);
  decorate();
}

/* ── base globals 동기화 ─────────────────────────────────────────── */
function onSubjectChanged(subj){
  if(!subj||subj===wteSubj) return;
  wteSubj=subj;
  const box=$('#wte-subclaims');
  if(box) box.innerHTML='<div class="wte-sc"><div class="q muted">'
    +'Subclaims · 분석 을 눌러 planner 실행 (on-request)</div></div>';
  ensureChronicle();               // 최초 선택 1회 (그 뒤 캐시)
}
function onFocusChanged(){
  const f=(typeof focus!=='undefined'?focus:null);
  if(f!=null&&isClaim(f)&&f!==wteFocusShown) showClaim(f);
  renderMore();
}
function attachDom(){
  const frag=$('#wte-frag'); if(!frag) return;
  const head=$('#campaign-map .panel-head');
  if(head) head.appendChild($('#wte-subclaim-btn'));
  const pred=$('#pred-list');
  if(pred&&pred.parentNode) pred.parentNode.insertBefore($('#wte-subclaims'),pred);
  const canvas=$('#war-canvas');
  const wl=$('#wt-list'),moreEl=$('#wt-expand-more');
  if(moreEl&&canvas){
    if(wl&&wl.parentNode===canvas) canvas.insertBefore(moreEl,wl);
    else if(canvas.lastElementChild) canvas.insertBefore(moreEl,canvas.lastElementChild);
    else canvas.appendChild(moreEl);
  }
  const insp=$('#inspector');
  if(insp) insp.appendChild($('#wte-claim-detail'));
  const rail=$('#chronicle-rail');
  if(rail&&rail.parentNode)
    rail.parentNode.insertBefore($('#wte-chron'),rail.nextSibling);
  frag.remove();
}
function watchBase(){
  // base 가 innerHTML 로 #type-chips·#wt-svg 를 갈아치우면 복원·재데코.
  const chips=$('#type-chips'),svg=$('#wt-svg');
  if(window.MutationObserver){
    if(chips)
      new MutationObserver(function(){renderChips();decorate();})
        .observe(chips,{childList:true,subtree:true});
    if(svg)
      new MutationObserver(function(){snapshotLabels();decorate();})
        .observe(svg,{childList:true,subtree:true});
  }
  // current/focus 는 let 바인딩 — 클릭 직후 동기 읽기로 변화 추적 (poll 금지).
  document.addEventListener('click',function(){
    setTimeout(function(){
      if(typeof current!=='undefined') onSubjectChanged(current);
      onFocusChanged();
    },0);
  },true);
  // 첫 진입 (base 부트strap 의 await 체이닝 뒤 자동 selectSubject) 대비 —
  // current 가 Set 될 때까지 유한 지연 재확인 3회 (정기 poll 아님).
  [400,1200,2500].forEach(function(ms){
    setTimeout(function(){
      if(typeof current!=='undefined'&&current) onSubjectChanged(current);
    },ms);
  });
}

/* ── init: DOM 이관·바인딩 (fetch 없음 — 전부 사용자 액션까지 lazy) ── */
// bindView 가 #wt-viewbar 를 #wte-frag 안에서 꺼내므로 attachDom(frag 제거) 보다 먼저.
bindView();
attachDom();
bindChips();
renderChips();
applyView();
const wteBtn=$('#wte-subclaim-btn'); if(wteBtn) wteBtn.onclick=runInvestigate;
const wteMore=$('#wt-expand-more'); if(wteMore) wteMore.onclick=expandMore;
const wteEvtBox=$('#wte-evt-box');
if(wteEvtBox) wteEvtBox.addEventListener('click',onEventClick);
watchBase();
})();
"""


def build() -> tuple[str, str]:
    """(본문 HTML 조각, 스크립트 문 블록) — integration용 순수 어셈블리 반환."""
    return PAGE_TABLE_EXT_BODY, PAGE_TABLE_EXT_JS



def pure_block() -> str:
    """PAGE_TABLE_EXT_JS 의 /*==PURE==*/…/*==ENDPURE==*/ 헬퍼 문 블록 (node 테스트용)."""
    start = PAGE_TABLE_EXT_JS.index("/*==PURE==*/") + len("/*==PURE==*/")
    end = PAGE_TABLE_EXT_JS.index("/*==ENDPURE==*/")
    return PAGE_TABLE_EXT_JS[start:end]
