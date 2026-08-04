"""TDD Red — 실제 HTML→S3 파싱→프로비넌스 왕복 (04 §3, 03 §3, DoD ①).

실제 수집 HTML(태그·엔티티 포함)에 대해:
- extract_html이 clean text/title/publication_time/parser_version 추출 (S3 §3.1)
- parse_document가 문장 segment 생성, char offset이 정규화 텍스트를 slice복원 (ADR-302)
- E2E: HTML → extract → segment → MutationLog claim → resolve_claim 왕복
"""
import pytest

from orc_citadel.normalize import Segment
from orc_citadel.raw_store import RawStore
from orc_citadel.mutation_log import MutationLog
from orc_citadel.parse import extract_html, parse_document, ParsedDoc, PARSER_VERSION

# 실제 NVIDIA 보도자료 형태의 대표 HTML 픽스처 (04 §1.4 official)
NVIDIA_HTML = b"""<!doctype html><html><head>
<title>NVIDIA Sets Conference Call for Second-Quarter Financial Results | NVIDIA Newsroom</title>
<meta property="article:published_time" content="2026-08-01T14:00:00+00:00"/>
</head><body>
<article>
<h1>NVIDIA Sets Conference Call for Second-Quarter Financial Results</h1>
<p>NVIDIA will host a conference call on Wednesday, August 26. The call discusses financial results.</p>
<p>Results cover fiscal year 2027, which ended July 26, 2026 &amp; the company outlook.</p>
</article></body></html>"""


# ---- 1. extract_html: S3 §3.1 documents 필드 추출 ----
def test_extract_html_strips_tags_and_entities():
    doc = extract_html(NVIDIA_HTML, "https://nvidianews.nvidia.com/news/x")
    assert isinstance(doc, ParsedDoc)
    # 태그 제거 + 엔티티 언이스케이프됨 (캐리지&앰프샌드의 엔티티 형태가 사라짐)
    assert "<" not in doc.text
    assert "&amp;" not in doc.text
    assert "2026 & the company outlook" in doc.text
    # 본문 문단 텍스트 포함 (공백 정규화)
    assert "NVIDIA will host a conference call" in doc.text
    assert "fiscal year 2027" in doc.text
    # 문서 메타
    assert "Second-Quarter Financial Results" in doc.title
    assert doc.parser_version == PARSER_VERSION


def test_extract_html_publication_time():
    doc = extract_html(NVIDIA_HTML, "https://nvidianews.nvidia.com/news/x")
    assert doc.publication_time is not None
    assert doc.publication_time.isoformat().startswith("2026-08-01")


# ---- 2. parse_document: segment char offset이 정규화 텍스트 slice 복원 (ADR-302) ----
def test_parse_document_segments_slice_clean_text():
    doc = extract_html(NVIDIA_HTML, "https://nvidianews.nvidia.com/news/x")
    segments = parse_document("doc-realhtml0123456789abcdef", doc)
    assert len(segments) >= 2
    assert all(isinstance(s, Segment) for s in segments)
    for seg in segments:
        # char offset으로 정규화 텍스트 slice → segment.text 재현 (왕복 보장)
        assert doc.text[seg.char_start:seg.char_end] == seg.text


# ---- 3. E2E: HTML → 왕복 프로비넌스 (DoD ①) ----
def test_e2e_html_to_claim_roundtrip():
    html = NVIDIA_HTML
    store = RawStore()
    # raw zone: immutable HTML 저장 (doc_id = sha256(html))
    html_doc_id = store.put("src-official-nvidia-news", "https://nvidianews.nvidia.com/news/x", html)

    # S3: clean text 추출 + segmentable layer 저장
    doc = extract_html(html, "https://nvidianews.nvidia.com/news/x")
    text_doc_id = store.put("src-official-nvidia-news", "https://nvidianews.nvidia.com/news/x", doc.text.encode())
    segments = parse_document(text_doc_id, doc)

    # claim 생성 (두 번째 문장 segment span)
    seg = segments[1]
    ml = MutationLog(store)
    span = (seg.segment_id, seg.char_start, seg.char_end)
    ml.apply(text_doc_id, "create_claim", source_span=span,
             idempotency_key=f"{html_doc_id}:{seg.segment_id}")
    # apply는 mutation_id를 반환 — 실제 claim_id는 span으로 역조회 (mutation_log 계약).
    claim_ids = ml.claims_for(source_span=span)
    assert len(claim_ids) == 1
    claim_id = claim_ids[0]

    # 왕복: resolve_claim이 segment.text를 원문 slice로 재현
    resolved = store.resolve_claim(claim_id)
    assert resolved.segment_id == seg.segment_id
    assert resolved.text == seg.text
    assert resolved.text in doc.text
    # content_hash = text_doc_id (내용 기반, 03 §2.1)
    assert resolved.content_hash == text_doc_id
    # 업스트림 raw HTML과 연결 (url 공유 + html_doc_id 파생 주장)
    assert store.has(html_doc_id)


def test_extract_html_rejects_empty_or_untitled():
    with pytest.raises(ValueError):
        extract_html(b"", "https://x")


# ---- 4. 실제 웹에서 노출된 버그 회귀 (article 컨테이너 우선, UTF-8 offset) ----

def test_extract_prefers_article_body_over_nav():
    """nav의 <p>보다 article-body 컨테이너 본문을 본문으로 선택 (실 NVIDIA 구조)."""
    html = b"""<html><body>
    <nav><p>PLATFORMS Cloud Autonomous Machines</p><p>Shop Laptops</p></nav>
    <div class="article-body">
      <p>NVIDIA will host a conference call on Wednesday.</p>
      <p>The financial results cover Q2 fiscal 2027.</p>
    </div>
    </body></html>"""
    doc = extract_html(html, "https://nvidianews.nvidia.com/news/x")
    assert "PLATFORMS Cloud Autonomous" not in doc.text
    assert "Shop Laptops" not in doc.text
    assert "conference call on Wednesday" in doc.text
    assert "Q2 fiscal 2027" in doc.text


def test_utf8_multibyte_offset_roundtrip():
    """다중 바이트 UTF-8 코드포인트 후에도 char offset slice가 왕복 보존 (ADR-302)."""
    html = b'''<html><body><article class="entry-content">
    <p>NVIDIA said \xe2\x80\x9cchip demand rose.\xe2\x80\x9d The datacenter segment grew sharply.</p>
    </article></body></html>'''
    store = RawStore()
    doc = extract_html(html, "https://x")
    tid = store.put("src-official", "https://x", doc.text.encode())
    segments = parse_document(tid, doc)
    ml = MutationLog(store)
    # 곡 따옴표(다중 바이트) 다음 문장인 두 번째 segment를 선택
    seg = segments[-1]
    span = (seg.segment_id, seg.char_start, seg.char_end)
    ml.apply(tid, "create_claim", source_span=span, idempotency_key="utf8")
    r = store.resolve_claim(ml.claims_for(source_span=span)[0])
    assert r.text == seg.text
    assert doc.text[seg.char_start:seg.char_end] == seg.text
