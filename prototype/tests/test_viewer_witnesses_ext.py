"""Hall of Witnesses remaining-gaps 프런트 블록 (witnesses_ext) — 순수 조립 + 앵커.

기존 3-column PAGE_WITNESSES 위에 덧붙이는 섹션: claim 카드(per-claim
confidence)·bitemporal join·독립성 근거·실 인용·반박 후보·trail 완전 전개·
toolbar 딥링크·legend. JS 순수 함수(WITX)는 node 로 실행해 객수를 봉인하고,
실 파이프라인 wire(/api/subject_claims·/api/claim·assertions)을 그대로 넣어
contract 를 확인한다. 목업 예시 수치가 코드에 침입하지 않는지도 정적 가드.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import types
from pathlib import Path

import pytest

from orc_citadel import witnesses_ext as W
from orc_citadel.curated_zone import CuratedZone
from orc_citadel.pipeline_runner import run_pipeline
from orc_citadel.viewer import Handler

HTML = b"""<html><head>
<title>NVIDIA Conference Call</title>
<meta property="article:published_time" content="2026-08-01T14:00:00+00:00"/>
</head><body><article>
<h1>NVIDIA Sets Conference Call</h1>
<p>NVIDIA will host a conference call on Wednesday, August 26.</p>
<p>NVIDIA powers the data center and announces new accelerator products.</p>
</article></body></html>"""

ANCHORS = (
    "witx-block", "witx-status", "witx-modality", "witx-claims",
    "witx-bitemporal", "witx-independence", "witx-evidence",
    "witx-counter", "witx-run-counter", "witx-counter-body",
    "witx-trail", "witx-toolbar", "witx-legend",
)


def _facade():
    from orc_citadel.api_facade import ApiFacade
    from orc_citadel.graph_service import GraphService

    z = CuratedZone(":memory:")
    z.initialize()
    run_pipeline([{"source_id": "official-nvidia", "url": "https://e/n",
                   "doc_id": "doc-witx000000000000000000001",
                   "content": HTML}], z)
    return ApiFacade(z, GraphService())


def _run_witx(tmp_path, script: str):
    """WITX 순수 블록 + script(node) 실행 → stdout JSON."""
    f = tmp_path / "witx.js"
    f.write_text(W._pure_js() + "\n" + script, encoding="utf-8")
    r = subprocess.run(["node", str(f)], capture_output=True, text=True)
    assert r.returncode == 0, f"node 오류:\n{r.stderr}"
    return json.loads(r.stdout.strip())


needs_node = pytest.mark.skipif(shutil.which("node") is None,
                                reason="node not available")


# --- 앵커 / 정적 가드 -----------------------------------------------------------

def test_build_returns_body_and_js():
    body, js = W.build()
    assert body == W.PAGE_WITNESSES_EXT_BODY and js == W.PAGE_WITNESSES_EXT_JS
    assert isinstance(body, str) and isinstance(js, str)


def test_body_has_all_extension_anchors():
    for a in ANCHORS:
        assert f'id="{a}"' in W.PAGE_WITNESSES_EXT_BODY, a


def test_js_uses_shared_helpers_without_redefining_them():
    js = W.PAGE_WITNESSES_EXT_JS
    # viewer_pages 헬퍼 재사용·재정의 금지 (esc/empty/$ 는 호출만).
    assert "esc(" in js and "empty(" in js
    assert "function esc(" not in js and "function empty(" not in js
    assert "const $=" not in js and "querySelectorAll" in js
    # merge 시 최상위 전역 충돌 회피: column-0 선언은 WITX 하나.
    tops = re.findall(r"^(?:var|let|const|function)\s+([A-Za-z_$][\w$]*)",
                      js, flags=re.M)
    assert tops == ["WITX"], tops


def test_no_subject_report_confidence_reuse_and_no_mockup_numbers():
    src = Path(W.__file__).read_text(encoding="utf-8")
    js = W.PAGE_WITNESSES_EXT_JS
    # subject 보고서 confidence 재사용 금지 → /api/report 를 fetch 하지 않는다.
    assert "/api/report" not in js
    # 목업(hall-of-witnesses.html) 예시 수치·id 침입 금지 — 정직 실측만.
    for banned in ("0.61", "0.78", "0.33", "claim-123", "claim-201",
                   "doc-2291", "doc-5540", "dc-77", "evd-456", "1180"):
        assert banned not in src, banned
    # 확정 반박 문구 금지 — 후보 라벨만.
    assert "CONTRADICTS" not in src and "반박 확정" not in src


def test_trail_wire_field_whitelist_excludes_unexposed_fields():
    # wire(api_facade.get_evidence_provenance er_step)가 노출하지 않는 필드는
    # 표시 금지 — 화이트리스트에 없어야 한다.
    for banned in ("model_id", "schema_version", "fetched_at",
                   "prompt_template_hash", "preprocess_code_version",
                   "published_at"):
        assert banned not in W.TRAIL_EXTRACTION_FIELDS
    # document_meta 역시 /api/document 컬럼 그대로.
    assert W.DOCUMENT_META_FIELDS == ("doc_id", "source_id", "url", "language",
                                      "publication_time", "parser_version")


# --- WITX 순수 함수 (node 실행) --------------------------------------------------

@needs_node
def test_claim_card_per_claim_confidence_and_sentence(tmp_path):
    row = {"claim_id": "clm-1", "predicate": "announces", "object_literal": "call",
           "modality": "fact", "subject_id": "ent-1"}
    claim = {"claim_id": "clm-1", "subject_id": "ent-1", "predicate": "announces",
             "modality": "fact", "surface_fragment": "NVIDIA announces call",
             "object_literal": "call",
             "confidence": {"value": 0.42, "evidence_count": 1,
                            "independent_source_count": 1, "basis": "지지 근거 1건"}}
    out = _run_witx(tmp_path, "console.log(JSON.stringify("
                  "WITX.claimCard(%s,%s,null)));" % (json.dumps(row), json.dumps(claim)))
    assert out["text"] == "NVIDIA announces call"          # surface_fragment 우선
    assert out["confidence"]["value"] == 0.42              # per-claim 봉투
    assert out["modality"] == "fact"
    assert out["time"]["valid_from"] is None               # chronicle 미조인 → 정직 null
    # /api/claim not_found 는 confidence null (임의 수치 생성 금지).
    nf = _run_witx(tmp_path, "console.log(JSON.stringify("
                   "WITX.claimCard(%s,{\"error\":\"not_found\"},null)));" % json.dumps(row))
    assert nf["confidence"] is None and nf["claim_id"] == "clm-1"


@needs_node
def test_modality_facet_filter(tmp_path):
    cards = [{"claim_id": "a", "modality": "fact"}, {"claim_id": "b", "modality": "opinion"},
             {"claim_id": "c", "modality": None}]
    script = ("var cs=%s;"
              "console.log(JSON.stringify([WITX.filterByModality(cs,'fact')"
              ".map(function(c){return c.claim_id;}),"
              "WITX.filterByModality(cs,'').length]));" % json.dumps(cards))
    both, alln = _run_witx(tmp_path, script)
    assert both == ["a"] and alln == 3


@needs_node
def test_chronicle_bitemporal_join(tmp_path):
    script = """
    var rows=[{assertion_id:"as-1",claim_id:"clm-1",valid_from:null,valid_to:null,
               tx_from:"2026-08-03T21:00:00",tx_to:null,time_precision:"unknown"},
              {assertion_id:"as-2",claim_id:"clm-2",valid_from:"2026-01-01T00:00:00",
               valid_to:"2026-02-01T00:00:00",tx_from:"2026-01-05T00:00:00",
               tx_to:"2026-03-01T00:00:00",time_precision:"day"}];
    var m=WITX.joinChronicle(rows);
    console.log(JSON.stringify([WITX.timeRow(m["clm-1"]),WITX.timeRow(m["clm-2"]),
                                Object.keys(m).length]));"""
    t1, t2, n = _run_witx(tmp_path, script)
    assert n == 2
    assert t1["tx_from"] == "2026-08-03T21:00:00" and t1["valid_to"] is None
    assert t2["valid_to"] == "2026-02-01T00:00:00" and t2["time_precision"] == "day"


@needs_node
def test_trail_steps_wire_fields_only(tmp_path):
    script = """
    var prov={trail:[
      {step:"claim",claim_id:"clm-1",predicate:"announces",ontology_version:"v1"},
      {step:"extraction_record",extraction_id:"ex-1",segment_id:"doc-1#p2",
       char_start:3,char_end:9,content_hash:"sha256:aa",
       model_id:"seer-v3",schema_version:"v0.4",fetched_at:"2026-08-01"},
      {step:"document",doc_id:"doc-1"}]};
    var doc={documents:[{doc_id:"doc-1",source_id:"official-nvidia",
      url:"https://e/n",title:"T",language:"en",publication_time:"2026-08-01",
      parser_version:"html2md-4",char_len:99}]};
    console.log(JSON.stringify(WITX.trailSteps(prov,doc)));"""
    steps = _run_witx(tmp_path, script)
    kinds = [s["step"] for s in steps]
    assert kinds == ["claim", "extraction_record", "document", "document_meta"]
    ext = steps[1]["fields"]
    assert set(ext) == {"extraction_id", "segment_id", "char_start", "char_end",
                        "content_hash"}                      # model_id 등 미노출
    meta = steps[3]["fields"]
    assert "title" not in meta and "char_len" not in meta    # DOCUMENT_META_FIELDS 뿐
    assert meta["source_type"] == "official"                 # source_id 접두사
    assert _run_witx(tmp_path, "console.log(JSON.stringify("
                   "WITX.sourceType('weird-x')))") == "source"


@needs_node
def test_citation_char_span_excerpt(tmp_path):
    script = """
    var segs=[{segment_id:"doc-1#p0.s1",ord:1,text:"0123456789"},
              {segment_id:"doc-1#p0.s2",ord:2,text:"abcdefghij"}];
    console.log(JSON.stringify([
      WITX.citation(segs,"doc-1#p2",3,9),
      WITX.citation(segs,"doc-1#p9",0,1),
      WITX.citation(segs,null,0,1),
      WITX.citation([],  "doc-1#p1",0,1)]));"""
    hit, miss_ord, miss_ext, no_segs = _run_witx(tmp_path, script)
    assert hit["quote"] == "defghi" and hit["ord"] == 2      # slice(3,9)·마지막 숫자→ord
    assert hit["char_start"] == 3 and hit["char_end"] == 9
    assert miss_ord is None and miss_ext is None and no_segs is None


@needs_node
def test_independence_honest_zero_and_cluster_members(tmp_path):
    script = """
    console.log(JSON.stringify([
      WITX.independence("지지 근거 2건 (독립 출처 2건), 반박 근거 0건",
                        [{doc_id:"doc-1"}], 0),
      WITX.independence(null,
        [{doc_id:"doc-1",cluster_role:"root"},{doc_id:"doc-2",cluster_role:"derived"}], 3),
      WITX.independence(null,[{doc_id:"doc-9"}], 2)]));"""
    zero, roles, unmapped = _run_witx(tmp_path, script)
    assert zero["measured"] is False and zero["clusters"] == 0
    assert "실측 0" in zero["text"] and "honest-gap" in zero["text"]
    assert zero["basis"] == "지지 근거 2건 (독립 출처 2건), 반박 근거 0건"
    assert roles["measured"] is True and "doc-1→root" in roles["text"]
    assert "dup_clusters 3" in roles["text"]
    assert "미매핑" in unmapped["text"]


@needs_node
def test_counter_cards_candidate_label_only(tmp_path):
    script = """
    var arr=[{subject_id:"ent-1",id:"sc-1",hypotheses:["H not true"],
              negative_queries:["ent-1 denied announces"],
              contradiction_candidates:[{conflict_type:"x"}]}];
    console.log(JSON.stringify([WITX.counterCards(arr),WITX.counterCards([]),
                                WITX.counterCards(null)]));"""
    hit, empty, nul = _run_witx(tmp_path, script)
    assert hit["measured"] is True and hit["cards"][0]["label"] == "결정적 후보"
    assert hit["cards"][0]["hypotheses"] == ["H not true"]
    assert hit["cards"][0]["negative_queries"] == ["ent-1 denied announces"]
    # 확정 반박 승격 금지 — wire 의 contradiction_candidates 는 그대로 삼지 않는다.
    assert "contradiction_candidates" not in json.dumps(hit, ensure_ascii=False)
    assert "CONTRADICTS" not in json.dumps(hit, ensure_ascii=False)
    assert empty["measured"] is False and empty["cards"] == []
    assert nul["cards"] == []


@needs_node
def test_toolbar_deeplinks_and_revision_join(tmp_path):
    script = """
    var doc={doc_id:"doc-1",documents:[{doc_id:"doc-1",source_id:"press-x",
      url:"u",language:"en",publication_time:"2026-08-01T00:00:00",
      parser_version:"p1"}]};
    var arch={revision_time:"2026-08-02T00:00:00"};
    console.log(JSON.stringify([WITX.toolbar(doc,arch,"ent/1"),
                                WITX.toolbar(null,null,null)]));"""
    tb, none = _run_witx(tmp_path, script)
    assert tb["meta"]["parser_version"] == "p1"
    assert tb["meta"]["revision_time"] == "2026-08-02T00:00:00"   # archive 조인
    assert tb["meta"]["source_type"] == "press"
    hrefs = [l["href"] for l in tb["links"]]
    assert hrefs == ["/archive?doc=doc-1", "/table?subject=ent%2F1"]
    assert none["doc_id"] is None and none["meta"]["parser_version"] is None
    assert none["links"][0]["href"] == "/archive?doc="            # 미선택 정직


@needs_node
def test_legend_candidate_span_zero_from_data(tmp_path):
    script = """
    console.log(JSON.stringify([WITX.legend(2,WITX.counterCards([])),
      WITX.legend(0,{cards:[{subject_id:"s"}],measured:false,note:""})]));"""
    lg0, lg1 = _run_witx(tmp_path, script)
    kinds = [i["kind"] for i in lg0["items"]]
    assert kinds == ["supports", "candidate"]
    assert "인용 실측 2건" in lg0["items"][0]["note"]
    assert "실측 0" in lg0["items"][1]["note"]      # 후보 span 연결 실측 0 주석
    assert "인용 실측 0건" in lg1["items"][0]["note"]


def test_ext_js_parses_with_node(tmp_path):
    if shutil.which("node") is None:
        pytest.skip("node not available")
    f = tmp_path / "ext.js"
    f.write_text(W.PAGE_WITNESSES_EXT_JS, encoding="utf-8")
    r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# --- 실 wire → WITX 계약 ----------------------------------------------------------

@needs_node
def test_real_wire_flows_through_claim_card(tmp_path):
    """run_pipeline 실 wire(subject_claims·claim·assertions)를 그대로 node 에 넣어
    카드가 실측 봉투만 소비하는지 확인 (키 드림 = Wave 1 계약)."""
    facade = _facade()
    self = types.SimpleNamespace(facade=facade)
    subj = sorted({r["subject_id"] for r in facade.zone.claims()})[0]
    claims = json.loads(Handler._api_subject_claims(self, {"subject": subj}))
    assert claims["items"], "실 파이프라인에 claim 이 있어야 한다"
    claim = json.loads(Handler._api_claim(
        self, {"claim": claims["items"][0]["claim_id"]}))
    chron = {"assertions": json.loads(json.dumps(
        facade.zone.assertions(), default=str))}  # /api/chronicle.assertions 동일 행
    script = ("console.log(JSON.stringify((function(){"
              "var m=WITX.joinChronicle(%s.assertions);"
              "var c=WITX.claimCard(%s,%s,m[%s]);"
              "return [c.confidence&&c.confidence.value,c.time.tx_from!=null,"
              "c.claim_id];})()));"
              % (json.dumps(chron), json.dumps(claims["items"][0]),
                 json.dumps(claim, default=str),
                 json.dumps(claims["items"][0]["claim_id"])))
    value, has_tx, cid = _run_witx(tmp_path, script)
    assert cid == claims["items"][0]["claim_id"]
    assert has_tx is True                              # assertions tx_from 실측
    if claim.get("confidence"):
        assert value == claim["confidence"]["value"]   # 재계산 아닌 wire 그대로
    else:
        assert value is None


# --- URL bootstrap (?claim=·?doc=) 순수 로직 -----------------------------------

@needs_node
def test_bootplan_claim_match_and_honest_miss(tmp_path):
    script = """
    var cs=[{claim_id:"clm-1",doc_id:"doc-a"},{claim_id:"clm-2",doc_id:"doc-b"}];
    console.log(JSON.stringify([
      WITX.bootPlan(cs,{claim:"clm-2",doc:""}),
      WITX.bootPlan(cs,{claim:"clm-404",doc:""}),
      WITX.bootPlan(cs,{claim:"",doc:""}),
      WITX.bootPlan([],{claim:"clm-1",doc:""})]));"""
    hit, miss, default, noCards = _run_witx(tmp_path, script)
    assert hit["mode"] == "claim" and hit["claimId"] == "clm-2" and hit["status"] is None
    # 불일치: 선택 없음 + 정직 문구(목업 값 아님 — URL 파라미터만 반영).
    assert miss["claimId"] is None and "clm-404" in miss["status"]
    assert "honest-gap" in miss["status"]
    assert default == {"mode": "default", "claimId": "clm-1",
                       "docId": None, "status": None}   # 파라미터 없으면 첫 카드
    assert noCards["claimId"] is None and "실측 무" in noCards["status"]


@needs_node
def test_bootplan_doc_maps_to_owning_claim(tmp_path):
    script = """
    var cs=[{claim_id:"clm-1",doc_id:"doc-a"},{claim_id:"clm-2",doc_id:"doc-b"}];
    console.log(JSON.stringify([
      WITX.bootPlan(cs,{claim:"",doc:"doc-b"}),
      WITX.bootPlan(cs,{claim:"",doc:"doc-404"}),
      WITX.bootPlan(cs,{claim:"clm-1",doc:"doc-b"})]));"""
    hit, miss, prio = _run_witx(tmp_path, script)
    assert hit["mode"] == "doc" and hit["claimId"] == "clm-2" and hit["docId"] == "doc-b"
    assert hit["status"] is None
    assert miss["claimId"] is None and miss["docId"] is None
    assert "doc-404" in miss["status"] and "honest-gap" in miss["status"]
    # claim 파라미터가 doc 보다 우선 (중복 지정 시 결정적).
    assert prio["mode"] == "claim" and prio["claimId"] == "clm-1" and prio["docId"] is None


@needs_node
def test_bootplan_doc_id_flows_from_claim_wire(tmp_path):
    """claimCard 는 /api/claim 병합 응답의 doc_id 를 카드에 싣는다 — bootPlan 의
    doc 조인 축이 실 wire 키에서 오는지 봉인."""
    row = {"claim_id": "clm-1", "predicate": "announces", "modality": "fact"}
    cw = {"claim_id": "clm-1", "doc_id": "doc-w1", "confidence": None}
    script = ("console.log(JSON.stringify(WITX.bootPlan("
              "[WITX.claimCard(%s,%s,null)],{claim:'',doc:'doc-w1'})));"
              % (json.dumps(row), json.dumps(cw)))
    plan = _run_witx(tmp_path, script)
    assert plan["mode"] == "doc" and plan["claimId"] == "clm-1"
    assert plan["docId"] == "doc-w1" and plan["status"] is None


def test_init_js_bootstrap_wiring():
    js = W.PAGE_WITNESSES_EXT_JS
    assert "URLSearchParams" in js and "location.search" in js
    assert "WITX.bootPlan" in js
    # doc 하이라이트는 페이지 전역 fetchDoc 재사용 — 중복 마킹 경로 금지.
    assert "typeof fetchDoc" in js and "fetchDoc(docId" in js
