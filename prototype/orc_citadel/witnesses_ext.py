"""Hall of Witnesses — remaining-gaps 프런트 확장 블록 (Wave 2).

`viewer_pages.PAGE_WITNESSES`(3-column)에 덧붙이는 단일 섹션:

1. claim 카드 상세 — `/api/subject_claims` 행 + `/api/claim` 병합(per-claim
   confidence 봉투). subject 보고서(`/api/report`) confidence 는 절대 재사용하지
   않는다 — 이 블록은 `/api/report` 를 fetch 하지 않는다.
2. bitemporal 메타 — `/api/chronicle`.assertions 를 claim_id 로 조인
   (valid_from/valid_to/tx_from/tx_to/time_precision).
3. 독립성 근거 — claim confidence.basis + `/api/archive` dedup_clusters/
   cluster_role 실측. clusters 0 이면 정직 빈 (curated.duckdb 실측 0).
4. Supporting Evidence 실 인용 — `/api/provenance` extraction_record offset →
   `/api/document` 세그먼트 char span 발췌 + source_type(source_id 접두사).
5. 반박 후보 — `/api/investigate`.counter_evidence(hypotheses·negative_queries)
   는 버튼 클릭 시에만 fetch, '결정적 후보' 라벨만. 확정 반박 문구 없음.
6. Provenance Trail 완전 전개 — 단, wire 에 실재하는 필드만:
   extraction_record 는 {extraction_id, segment_id, char_start, char_end,
   content_hash} (model_id·schema_version·fetched_at 은 trail wire 미노출 →
   표시하지 않는다), documentMeta 는 {doc_id, source_id, url, language,
   publication_time, parser_version}.
7. 원문 toolbar — parser_version·publication_time·revision_time(archive 조인,
   `/api/document` wire 에 없으면 '—') + /archive?doc=·/table?subject= 딥링크.
8. 하이라이트 legend — supports span 실측 수 + 후보 span 연결 없음 주석.

불변식: read-only·stdlib only·오프라인·honest-gap. 목업 예시 수치는 아무 데도
하드코딩하지 않는다 — 모든 수치는 wire 응답에서 계산된다.

integration: 오케스트레이터가 `PAGE_WITNESSES_EXT_BODY`(본문 HTML 조각)와
`PAGE_WITNESSES_EXT_JS`(<script> 안의 문 블록; 자기초기화 IIFE 로 끝)를
shell() 안에 기존 PAGE_WITNESSES 본문 뒤로 이어붙인다. JS 는 페이지의 기존
전역 헬퍼(`$`·`esc`·`empty`)만 사용하고 재정의하지 않는다. 최상위 신규
전역은 `WITX`(순수 데이터 조립 헬퍼, node 로 단위 검증 가능) 하나뿐.
"""
from __future__ import annotations

import json

# --- wire 계약 상수 (JS 와 단일 진화 — JS 쪽 WITX 에 동일 배열로 주입) ----------

MODALITIES = ("fact", "asserted", "opinion", "prediction")
# design 02 §2.3 — viewer._source_type 과 동일 vocab.
SOURCE_TYPE_TOKENS = ("official", "press", "gov", "research", "exchange")
COUNTER_LABEL = "결정적 후보"
# /api/provenance extraction_record step 의 wire 실재 필드 (api_facade
# get_evidence_provenance er_step). model_id·schema_version·fetched_at 은
# zone 스키마에는 존재하나 trail wire 가 노출하지 않는다 → 미표시.
TRAIL_EXTRACTION_FIELDS = ("extraction_id", "segment_id", "char_start",
                           "char_end", "content_hash")
# /api/document documents[] 행의 wire 실재 컬럼.
DOCUMENT_META_FIELDS = ("doc_id", "source_id", "url", "language",
                        "publication_time", "parser_version")
# /api/chronicle assertions[] 행의 bitemporal 컬럼.
TIME_FIELDS = ("valid_from", "valid_to", "tx_from", "tx_to", "time_precision")


# --- 본문 HTML 조각 (shell() 안에 그대로 이어붙이는 섹션) -----------------------

_EXT_CSS = """<style>
 .witx-block{margin-top:var(--sp-lg)}
 .witx-cols{display:grid;grid-template-columns:300px 1fr;border:1px solid var(--surface-variant);border-radius:var(--r-lg);overflow:hidden}
 .witx-cols>.witx-col{padding:var(--sp-md);min-width:0}
 .witx-cols>.witx-col:first-child{border-right:1px solid var(--surface-variant)}
 .witx-chips .chip{cursor:pointer}
 .witx-chips .chip.on{border-color:var(--primary);color:var(--primary);background:rgba(69,224,111,.08)}
 .witx-none{font-size:11px;color:var(--on-surface-muted)}
 .witx-legend{display:flex;gap:var(--sp-md);flex-wrap:wrap;font-size:11px;color:var(--on-surface-muted);margin-top:10px}
 .witx-legend .item{display:inline-flex;align-items:center;gap:6px}
 .witx-sw{width:10px;height:10px;border-radius:3px;display:inline-block}
 .witx-sw.supports{background:rgba(69,224,111,.45)}
 .witx-sw.candidate{background:rgba(224,82,82,.45)}
 .witx-qlist{margin:4px 0 0 16px;font-size:12px;color:var(--on-surface-muted)}
 .witx-meta{display:flex;gap:10px;flex-wrap:wrap;font-size:11px;color:var(--on-surface-muted)}
 .witx-meta b{color:var(--on-surface);font-weight:600}
</style>
"""

PAGE_WITNESSES_EXT_BODY = _EXT_CSS + """<section class="panel witx-block" id="witx-block">
  <div class="panel-head"><h2>Witnesses Extended · remaining-gaps</h2><span class="sub" id="witx-status">—</span></div>
  <div class="witx-cols">
    <div class="witx-col">
      <div class="sec-label" style="margin-top:0">Claims · per-claim confidence</div>
      <div class="witx-chips" id="witx-modality"></div>
      <div id="witx-claims"></div>
    </div>
    <div class="witx-col">
      <div class="sec-label" style="margin-top:0">Bitemporal · chronicle join</div>
      <div id="witx-bitemporal"></div>
      <div class="sec-label">독립성 근거</div>
      <div id="witx-independence"></div>
      <div class="sec-label">Supporting Evidence · 실 인용</div>
      <div id="witx-evidence"></div>
      <div class="sec-label">반박 후보 · /api/investigate</div>
      <div id="witx-counter"><button class="btn" id="witx-run-counter" type="button">후보 계산 (on-request)</button><div id="witx-counter-body"></div></div>
      <div class="sec-label">Provenance Trail · 완전 전개 (wire 필드만)</div>
      <div id="witx-trail"></div>
      <div class="doc-toolbar" id="witx-toolbar" style="border:1px solid var(--surface-variant);border-radius:var(--r-md)"></div>
      <div class="witx-legend" id="witx-legend"></div>
    </div>
  </div>
</section>
"""


# --- 순수 데이터 조립 헬퍼 (JS) — node 로 입력 wire → 출력 객수 검증 가능 --------

WITNESS_PURE_JS = r"""var WITX=(function(){
  "use strict";
  var MODALITIES=__MODALITIES__;
  var SOURCE_TYPE_TOKENS=__SOURCE_TYPES__;
  var COUNTER_LABEL=__COUNTER_LABEL__;
  var TRAIL_EXTRACTION_FIELDS=__TRAIL_EXT__;
  var DOCUMENT_META_FIELDS=__DOC_META__;
  var TIME_FIELDS=__TIME_FIELDS__;
  // source_id 접두사 → source_type (viewer._source_type 미러). 미지수면 null.
  function sourceType(sid){
    if(sid==null||sid==="") return null;
    var head=String(sid).split("-",1)[0];
    return SOURCE_TYPE_TOKENS.indexOf(head)>=0?head:"source";
  }
  // wire 필드 화이트리스트 발췌 — null/빈문자 제거(임의 확장 방지).
  function pick(o,keys){
    var r={};
    if(!o) return r;
    for(var i=0;i<keys.length;i++){var k=keys[i];if(o[k]!=null&&o[k]!=="")r[k]=o[k];}
    return r;
  }
  function fmtTs(v){
    if(v==null||v==="") return "\u2014";
    return String(v).replace("T"," ").slice(0,19);
  }
  // /api/chronicle assertions[] → claim_id 조인 맵 (동일 claim 은 마지막 행 우선).
  function joinChronicle(assertions){
    var m={};
    (assertions||[]).forEach(function(a){ if(a&&a.claim_id!=null) m[a.claim_id]=a; });
    return m;
  }
  function timeRow(row){
    var t={};
    TIME_FIELDS.forEach(function(k){ t[k]=(row&&row[k]!=null)?row[k]:null; });
    return t;
  }
  // claim 카드 — row(/api/subject_claims 행) + claimWire(/api/claim 병합 응답) +
  // chronRow(/api/chronicle assertions 행). subject 보고서 confidence 는
  // 입력 자체가 없다 → 재사용 구조적 불가.
  function claimCard(row,claimWire,chronRow){
    var r=row||{}, cw=claimWire||{};
    var pred=cw.predicate!=null?cw.predicate:(r.predicate!=null?r.predicate:null);
    var lit=cw.object_literal!=null?cw.object_literal:(r.object_literal!=null?r.object_literal:null);
    var oid=cw.object_id!=null?cw.object_id:(r.object_id!=null?r.object_id:null);
    var text=cw.surface_fragment||lit||
      ((pred!=null?pred:"\u2014")+" \u00b7 "+(lit!=null?lit:(oid!=null?oid:"\u2014")));
    var notFound=!!cw.error;
    return {
      claim_id:cw.claim_id!=null?cw.claim_id:(r.claim_id!=null?r.claim_id:null),
      subject_id:cw.subject_id!=null?cw.subject_id:(r.subject_id!=null?r.subject_id:null),
      predicate:pred,
      object_literal:lit,
      modality:cw.modality!=null?cw.modality:(r.modality!=null?r.modality:null),
      text:text,
      // per-claim 봉투만 — value 단일 게이지 금지(evidence/independent 동봉).
      confidence:(!notFound&&cw.confidence)?cw.confidence:null,
      doc_id:cw.doc_id!=null?cw.doc_id:(r.doc_id!=null?r.doc_id:null),
      time:timeRow(chronRow)
    };
  }
  function filterByModality(cards,m){
    var arr=(cards||[]).slice();
    return m?arr.filter(function(c){return c.modality===m;}):arr;
  }
  // /api/provenance trail + /api/document → 표시 단계[] (wire 실재 필드만).
  function trailSteps(prov,docWire){
    var out=[];
    var trail=(prov&&prov.trail)||[];
    var doc0=(docWire&&docWire.documents&&docWire.documents[0])||null;
    trail.forEach(function(s){
      if(!s||s.step==null) return;
      if(s.step==="claim"){ out.push({step:"claim",fields:pick(s,["claim_id","predicate","ontology_version"])}); }
      else if(s.step==="extraction_record"){ out.push({step:"extraction_record",fields:pick(s,TRAIL_EXTRACTION_FIELDS)}); }
      else if(s.step==="document"){
        out.push({step:"document",fields:pick(s,["doc_id"])});
        var meta=pick(doc0,DOCUMENT_META_FIELDS);
        var st=sourceType(meta.source_id);
        if(st!=null) meta.source_type=st;
        out.push({step:"document_meta",fields:meta});
      }
      else { out.push({step:s.step,fields:pick(s,Object.keys(s).filter(function(k){return k!=="step";}))}); }
    });
    return out;
  }
  // extraction offset → normalized 세그먼트 char span 발췌 인용.
  // 세그먼트 id 축 불일치({doc}#p{n} vs {doc}#p0.s{n}) — 마지막 숫자 인덱스로 ord 대응
  // (기존 PAGE_WITNESSES fetchDoc 와 동일 규칙). 매핑 실패는 정직 null.
  function citation(segments,segmentId,charStart,charEnd){
    if(!segments||!segments.length||segmentId==null||charStart==null||charEnd==null) return null;
    var m=/(\d+)$/.exec(String(segmentId));
    if(!m) return null;
    var ord=+m[1];
    var seg=null;
    for(var i=0;i<segments.length;i++){ if(segments[i]&&segments[i].ord===ord){seg=segments[i];break;} }
    if(!seg) return null;
    var text=String(seg.text==null?"":seg.text);
    var q=text.slice(charStart,charEnd);
    if(!q) return null;
    return {quote:q,segment_id:seg.segment_id!=null?seg.segment_id:segmentId,
            ord:ord,char_start:charStart,char_end:charEnd};
  }
  // 독립성 근거 — basis(claim 봉투 실측) + dup cluster 멤버 설명.
  // dedupClusters==0(curated.duckdb 실측) → 보정 근거 정직 빈.
  function independence(basis,evidenceDocs,dedupClusters){
    var docs=evidenceDocs||[];
    var n=(dedupClusters==null?0:+dedupClusters);
    var res={basis:(basis!=null&&basis!=="")?basis:null,
             clusters:n,measured:n>0,text:null};
    if(n>0){
      var known=docs.filter(function(d){return d&&d.cluster_role;});
      if(known.length){
        res.text="클러스터 계보: "+known.map(function(d){
          return d.doc_id+"\u2192"+d.cluster_role;
        }).join(" \u00b7 ")+" (dup_clusters "+n+")";
      } else {
        res.text="dup_clusters 실측 "+n+" — 지지 문서와 멤버 설명 미매핑";
      }
    } else {
      res.text="dup_clusters 실측 0 — 독립성 보정 근거(클러스터 멤버) 미존재 (honest-gap \u00a76.2)";
    }
    return res;
  }
  // 반박 후보 — /api/investigate counter_evidence 배열(결정적 규칙 산출)만.
  // wire 는 hypotheses/negative_queries 를 노출하고 확정 판정(contradiction_
  // candidates)을 노출하지 않는다 → '결정적 후보' 라벨만 부여.
  function counterCards(arr){
    var cards=(arr||[]).map(function(x){
      x=x||{};
      return {subject_id:x.subject_id!=null?x.subject_id:null,
              id:x.id!=null?x.id:null,
              label:COUNTER_LABEL,
              hypotheses:(x.hypotheses||[]).slice(),
              negative_queries:(x.negative_queries||[]).slice()};
    });
    return {cards:cards,measured:cards.length>0,
            note:"확정 반박 판정은 wire 미로딩 — 연결 span 없음 (honest-gap \u00a76.2)"};
  }
  // 원문 toolbar — /api/document 메타 + archive 조인 revision_time + 딥링크.
  function toolbar(docWire,archiveDoc,subjectId){
    var doc0=(docWire&&docWire.documents&&docWire.documents[0])||{};
    var ad=archiveDoc||{};
    var docId=(docWire&&docWire.doc_id)||doc0.doc_id||null;
    var rev=(ad.revision_time!=null)?ad.revision_time:(doc0.revision_time!=null?doc0.revision_time:null);
    return {
      doc_id:docId,
      meta:{parser_version:doc0.parser_version!=null?doc0.parser_version:null,
            publication_time:doc0.publication_time!=null?doc0.publication_time:null,
            revision_time:rev,
            source_type:sourceType(doc0.source_id!=null?doc0.source_id:ad.source_id)},
      links:[{href:"/archive?doc="+encodeURIComponent(docId==null?"":docId),label:"\u2192 Grand Archive \ubb38\uc11c"},
             {href:"/table?subject="+encodeURIComponent(subjectId==null?"":subjectId),label:"\u2192 War Table \uadf8\ub798\ud504"}]
    };
  }
  // legend — supports 하이라이트는 인용 실측 수, 후보 span 은 연결 수로 계산.
  // (counter_evidence wire 는 span 을 보유하지 않는다 → candidateSpans 항시 0,
  //  단 그 0 도 입력 배열에서 계산된 값이다.)
  function legend(citedCount,counterResult){
    var cs=0;
    if(counterResult&&counterResult.cards){
      cs=counterResult.cards.filter(function(c){return c&&(c.char_start!=null||c.segment_id!=null);}).length;
    }
    return {items:[
      {kind:"supports",label:"supports \ud558\uc774\ub77c\uc774\ud2b8",
       note:"인용 실측 "+(citedCount|0)+"\uac74"},
      {kind:"candidate",label:"반박 후보 span",
       note:cs>0?("\uc5f0\uacb0 span "+cs+"\uac74"):("\uc5f0\uacb0 span \uc2e4\uce21 0 \u2014 \ud6c4\ubcf4\ub294 \ud310\uc815\u00b7span \ubbf8\ubcf4\uc720 (honest-gap \u00a76.2)")}
    ]};
  }
  // URL bootstrap 계획 — /witnesses?claim=·?doc= 파라미터로 초기 선택을 결정.
  // claim: 로드된 카드에서 정확 일치 시 그 claim 선택, 불일치 시 정직 문구.
  // doc: 카드의 doc_id(/api/claim 병합 키)가 일치하는 첫 claim 선택 + 하이라이트
  //      포커스; 불일치 시 정직 문구. 파라미터 없으면 기본 첫 카드.
  function bootPlan(cards,params){
    var q=params||{},cs=cards||[];
    if(q.claim!=null&&q.claim!==""){
      var hc=cs.find(function(c){return c&&c.claim_id===q.claim;})||null;
      return {mode:"claim",claimId:hc?q.claim:null,docId:null,
              status:hc?null:"URL claim '"+q.claim+"' — 실측 무 (honest-gap \u00a76.2)"};
    }
    if(q.doc!=null&&q.doc!==""){
      var hd=cs.find(function(c){return c&&c.doc_id===q.doc;})||null;
      return {mode:"doc",claimId:hd?hd.claim_id:null,docId:hd?q.doc:null,
              status:hd?null:"URL doc '"+q.doc+"' — 연결 claim 실측 무 (honest-gap \u00a76.2)"};
    }
    return {mode:"default",claimId:cs.length?cs[0].claim_id:null,docId:null,status:null};
  }
  return {MODALITIES:MODALITIES,SOURCE_TYPE_TOKENS:SOURCE_TYPE_TOKENS,
          COUNTER_LABEL:COUNTER_LABEL,
          TRAIL_EXTRACTION_FIELDS:TRAIL_EXTRACTION_FIELDS,
          DOCUMENT_META_FIELDS:DOCUMENT_META_FIELDS,TIME_FIELDS:TIME_FIELDS,
          sourceType:sourceType,pick:pick,fmtTs:fmtTs,joinChronicle:joinChronicle,
          timeRow:timeRow,claimCard:claimCard,filterByModality:filterByModality,
          trailSteps:trailSteps,citation:citation,independence:independence,
          counterCards:counterCards,toolbar:toolbar,legend:legend,bootPlan:bootPlan};
})();
"""


def _pure_js() -> str:
    """wire 계약 상수 tuples 를 JS 배열로 주입 (Python/JS 단일 진화)."""
    return (WITNESS_PURE_JS
            .replace("__MODALITIES__", json.dumps(list(MODALITIES)))
            .replace("__SOURCE_TYPES__", json.dumps(list(SOURCE_TYPE_TOKENS)))
            .replace("__COUNTER_LABEL__", json.dumps(COUNTER_LABEL))
            .replace("__TRAIL_EXT__", json.dumps(list(TRAIL_EXTRACTION_FIELDS)))
            .replace("__DOC_META__", json.dumps(list(DOCUMENT_META_FIELDS)))
            .replace("__TIME_FIELDS__", json.dumps(list(TIME_FIELDS))))


# --- 렌더 + 로딩 IIFE (자기초기화; 페이지 전역 $·esc·empty 만 사용) --------------

WITNESS_INIT_JS = r"""(async function witxExtInit(){
  "use strict";
  function japi(p){return fetch(p).then(function(r){return r.json();});}
  var wclaims=[],wchron={},warchiveDocs={},wdedup=0,wselected=null,wmodality="",
      wcounter=WITX.counterCards([]),wCited=0;
  // modBadge·esc·empty·$ — 페이지(PAGE_WITNESSES) 전역 헬퍼 재사용(재정의 금지).
  function confTrio(conf){
    if(!conf) return '<span class="witx-none">confidence \ubbf8\uc874\uc7ac (honest-gap)</span>';
    return '<span class="cmini"><b>'+(+conf.value).toFixed(2)+'</b></span>'
      +'<span class="witx-none">ev '+(conf.evidence_count!=null?conf.evidence_count:'\u2014')
      +' \u00b7 \ub3c5\ub9bd '+(conf.independent_source_count!=null?conf.independent_source_count:'\u2014')+'</span>';
  }
  function renderChips(){
    var seen={},mods=[];
    wclaims.forEach(function(c){ if(c.modality&&!seen[c.modality]){seen[c.modality]=1;mods.push(c.modality);} });
    mods.sort();
    $('#witx-modality').innerHTML=mods.map(function(m){
      return '<span class="chip'+(m===wmodality?' on':'')+'" data-m="'+esc(m)+'"><span class="sw" style="background:var(--primary)"></span>'+esc(m)+'</span>';
    }).join('');
    document.querySelectorAll('#witx-modality .chip').forEach(function(ch){
      ch.onclick=function(){wmodality=(wmodality===ch.dataset.m?'':ch.dataset.m);renderChips();renderList();};
    });
  }
  function renderList(){
    var shown=WITX.filterByModality(wclaims,wmodality);
    $('#witx-claims').innerHTML=shown.map(function(c){
      return '<div class="claim-row'+(c.claim_id===wselected?' active':'')+'" data-c="'+esc(c.claim_id)+'">'
        +'<div class="q">'+esc(c.text)+'</div>'
        +'<div class="cid">'+esc(c.claim_id||'\u2014')+' \u00b7 '+esc(c.predicate||'\u2014')+'</div>'
        +'<div class="foot">'+modBadge(c.modality)+confTrio(c.confidence)+'</div></div>';
    }).join('')||empty('claim \uc5c6\uc74c','\ud45c\uc2dc\ud560 claim \uc2e4\uce21\uc774 \uc5c6\uc2b5\ub2c8\ub2e4.');
    document.querySelectorAll('#witx-claims .claim-row').forEach(function(r){
      r.onclick=function(){wSelect(r.dataset.c);};
    });
  }
  function renderBitemporal(c){
    var t=(c&&c.time)||{};
    var open=t.valid_to==null;
    var rows=[
      ['valid_from',WITX.fmtTs(t.valid_from)],
      ['valid_to',open?(t.valid_from!=null?'open (\ud604\uc7ac \uc720\ud6a8)':WITX.fmtTs(null)):WITX.fmtTs(t.valid_to)],
      ['tx_from',WITX.fmtTs(t.tx_from)],
      ['tx_to',t.tx_to==null?'open':WITX.fmtTs(t.tx_to)],
      ['time_precision',t.time_precision!=null?String(t.time_precision):'\u2014']
    ];
    var measured=t.valid_from!=null||t.valid_to!=null||t.tx_from!=null||t.tx_to!=null;
    $('#witx-bitemporal').innerHTML='<div class="witx-meta">'+rows.map(function(kv){
      return '<span>'+esc(kv[0])+' <b>'+esc(kv[1])+'</b></span>';
    }).join('')+'</div>'
      +(measured?'':'<div class="witx-none" style="margin-top:6px">chronicle assertions \uc870\uc778 \uc2e4\ucce4 \u2014 bitemporal \uba54\ud2b8 \ubb34 (\ud45c \u2014)</div>');
  }
  function renderIndependence(c,evDocs){
    var ind=WITX.independence(c&&c.confidence?c.confidence.basis:null,evDocs,wdedup);
    var h='';
    if(ind.basis) h+='<div class="indep"><b>\ub3c5\ub9bd\uc131 basis</b> \u2014 '+esc(ind.basis)+'</div>';
    h+='<div class="'+(ind.measured?'indep':'witx-none')+'" id="witx-indep-clusters">'
      +esc(ind.text)+'</div>';
    $('#witx-independence').innerHTML=h;
  }
  function trailOf(prov){return (prov&&prov.trail)||[];}
  function docIdOf(prov){
    var d=trailOf(prov).find(function(s){return s&&s.step==='document';});
    return d?d.doc_id:null;
  }
  function extOf(prov){return trailOf(prov).find(function(s){return s&&s.step==='extraction_record';})||null;}
  function renderEvidence(items,provs,docCache){
    var cited=0;
    var html=items.map(function(it,i){
      var prov=provs[i]||{};
      var docId=docIdOf(prov);
      var dwire=docId!=null?docCache[docId]:null;
      var doc0=(dwire&&dwire.documents&&dwire.documents[0])||{};
      var adoc=docId!=null?warchiveDocs[docId]:null;
      var st=WITX.sourceType(doc0.source_id!=null?doc0.source_id:(adoc?adoc.source_id:null));
      var ext=extOf(prov);
      var cit=ext?WITX.citation(dwire&&dwire.segments,ext.segment_id,ext.char_start,ext.char_end):null;
      if(cit) cited++;
      var quote=cit
        ?'<span class="span">"'+esc(cit.quote)+'"</span>'
        :(ext?'<div class="witx-none">원문 세그먼트 미실측 — offset 조인 불가 (honest-gap \u00a76.2)</div>'
              :'<div class="witx-none">\ucd94\ucd9c offset \uc5c6\uc74c \u2014 extraction_record \ubbf8\uc2e4\uce21 \u2192 \uc778\uc6a9 \ubd88\uac00 (honest-gap \u00a76.2)</div>');
      var tr='<div class="trail"><span>'+esc(String(it.evidence_id||'').slice(0,10))+'</span><span>\u203a</span>'
        +'<span>'+esc(docId||'\u2014')+'</span>'
        +(cit?'<span>\u00b7</span><span>char '+cit.char_start+'\u2013'+cit.char_end+'</span>':'')
        +(st?'<span>\u00b7</span><span>'+esc(st)+'</span>':'')+'</div>';
      return '<div class="ev support"><div class="top"><span class="rel">supports</span>'
        +'<span class="src">'+esc(it.source_doc||docId||'\u2014')+'</span></div>'
        +quote+tr+'</div>';
    }).join('');
    $('#witx-evidence').innerHTML=html||empty('\uadfc\uac70 \uc5c6\uc74c','\uc774 claim\uc758 supporting evidence \uc2e4\uce21\uc774 \uc5c6\uc2b5\ub2c8\ub2e4.');
    wCited=cited; return cited;
  }
  function renderTrail(provs,docCache){
    var src=provs.find(function(p){return p&&p.trail;});
    if(!src){$('#witx-trail').innerHTML=empty('trail \uc5c6\uc74c','provenance \uc2e4\uce21 \ubb34 (honest-gap \u00a76.2)');return;}
    var docId=docIdOf(src);
    var steps=WITX.trailSteps(src,docId!=null?docCache[docId]:null);
    $('#witx-trail').innerHTML=steps.map(function(s,idx){
      var fields=Object.keys(s.fields).map(function(k){
        return '<span>'+esc(k)+' <b>'+esc(s.fields[k])+'</b></span>';
      }).join('');
      var val=s.fields.doc_id||s.fields.segment_id||s.fields.claim_id||s.step;
      return '<div class="prov-step"><div class="prov-rail"><span class="node"></span>'
        +(idx<steps.length-1?'<span class="link"></span>':'')+'</div>'
        +'<div class="prov-main"><div class="lbl">'+esc(s.step)+'</div>'
        +'<div class="val mono">'+esc(val)+'</div><div class="fields">'+fields+'</div></div></div>';
    }).join('');
  }
  function renderToolbarCounterShell(c,provs,docCache){
    var src=provs.find(function(p){return p&&p.trail;});
    var docId=src?docIdOf(src):null;
    var tb=WITX.toolbar(docId!=null?docCache[docId]:null,
                        docId!=null?warchiveDocs[docId]:null,c.subject_id);
    var m=tb.meta;
    $('#witx-toolbar').innerHTML='<span class="dmeta mono">'
      +esc(tb.doc_id||'\uc6d0\ubb38 \ubbf8\uc120\ud0dd')
      +' \u00b7 parser <b>'+esc(m.parser_version!=null?m.parser_version:'\u2014')+'</b>'
      +' \u00b7 pub <b>'+esc(WITX.fmtTs(m.publication_time))+'</b>'
      +' \u00b7 rev <b>'+esc(WITX.fmtTs(m.revision_time))+'</b>'
      +(m.source_type?' \u00b7 '+esc(m.source_type):'')+'</span>'
      +'<div class="grow"></div>'
      +tb.links.map(function(l){return '<a class="btn" href="'+esc(l.href)+'">'+esc(l.label)+'</a>';}).join('');
  }
  function renderLegend(cited){
    var lg=WITX.legend(cited,wcounter);
    $('#witx-legend').innerHTML=lg.items.map(function(it){
      return '<span class="item"><span class="witx-sw '+esc(it.kind)+'"></span>'
        +esc(it.label)+' \u00b7 '+esc(it.note)+'</span>';
    }).join('');
  }
  function renderCounter(){
    var cc=wcounter;
    var body=cc.cards.map(function(x){
      return '<div class="ev contra"><div class="top"><span class="rel">'+esc(cc.cards.length?x.label:'')+'</span>'
        +'<span class="src">'+esc(x.subject_id||'\u2014')+'</span></div>'
        +'<div class="witx-none">hypotheses</div><ul class="witx-qlist">'
        +x.hypotheses.map(function(h){return '<li>'+esc(h)+'</li>';}).join('')+'</ul>'
        +'<div class="witx-none">negative_queries</div><ul class="witx-qlist">'
        +x.negative_queries.map(function(q){return '<li>'+esc(q)+'</li>';}).join('')+'</ul></div>';
    }).join('');
    $('#witx-counter-body').innerHTML=cc.measured
      ? body+'<div class="witx-none" style="margin-top:6px">'+esc(cc.note)+'</div>'
      : '<div class="witx-none" style="margin-top:8px">'+esc(cc.note)+'</div>';
  }
  // 필요한 doc_id 만 /api/archive?doc_ids= 로 채운다 (미실측은 null 로 봉인 —
  // 같은 문서를 매 렌더마다 다시 묻지 않게).
  async function ensureArchiveDocs(ids){
    var miss=ids.filter(function(d,i){
      return d!=null&&!(d in warchiveDocs)&&ids.indexOf(d)===i;
    });
    if(!miss.length) return;
    var r=await japi('/api/archive?limit='+miss.length+'&doc_ids='
                     +miss.map(encodeURIComponent).join(','));
    ((r&&r.normalized_documents)||[]).forEach(function(d){warchiveDocs[d.doc_id]=d;});
    miss.forEach(function(d){ if(!(d in warchiveDocs)) warchiveDocs[d]=null; });
  }
  async function wSelect(cid){
    wselected=cid; renderList();
    var c=wclaims.find(function(x){return x.claim_id===cid;})||{claim_id:cid};
    renderBitemporal(c);
    wcounter=WITX.counterCards([]); renderCounter();
    var ev=await japi('/api/evidence?claim='+encodeURIComponent(cid));
    var items=(ev&&ev.items)||[];
    await ensureArchiveDocs(items.map(function(it){return it.source_doc;}));
    renderIndependence(c,items.map(function(it){
      var ad=it.source_doc!=null?warchiveDocs[it.source_doc]:null;
      return {doc_id:it.source_doc,cluster_role:ad?ad.cluster_role:null};
    }));
    var provs=await Promise.all(items.map(function(it){
      return japi('/api/provenance?evidence='+encodeURIComponent(it.evidence_id));
    }));
    var docCache={},ids=[];
    provs.forEach(function(p){ var d=docIdOf(p); if(d!=null&&ids.indexOf(d)<0) ids.push(d); });
    await ensureArchiveDocs(ids);
    await Promise.all(ids.map(function(d){
      return japi('/api/document?doc='+encodeURIComponent(d)).then(function(w){docCache[d]=w;});
    }));
    var cited=renderEvidence(items,provs,docCache);
    renderTrail(provs,docCache);
    renderToolbarCounterShell(c,provs,docCache);
    renderLegend(cited);
  }
  var btn=document.querySelector('#witx-run-counter');
  if(btn) btn.onclick=async function(){
    var c=wclaims.find(function(x){return x.claim_id===wselected;});
    if(!c||c.subject_id==null){$('#witx-counter-body').innerHTML='<div class="witx-none">subject \ubbf8\uc815 \u2014 \ud6c4\ubcf4 \ubd88\uac00</div>';return;}
    btn.disabled=true;
    try{
      var r=await japi('/api/investigate?subject='+encodeURIComponent(c.subject_id));
      wcounter=WITX.counterCards(r&&r.counter_evidence);
      renderCounter();
      renderLegend(wCited);
    }catch(e){
      $('#witx-counter-body').innerHTML='<div class="witx-none err">\ud22c\uc790 \uc2e4\ud328: '+esc(String(e))+'</div>';
    }finally{ btn.disabled=false; }
  };
  // ?doc= 하이라이트: 기존 페이지의 전역 fetchDoc(docId, extStep) 경로를 재사용 —
  // ext 블록이 별도 마킹을 중복 생성하지 않는다. 함수 없으면 조용히 스킵(정직).
  async function docHighlight(docId){
    if(typeof fetchDoc!=='function'||!wselected) return;
    var ev=await japi('/api/evidence?claim='+encodeURIComponent(wselected));
    var items=(ev&&ev.items)||[];
    for(const it of items){
      var p=await japi('/api/provenance?evidence='+encodeURIComponent(it.evidence_id));
      if(docIdOf(p)===docId){ await fetchDoc(docId,extOf(p)); return; }
    }
  }
  function urlParams(){
    try{
      var u=new URLSearchParams(location.search);
      return {claim:u.get('claim')||'',doc:u.get('doc')||''};
    }catch(e){ return {claim:'',doc:''}; }
  }
  async function load(){
    try{
      var t=await japi('/api/table');
      var rows=await Promise.all(((t&&t.subjects)||[]).map(function(s){
        return japi('/api/subject_claims?subject='+encodeURIComponent(s.subject_id))
          .then(function(c){return {subject_id:s.subject_id,items:(c&&c.items)||[]};});
      }));
      // /api/archive 는 페이지네이션 응답이다 — 여기서 필요한 건 dedup 수뿐이고,
      // 문서 메타는 선택한 claim 이 참조하는 doc_id 만 뒤에서 채운다(전량 로드 금지).
      var pair=await Promise.all([japi('/api/chronicle'),japi('/api/archive?limit=1')]);
      wchron=WITX.joinChronicle(pair[0]&&pair[0].assertions);
      var arch=pair[1]||{};
      wdedup=arch.dedup_clusters!=null?arch.dedup_clusters:0;
      warchiveDocs={};
      wclaims=[];
      for(const grp of rows){
        for(const it of grp.items){
          var cw=await japi('/api/claim?claim='+encodeURIComponent(it.claim_id));
          var card=WITX.claimCard(it,cw,wchron[it.claim_id]);
          if(card.subject_id==null) card.subject_id=grp.subject_id;
          wclaims.push(card);
        }
      }
      renderChips(); renderList();
      var plan=WITX.bootPlan(wclaims,urlParams());
      $('#witx-status').textContent=plan.status
        ? plan.status
        : 'claims '+wclaims.length+' \u00b7 dup_clusters '+wdedup;
      if(plan.claimId!=null){
        await wSelect(plan.claimId);
        if(plan.mode==='doc'&&plan.docId!=null) await docHighlight(plan.docId);
      } else if(plan.mode==='default'&&wclaims.length){
        await wSelect(wclaims[0].claim_id);
      } else if(!wclaims.length){
        $('#witx-evidence').innerHTML=empty('claim \uc2e4\uce21 0','claims \ubb34 (honest-gap \u00a76.2)');
      }
    }catch(e){
      $('#witx-status').textContent='\ub85c\ub4dc \uc2e4\ud328: '+esc(String(e));
    }
  }
  await load();
})();
"""

PAGE_WITNESSES_EXT_JS = _pure_js() + "\n" + WITNESS_INIT_JS


def build() -> tuple[str, str]:
    """(본문 HTML 조각, <script> 안의 JS 블록) — 오케스트레이터 병합용."""
    return PAGE_WITNESSES_EXT_BODY, PAGE_WITNESSES_EXT_JS
