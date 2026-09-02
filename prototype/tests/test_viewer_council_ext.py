"""Council Chamber remaining-gaps 확장 (council_ext) — 조회 전용 블록 계약.

봉인 대상:
- export 형태 (body, js) + 신규 DOM id · 8역할 카탈로그.
- honest-gap: 목업 수치/임계 상수/모델 ID/timestamp/‘실시간’ 문구 금지,
  분모 0 audit 의 PASS 과장 금지, on-request non-persistent 주석.
- fetch 규율: /api/investigate 는 버튼 클릭 경로 1회만 (로드 시 자동 fetch 없음).
- Wave 1 wire: WIRE_KEYS ⊆ /api/investigate 실제 응답 키.
- 딥링크 URL 생성만: /witnesses?claim= · /table?subject= (+encodeURIComponent).
- 인라인 JS node --check 문법 가드 (viewer_aux 패턴).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import types

import pytest

from orc_citadel.curated_zone import CuratedZone
from orc_citadel.pipeline_runner import run_pipeline
from orc_citadel.viewer import Handler
from orc_citadel import council_ext as CX
from orc_citadel.viewer_pages import PAGE_COUNCIL

RICH_HTML = b"""<html><head>
<title>NVIDIA Conference Call</title>
<meta property="article:published_time" content="2026-08-01T14:00:00+00:00"/>
</head><body><article>
<h1>NVIDIA Sets Conference Call</h1>
<p>NVIDIA will host a conference call on Wednesday, August 26.</p>
<p>NVIDIA powers the data center and announces new accelerator products.</p>
</article></body></html>"""


def _rich_facade():
    from orc_citadel.api_facade import ApiFacade
    from orc_citadel.graph_service import GraphService

    z = CuratedZone(":memory:")
    z.initialize()
    run_pipeline([{"source_id": "test", "url": "https://e/n",
                   "doc_id": "doc-cncil00000000000000000001", "content": RICH_HTML}], z)
    g = GraphService()
    events = []
    for a in z.assertions():
        for node, uid in ((a["subject_id"], f"n-{a['assertion_id']}"),
                          (a["claim_id"], f"n2-{a['assertion_id']}")):
            events.append({"mutation_id": uid, "idempotency_key": uid,
                           "op": "create_node", "payload": {"id": node, "props": {}}})
        events.append({"mutation_id": f"e-{a['assertion_id']}",
                       "idempotency_key": f"e-{a['assertion_id']}",
                       "op": "create_edge",
                       "payload": {"type": "ABOUT", "from": a["subject_id"],
                                   "to": a["claim_id"], "props": {}}})
    g.apply(events)
    return ApiFacade(z, g)


BODY, JS = CX.build()


# --- export 형태 · DOM 앵커 ----------------------------------------------------

def test_build_returns_body_and_js_with_all_dom_ids():
    """build() → (str, str); 본문을 shell 로 감싼 형태가 아니라 생 조각이고 전 패널 id 존재."""
    assert isinstance(BODY, str) and isinstance(JS, str)
    assert "<!doctype" not in BODY.lower() and "<script" not in BODY.lower()
    for pid in ("council-ext", "ce-agents", "ce-agents-sub", "ce-loop", "ce-subclaims",
                "ce-retrieved", "ce-counter", "ce-statements", "ce-stop", "ce-audit",
                "ce-trace-btn"):
        assert f'id="{pid}"' in BODY, pid


def test_js_does_not_redefine_shared_helpers():
    """합병 계약: $·esc·empty·api·pill 은 viewer_pages 소유 — 재정의 금지."""
    for pat in (r"function\s+esc\s*\(", r"function\s+empty\s*\(",
                r"function\s+pill\s*\(", r"function\s+api\s*\(",
                r"const\s+\$\s*=", r"let\s+subjects\s*="):
        assert not re.search(pat, JS), pat


# --- 8역할 카탈로그 -------------------------------------------------------------

def test_agent_catalog_eight_roles():
    """AGENT_ROLES 8종이 JS CX_ROLES 에 순서대로 있고 executed/not-run 배지만 렌더."""
    assert len(CX.AGENT_ROLES) == 8
    for role in CX.AGENT_ROLES:
        assert role in JS, role
    assert JS.count("executed") >= 2 and "not-run" in JS
    # 실행/시간/모델 표기 금지 — 배지는 wire 필드 존재 여부만.
    assert "running" not in JS and "done<" not in JS


# --- honest-gap 금지 문자열 ------------------------------------------------------

def test_honest_gap_no_mockup_numbers_realtime_or_models():
    """목업 예시 수치·'실시간'·모델 ID·timestamp·임계 하드코딩 금지."""
    for banned in ("실시간", "realtime", "live", "opus", "sonnet", "haiku",
                   "new Date", "toISOString", "0.63", "$3.02", "0.90", "0.80",
                   "0.05", "subclaim 8"):
        assert banned not in JS, banned
        assert banned not in BODY, banned
    # on-request 주석은 양쪽 계약.
    assert "on-request, non-persistent" in JS
    assert "computed" in JS


def test_audit_zero_denominator_no_pass_inflation():
    """verifiable=0 → PASS 과장 금지 문구와 분모 가드가 JS 에 존재."""
    assert "검증가능 문장 없음" in JS
    assert re.search(r"v===0", JS)
    # linkage 는 실측 linked/verifiable 만 렌더 (ratio 상수 없음).
    assert "linkage_ratio" in JS


def test_stopping_uses_actual_inputs_only():
    """A/B/C/D 는 coverage·gaps·counter·iterations·terminated_by 실제값/텍스트만."""
    for field in ("r.coverage", "r.gaps", "r.counter_evidence", "r.iterations",
                  "r.terminated_by"):
        assert field in JS, field
    assert "임계 상수는 wire 미노출" in JS


# --- fetch 규율 · 루프 trace ------------------------------------------------------

def test_investigate_fetched_only_via_button():
    """/api/investigate 는 runTrace(클릭 핸들러) 안에서 1회; 로드 시 자동 호출 금지."""
    assert JS.count("/api/investigate") == 1
    assert "onclick=runTrace" in JS
    # 초기화 IIFE 말미에서 runTrace() 직접 호출 없음 (정의/핸들러 참조만).
    assert not re.search(r"^\s*runTrace\(\)\s*$", JS, flags=re.M)
    assert "setInterval" not in JS and "EventSource" not in JS


def test_loop_stepper_is_result_trace_order():
    """stepper 는 coverage→gaps→retrieved→counter_evidence→statements→audit 순서."""
    order = ["coverage", "gaps", "retrieved", "counter_evidence", "statements", "audit"]
    positions = [JS.index(f"'{k}'") for k in order]
    assert positions == sorted(positions)
    assert "결과 trace" in JS and "실행 로그 아님" in JS


# --- 딥링크 (URL 생성만) ----------------------------------------------------------

def test_deeplinks_encode_claim_and_subject():
    assert '"/witnesses?claim=' in JS and "encodeURIComponent(st.claim_ref)" in JS
    assert '"/table?subject=' in JS and "encodeURIComponent(subj)" in JS
    # 대상 페이지 bootstrap 파라미터만 사용 — 미지원 파라미터 추가 금지.
    assert not re.search(r"/witnesses\?[a-z]+=.*&", JS)
    assert "?claim=" in JS.replace('/witnesses?claim=', '?claim=')


# --- Wave 1 wire 계약 통합 --------------------------------------------------------

def test_wire_keys_present_in_investigate_response():
    """WIRE_KEYS 전부가 실제 /api/investigate 응답에 존재 (routed field 봉인)."""
    facade = _rich_facade()
    subj = facade.zone.assertions()[0]["subject_id"]
    self = types.SimpleNamespace(facade=facade)
    r = json.loads(Handler._api_investigate(self, {"subject": subj}))
    missing = [k for k in CX.WIRE_KEYS if k not in r]
    assert not missing, missing
    assert r["computed"] == "on-request, non-persistent"
    for sc in r["planned_subclaims"]:
        assert {"id", "text", "known", "gap_reason"} <= set(sc)
    for ce in r["counter_evidence"]:
        assert "hypotheses" in ce and "negative_queries" in ce
    at = r["audit_trace"]
    assert {"verifiable", "linked", "linkage_ratio", "blocked_statements"} <= set(at)


def test_merged_anchor_current_exists_in_page_council():
    """cxCurrent() 가 의존하는 `current`(선택 subject) 가 기존 PAGE_COUNCIL 에 실재."""
    assert re.search(r"let current\s*=", PAGE_COUNCIL)
    assert "/api/council?subject=" in PAGE_COUNCIL  # subject 선택 fetch 1회는 기존 소유


# --- JS 문법 가드 -----------------------------------------------------------------

@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_ext_js_parses_under_node_check():
    js = ("async function api(p){return (await fetch(p)).json()}\n"
          "function esc(s){return String(s==null?'':s)}\n"
          "function empty(t,d){return t+d}\n"
          "const $=s=>document.querySelector(s);\n"
          "let current=null;\n" + JS)
    r = subprocess.run(["node", "--check", "-"], input=js, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
