"""S3 Parse/Normalize — HTML→clean text 추출 (04 §3, 03 §3.1).

raw zone은 immutable HTML bytes를 보존(doc_id = sha256(html))하고, 이 모듈이
본문 clean text·메타(title/publication_time)를 추출·정규화한다. prototype은
stdlib(`html.unescape` + 정규식)만 사용해 외부 파서 의존성 없이 동작한다.

ADR-302 (양방향 offset): parse_document로 만든 segment의 char_start/char_end는
**clean text** 기준 offset이며, 그로 text를 slice하면 segment.text가 재현된다.
원문(HTML) 바이트 인덱스로의 정확 역매핑은 일반 케이스에서 이후 증분으로 미룬다
(04 §3.4 프로토타입 범위 기술과 동일).
"""
from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass, field
from datetime import datetime

from .normalize import Segment, segment_document

# 문단 분할 규칙·정규화(엔티티/공백) 로직 식별 — 변경 시 상향(→재파싱, 04 §3.3).
PARSER_VERSION = "p1"

_SCRIPT_STYLE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")
_TITLE_TAG = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
_PUBLISHED_META = re.compile(
    r'<meta[^>]+property\s*=\s*["\'](?:\w+:)?(?:article:)?published_time["\'][^>]*content\s*=\s*["\']([^"\']+)["\']',
    re.I,
)
_PARAGRAPH = re.compile(r"<p[^>]*>(.*?)</p>", re.S | re.I)
_HEADING = re.compile(r"<h[1-6][^>]*>(.*?)</h[1-6]>", re.S | re.I)
_WS = re.compile(r"\s+")
# 본문 컨테이너 후보 (클래스/id) — 순서대로 우선. 산문 본문 외 nav·footer boilerplate 배제.
# 시작 태그를 찾은 뒤 열린 컨테이너 깊이만큼 대응 닫는 태그까지 잘라내기 위해,
# 정규식은 시작 태그의 tag명을 잡고, 파싱은 _container_content()로 처리한다.
_ARTICLE_CONTAINER_OPEN = re.compile(
    r'<(?P<tag>\w+)[^>]*(?:class|id)\s*=\s*["\'][^"\']*?(?:article-body|article_body|'
    r'entry-content|post-content|post_content|pna_l_article_wrapper|main-content|'
    r'story-content)[^"\']*?["\']',
    re.I,
)


def _container_content(html: str) -> str:
    """대표 article 컨테이너들이 담은 내부 마크업을 반환.

    시작 태그의 tag명을 보고 대응 닫는 태그(중첩 고려, 깊이 카운트)까지의 바이트를
    취한다. 정규식으로는 균형 잡힌 중첩 태그를 못 다루므로 간단한 깊이 스캔을 사용
    (prototype 수준 — 실제 문서의 article-body/entry-content 유형에서 충분).
    """
    for m in _ARTICLE_CONTAINER_OPEN.finditer(html):
        tag = m.group("tag")
        start = m.end()
        open_pat = re.compile(rf"<{tag}\b", re.I)
        close_pat = re.compile(rf"</{tag}\s*>", re.I)
        open_pos = [o.start() for o in open_pat.finditer(html, start)]
        close_pos = [c.start() for c in close_pat.finditer(html, start)]
        # 깊이 스캔: 열림/닫힘을 순서대로, 깊이 0이 되는 첫 닫힘이 실제 닫는 태그.
        depth, stack = 1, 0
        i = j = 0
        while i < len(open_pos) or j < len(close_pos):
            use_open = j >= len(close_pos) or (i < len(open_pos) and open_pos[i] < close_pos[j])
            if use_open:
                depth += 1
                i += 1
            else:
                depth -= 1
                j += 1
                if depth == 0:
                    return html[start:close_pos[j - 1]]
        # 열린 채 끝나면 시작부터 끝까지로 처리.
        return html[start:]
    return ""


@dataclass(frozen=True)
class ParsedDoc:
    """S3 §3.1 documents 최소 필드 (prototype)."""

    text: str
    title: str
    publication_time: datetime | None = None
    parser_version: str = PARSER_VERSION
    kind: str = "paragraph"
    extra: dict[str, str] = field(default_factory=dict)


def _clean_fragment(fragment: str) -> str:
    """HTML fragment에서 태그 제거 + 엔티티 언이스케이프 + 공백 축약."""
    frag = _TAG.sub("", fragment)
    return _WS.sub(" ", _html.unescape(frag)).strip()


def _title_of(html: str) -> str:
    m = _TITLE_TAG.search(html)
    if m:
        t = _clean_fragment(m.group(1))
        # " | NVIDIA Newsroom" 류 사이트 접미 제거 (간단 분리)
        t = re.sub(r"\s*[|–-]\s*[^|–-]*$", "", t).strip()
        if t:
            return t
    # h1 대체
    h = _HEADING.search(html)
    return _clean_fragment(h.group(1)) if h else ""


def _parse_iso(text: str) -> datetime | None:
    try:
        return datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def extract_html(html_bytes: bytes, url: str) -> ParsedDoc:
    """S3 §3.1: HTML에서 clean text + title + publication_time 추출."""
    html = _SCRIPT_STYLE.sub(" ", html_bytes.decode("utf-8", errors="replace"))
    if not _TAG.sub("", html).strip():
        raise ValueError(f"no parseable content: {url}")

    # 본문: 알려진 article 컨테이너의 <p>를 우선 (nav·footer boilerplate 배제),
    # 없으면 문서 전체 <p>, 마지막으로 heading 본문.
    container = _container_content(html)
    paragraphs = [p for p in (_clean_fragment(p) for p in _PARAGRAPH.findall(container or html)) if p]
    body = paragraphs or [p for p in (_clean_fragment(h) for h in _HEADING.findall(html)) if p]

    pub = None
    meta = _PUBLISHED_META.search(_html.unescape(html))
    if meta:
        pub = _parse_iso(meta.group(1).strip())

    return ParsedDoc(
        text=" ".join(body),
        title=_title_of(html),
        publication_time=pub,
        parser_version=PARSER_VERSION,
    )


def parse_document(doc_id: str, doc: ParsedDoc) -> list[Segment]:
    """clean text를 문장 segment로 분절 (ADR-302: offset은 clean text 기준)."""
    return segment_document(doc_id, doc.text)
