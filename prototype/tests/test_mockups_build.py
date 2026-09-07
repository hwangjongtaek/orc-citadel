"""목업 생성물 회귀 — `docs/mockups/` 가 커밋된 상태와 계약을 지키는지.

목업은 `astryx theme build` 와 같은 정책이다: node 는 저작 도구일 뿐이고 생성물을
커밋한다. 저작 소스는 `design-system/mockups/src/`, 출력은 `docs/mockups/`(정본).
이 테스트는 node 없이 HTML 텍스트만 검사해 기존 pytest 스위트에 붙는다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

DIST = Path(__file__).resolve().parents[2] / "docs" / "mockups"

PAGES = [
    "index", "citadel-gate", "war-table", "hall-of-witnesses", "council-chamber",
    "watchtower", "grand-archive", "chronicle-vault", "signal-spire", "empty-states",
]

# 공간 페이지가 반드시 실어야 하는 핵심 정보 블록 (원본 목업 대비 재현 확인).
REQUIRED = {
    "citadel-gate": ["New Campaign", "Campaigns · 진행 중 조사", "Watchtower", "공간 빠른 진입"],
    "war-table": ["Campaign Map", "Temporal Evidence Graph", "Evidence Inspector",
                  "Chronicle", "supports", "contradicts", "superseded"],
    "hall-of-witnesses": ["Claims", "Evidence &amp; Provenance", "Provenance Trail",
                          "독립성 보정", "Round-trip"],
    "council-chamber": ["Warchief&#x27;s Council", "Investigation Loop",
                        "Stopping · Cost · Audit", "Audit Agent"],
    "watchtower": ["Stage Throughput", "Correlation ID", "Dead-letter", "SLO"],
    "grand-archive": ["Sifter", "Stacks", "Codex", "Dedup Cluster"],
    "chronicle-vault": ["Bitemporal Plane", "AS-OF Snapshot", "Supersession"],
    "signal-spire": ["Triggers", "Alert Feed", "Subscriptions", "dedup:"],
    "empty-states": ["empty-wartable.png", "empty-spire.png"],
}


@pytest.fixture(scope="module")
def pages() -> dict[str, str]:
    if not DIST.exists():  # pragma: no cover - 빌드 누락 시에만
        pytest.fail(f"{DIST} 없음 — design-system/mockups 에서 `npm run build` 후 커밋한다.")
    return {p: (DIST / f"{p}.html").read_text(encoding="utf-8") for p in PAGES}


@pytest.mark.parametrize("name", PAGES)
def test_page_exists_and_is_themed(pages: dict[str, str], name: str) -> None:
    html = pages[name]
    assert html.startswith("<!doctype html>")
    # theme-citadel 스코프가 없으면 토큰이 하나도 적용되지 않는다.
    assert 'data-astryx-theme="citadel"' in html
    for sheet in ("reset.css", "astryx.css", "theme-citadel.css"):
        assert f'href="./{sheet}"' in html, sheet


@pytest.mark.parametrize("name", PAGES)
def test_no_client_javascript(pages: dict[str, str], name: str) -> None:
    """목업은 정적이다 — 클라이언트 JS 가 새어 들어오면 SSG 성질이 깨진다."""
    html = pages[name]
    assert "<script" not in html.lower()


@pytest.mark.parametrize("name", sorted(REQUIRED))
def test_required_blocks_rendered(pages: dict[str, str], name: str) -> None:
    html = pages[name]
    missing = [b for b in REQUIRED[name] if b not in html]
    assert not missing, f"{name}: 누락 블록 {missing}"


@pytest.mark.parametrize("name", PAGES)
def test_astryx_components_actually_rendered(pages: dict[str, str], name: str) -> None:
    """Astryx 가 런타임에 붙이는 시맨틱 클래스 — 컴포넌트를 실제로 통과했다는 증거.

    스타일시트에는 해시 클래스(`.x100vrsf`)만 있고 이 이름들은 컴포넌트가 렌더 시점에
    붙인다. 즉 손으로 쓴 div 만으로는 절대 나올 수 없다.
    """
    html = pages[name]
    components = set(re.findall(r"astryx-[a-z][a-z-]*", html))
    assert "astryx-text" in components
    assert len(components) >= 2, f"{name}: Astryx 컴포넌트 사용 흔적 부족 {components}"


def test_every_space_is_linked_from_shell(pages: dict[str, str]) -> None:
    """공간 탭이 8개 공간을 모두 건다 — 원본 목업에 없던 순회 경로."""
    spaces = ["citadel-gate", "war-table", "hall-of-witnesses", "council-chamber",
              "watchtower", "grand-archive", "chronicle-vault", "signal-spire"]
    for slug in spaces:
        assert f'href="./{slug}.html"' in pages["war-table"], slug


def test_assets_referenced_exist(pages: dict[str, str]) -> None:
    """히어로·초상·빈상태 PNG 참조가 전부 실제 파일로 존재한다."""
    source = DIST / "assets"
    referenced: set[str] = set()
    for html in pages.values():
        referenced |= set(re.findall(r"\./assets/([A-Za-z0-9_.-]+)", html))
    assert referenced, "자산 참조가 하나도 없다 — 셸이 깨졌을 가능성"
    missing = sorted(f for f in referenced if not (source / f).exists())
    assert not missing, f"참조되지만 없는 자산: {missing}"


# 히어로는 전부 1920×720 (8:3). 고정 높이 밴드에 cover 로 넣으면 세로 23% 만 보인다.
# 문서형 페이지는 8:3 을 지켜 그림 전체를 보이고, 앱셸 페이지는 좌·우 패널이
# 세로를 다투므로 압축 밴드를 쓴다.
FULL_HERO = ["index", "citadel-gate", "watchtower", "empty-states"]
BAND_HERO = ["war-table", "hall-of-witnesses", "council-chamber",
             "grand-archive", "chronicle-vault", "signal-spire"]


@pytest.mark.parametrize("name", FULL_HERO)
def test_document_pages_show_full_hero(pages: dict[str, str], name: str) -> None:
    html = pages[name]
    assert "aspect-ratio:8 / 3" in html, f"{name}: 히어로가 8:3 을 지키지 않는다"
    assert "height:132px" not in html
    # `height: fill` 이면 헤더가 뷰포트 안으로 눌려 8:3 이 도로 잘린다.
    assert 'data-height="auto"' in html or "height:132px" not in html


@pytest.mark.parametrize("name", BAND_HERO)
def test_app_shell_pages_keep_compact_band(pages: dict[str, str], name: str) -> None:
    """좌·우 패널이 있는 페이지에서 8:3 히어로를 쓰면 본문이 화면 밖으로 밀린다."""
    html = pages[name]
    assert "height:132px" in html, f"{name}: 압축 밴드가 아니다"
    assert "aspect-ratio:8 / 3" not in html


def test_masthead_has_explicit_width(pages: dict[str, str]) -> None:
    """LayoutHeader 의 flex 자식이라 width 를 안 주면 폭이 접히고,
    그러면 aspect-ratio 가 접힌 폭 기준으로 계산돼 히어로가 조각으로 나온다."""
    for name in FULL_HERO:
        mast = re.search(r'style="[^"]*aspect-ratio:8 / 3[^"]*"', pages[name])
        assert mast and "width:100%" in mast.group(0), name


def test_design_tokens_not_hardcoded_in_shell(pages: dict[str, str]) -> None:
    """셸은 theme-citadel 토큰을 참조해야 한다 — 원본 목업의 하드코딩 hex 복제 방지."""
    html = pages["citadel-gate"]
    assert "var(--color-background-card)" in html
    assert "var(--astryx-theme-citadel-" in html
