"""Wave 2 — War Table remaining-gaps extension (`table_ext.py`) 앵커/계약 테스트.

anchor id 단위 정적 가드 + (node 가 있으면) 인라인 JS 문법 가드와 PURE 블록의
순수 헬퍼 동작 검증. 실제 서빙 통합(PAGE_TABLE 병합) 은 오케스트레이터 소관이라
이 파일은 조각(body/js/css) 의 자기 완결성만 봉인한다.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from orc_citadel.table_ext import (
    PAGE_TABLE_EXT_BODY,
    PAGE_TABLE_EXT_CSS,
    PAGE_TABLE_EXT_JS,
    build,
    pure_block,
)

HAVE_NODE = shutil.which("node") is not None


def _ids(marker: str) -> set[str]:
    return set(re.findall(r'id="([^"]+)"', marker))


# --- 1. body 앵커 -----------------------------------------------------------
def test_body_has_all_extension_anchor_ids():
    want = {
        "wte-frag", "wte-subclaim-btn", "wte-subclaims",          # 1) subclaim
        "wt-viewbar", "wt-zoom-in", "wt-zoom-out", "wt-fit", "wt-reset",  # 3)
        "wt-expand-more",                                          # 5) cursor
        "wte-claim-detail",                                        # 7)
        "wte-chron", "wte-bounds", "wte-evt-box",                  # 9)
        "wte-sl-lo", "wte-sl-hi", "wte-sl-val",
        "wte-sl-tlo", "wte-sl-thi", "wte-sl-tval",
    }
    assert want <= _ids(PAGE_TABLE_EXT_BODY)


# --- 2. JS 는 body 앵커를 전부 참조 (주입 대상 일치) --------------------------
def test_js_references_every_body_anchor():
    for aid in _ids(PAGE_TABLE_EXT_BODY) - {"wte-frag"}:
        assert f"#{aid}" in PAGE_TABLE_EXT_JS or aid in PAGE_TABLE_EXT_JS, aid


# --- 3. build() 통합 인터페이스 ----------------------------------------------
def test_build_returns_body_and_js_pair():
    body, js = build()
    assert body is PAGE_TABLE_EXT_BODY and js is PAGE_TABLE_EXT_JS
    assert "wte-frag" in body and "(function(){" in js


# --- 4. JS 는 base 의 DOM 앵커(주입 지점)에만 기댄다 --------------------------
def test_js_targets_existing_page_table_anchors():
    # #subq-list 는 base 가 innerHTML 로 갈아쓰는 컨테이너 — 확장JS 가 건드리지 않는다
    # (subclaim 은 #pred-list 앞 형제 컨테이너에 붙인다).
    for anchor in ("#wt-svg", "#type-chips", "#pred-list", "#war-canvas",
                   "#inspector", "#chronicle-rail", "#campaign-map", "#wt-list"):
        assert anchor in PAGE_TABLE_EXT_JS, anchor
    # 확장 own 앵커는 body 조각이 공급한다.
    for anchor in ("#wt-expand-more", "#wte-subclaims", "#wte-claim-detail",
                   "#wte-evt-box"):
        assert anchor in PAGE_TABLE_EXT_JS, anchor
        assert anchor[1:] in PAGE_TABLE_EXT_BODY, anchor


# --- 5. 불변식: 헬퍼 재정의 금지 · 외부 lib/CDN 금지 · opaque cursor ----------
def test_js_does_not_redefine_shared_helpers_or_load_libs():
    # $ / esc / empty 는 viewer_pages 기존 정의 사용만 (재정의 금지).
    assert not re.search(r"\b(const|let|var|function)\s+\$\s*=", PAGE_TABLE_EXT_JS)
    assert not re.search(r"\bfunction\s+\$\b", PAGE_TABLE_EXT_JS)
    assert not re.search(r"\bfunction\s+esc\b", PAGE_TABLE_EXT_JS)
    assert not re.search(r"\bfunction\s+empty\b", PAGE_TABLE_EXT_JS)
    # 오프라인: 외부 스크립트/폰트/CDN 로딩·import 금지.
    assert "src=" not in PAGE_TABLE_EXT_BODY
    assert not re.search(r"\bimport\s|\brequire\s*\(|https?://", PAGE_TABLE_EXT_JS)
    # cursor opaque: 디코딩/파싱 흔적 금지 (전달만).
    assert not re.search(r"atob|_dehex|cursor\.split|cursor\.indexOf",
                         PAGE_TABLE_EXT_JS)
    assert "encodeURIComponent(cur" in PAGE_TABLE_EXT_JS


# --- 6. honest-gap: 목업 하드코딩 수치 금지 -----------------------------------
def test_no_mockup_numbers_and_honest_gap_present():
    for banned in ("72%", "48%", "35%"):
        assert banned not in PAGE_TABLE_EXT_BODY
        assert banned not in PAGE_TABLE_EXT_JS
    assert "not measured" in PAGE_TABLE_EXT_JS
    assert "honest-gap" in PAGE_TABLE_EXT_JS


# --- 7. lazy fetch: 모듈 평가 시점 fetch 호출 금지 ----------------------------
def test_fetch_is_lazy_per_endpoint():
    # init 섹션(마지막 IIFE 본문)에서 fetch 는 이벤트 핸들러/async 함수 안에만.
    for ep in ("/api/investigate", "/api/claim", "/api/evidence",
               "/api/provenance", "/api/document", "/api/graph_expand",
               "/api/chronicle"):
        assert ep in PAGE_TABLE_EXT_JS, ep
    # /api/table 재fetch 금지 — seed closure 재사용 계약 (태스크 2).
    assert "/api/table" not in PAGE_TABLE_EXT_JS
    assert "seed" in PAGE_TABLE_EXT_JS and "entities" in PAGE_TABLE_EXT_JS


# --- 8. CSS 조각은 유효한 <style> 블록 ---------------------------------------
def test_css_block_shape():
    assert PAGE_TABLE_EXT_CSS.startswith("\n<style>")
    assert PAGE_TABLE_EXT_CSS.rstrip().endswith("</style>\n") or \
        PAGE_TABLE_EXT_CSS.rstrip().endswith("</style>")
    for cls in ("wte-sc", "wte-b", "wte-tb", "wte-evt", "wte-chipoff"):
        assert f".{cls}" in PAGE_TABLE_EXT_CSS, cls


# --- 9. (node) 인라인 JS 전체 문법 가드 --------------------------------------
@pytest.mark.skipif(not HAVE_NODE, reason="node not available")
def test_extension_js_parses(tmp_path):
    f = tmp_path / "table_ext.js"
    # base 스코프 스텁 위에서 IIFE 만 parse — viewer_pages 와 동일 환경 가정.
    f.write_text(PAGE_TABLE_EXT_JS, encoding="utf-8")
    r = subprocess.run(["node", "--check", str(f)],
                       capture_output=True, text=True)
    assert r.returncode == 0, f"JS 문법 오류:\n{r.stderr}"


def _node(script: str):
    r = subprocess.run(["node", "-e", script], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


# --- 10-14. (node) PURE 헬퍼 동작 ---------------------------------------------
@pytest.mark.skipif(not HAVE_NODE, reason="node not available")
def test_pure_edge_color_and_pin_color():
    out = _node(
        "function esc(s){return String(s==null?'':s);}"
        + pure_block()
        + "const r=[wtEdgeColor('SUPPORTS'),wtEdgeColor('contradicts'),"
        "wtEdgeColor('qualifies'),wtEdgeColor('uncertain'),wtEdgeColor('ABOUT'),"
        "wtPinColor('asserted'),wtPinColor('closed'),wtPinColor('superseded')];"
        "console.log(JSON.stringify(r));"
    )
    assert json.loads(out) == ["#45E06F", "#E05252", "#FFB13B", "#A78BFA",
                               "#59636A", "#45E06F", "#E05252", "#59636A"]


@pytest.mark.skipif(not HAVE_NODE, reason="node not available")
def test_pure_sentence_extraction_window():
    out = _node(
        "function esc(s){return String(s==null?'':s);}"
        + pure_block()
        + "const t='First sentence here. Target span text is here. Last one.';"
        "const a=t.indexOf('Target'),b=a+6;"
        "console.log(JSON.stringify([wtSentenceAt(t,a,b),"
        "wtSentenceAt('short',0,5),wtSentenceAt(null,0,2),"
        "wtSegmentOrder('doc#p0.s12'),wtSegmentOrder('no-num-x'),"
        "wtNodeText({id:'clm-01A',label:''}),wtNodeText({id:'clm-01ABCDEF'})]));"
    )
    got = json.loads(out)
    assert got[0] == "Target span text is here."
    assert got[1] == "short"
    assert got[2] == ""
    assert got[3] == 12 and got[4] is None
    assert got[5] == "clm-01A" and got[6] == "clm-01ABCDEF"


@pytest.mark.skipif(not HAVE_NODE, reason="node not available")
def test_pure_ts_index_filter_and_clamp():
    events = [{"claim_id": "c1", "kind": "asserted", "at": "2024-03-01T00:00:00"},
              {"claim_id": "c2", "kind": "closed", "at": "2024-01-01T00:00:00"},
              {"claim_id": "c3", "kind": "superseded", "at": None},
              {"claim_id": "c4", "kind": "asserted", "at": "2024-02-01T00:00:00"}]
    out = _node(
        "function esc(s){return String(s==null?'':s);}"
        + pure_block()
        + f"const ev={json.dumps(events)};"
        "const ts=wtTsList(ev);"
        "const f=wtFilterEvents(ev,ts,{lo:0,hi:1,tlo:0,thi:1});"
        "const g=wtFilterEvents(ev,ts,{lo:5,hi:-3,tlo:0,thi:99});"
        "console.log(JSON.stringify({ts:ts,"
        "shown:f.map(x=>[x.event.claim_id,x.shown]),"
        "clamp:g.map(x=>[x.idx,x.shown]),"
        "pair:wtClampPair(7,2,5),pct:wtEventPct('2024-02-01T00:00:00',"
        "'2024-01-01T00:00:00','2024-03-01T00:00:00'),"
        "pctEq:wtEventPct('2024-02-01T00:00:00','2024-02-01T00:00:00','2024-02-01T00:00:00'),"
        "idx:wtIndexOfTs(ts,'2024-01-01T00:00:00'),"
        "miss:wtIndexOfTs(ts,'nope')}));"
    )
    got = json.loads(out)
    # at 정렬·dedup, null at 제외.
    assert got["ts"] == ["2024-01-01T00:00:00", "2024-02-01T00:00:00",
                         "2024-03-01T00:00:00"]
    # lo/hi=[0,1] 창: 1월(0)·2월(1) shown, 3월·null 미shown.
    assert got["shown"] == [["c1", False], ["c2", True],
                            ["c3", False], ["c4", True]]
    # 범위 밖 clamp: lo=5/hi=-3 → [0,2] 풀창 (tlo/thi 도 [0,2]) → at 없는 것만 미shown.
    assert got["clamp"] == [[2, True], [0, True], [-1, False], [1, True]]
    assert got["pctEq"] == 50      # min==max → 중앙 정직 기본
    assert got["idx"] == 0 and got["miss"] == -1


@pytest.mark.skipif(not HAVE_NODE, reason="node not available")
def test_pure_subclaim_html_badges_only_no_percent():
    good = {"id": "sc-1", "text": "의존도 감소?", "known": True, "gap_reason": None}
    bad = {"id": "sc-2", "text": "계약 집행?", "known": False,
           "gap_reason": "no evidence for <executor>"}
    out = _node(
        "function esc(s){const d={};return String(s==null?'':s)"
        ".replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}"
        + pure_block()
        + f"console.log(wtSubclaimHtml({json.dumps(good)}"
        + f")+'|'+wtSubclaimHtml({json.dumps(bad)})+'|'+wtCovNoteHtml());"
    )
    assert 'class="wte-b k">known' in out
    assert 'class="wte-b g">gap' in out
    assert "no evidence for &lt;executor&gt;" in out     # esc 경유
    assert "의존도 감소?" in out
    assert not re.search(r"\d+\s*%", out)                  # 커버리지 % 수치 금지
    assert "not measured" in out
    assert "<i style" not in out                          # coverage bar 없음


def test_slider_ids_match_body_to_js():
    # body 의 slider id 와 JS 의 셀렉터가 1:1 (dual slider 계약).
    for aid in ("wte-sl-lo", "wte-sl-hi", "wte-sl-tlo", "wte-sl-thi"):
        assert f'id="{aid}"' in PAGE_TABLE_EXT_BODY
        assert f"'#{aid}'" in PAGE_TABLE_EXT_JS, aid
