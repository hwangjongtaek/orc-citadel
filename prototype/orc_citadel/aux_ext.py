"""보조 페이지 remaining-gaps 프런트 블록 (Wave 2 — Gate·Watchtower·Archive·Chronicle + 공유 검색).

`viewer_pages.shell()` 은 오케스트레이터가 최종 배선하므로, 이 모듈은 본문 HTML
조각(`*_BODY`)과 `<script>` 안에 들어갈 문 블록(`*_JS`)만 export 한다. 각 `*_JS`
는 최상위에서 `var`/function 선언만 쓰고 초기화는 IIFE 로 감싼다 — 병합 후에도
viewer_pages 의 공유 헬퍼(`api`·`esc`·`empty`·`$`) 를 재정의하지 않고 사용만 쓴다.

불변식: read-only·stdlib only·오프라인(외부 lib/폰트/CDN 금지 — 차트는 인라인 SVG)·
honest-gap(실측 없으면 정직 빈/not-measured). 목업 예시 수치는 절대 하드코딩하지
않는다: 검색은 DuckDB ILIKE/substring substring 기반이라 UI 문구도 'text contains'
(BM25 아님)로 정직하게 표기한다.
"""

# --- 공유 검색 (shell header input) -------------------------------------------
# shell() 의 `.search input` 에 enter 핸들러를 붙여 /api/search?q= 결과를 fixed
# 드롭다운(div)로 렌더 — body 컨테이너 불필요. 딥링크: entity→/table?subject=,
# claim→/witnesses?claim=, document→/archive?doc=.
SEARCH_JS = r"""
var GS_OPEN=false;
function gsDropdown(){
  var dd=document.getElementById('global-search-dd');
  if(dd) return dd;
  dd=document.createElement('div');
  dd.id='global-search-dd';
  dd.style.cssText='position:fixed;display:none;z-index:99;background:var(--surface);'
    +'border:1px solid var(--surface-variant);border-radius:var(--r-md);'
    +'max-height:60vh;overflow-y:auto;box-shadow:0 12px 32px -8px rgba(0,0,0,.6)';
  document.body.appendChild(dd);
  return dd;
}
function gsPlace(dd,sb){
  var r=sb.getBoundingClientRect();
  dd.style.top=(r.bottom+6)+'px';
  dd.style.left=Math.max(8,r.left)+'px';
  dd.style.width=Math.min(420,Math.max(280,r.width))+'px';
}
function gsRow(href,l,d,color){
  return '<a href="'+href+'" style="display:block;padding:8px 12px;border-bottom:1px solid var(--surface-variant);color:inherit;text-decoration:none">'
    +'<div style="font-size:12.5px;color:'+(color||'var(--on-surface)')+';font-family:var(--font-head);font-weight:600">'+l+'</div>'
    +'<div class="dim" style="font-family:var(--font-data);font-size:10.5px">'+d+'</div></a>';
}
function gsGroup(t,n){
  return '<div style="font-family:var(--font-head);font-size:9.5px;font-weight:700;letter-spacing:.12em;'
    +'text-transform:uppercase;color:var(--on-surface-muted);padding:8px 12px 4px">'+t+' · '+n+'</div>';
}
async function gsRun(sb,dd){
  var q=(sb.value||'').trim();
  if(!q){ dd.style.display='none'; GS_OPEN=false; return; }
  var r=await api('/api/search?q='+encodeURIComponent(q));
  var h='<div style="padding:8px 12px;border-bottom:1px solid var(--surface-variant)">'
    +'<span class="dim" style="font-size:10.5px">text contains 검색 (DuckDB ILIKE · substring — BM25 아님)</span></div>';
  if(r.counts){
    h+=gsGroup('Entities',r.counts.entities||0);
    h+=(r.entities||[]).map(e=>gsRow('/table?subject='+encodeURIComponent(e.entity_id),
      esc(e.name||e.entity_id),esc(e.entity_id+(e.mention_type?' · '+e.mention_type:'')),'var(--primary)')).join('');
    h+=gsGroup('Claims',r.counts.claims||0);
    h+=(r.claims||[]).map(c=>gsRow('/witnesses?claim='+encodeURIComponent(c.claim_id),
      esc((c.predicate||'claim')+' → '+(c.object_literal==null?'':c.object_literal)),esc(c.claim_id+' · '+(c.subject_id||'')),'var(--parchment)')).join('');
    h+=gsGroup('Documents',r.counts.documents||0);
    h+=(r.documents||[]).map(d=>gsRow('/archive?doc='+encodeURIComponent(d.doc_id),
      esc(d.title||d.doc_id),esc(d.doc_id+(d.source_id?' · '+d.source_id:'')))).join('');
  }
  var none=!(r.entities&&r.entities.length||r.claims&&r.claims.length||r.documents&&r.documents.length);
  dd.innerHTML=none?empty('text contains 일치 없음','쿼리를 줄이거나 부분 일치로 다시 시도하세요.'):h;
  gsPlace(dd,sb);
  dd.style.display='block';
  GS_OPEN=true;
}
(function(){
  var sb=document.querySelector('.search input');
  if(!sb) return;
  var dd=gsDropdown();
  sb.addEventListener('keydown',function(e){
    if(e.key==='Enter'){ e.preventDefault(); gsRun(sb,dd); }
    else if(e.key==='Escape'){ dd.style.display='none'; GS_OPEN=false; }
  });
  // URL bootstrap: /?q= 로 들어오면 헤더 검색을 즉시 실행 (Gate 딥링크 복원).
  var qp=new URLSearchParams(location.search).get('q');
  if(qp){ sb.value=qp; gsRun(sb,dd); }
  document.addEventListener('click',function(e){
    if(GS_OPEN && !dd.contains(e.target) && e.target!==sb){ dd.style.display='none'; GS_OPEN=false; }
  });
})();
"""

# --- Citadel Gate: mini-watchtower 카드 ----------------------------------------
# quarantined(/api/table 실측 count) + source 별 last_fetch(/api/watchtower intake).
GATE_EXT_BODY = """<h2>🛰️ Watchtower · 수집 관제 요약 <span class="dim">(mini — last_fetch · quarantine 현황 /api 실측)</span></h2>
<div class="card"><table id="gate-mini-watchtower"></table></div>
"""

GATE_EXT_JS = r"""
(function(){
  Promise.all([api('/api/watchtower'),api('/api/table')]).then(function(rs){
    var w=rs[0], t=rs[1];
    var intake=w.intake||{};
    var lf={};
    (intake.last_fetch_by_source||[]).forEach(function(s){ lf[s.source_id]=s.fetched_at; });
    var rows=[{k:'Quarantine 현황',
      v:'<span class="badge warn">'+Number(t.quarantined||0)+' quarantine</span> <a href="/table">War Table ›</a>',
      d:'claims status 실측 count (/api/table)'}];
    var srcs=w.sources||[];
    if(!srcs.length){ rows.push({k:'Sources',v:'<span class="muted">수집 source 없음</span>',d:''}); }
    srcs.forEach(function(s){
      var at=lf[s.source_id]||s.last_fetch;
      rows.push({k:esc(s.source_id),
        v:at?esc(String(at).slice(0,19).replace('T',' ')):'<span class="na">not-measured</span>',
        d:'doc '+s.doc_count});
    });
    var el=document.querySelector('#gate-mini-watchtower');
    if(!el) return;
    el.innerHTML='<tr><th>항목</th><th>실측</th><th>비고</th></tr>'+rows.map(function(r){
      return '<tr><td style="font-weight:600">'+r.k+'</td><td>'+r.v+'</td><td class="dim">'+r.d+'</td></tr>';
    }).join('');
  });
})();
"""

# --- Watchtower: intake 시계열 + sources 확장 테이블 ---------------------------
# arrivals_per_hour 버킷 → 인라인 SVG 막대 (외부 lib 금지). measured=False 정직 빈.
WT_EXT_BODY = """<h2>📥 Intake · 도착 시계열 <span class="dim">(fetch.json fetched_at 실측 1h 버킷 — 인라인 SVG · 외부 lib 없음)</span></h2>
<div class="grid" id="wt-intake"></div>

<h2>🗂️ Sources 확장 <span class="dim">(last_fetch · governance — fetch.json 표본 실측)</span></h2>
<div class="card"><table id="wt-sources-ext"></table></div>
"""

WT_EXT_JS = r"""
function wtBarPath(max,b,i){
  var w=14, gap=(720-24*14)/23, x=2+i*(w+gap);
  var h=Math.max(1,Math.round(108*(b.count/max))), y=118-h;
  return '<rect x="'+x+'" y="'+y+'" width="'+w+'" height="'+h+'" rx="2" fill="var(--primary)"><title>'+esc(b.bucket)+' · '+b.count+'</title></rect>'
    +'<text x="'+(x+w/2)+'" y="132" text-anchor="middle" font-size="7.5" fill="var(--on-surface-muted)">'+esc(String(b.bucket).slice(11,13))+'</text>';
}
(function(){
  api('/api/watchtower').then(function(r){
    var intake=r.intake||{}, b=intake.arrivals_per_hour||[];
    var chart;
    if(!intake.measured||!b.length){
      chart=empty('intake 미측정',intake.note||'fetch.json 에 fetched_at 없음 (honest-gap §6.2)');
    } else {
      var bmax=1, bi=0;
      for(bi=0;bi<b.length;bi++){ if(b[bi].count>bmax) bmax=b[bi].count; }
      chart='<svg width="720" height="140" viewBox="0 0 720 140" role="img" aria-label="arrivals per hour">'
        +'<line x1="0" y1="118" x2="720" y2="118" stroke="var(--surface-variant)"/>'
        +b.map(function(bb,ii){ return wtBarPath(bmax,bb,ii); }).join('')+'</svg>'
        +'<p class="dim">window '+esc(intake.window_hours)+'h · 버킷 = 최근 도착 기준 1시간</p>';
    }
    var lf=intake.last_fetch_by_source||[];
    document.querySelector('#wt-intake').innerHTML=
      '<div class="card" style="overflow-x:auto"><div class="body">'+chart+'</div></div>'
      +'<div class="card"><div class="body"><div class="sec-label">last_fetch · source</div>'
      +(lf.length?lf.map(function(s){
          return '<div class="arow"><span class="al">'+esc(s.source_id)+'</span>'
            +'<span class="as mono" style="margin-left:auto">'+esc(String(s.fetched_at||'—').slice(0,19).replace('T',' '))+'</span></div>';
        }).join(''):'<span class="muted">측정 없음</span>')
      +'</div></div>';
    var srcs=r.sources||[];
    document.querySelector('#wt-sources-ext').innerHTML=
      '<tr><th>Source</th><th>last_fetch</th><th>http_status</th><th>robots</th></tr>'
      +(srcs.length?srcs.map(function(s){
        var g=s.governance||{};
        var rob=g.robots_allowed===true?'<span class="badge good">allow</span>'
          :g.robots_allowed===false?'<span class="badge err">disallow</span>'
          :'<span class="na">not-measured</span>';
        var st=g.http_status==null?'<span class="na">not-measured</span>':'<span class="badge">'+esc(g.http_status)+'</span>';
        return '<tr><td>'+esc(s.source_id)+'</td>'
          +'<td class="mono">'+(s.last_fetch?esc(String(s.last_fetch).slice(0,19).replace('T',' ')):'<span class="na">not-measured</span>')+'</td>'
          +'<td>'+st+'</td><td>'+rob+'</td></tr>';
      }).join(''):'<tr><td colspan="4" class="muted">source 없음</td></tr>');
  });
})();
"""

# --- Grand Archive: facet·Stacks·contains 검색·Codex 메타·?doc= 부트스트랩 ------
# /api/archive 확장(cluster_role·language·publication_time·segment_kinds·url_groups)
# 과 /api/search documents join. `codex` 래퍼로 기존 상세 패널에 메타+딥링크 appended.
AR_EXT_BODY = """<h2>🧮 Archive Ext <span class="dim">(language · dedup role · publication 정렬 · 본문 contains)</span></h2>
<div class="card"><div class="body">
  <div class="search" style="width:100%;max-width:560px"><svg width="15" height="15" viewBox="0 0 24 24" fill="none"><circle cx="11" cy="11" r="7" stroke="currentColor" stroke-width="2"/><path d="M20 20 L16.5 16.5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
    <input id="ar-q" placeholder="본문 contains 검색 (title · url · doc_id — /api search join)" /></div>
  <p class="dim" style="margin-top:6px">text contains 검색 — DuckDB ILIKE substring 정합 (BM25 · rank 없음).</p>
  <div class="sec-label">Facet · language / role / sort</div>
  <div id="ar-facets"></div>
  <div class="card" id="ar-table" style="margin-top:8px"></div>
</div></div>

<h2>🗃️ Stacks · 동일 URL 문서군 <span class="dim">(url_groups ≥2 · ≤20)</span></h2>
<div class="card" id="ar-stacks"></div>

<h2>🧩 Segment kinds 현황 <span class="dim">(normalized segments GROUP BY)</span></h2>
<div class="card" id="ar-kinds"></div>
"""

AR_EXT_JS = r"""
(function(){
  var aextDocs=[], aextLang='', aextRole='', aextSort=false, aextMode='', aextStacks=[];
  function drow(d){
    return '<tr data-doc="'+esc(d.doc_id)+'"><td><code>'+esc(d.doc_id)+'</code></td><td>'+esc(d.source_id||'')+'</td>'
      +'<td>'+esc(d.title||'')+'</td><td><span class="badge">'+esc(d.language||'unknown')+'</span></td>'
      +'<td>'+clusterRoleChip(d.cluster_role)+'</td>'
      +'<td class="mono">'+(d.publication_time?esc(String(d.publication_time).slice(0,10)):'<span class="na">—</span>')+'</td>'
      +'<td>'+Number(d.segments||0)+'</td></tr>';
  }
  function tableHtml(rows){
    return '<table><tr><th>doc_id</th><th>source</th><th>title</th><th>language</th><th>role</th><th>publication</th><th>segments</th></tr>'
      +(rows.length?rows.map(drow).join('')
        :'<tr><td colspan="7" class="muted">조건 일치 문서 없음</td></tr>')+'</table>';
  }
  function clusterRoleChip(r){
    if(!r) return '<span class="muted">—</span>';
    var cls=r==='root'?'good':(r==='derived'?'uncert':'warn');
    return '<span class="badge '+cls+'">'+esc(r)+'</span>';
  }
  function chip(label,active,onclick,color){
    var s=document.createElement('span');
    s.className='chip'+(active?' active':'');
    s.style.cursor='pointer';
    if(active) s.style.borderColor='var(--primary)';
    s.innerHTML='<span class="sw" style="background:'+(color||'var(--primary)')+'"></span>'+esc(label);
    s.onclick=onclick;
    return s;
  }
  function rowsNow(){
    var rows=aextDocs.filter(function(d){
      return (!aextLang||(d.language||'unknown')===aextLang)&&(!aextRole||(d.cluster_role||'')==aextRole);
    });
    if(aextSort) rows=rows.slice().sort(function(a,b){
      return String(b.publication_time||'').localeCompare(String(a.publication_time||''));
    });
    return rows;
  }
  function rebuild(){
    var wrap=document.querySelector('#ar-facets');
    if(!wrap) return;
    wrap.textContent='';
    var lo={}, ro={};
    aextDocs.forEach(function(d){
      var l=d.language||'unknown'; lo[l]=(lo[l]||0)+1;
      if(d.cluster_role) ro[d.cluster_role]=(ro[d.cluster_role]||0)+1;
    });
    Object.keys(lo).sort().forEach(function(l){
      wrap.appendChild(chip(l+' · '+lo[l],aextLang===l,function(){ aextLang=aextLang===l?'':l; rebuild(); }));
    });
    Object.keys(ro).sort().forEach(function(rr){
      wrap.appendChild(chip('role:'+rr+' · '+ro[rr],aextRole===rr,function(){ aextRole=aextRole===rr?'':rr; rebuild(); },'var(--parchment)'));
    });
    wrap.appendChild(chip(aextSort?'publication newest-first':'publication 정렬',aextSort,function(){ aextSort=!aextSort; rebuild(); },'var(--signal-amber)'));
    var tb=document.querySelector('#ar-table');
    if(aextMode==='doc'&&aextSearchNote){
      tb.innerHTML='<div class="panel-body">'+aextSearchNote+tableHtml(rowsNow())+'</div>';
    } else {
      tb.innerHTML=tableHtml(rowsNow());
    }
    tb.querySelectorAll('tr[data-doc]').forEach(function(tr){
      tr.style.cursor='pointer';
      tr.onclick=function(){ try{ codex(tr.getAttribute('data-doc')); }catch(_e){} };
    });
  }
  var aextSearchNote='';
  function applyDocIds(ids,label){
    var set={};
    ids.forEach(function(i){ set[i]=1; });
    aextDocs=aextAll.filter(function(d){ return set[d.doc_id]; });
    aextMode='doc';
    aextSearchNote='<p class="dim" style="margin-bottom:8px">'+esc(label)+'</p>';
    rebuild();
  }
  var aextAll=[];
  function renderKinds(sk){
    var el=document.querySelector('#ar-kinds');
    var keys=Object.keys(sk||{});
    el.innerHTML=keys.length?keys.sort().map(function(k){
      return '<span class="chip"><span class="sw" style="background:var(--secondary)"></span>'+esc(k)+' · '+sk[k]+'</span>';
    }).join(''):empty('segment kinds 미측정','normalized 존 segments 없음 (honest-gap §6.2)');
  }
  function renderStacks(groups){
    var el=document.querySelector('#ar-stacks');
    el.innerHTML=groups.length?'<table><tr><th>url</th><th class="num">문서 수</th><th>doc_ids</th></tr>'
      +groups.map(function(g){
        return '<tr><td class="mono">'+esc(g.url||'—')+'</td><td class="num">'+g.count+'</td>'
          +'<td>'+(g.doc_ids||[]).map(function(id){
              return '<a href="/archive?doc='+encodeURIComponent(id)+'" class="badge" style="margin-right:4px;text-decoration:none">'+esc(id.slice(0,12))+'…</a>';
            }).join('')+'</td></tr>';
      }).join('')+'</table>'
      :empty('동일 URL 스택 없음','url_groups 실측 0 — 서로 다른 URL 문서만 존재');
  }
  // Codex 상세 확장: language/parser/version 메타 + /witnesses?doc= 딥링크 (래퍼).
  if(typeof window.codex==='function'){
    var codexOrig=window.codex;
    window.codex=function(docId){
      codexOrig(docId);
      var d=aextAll.filter(function(x){ return x.doc_id===docId; })[0];
      var panel=document.querySelector('#archive-codex');
      if(!d||!panel) return;
      var meta=document.createElement('div');
      meta.innerHTML='<hr style="border:none;border-top:1px solid var(--surface-variant);margin:10px 0"/>'
        +'<div class="conf" style="margin:10px 0">'
        +'<div class="cell"><div class="num" style="font-size:13px">'+esc(d.language||'unknown')+'</div><div class="cap">language</div></div>'
        +'<div class="cell"><div class="num" style="font-size:13px">'+esc(d.parser_version||'—')+'</div><div class="cap">parser_version</div></div>'
        +'<div class="cell"><div class="num" style="font-size:13px">'+clusterRoleChip(d.cluster_role)+'</div><div class="cap">cluster_role</div></div>'
        +'</div>'
        +'<p class="dim mono">publication '+esc(String(d.publication_time||'—').slice(0,19))+' · revision '+esc(String(d.revision_time||'—').slice(0,19))+'</p>'
        +'<p><a href="/witnesses?doc='+encodeURIComponent(d.doc_id)+'">Hall of Witnesses · 이 문서의 증거 ›</a></p>';
      panel.appendChild(meta);
    };
  }
  var q=document.querySelector('#ar-q');
  if(q) q.addEventListener('keydown',function(e){
    if(e.key!=='Enter') return;
    e.preventDefault();
    var v=(q.value||'').trim();
    if(!v){ aextDocs=aextAll.slice(); aextMode=''; aextSearchNote=''; rebuild(); return; }
    api('/api/search?q='+encodeURIComponent(v)).then(function(sr){
      var ids=(sr.documents||[]).map(function(d){ return d.doc_id; });
      applyDocIds(ids,'text contains "'+v+'" — documents '+ids.length+'건 join (title·url ILIKE, BM25 아님)');
    });
  });
  api('/api/archive').then(function(r){
    aextAll=(r.normalized_documents||[]).slice();
    aextDocs=aextAll.slice();
    aextStacks=r.url_groups||[];
    renderKinds(r.segment_kinds||{});
    renderStacks(aextStacks);
    var p=new URLSearchParams(location.search);
    var doc=p.get('doc'), src=p.get('src');
    if(doc){
      if(q) q.value=doc;
      applyDocIds([doc],'URL 부트스트랩 — /archive?doc= 단일 문서 선택');
      try{ codex(doc); }catch(_e){}
    } else if(src){
      aextDocs=aextAll.filter(function(d){ return d.source_id===src; });
      aextMode='doc';
      aextSearchNote='<p class="dim" style="margin-bottom:8px">Stacks 딥링크 — source '+esc(src)+' 문서</p>';
      rebuild();
    } else {
      rebuild();
    }
  });
})();
"""

# --- Chronicle Vault: dual slider · preset · events rail · as-of 상세 -----------
# bounds(/api/chronicle) 로 valid·tx 레일 스케일을 그리고, preset 질문 3 종은
# 실재 assertion 에서 파생 — 재료 없으면 그 preset 은 비활성(chip.disabled).
# /archive?doc= 부트스트랩과 달리 여기서는 URL as-of 파라미터로 타임슬라이더 복원.
CH_BODY = """<h2>📐 Bitemporal Plane · 타임 슬라이더 <span class="dim">(valid × tx — /api/chronicle bounds 실측)</span></h2>
<div class="card"><div class="body" id="ch-plane"></div></div>

<h2>🧭 Preset 질문 <span class="dim">(실재 assertion 파생 — 재료 없으면 비활성)</span></h2>
<div class="card"><div class="body" id="ch-presets"></div></div>

<h2>🛤️ Events rail <span class="dim">(asserted · closed · superseded)</span></h2>
<div class="card"><div class="body" id="ch-events-rail"></div></div>

<h2>🔖 As-of assertion 상세</h2>
<div class="card" id="ch-assertion-detail"><span class="muted">assertion 테이블 행을 선택하세요.</span></div>
"""

CH_JS = r"""
(function(){
  var chAll=[], chBounds={}, chEvents=[];
  function chTs(v){ var x=v?Date.parse(String(v)):NaN; return isNaN(x)?null:x; }
  function chFmt(ms){ if(ms==null) return '—'; var d=new Date(ms); return d.toISOString().slice(0,16).replace('T',' '); }
  function chScrub(which){
    var v=chBounds[which+'_min'], x=chBounds[which+'_max'];
    var a=document.getElementById('ch-'+which+'-a'), b=document.getElementById('ch-'+which+'-b');
    var lab=document.getElementById('ch-'+which+'-lab');
    var va=chTs(v), vb=chTs(x);
    if(lab&&va!=null&&vb!=null&&a&&b){
      var span=Math.max(1,vb-va);
      lab.textContent=chFmt(va+span*(Number(a.value)||0)/100)+' — '+chFmt(va+span*(Number(b.value)||0)/100);
    }
  }
  function chApply(){
    var host=document.getElementById('ch-plane-links');
    if(!host) return;
    var p=new URLSearchParams();
    var va=document.getElementById('ch-valid-a'), vb=document.getElementById('ch-valid-b');
    var ta=document.getElementById('ch-tx-a'), tb=document.getElementById('ch-tx-b');
    function spanOf(a,b,which){
      var lo=chTs(chBounds[which+'_min']), hi=chTs(chBounds[which+'_max']);
      if(lo==null||hi==null||!a||!b) return null;
      var s=Math.max(1,hi-lo);
      var x=lo+s*(Number(a.value)||0)/100, y=lo+s*(Number(b.value)||0)/100;
      return new Date(Math.min(x,y)).toISOString();
    }
    var validTo=spanOf(va,vb,'valid'), txTo=spanOf(ta,tb,'tx');
    if(validTo) p.set('as_of_valid',validTo);
    if(txTo) p.set('as_of_tx',txTo);
    var q=p.toString();
    host.innerHTML=
      '<p><a class="btn primary" href="/table'+(q?('?'+q):'')+'">War Table @ 슬라이더 시점 ›</a></p>'
      +'<p class="dim mono">'+(q?esc(q):'bounds 미측정 — 딥링크는 현재 시점 기본')+'</p>';
  }
  function renderPlane(){
    var host=document.getElementById('ch-plane');
    if(!chBounds||(chBounds.valid_min==null&&chBounds.tx_min==null)){
      host.innerHTML=empty('bitemporal bounds 미측정','assertions 의 valid/tx 타임스탬프 실측 없음 (honest-gap §6.2)');
      return;
    }
    function axis(which,cap,color){
      var lo=String(chBounds[which+'_min']||'—').slice(0,16), hi=String(chBounds[which+'_max']||'—').slice(0,16);
      return '<label style="display:block;margin:8px 0 4px;font-family:var(--font-head);font-size:10px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:'+color+'">'
        +cap+' <span id="ch-'+which+'-lab" class="mono" style="letter-spacing:0;text-transform:none;color:var(--on-surface-muted)"></span></label>'
        +'<div style="display:flex;align-items:center;gap:8px">'
        +'<span class="mono dim">'+esc(lo)+'</span>'
        +'<div style="position:relative;flex:1;height:22px">'
        +'<input id="ch-'+which+'-a" type="range" min="0" max="100" value="0" style="position:absolute;left:0;right:0;top:0;width:100%;pointer-events:none;appearance:none;background:none">'
        +'<input id="ch-'+which+'-b" type="range" min="0" max="100" value="100" style="position:absolute;left:0;right:0;top:0;width:100%;pointer-events:none;appearance:none;background:none">'
        +'</div><span class="mono dim">'+esc(hi)+'</span></div>';
    }
    host.innerHTML=axis('valid','valid 시간축','var(--primary)')+axis('tx','tx 시간축','var(--signal-amber)')
      +'<style>#ch-plane input[type=range]::-webkit-slider-thumb{pointer-events:auto;appearance:none;width:12px;height:12px;border-radius:9999px;background:var(--on-surface);border:2px solid var(--citadel-night);cursor:pointer;margin-top:-5px}'
      +'#ch-plane input[type=range]::-webkit-slider-runnable-track{height:2px;background:var(--surface-variant)}</style>'
      +'<div id="ch-plane-links" style="margin-top:10px"></div>';
    ['valid','tx'].forEach(function(which){
      ['a','b'].forEach(function(k){
        var el=document.getElementById('ch-'+which+'-'+k);
        if(el) el.addEventListener('input',function(){ chScrub(which); chApply(); });
      });
    });
    chScrub('valid'); chScrub('tx'); chApply();
  }
  function chQuestions(a){
    var subj=a&&a.subject_id||'', pred=a&&a.predicate||'';
    return [
      {label:subj?('무엇이 '+subj+'(으)로 확인됐나?'):'과거 시점에는 무엇을 알고 있었나?',
       enabled:!!subj, valid:true, tx:false},
      {label:pred?(subj+'는 무엇을 '+pred+'했나?'):'무엇을 믿었나?',
       enabled:!!pred, valid:true, tx:true},
      {label:subj?(subj+'에 대해 무엇이 정정됐나?'):'정정 자료가 과거 결론을 어떻게 바꿨나?',
       enabled:!!subj, valid:false, tx:true}
    ];
  }
  function renderPresets(){
    var host=document.getElementById('ch-presets');
    var sorted=chAll.slice().sort(function(x,y){
      return String(y.tx_from||'').localeCompare(String(x.tx_from||''));
    });
    var best=sorted[0]||{};
    var qs=chQuestions({subject_id:best.subject_id,predicate:best.predicate,object_literal:best.object_literal});
    var claims=(chEvents[0]&&chEvents[0].claim_id)||'';
    var href='/witnesses'+(claims?('?claim='+encodeURIComponent(claims)):'');
    var n=0;
    host.innerHTML=qs.map(function(q){
      return '<span class="chip'+(q.enabled?' active':'')+'"'+(q.enabled?'':' style="opacity:.45;cursor:not-allowed"')+' data-ch-preset="'+n+++'">'
        +'<span class="sw" style="background:'+(q.enabled?'var(--primary)':'var(--on-surface-muted)')+'"></span>'
        +esc(q.label)+(q.enabled?'':' · 재료 없음 (비활성)')+'</span>';
    }).join('')+'<span class="dim">claim 재료 → <a href="'+esc(href)+'">Hall of Witnesses ›</a></span>';
    host.querySelectorAll('[data-ch-preset]').forEach(function(el){
      var q=qs[Number(el.getAttribute('data-ch-preset'))];
      if(!q||!q.enabled) return;
      el.style.cursor='pointer';
      el.onclick=function(){
        var v=chBounds.valid_min, tx=chBounds.tx_max;
        var va=document.getElementById('ch-valid-a'), vb=document.getElementById('ch-valid-b');
        var ta=document.getElementById('ch-tx-a'), tb=document.getElementById('ch-tx-b');
        if(va) va.value=q.valid?'0':'100';
        if(vb) vb.value='100';
        if(ta) ta.value=q.tx?'0':'100';
        if(tb) tb.value='100';
        if(v||tx){ chScrub('valid'); chScrub('tx'); chApply(); }
        var p=new URLSearchParams();
        if(q.valid&&v) p.set('valid_at',String(v));
        if(q.tx&&tx) p.set('tx_at',String(tx));
        var el2=document.getElementById('v'), el3=document.getElementById('t');
        if(el2&&p.get('valid_at')) el2.value=p.get('valid_at');
        if(el3&&p.get('tx_at')) el3.value=p.get('tx_at');
        api('/api/chronicle'+(p.toString()?('?'+p.toString()):'')).then(function(r){
          var d=document.getElementById('ch-assertion-detail');
          var rows=r&&r.assertions||[];
          d.innerHTML='<p class="dim">'+esc(q.label)+' — as-of 유효 assertion <b>'+rows.length+'</b>건</p>'
            +'<table><tr><th>assertion</th><th>predicate</th><th>valid_from</th><th>tx_from</th></tr>'
            +rows.slice(0,10).map(function(a){
                return '<tr data-ch-asof="'+esc(a.assertion_id)+'" style="cursor:pointer"><td><code>'+esc(a.assertion_id)+'</code></td>'
                  +'<td>'+esc(a.predicate||'')+'</td><td class="mono">'+esc(String(a.valid_from||'—').slice(0,10))+'</td>'
                  +'<td class="mono">'+esc(String(a.tx_from||'—').slice(0,10))+'</td></tr>';
              }).join('')+'</table>';
          bindRail();
        });
      };
    });
  }
  function renderRail(){
    var host=document.getElementById('ch-events-rail');
    if(!chEvents.length||!chEvents.some(function(e){ return chTs(e.at)!=null; })){
      host.innerHTML=empty('이벤트 실측 없음','assertion tx 타임스탬프 미누적 (honest-gap §6.2)');
      return;
    }
    var ts=chEvents.map(function(e){ return chTs(e.at); }).filter(function(x){ return x!=null; });
    var lo=Math.min.apply(null,ts), hi=Math.max.apply(null,ts);
    var span=Math.max(1,hi-lo);
    var COLORS={asserted:'var(--primary)',closed:'var(--error)',superseded:'var(--uncertain)'};
    var pins=chEvents.map(function(e,i){
      var t=chTs(e.at);
      if(t==null) return '';
      var pct=(100*(t-lo)/span).toFixed(2);
      return '<span class="ch-evpin" data-ch-ev="'+i+'" title="'+esc(String(e.at)+' · '+e.kind+' · '+(e.predicate||''))+'"'
        +' style="position:absolute;top:50%;left:'+pct+'%;transform:translate(-50%,-50%);width:9px;height:9px;border-radius:9999px;'
        +'background:'+(COLORS[e.kind]||'var(--surface-variant)')+';border:2px solid var(--citadel-night);cursor:pointer"></span>';
    }).join('');
    host.innerHTML='<div class="rail" style="margin:14px 8px"><div class="line"></div>'+pins+'</div>'
      +'<div style="display:flex;justify-content:space-between" class="dim mono">'
      +'<span>'+esc(new Date(lo).toISOString().slice(0,10))+'</span>'
      +'<span>'+chEvents.length+' events · asserted <span class="pill hi">●</span> closed <span class="pill lo">●</span> superseded <span class="pill med">●</span></span>'
      +'<span>'+esc(new Date(hi).toISOString().slice(0,10))+'</span></div>';
    bindRail();
  }
  function assertionCard(a){
    var host=document.getElementById('ch-assertion-detail');
    if(!a){ host.innerHTML=empty('assertion 미존재','id 확인 (honest-gap §6.2)'); return; }
    var chain=[];
    var seen={}, cur=a, guard=0;
    while(cur&&cur.supersedes_id&&guard++<20&&!seen[cur.supersedes_id]){
      seen[cur.supersedes_id]=1;
      var prev=chAll.filter(function(x){ return x.assertion_id===cur.supersedes_id; })[0];
      if(!prev) break;
      chain.push(prev.assertion_id);
      cur=prev;
    }
    var evs=chEvents.filter(function(e){ return e.assertion_id===a.assertion_id; });
    host.innerHTML='<div class="claim-card">'
      +'<div class="text"><b>'+esc(a.predicate||'assertion')+'</b>'+(a.object_literal!=null?(' → '+esc(a.object_literal)):'')+'</div>'
      +'<div class="id mono">'+esc(a.assertion_id)+' · subject '+esc(a.subject_id||'—')+' · claim '+esc(a.claim_id||'—')+'</div></div>'
      +'<div class="conf" style="margin:10px 0">'
      +'<div class="cell"><div class="num" style="font-size:13px">'+esc(String(a.valid_from||'—').slice(0,10))+'</div><div class="cap">valid_from</div></div>'
      +'<div class="cell"><div class="num" style="font-size:13px">'+esc(String(a.valid_to||'∞').slice(0,10))+'</div><div class="cap">valid_to</div></div>'
      +'<div class="cell"><div class="num" style="font-size:13px">'+esc(String(a.tx_from||'—').slice(0,10))+'</div><div class="cap">tx_from</div></div>'
      +'<div class="cell"><div class="num" style="font-size:13px">'+esc(String(a.tx_to||'∞').slice(0,10))+'</div><div class="cap">tx_to</div></div>'
      +'<div class="cell"><div class="num" style="font-size:13px">'+(a.supersedes_id?'<code>'+esc(a.supersedes_id.slice(0,10))+'…</code>':'<span class="na">—</span>')+'</div><div class="cap">supersedes</div></div>'
      +'<div class="cell"><div class="num" style="font-size:13px">'+evs.length+'</div><div class="cap">events</div></div>'
      +'</div>'
      +'<div class="sec-label">Timeline</div><div class="trail">'+(evs.length?evs.map(function(e){
          return '<span>'+esc(String(e.at||'—').slice(0,16).replace('T',' '))+' · '+esc(e.kind)+'</span>';
        }).join(' → '):'<span class="muted">이벤트 없음</span>')+'</div>'
      +(chain.length?('<div class="sec-label">Supersedes 체인</div><div class="trail">'+chain.map(function(c){ return '<span>◀ '+esc(c)+'</span>'; }).join('')+'</div>'):'')
      +'</div>';
  }
  function bindRail(){
    document.querySelectorAll('.ch-evpin[data-ch-ev]').forEach(function(el){
      el.onclick=function(){
        var e=chEvents[Number(el.getAttribute('data-ch-ev'))];
        if(!e) return;
        var a=chAll.filter(function(x){ return x.assertion_id===e.assertion_id; })[0];
        assertionCard(a||{assertion_id:e.assertion_id,claim_id:e.claim_id,predicate:e.predicate});
      };
    });
    document.querySelectorAll('[data-ch-asof]').forEach(function(tr){
      tr.onclick=function(){
        var id=tr.getAttribute('data-ch-asof');
        assertionCard(chAll.filter(function(x){ return x.assertion_id===id; })[0]);
      };
    });
  }
  api('/api/chronicle').then(function(r){
    chAll=r.assertions||[];
    chBounds=r.bounds||{};
    chEvents=r.events||[];
    renderPlane();
    renderPresets();
    renderRail();
    // URL bootstrap: ?doc= / ?claim= 로 도착한 assertion 상세 복원 (archive·witnesses 딥링크).
    var p=new URLSearchParams(location.search);
    var claim=p.get('claim');
    // as-of 파라미터(valid_at/tx_at 또는 as_of_*) 는 기존 폼에 반영만 한다 (재조회 없음 —
    // load() 는 페이지 본문 JS 소관). ?claim= 은 assertion 상세 복원.
    var va=p.get('valid_at')||p.get('as_of_valid'), tx=p.get('tx_at')||p.get('as_of_tx');
    var fv=document.getElementById('v'), ft=document.getElementById('t');
    if(fv&&va) fv.value=va;
    if(ft&&tx) ft.value=tx;
    if(claim){
      var hit=chAll.filter(function(a){ return String(a.claim_id||'')===claim; })[0]||null;
      var det=document.getElementById('ch-assertion-detail');
      if(hit) assertionCard(hit);
      else if(det) det.innerHTML=empty('딥링크 미일치','?claim= '+claim+' 와 일치하는 assertion 실측 없음 (honest-gap §6.2)');
    }
    // assertion 테이블 행 → 상세 카드 (기존 #assertions 테이블 래퍼, 행 추가 렌더 없음).
    var tbl=document.getElementById('assertions');
    if(tbl) tbl.addEventListener('click',function(ev){
      var tr=ev.target&&ev.target.closest?ev.target.closest('tr'):null;
      if(!tr) return;
      var code=tr.querySelector('code');
      if(!code) return;
      var id=code.textContent;
      var a=chAll.filter(function(x){ return x.assertion_id===id; })[0];
      if(a) assertionCard(a);
    });
  });
})();
"""


def build() -> tuple:
    """병합 재료 반환: (bodies, scripts).

    bodies — PAGE_* 본문에 삽입할 HTML 조각 순서대로 (shell 래핑 전).
    scripts — `<script>` 블록 안에 들어갈 JS 순서대로 (SEARCH_JS 는 어떤 페이지든
    header input 존재 시 자기초기화; page JS 는 해당 페이지 shell() body 마지막).
    """
    bodies = (GATE_EXT_BODY, WT_EXT_BODY, AR_EXT_BODY, CH_BODY)
    scripts = (SEARCH_JS, GATE_EXT_JS, WT_EXT_JS, AR_EXT_JS, CH_JS)
    return bodies, scripts
