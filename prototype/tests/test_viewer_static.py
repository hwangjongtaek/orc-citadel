"""P2 viewer — 정적 자산 서빙 (`/assets/*`) 계약.

현재 뷰어는 미지정 경로를 전부 Gate HTML 200 으로 돌려준다 — `GET /assets/x.png`
이 PNG 가 아니라 HTML 을 준다는 뜻이고, 404 도 없다(갭 A1·A8).

자산은 리포에 이미 있는 것을 **복제하지 않고** 참조한다:
  img   docs/mockups/assets/          (히어로·초상·빈상태 19MB — 복제 금지)
  css   design-system/theme-citadel/dist/theme.css
  fonts design-system/fonts/dist/
컨테이너에는 `prototype/` 만 COPY 되므로 위 경로는 바인드 마운트로 주입한다.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from orc_citadel import viewer_static as vs


@pytest.fixture
def roots(tmp_path):
    """세 루트를 흉내낸 임시 트리."""
    img = tmp_path / "img"
    img.mkdir()
    (img / "gate-hero.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    (img / "empty-spire.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"1" * 16)

    ds = tmp_path / "ds"
    (ds / "theme-citadel" / "dist").mkdir(parents=True)
    (ds / "theme-citadel" / "dist" / "theme.css").write_text(":root{--x:1}", encoding="utf-8")
    (ds / "fonts" / "dist" / "files").mkdir(parents=True)
    (ds / "fonts" / "dist" / "fonts.css").write_text("@font-face{}", encoding="utf-8")
    (ds / "fonts" / "dist" / "files" / "inter-latin-400-normal.woff2").write_bytes(b"wOF2")

    return vs.StaticRoots(img=img, theme_css=ds / "theme-citadel" / "dist" / "theme.css",
                          fonts=ds / "fonts" / "dist")


def test_serves_image_with_correct_mime(roots):
    got = roots.resolve("/assets/img/gate-hero.png")
    assert got is not None
    path, mime = got
    assert path.read_bytes().startswith(b"\x89PNG")
    assert mime == "image/png"


def test_serves_theme_css(roots):
    got = roots.resolve("/assets/theme-citadel.css")
    assert got is not None
    path, mime = got
    assert "--x" in path.read_text(encoding="utf-8")
    assert mime == "text/css; charset=utf-8"


def test_serves_font_and_font_css(roots):
    css = roots.resolve("/assets/fonts/fonts.css")
    assert css and css[1] == "text/css; charset=utf-8"
    woff = roots.resolve("/assets/fonts/files/inter-latin-400-normal.woff2")
    assert woff and woff[1] == "font/woff2"


def test_unknown_asset_is_not_found(roots):
    assert roots.resolve("/assets/img/does-not-exist.png") is None
    assert roots.resolve("/assets/nope.css") is None
    assert roots.resolve("/not-assets/x.png") is None


@pytest.mark.parametrize("attack", [
    "/assets/img/../../../etc/passwd",
    "/assets/img/..%2f..%2fetc%2fpasswd",
    "/assets/fonts/../../../../etc/passwd",
    "/assets/img//etc/passwd",
    "/assets/img/./../../secret",
])
def test_path_traversal_is_refused(roots, attack):
    """경로 탈출은 루트 밖 파일을 절대 열어선 안 된다."""
    assert roots.resolve(attack) is None


def test_directory_is_not_served(roots):
    assert roots.resolve("/assets/fonts/files") is None
    assert roots.resolve("/assets/img") is None


def test_repo_defaults_point_at_real_files():
    """기본 해석이 실제 리포 배치를 찾아낸다 — 복제본이 아니라 원본을 가리킨다."""
    roots = vs.default_roots()
    assert roots is not None, "리포 루트를 못 찾음"
    assert roots.theme_css.name == "theme.css"
    assert roots.theme_css.exists(), roots.theme_css
    assert (roots.fonts / "fonts.css").exists(), roots.fonts
    assert (roots.img / "gate-hero.png").exists(), roots.img
    # 복제 금지 — 자산은 docs/mockups/assets 원본이어야 한다.
    assert roots.img.parts[-3:] == ("docs", "mockups", "assets"), roots.img


# --- 라우트 통합 (Handler 경유) ---------------------------------------------

def _get(path, roots=None):
    """Handler.do_GET 을 소켓 없이 태워 (status, headers, body) 를 얻는다."""
    import io
    from orc_citadel.viewer import Handler

    class _H(Handler):
        def __init__(self):  # BaseHTTPRequestHandler.__init__ 우회 (소켓 없음)
            self.wfile = io.BytesIO()
            self.path = path
            self.requestline = f"GET {path} HTTP/1.1"
            self.request_version = "HTTP/1.1"
            self.command = "GET"
            self.headers = {}
            self._status = None
            self._headers = {}

        def send_response(self, code, *a):
            self._status = code

        def send_header(self, k, v):
            self._headers[k] = v

        def end_headers(self):
            pass

        def log_message(self, *a):
            pass

    h = _H()
    if roots is not None:
        h.static_roots = roots
    # 파사드 빌드를 건너뛴다 — 이 테스트는 라우팅 계약만 본다. `_build()` 는
    # curated 전체를 그래프로 올리고 DuckDB 를 잡아서(뷰어 동시 실행 시 잠금 충돌)
    # 라우팅과 무관한 이유로 깨진다.
    prev = Handler.facade
    Handler.facade = prev or object()
    try:
        h.do_GET()
    finally:
        Handler.facade = prev
    return h._status, h._headers, h.wfile.getvalue()


def test_route_serves_asset_bytes_and_mime(roots):
    status, headers, body = _get("/assets/img/gate-hero.png", roots)
    assert status == 200
    assert headers["Content-Type"] == "image/png"
    assert body.startswith(b"\x89PNG")
    assert headers["Content-Length"] == str(len(body))


def test_route_404s_missing_asset(roots):
    status, _, body = _get("/assets/img/nope.png", roots)
    assert status == 404
    assert body == b"404 Not Found"


def test_route_404s_unknown_page():
    """미지정 경로가 Gate HTML 200 을 돌려주던 결함 (갭 A8)."""
    status, headers, body = _get("/오타-경로")
    assert status == 404
    assert "text/html" not in headers.get("Content-Type", "")
    assert b"<!doctype" not in body.lower()


def test_route_still_serves_known_pages():
    for path in ("/", "/table", "/witnesses", "/council",
                 "/watchtower", "/archive", "/chronicle", "/spire"):
        status, headers, body = _get(path)
        assert status == 200, path
        assert headers["Content-Type"].startswith("text/html"), path
        assert body.lower().startswith(b"<!doctype html>"), path


# --- 셸 계약 (S2·S4·S5·S6) ---------------------------------------------------

@pytest.fixture(scope="module")
def shells():
    from orc_citadel.viewer import _PAGES
    return dict(_PAGES)


def test_scope_root_is_html(shells):
    """astryx 기본 토큰이 `:root` 에 light-dark() 로 깔려 있다 — `<body>` 를 스코프
    루트로 잡으면 `<html>` 이 라이트 팔레트를 써서 본문 아래가 흰색으로 남는다."""
    for route, page in shells.items():
        assert '<html lang="ko" data-astryx-theme="citadel"' in page, route
        assert "<body data-astryx-theme" not in page, route


def test_theme_and_fonts_are_linked(shells):
    for route, page in shells.items():
        assert '<link rel="stylesheet" href="/assets/fonts/fonts.css">' in page, route
        assert '<link rel="stylesheet" href="/assets/theme-citadel.css">' in page, route


def test_tokens_are_aliased_not_hardcoded(shells):
    """색 정본은 theme-citadel 이다 — 뷰어 CSS 는 별칭만 둔다.
    폴백 hex 는 테마 미로드 시에도 화면이 서게 하려는 것이라 허용."""
    page = shells["/"]
    assert "--surface:var(--color-background-card,#111820)" in page
    assert "--primary:var(--color-accent,#45E06F)" in page
    assert "--parchment:var(--astryx-theme-citadel-parchment,#C8B58E)" in page


@pytest.mark.parametrize("route,cap", [
    ("/", 360), ("/watchtower", 360), ("/table", 300), ("/witnesses", 300),
    ("/council", 300), ("/archive", 300), ("/chronicle", 300), ("/spire", 300),
])
def test_masthead_has_hero_with_cap(shells, route: str, cap: int):
    """히어로는 전부 1920×720(8:3). 고정 밴드면 세로 23% 만 보이고,
    상한이 없으면 2560px 뷰포트에서 960px 를 먹는다."""
    page = shells[route]
    assert "aspect-ratio:8/3" in page, route
    assert f"max-height:{cap}px" in page, route
    assert "url('/assets/img/" in page, route


@pytest.mark.parametrize("route,art", [
    ("/table", "empty-wartable.png"), ("/witnesses", "empty-witnesses.png"),
    ("/watchtower", "empty-watchtower.png"), ("/archive", "empty-archive.png"),
    ("/chronicle", "empty-chronicle.png"), ("/spire", "empty-spire.png"),
])
def test_empty_state_art_is_declared(shells, route: str, art: str):
    assert f'data-empty-art="{art}"' in shells[route], route


def test_gate_and_council_have_no_empty_art(shells):
    """대응 아트가 없는 공간은 빈 문자열 — 가짜로 채우지 않는다 (honest-gap §6.2)."""
    for route in ("/", "/council"):
        assert 'data-empty-art=""' in shells[route], route


def test_header_search_works_on_every_page(shells):
    """헤더 검색이 8페이지 중 2곳에서만 동작하던 결함 (갭 A4)."""
    for route, page in shells.items():
        assert "/api/search" in page, route


def test_referenced_assets_exist():
    """셸이 거는 히어로·빈상태 파일이 실제로 존재한다."""
    import re

    from orc_citadel.viewer import _PAGES
    roots = vs.default_roots()
    assert roots is not None
    names = set()
    for page in _PAGES.values():
        names |= set(re.findall(r"/assets/img/([A-Za-z0-9_.-]+)", page))
        names |= set(re.findall(r'data-empty-art="([A-Za-z0-9_.-]+)"', page))
    assert names
    missing = sorted(n for n in names if not (roots.img / n).exists())
    assert not missing, missing


def test_masthead_matches_content_width(shells):
    """배너 폭은 본문(main max-width)과 맞춘다.

    전폭이면 본문(1200px)과 어긋날 뿐 아니라, 넓을수록 8:3 상한에 더 많이 걸려
    세로가 잘린다 — 2560px 전폭에서 360px 상한은 세로 37%, 1200px 에서는 80%.
    좁히는 쪽이 오히려 그림이 더 보인다.
    """
    page = shells["/"]
    assert "main{max-width:1200px" in page
    assert ".masthead{" in page
    mast = page[page.index(".masthead{"):]
    mast = mast[:mast.index("}")]
    assert "max-width:1200px" in mast, mast
    assert "margin:var(--sp-md) auto 0" in mast, mast
