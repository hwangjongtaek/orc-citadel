"""뷰어 정적 자산 서빙 — `/assets/*`.

자산은 리포에 **이미 있는 것을 참조한다. 복제하지 않는다.**

    /assets/img/<file>        docs/mockups/assets/          히어로·초상·빈상태 (19MB)
    /assets/theme-citadel.css design-system/theme-citadel/dist/theme.css
    /assets/fonts/<path>      design-system/fonts/dist/     woff2 + @font-face

세 갈래로 나뉜 이유: 위 셋은 각각 다른 패키지의 산출물이고, 히어로 PNG 는 19MB
라 뷰어 쪽으로 복사하면 리포와 이미지가 그만큼 무거워진다. 컨테이너에는
`prototype/` 만 COPY 되므로(§Dockerfile) 위 경로는 바인드 마운트로 주입한다 —
`VIEWER_ASSETS_*` 환경변수로 덮어쓸 수 있다.

read-only (불변식 §3-3).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

# 서빙을 허용하는 확장자만. 목록에 없으면 404 — 실수로 소스가 새어 나가는 것을 막는다.
_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
    ".css": "text/css; charset=utf-8",
    ".woff2": "font/woff2",
    ".txt": "text/plain; charset=utf-8",
}


def _safe_child(root: Path, rel: str) -> Path | None:
    """`root` 아래로만 해석한다. 밖으로 나가면 None.

    `..`·절대경로·심볼릭 링크 탈출을 전부 막는다. 문자열 검사가 아니라 resolve 후
    부모 관계로 판정한다 — `%2e%2e` 같은 인코딩 우회를 놓치지 않기 위해서다.
    """
    rel = unquote(rel).strip("/")
    if not rel:
        return None
    try:
        target = (root / rel).resolve()
        root_resolved = root.resolve()
    except (OSError, RuntimeError):
        return None
    if target != root_resolved and root_resolved not in target.parents:
        return None
    return target


def _serve(path: Path | None) -> tuple[Path, str] | None:
    """파일이고 허용 확장자면 (경로, MIME). 디렉터리·미허용 확장자는 None."""
    if path is None or not path.is_file():
        return None
    mime = _MIME.get(path.suffix.lower())
    return (path, mime) if mime else None


@dataclass(frozen=True)
class StaticRoots:
    """`/assets/*` URL 공간 → 실제 파일 경로."""

    img: Path
    theme_css: Path
    fonts: Path

    def resolve(self, url_path: str) -> tuple[Path, str] | None:
        """URL 경로를 (파일, MIME) 로. 서빙 대상이 아니면 None (호출자가 404)."""
        if url_path == "/assets/theme-citadel.css":
            return _serve(self.theme_css)
        if url_path.startswith("/assets/img/"):
            return _serve(_safe_child(self.img, url_path[len("/assets/img/"):]))
        if url_path.startswith("/assets/fonts/"):
            return _serve(_safe_child(self.fonts, url_path[len("/assets/fonts/"):]))
        return None


def _repo_root() -> Path | None:
    """`prototype/orc_citadel/` 에서 위로 올라가 리포 루트를 찾는다."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "design-system").is_dir() and (parent / "docs").is_dir():
            return parent
    return None


def default_roots() -> StaticRoots | None:
    """환경변수 → 컨테이너 마운트 → 리포 배치 순으로 해석한다.

    셋 중 하나라도 못 찾으면 None — 호출자는 자산 없이 동작해야 한다(정직 갭).
    """
    env = {
        "img": os.getenv("VIEWER_ASSETS_IMG"),
        "theme": os.getenv("VIEWER_ASSETS_THEME"),
        "fonts": os.getenv("VIEWER_ASSETS_FONTS"),
    }
    repo = _repo_root()

    def pick(key: str, mount: str, repo_rel: str) -> Path | None:
        if env[key]:
            return Path(env[key])
        if Path(mount).exists():
            return Path(mount)
        return (repo / repo_rel) if repo else None

    img = pick("img", "/app/static/img", "docs/mockups/assets")
    theme = pick("theme", "/app/static/theme-citadel.css",
                 "design-system/theme-citadel/dist/theme.css")
    fonts = pick("fonts", "/app/static/fonts", "design-system/fonts/dist")
    if not (img and theme and fonts):
        return None
    return StaticRoots(img=img, theme_css=theme, fonts=fonts)
