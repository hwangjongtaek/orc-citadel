"""S3 Parse — arXiv API Atom <entry> metadata 추출 TDD (04 §1.4 metadata CC0 경로).

수집이 abs HTML 페이지 대신 API Atom entry 원문 XML을 raw 문서로 저장하므로,
파서는 entry의 title/summary/published를 clean text로 추출해야 한다.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from orc_citadel.parse import extract_html

ATOM_ENTRY = b"""<entry>
  <id>http://arxiv.org/abs/2401.00001v1</id>
  <updated>2026-01-05T12:00:00Z</updated>
  <published>2026-01-03T18:30:00Z</published>
  <title>Supply Chain Attacks on  AI Accelerators</title>
  <summary>  We study supply chain attacks targeting AI accelerator
firmware. Our results show &amp;quot;significant&amp;quot; exposure.
  </summary>
  <author><name>J. Doe</name></author>
</entry>"""


def test_atom_entry_title_and_summary():
    """Atom entry → title + summary 본문 (공백 축약·엔티티 해제)."""
    doc = extract_html(ATOM_ENTRY, "http://arxiv.org/abs/2401.00001v1")
    assert doc.title == "Supply Chain Attacks on AI Accelerators"
    assert "supply chain attacks targeting AI accelerator firmware" in doc.text
    assert "\n" not in doc.text


def test_atom_entry_published_time():
    """<published>가 publication_time으로 파싱된다."""
    doc = extract_html(ATOM_ENTRY, "http://arxiv.org/abs/2401.00001v1")
    assert doc.publication_time == datetime(2026, 1, 3, 18, 30, tzinfo=timezone.utc)


def test_html_page_still_parses_as_html():
    """기존 abs HTML 경로 회귀 방지 — <entry> 없는 HTML은 HTML 파서를 탄다."""
    html = b"""<html><head><title>[2307.1] Old Doc</title></head>
    <body><p>Existing html paragraph body.</p></body></html>"""
    doc = extract_html(html, "http://arxiv.org/abs/2307.1")
    assert "Existing html paragraph body." in doc.text
