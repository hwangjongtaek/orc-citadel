"""폰트 vendoring 계약 회귀 — `design-system/fonts/dist/`.

외부 CDN 금지(오프라인 전제) 규약 하에서 DESIGN.md 의 4역할 폰트를 로컬에서 서빙한다.
생성물을 커밋하므로 node 없이 텍스트·파일 존재만으로 검사한다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

DIST = Path(__file__).resolve().parents[2] / "design-system" / "fonts" / "dist"
CSS = DIST / "fonts.css"

# DESIGN.md typography 4역할 → (서체, 실제 사용하는 굵기).
EXPECTED = {
    "Cinzel": {700},           # display — 워드마크
    "Space Grotesk": {500, 600},  # heading — 제목·라벨·배지
    "Inter": {400, 600},       # body — 본문·테이블
    "JetBrains Mono": {400},   # code — ID·hash·timestamp·source span
}


@pytest.fixture(scope="module")
def css() -> str:
    if not CSS.exists():  # pragma: no cover - 빌드 누락 시에만
        pytest.fail(f"{CSS} 없음 — design-system/fonts 에서 `npm run build` 후 커밋한다.")
    return CSS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def faces(css: str) -> list[dict[str, str]]:
    out = []
    for block in css.split("@font-face")[1:]:
        out.append({
            "family": re.search(r'font-family:\s*"([^"]+)"', block).group(1),
            "weight": re.search(r"font-weight:\s*(\d+)", block).group(1),
            "src": re.search(r'url\("([^"]+)"\)', block).group(1),
            "range": re.search(r"unicode-range:\s*([^;]+);", block).group(1),
        })
    return out


@pytest.mark.parametrize("family,weights", sorted(EXPECTED.items()))
def test_design_md_roles_are_covered(faces, family: str, weights: set[int]) -> None:
    got = {int(f["weight"]) for f in faces if f["family"] == family}
    assert weights <= got, f"{family}: DESIGN.md 굵기 {sorted(weights - got)} 누락"


def test_every_face_has_unicode_range(faces) -> None:
    """서브셋이 둘(latin·latin-ext)이라 unicode-range 가 없으면 뒤엣것이 앞을 덮어
    기본 라틴 글리프가 통째로 사라진다. 조용히 깨지는 종류의 결함이라 가드한다."""
    for f in faces:
        assert f["range"], f
        # latin 서브셋만 기본 라틴(U+0000-00FF)을 담는다. latin-ext 는 확장 영역만
        # 담으므로 겹치면 안 된다 — 둘이 같은 범위면 하나가 무의미해진다.
        if re.search(r"-latin-\d", f["src"]):
            assert "U+0000-00FF" in f["range"], f["src"]
        elif "-latin-ext-" in f["src"]:
            assert "U+0000-00FF" not in f["range"], f["src"]


def test_woff2_files_exist(faces) -> None:
    missing = [f["src"] for f in faces if not (DIST / f["src"].lstrip("./")).exists()]
    assert not missing, f"참조되지만 없는 폰트 파일: {missing}"


def test_no_external_font_host(css: str) -> None:
    """CDN 금지 규약 — src 는 전부 상대 경로여야 한다."""
    assert "http://" not in css and "https://" not in css
    assert "fonts.googleapis.com" not in css and "fonts.gstatic.com" not in css


def test_ofl_licenses_bundled() -> None:
    """SIL OFL-1.1 재배포 조건 — 라이선스 원문 동봉."""
    licenses = sorted(p.name for p in DIST.glob("LICENSE-*.txt"))
    assert len(licenses) == 4, licenses
    for path in DIST.glob("LICENSE-*.txt"):
        assert "SIL OPEN FONT LICENSE" in path.read_text(encoding="utf-8").upper()


def test_mockups_link_vendored_fonts() -> None:
    """목업이 vendoring 폰트를 실제로 건다 — 링크 누락은 조용히 폴백으로만 드러난다."""
    mockups = DIST.parents[1] / "mockups" / "dist"
    if not mockups.exists():  # pragma: no cover
        pytest.skip("mockups dist 없음")
    html = (mockups / "citadel-gate.html").read_text(encoding="utf-8")
    assert 'href="./fonts/fonts.css"' in html
    assert (mockups / "fonts" / "fonts.css").exists()
