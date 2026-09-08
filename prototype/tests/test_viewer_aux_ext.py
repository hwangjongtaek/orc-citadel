"""Wave 2 보조 페이지 프런트 블록 (aux_ext) — export 앵커/함수 존재 + JS 문법 가드.

계약: local://gaps-contract.md Wave 2 — viewer_pages 수정 금지, 본문 조각+JS 문자열
export. 각 테스트는 병합 후 shell() 안에 들어갈 조각의 계약(앵커 id·API 경로·
honest-gap 문구·중첩 헬퍼 재정의 금지)만 봉인한다 (정적 가드 — JS 는 실행하지 않음).
"""
from __future__ import annotations

import re
import shutil
import subprocess

import pytest

from orc_citadel import aux_ext as AX

EXPORTS = ("SEARCH_JS", "GATE_EXT_BODY", "GATE_EXT_JS", "WT_EXT_BODY", "WT_EXT_JS",
           "AR_EXT_BODY", "AR_EXT_JS", "CH_BODY", "CH_JS")


def test_exports_present_and_str():
    for name in EXPORTS:
        v = getattr(AX, name)
        assert isinstance(v, str) and v.strip(), f"{name} 누락/빈 문자열"


def test_build_returns_bodies_scripts():
    bodies, scripts = AX.build()
    assert bodies == (AX.GATE_EXT_BODY, AX.WT_EXT_BODY, AX.AR_EXT_BODY, AX.CH_BODY)
    assert scripts == (AX.SEARCH_JS, AX.GATE_EXT_JS, AX.WT_EXT_JS,
                       AX.AR_EXT_JS, AX.CH_JS)


def test_js_does_not_redefine_shared_helpers():
    """viewer_pages 의 api·esc·empty·$ 재정의 금지 (contract: 사용만)."""
    for name in ("SEARCH_JS", "GATE_EXT_JS", "WT_EXT_JS", "AR_EXT_JS", "CH_JS"):
        js = getattr(AX, name)
        assert "function esc(" not in js, name
        assert "function empty(" not in js, name
        assert not re.search(r"(async )?function api\s*\(", js), name
        assert "const $=" not in js and "const $ =" not in js, name


# --- 1. 공유 검색 ---------------------------------------------------------------

def test_search_js_contract():
    js = AX.SEARCH_JS
    assert "/api/search?q=" in js
    # 'BM25' 가 아니라 'text contains' 문구 (honest-gap).
    assert "text contains" in js
    assert "BM25 아님" in js
    # 딥링크 3 종.
    assert "/table?subject=" in js
    assert "/witnesses?claim=" in js
    assert "/archive?doc=" in js
    # fixed 드롭다운 — body 임시 컨테이너 없이 생성.
    assert "position:fixed" in js
    assert "document.body.appendChild" in js
    # enter 핸들러 + 자기초기화 IIFE.
    assert "e.key==='Enter'" in js
    assert js.rstrip().endswith("})();")


# --- 2. Gate mini-watchtower -----------------------------------------------------

def test_gate_ext_anchors():
    assert 'id="gate-mini-watchtower"' in AX.GATE_EXT_BODY
    js = AX.GATE_EXT_JS
    assert "/api/table" in js and "/api/watchtower" in js
    assert "quarantined" in js
    assert "last_fetch_by_source" in js
    assert js.rstrip().endswith("})();")


# --- 3. Watchtower intake 시계열 + sources 확장 ----------------------------------

def test_watchtower_ext_anchors():
    body = AX.WT_EXT_BODY
    assert 'id="wt-intake"' in body and 'id="wt-sources-ext"' in body
    js = AX.WT_EXT_JS
    # 인라인 SVG 막대 — 외부 lib 금지.
    assert "<svg" in js and "createElement('script')" not in js
    assert "arrivals_per_hour" in js
    assert "measured" in js and "empty(" in js  # measured=False → 정직 빈
    assert "last_fetch" in js and "governance" in js
    assert "http_status" in js and "robots_allowed" in js


def test_watchtower_bar_path_is_index_safe():
    """barPath(max,bucket,i) — 단일 버킷 인덱스 계산을 배열 길이에 의존시키지 않는다."""
    js = AX.WT_EXT_JS
    m = re.search(r"function wtBarPath\(max,b,i\)", js)
    assert m, "wtBarPath 시그니처 (max,b,i) 봉인"
    assert "b.length" not in js.split("function wtBarPath")[1].split("}")[0]


# --- 4. Archive facet·Stacks·contains·Codex·?doc= --------------------------------

def test_archive_ext_anchors():
    body = AX.AR_EXT_BODY
    for anchor in ('id="ar-q"', 'id="ar-facets"', 'id="ar-table"',
                   'id="ar-stacks"', 'id="ar-kinds"'):
        assert anchor in body, anchor
    assert "text contains" in body and "BM25" in body  # 정직 표기


def test_archive_ext_js_facets_and_deeplink():
    js = AX.AR_EXT_JS
    assert "cluster_role" in js and "language" in js
    assert "publication_time" in js  # 정렬 축
    assert "segment_kinds" in js and "url_groups" in js
    # contains 검색은 서버 축 — /api/archive?q= (전량 join 폐기: 10만+ 문서를
    # 클라이언트로 내려 필터링하던 것이 /archive 를 멈추게 했다).
    assert "/api/archive" in js and "A.set({q:v" in js
    assert "/api/search?q=" not in js
    # 확장은 자기 fetch 를 하지 않고 본문 페이지 응답(window.ARCHIVE)을 공유한다.
    assert "window.ARCHIVE" in js and "A.on(" in js
    # Codex 확장: 메타 + /witnesses?doc= 딥링크 (래퍼).
    assert "/witnesses?doc=" in js
    assert "typeof window.codex==='function'" in js
    # /archive?doc= URL bootstrap.
    assert "URLSearchParams(location.search)" in js
    assert "p.get('doc')" in js


def test_archive_page_paginates_and_delegates_clicks():
    """본문 페이지 계약 — 페이저 앵커·서버 파라미터·행 클릭 위임(핸들러 N개 금지)."""
    from orc_citadel import viewer_pages as VP

    page = VP.PAGE_ARCHIVE
    assert 'id="docs-pager"' in page and 'id="pg-prev"' in page and 'id="pg-next"' in page
    assert "'/api/archive?'+archiveQs()" in page      # 상태 → 쿼리 파라미터
    assert "state:{limit:50,offset:0" in page          # 기본 한 페이지
    # 행 클릭은 위임 1회 — 행마다 onclick 을 다는 옛 경로가 돌아오면 안 된다.
    assert "#docs tr[data-doc]" not in page
    assert "addEventListener('click'" in page


# --- 5. Chronicle dual slider·preset·rail·as-of 상세 ------------------------------

def test_chronicle_ext_anchors():
    body = AX.CH_BODY
    for anchor in ('id="ch-plane"', 'id="ch-presets"',
                   'id="ch-events-rail"', 'id="ch-assertion-detail"'):
        assert anchor in body, anchor


def test_chronicle_js_bounds_slider_preset_rail():
    js = AX.CH_JS
    assert "/api/chronicle" in js and "bounds" in js
    # dual slider: valid·tx 두 축 × (a,b) 두 핸들.
    assert js.count("type=\"range\"") >= 1 and "ch-valid-a" in js and "ch-tx-b" in js
    # preset 질문 3 종 + 재료 없으면 비활성.
    assert js.count("enabled:") == 3
    assert "재료 없음 (비활성)" in js
    # events rail 3 종.
    for kind in ("asserted", "closed", "superseded"):
        assert kind in js
    # as-of assertion 상세.
    assert "ch-assertion-detail" in js and "supersedes_id" in js


# --- JS 문법 가드 (기존 test_viewer_aux 와 동일 패턴) -----------------------------

@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
@pytest.mark.parametrize("name", ["SEARCH_JS", "GATE_EXT_JS", "WT_EXT_JS",
                                  "AR_EXT_JS", "CH_JS"])
def test_js_blocks_parse_with_helpers(name, tmp_path):
    """병합 환경을 모사: 공유 헬퍼 스텁 + 페이지 JS 를 한 스크립트로 node --check."""
    prelude = ("async function api(p){return (await fetch(p)).json()}\n"
               "function esc(s){return String(s==null?'':s)}\n"
               "function empty(t,d){return '<div>'+t+d+'</div>'}\n"
               "const $=s=>document.querySelector(s);\n")
    f = tmp_path / f"{name}.js"
    f.write_text(prelude + getattr(AX, name), encoding="utf-8")
    r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
    assert r.returncode == 0, f"{name} JS 문법 오류:\n{r.stderr}"


def test_no_hardcoded_mockup_numbers():
    """honest-gap: 목업 예시 수치가 리터럴로 섞이지 않았는지 (id·배수 제외 3자리+ 숫자)."""
    blob = "".join(getattr(AX, n) for n in EXPORTS)
    # 허용: 좌표·픽셀 치수 (SVG/CSS). 검사 대상: HTML 텍스트 노드의 "N · " 형태 카운트.
    assert not re.search(r">\s*\d{3,}\s*(quarantine|docs|events)\b", blob)
