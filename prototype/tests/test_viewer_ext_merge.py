"""Wave 2 확장 병합 봉인 — viewer_pages 가 *_ext 모듈을 목업-충실 계약대로
주입했는지 + 병합 후에도 페이지 불변식(앵커 1회·JS 전역 재정의 없음·node parse)이
유지되는지 검증한다. 라이브 스모크 전의 정적 게이트.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from orc_citadel import viewer_pages as VP

PAGES = {
    "table": VP.PAGE_TABLE,
    "witnesses": VP.PAGE_WITNESSES,
    "council": VP.PAGE_COUNCIL,
    "gate": VP.PAGE_GATE,
    "watchtower": VP.PAGE_WATCHTOWER,
    "archive": VP.PAGE_ARCHIVE,
    "chronicle": VP.PAGE_CHRONICLE,
    "spire": VP.PAGE_SPIRE,
}


def test_ext_anchors_merged_into_pages():
    assert 'id="wte-frag"' in VP.PAGE_TABLE          # table_ext 본문
    assert "wteChron" in VP.PAGE_TABLE               # table_ext JS
    assert 'id="witx-block"' in VP.PAGE_WITNESSES    # witnesses_ext 본문
    assert "WITX.bootPlan" in VP.PAGE_WITNESSES      # witnesses_ext JS (bootstrap 포함)
    assert 'id="council-ext"' in VP.PAGE_COUNCIL     # council_ext 본문
    assert "URL_INVESTIGATE" in VP.PAGE_COUNCIL      # council_ext JS
    assert 'id="global-search-dd"' in VP.PAGE_GATE or "gsDropdown" in VP.PAGE_GATE
    assert 'id="gate-mini-watchtower"' in VP.PAGE_GATE
    assert 'id="wt-intake"' in VP.PAGE_WATCHTOWER
    assert 'id="ar-stacks"' in VP.PAGE_ARCHIVE
    assert 'id="ch-plane"' in VP.PAGE_CHRONICLE


def test_script_anchor_exactly_once_per_page():
    for name, page in PAGES.items():
        assert page.count("<script>") == 1, name
        assert page.count("</script>") == 1, name


def test_ext_js_does_not_redefine_page_helpers():
    # 확장이 esc/empty/api/$ 를 재정의하면 페이지 헬퍼가 붕괴한다 (closure 계약).
    for name in ("PAGE_TABLE_EXT_JS",):
        js = __import__("orc_citadel.table_ext", fromlist=[name]).__dict__[name]
        # table_ext 는 자체 api() 를 IIFE 로컬에서 정의하는 것이 허용됨(클로저 내).
        assert js.count("function esc(") == 0
        assert js.count("function empty(") == 0
    import orc_citadel.witnesses_ext as WX
    assert "function esc(" not in WX.PAGE_WITNESSES_EXT_JS
    assert "function empty(" not in WX.PAGE_WITNESSES_EXT_JS
    import orc_citadel.aux_ext as AX
    for js in (AX.SEARCH_JS, AX.GATE_EXT_JS, AX.WT_EXT_JS, AX.AR_EXT_JS, AX.CH_JS):
        assert "function esc(" not in js
        assert not re.search(r"(async )?function api\s*\(", js)


@pytest.mark.parametrize("name", sorted(PAGES))
@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_merged_page_js_parses(name, tmp_path):
    page = PAGES[name]
    js = re.findall(r"<script>(.*?)</script>", page, flags=re.S)[0]
    f = tmp_path / f"{name}.js"
    f.write_text(js, encoding="utf-8")
    r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
    assert r.returncode == 0, f"{name} 병합 JS 문법 오류:\n{r.stderr}"


def test_base_edge_label_no_nan_template():
    # viewer_pages:414 우선순위 버그 회귀 봉인 — y 연산은 괄호로 감싼 값만 문자열화.
    m = re.search(r"'<text class=\"edge-label\"[^;]+;", VP.PAGE_TABLE)
    assert m and '"/2-4"+"' not in m.group(0).replace(" ", ""), "edge-label NaN 회귀"


def test_spire_remains_honest_empty():
    # Spire 는 확장 없음 (alert 영속 부재) — 정직 빈 피드 문구가 유지돼야 한다.
    assert "not-fired" in VP.PAGE_SPIRE
