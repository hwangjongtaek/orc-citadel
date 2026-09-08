"""frontend 산출물 회귀 — `frontend/dist/` 가 커밋된 상태와 계약을 지키는지.

frontend 는 theme-citadel·목업과 같은 정책이다: node·Vite 는 저작 도구일 뿐이고
생성물(dist)을 커밋한다. 이 테스트는 node 없이 산출물 텍스트만 검사한다.

뷰어는 dist 를 `/app/*` 로 서빙한다 (specs/ui-overhaul-astryx TS-1) —
canonical 라우트 전환은 공간 이관 커밋에서 일어나고, 여기서는 서빙 계약만 가드.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DIST = REPO / "frontend" / "dist"

# 이관된 엔트리 목록 — 공간을 이관할 때마다 여기 추가한다.
ENTRIES = ["gate"]


@pytest.fixture(scope="module")
def pages() -> dict[str, str]:
    if not DIST.exists():  # pragma: no cover - 빌드 누락 시에만
        pytest.fail(f"{DIST} 없음 — frontend 에서 `npm run build` 후 커밋한다.")
    return {e: (DIST / f"{e}.html").read_text(encoding="utf-8") for e in ENTRIES}


@pytest.mark.parametrize("entry", ENTRIES)
def test_entry_html_contract(pages: dict[str, str], entry: str) -> None:
    html = pages[entry]
    assert html.lstrip().lower().startswith("<!doctype html>")
    # 스코프 루트는 <html> (목업과 동일한 함정 방지)
    assert 'data-astryx-theme="citadel"' in html
    # 자산은 전부 뷰어가 서빙하는 절대 경로 — /assets/*(공용) 또는 /app/*(번들)
    for sheet in ("/assets/reset.css", "/assets/astryx.css",
                  "/assets/theme-citadel.css", "/assets/fonts/fonts.css"):
        assert sheet in html, sheet
    assert "/assets/img/favicon-32.png" in html


@pytest.mark.parametrize("entry", ENTRIES)
def test_bundle_files_exist_and_are_local(pages: dict[str, str], entry: str) -> None:
    """엔트리가 참조하는 번들이 dist 에 실재하고, 외부 오리진 참조가 없다."""
    html = pages[entry]
    refs = re.findall(r'(?:src|href)="(/app/[^"]+)"', html)
    assert refs, f"{entry}: 번들 참조가 없다"
    for ref in refs:
        assert (DIST / ref[len("/app/"):]).is_file(), ref
    assert "http://" not in html and "https://" not in html, "외부 오리진 금지"


def test_bundles_have_no_external_origins() -> None:
    """번들 JS 도 외부 리소스를 로드하지 않는다 (CDN·원격 금지).

    React 가 에러 메시지에 넣는 문서 링크(react.dev)는 네트워크 요청이 아니라
    문자열이므로 허용한다.
    """
    # 네트워크 요청이 아닌 상수 문자열: React 에러 문서 링크 · XML 네임스페이스 URI.
    allowed = re.compile(r"https?://(react\.dev|www\.w3\.org)/[^\"'` )\\]*")
    for js in DIST.rglob("*.js"):
        text = js.read_text(encoding="utf-8", errors="ignore")
        leftover = allowed.sub("", text)
        bad = re.findall(r"https?://\S{0,60}", leftover)
        assert not bad, f"{js.name}: {bad[:3]}"


def test_gate_bundle_wires_search_palette() -> None:
    """⌘K 통합 검색 팔레트 (TS-3) — 번들이 /api/search 를 소비하고
    딥링크 3종(table?subject·witnesses?claim·archive?doc)을 만든다."""
    js = (DIST / "js" / "gate.js").read_text(encoding="utf-8", errors="ignore")
    assert "/api/search" in js
    for marker in ("/table?subject=", "/witnesses?claim=", "/archive?doc="):
        assert marker in js, marker


def test_root_route_serves_frontend_gate() -> None:
    """이관 1호 — canonical `/` 는 dist gate 를 서빙한다 (TS-1 라우트 전환)."""
    from orc_citadel.viewer_static import default_roots
    from test_viewer_static import _get

    status, headers, body = _get("/", default_roots())
    assert status == 200
    assert headers["Content-Type"].startswith("text/html")
    assert b"/app/js/gate.js" in body, "인라인 Gate 가 아니라 frontend dist 여야 한다"


def test_root_falls_back_to_inline_without_dist() -> None:
    """dist 가 없으면 인라인 Gate 로 폴백 — 롤백 안전 경로."""
    import dataclasses

    from orc_citadel.viewer_static import default_roots
    from test_viewer_static import _get

    roots = dataclasses.replace(default_roots(), app=None)
    status, headers, body = _get("/", roots)
    assert status == 200
    assert b"/app/js/gate.js" not in body


def test_legacy_gate_route_kept() -> None:
    """이관 기간 롤백 경로 — `/legacy/gate` 가 구 인라인 Gate 를 서빙한다."""
    from test_viewer_static import _get

    status, headers, body = _get("/legacy/gate")
    assert status == 200
    assert headers["Content-Type"].startswith("text/html")
    assert body.lower().startswith(b"<!doctype html>")


def test_viewer_serves_app_dist() -> None:
    """뷰어 `/app/*` 서빙 계약 — 200 + MIME, 경로 탈출 차단, 미지정 404."""
    from orc_citadel.viewer_static import app_root, StaticRoots, default_roots

    roots = default_roots()
    assert roots is not None and roots.app is not None
    ok = roots.resolve("/app/gate.html")
    assert ok is not None and ok[1].startswith("text/html")
    js = re.findall(r'src="(/app/[^"]+\.js)"',
                    (DIST / "gate.html").read_text(encoding="utf-8"))
    assert js and roots.resolve(js[0]) is not None
    assert roots.resolve("/app/../viewer.py") is None
    assert roots.resolve("/app/missing.html") is None
    assert app_root() == DIST
