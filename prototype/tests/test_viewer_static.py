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
