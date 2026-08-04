"""대형 수집 러너 — batch 계획·저장 멱등성 (resumable) TDD (04 §1.3/§1.4).

라이브 HTTP는 오프라인 테스트하지 않음 — 순수 계획(arxiv_batches)과 저장 멱등성
(_save_zone: content-hash 재개 무중복)만 검증한다. 진짜 대형 수집은 사용자 실행.
"""
from __future__ import annotations

import pathlib

import pytest

from orc_citadel.collect_large import _save_zone, arxiv_batches


class _NoSleep:
    def sleep(self, _):
        return None


def test_arxiv_batches_full_pages():
    """total이 page 배수 → 균등 배치."""
    assert arxiv_batches(300, page=100) == [(0, 100), (100, 100), (200, 100)]


def test_arxiv_batches_partial_last():
    """마지막 페이지는 남은 만큼."""
    assert arxiv_batches(250, page=100) == [(0, 100), (100, 100), (200, 50)]


def test_arxiv_batches_smaller_than_page():
    assert arxiv_batches(10, page=100) == [(0, 10)]


def test_arxiv_batches_zero():
    assert arxiv_batches(0) == []


def test_save_zone_idempotent_resume(tmp_path):
    """동일 content 재저장 → created=False (재개 무중복, 03 §2.1)."""
    raw = tmp_path / "raw"
    doc_id, created = _save_zone("src-test", "http://x/1", b"hello", {}, raw_dir=raw)
    assert created is True
    assert doc_id.startswith("doc-")
    # 같은 bytes 다시 → 이미 존재 → 스킵.
    doc_id2, created2 = _save_zone("src-test", "http://x/1", b"hello", {}, raw_dir=raw)
    assert doc_id2 == doc_id
    assert created2 is False


def test_save_zone_diff_content_new_docid(tmp_path):
    """다른 content → 다른 doc_id, 새 저장."""
    raw = tmp_path / "raw"
    a, _ = _save_zone("s", "http://x/1", b"alpha", {}, raw_dir=raw)
    b, _ = _save_zone("s", "http://x/2", b"beta", {}, raw_dir=raw)
    assert a != b
    assert (raw / "s" / "doc" / a).exists()
    assert (raw / "s" / "doc" / b).exists()


def test_save_zone_writes_metadata(tmp_path):
    """content.bin + fetch.json 작성 (raw 3-zone 계약)."""
    raw = tmp_path / "raw"
    doc_id, _ = _save_zone("s", "http://x/1", b"data", {"http_status": 200}, raw_dir=raw)
    d = raw / "s" / "doc" / doc_id
    assert (d / "content.bin").read_bytes() == b"data"
    assert (d / "fetch.json").exists()


def test_collect_arxiv_caps_at_limit(monkeypatch):
    """discover가 limit보다 많은 ref를 반환해도 total까지만 수집 (버그 재현/방지)."""
    import orc_citadel.collect_large as cl
    from orc_citadel.connectors.base import DiscoveredRef

    # fake: 100 refs를 yield (페이지당 max_results 초과 상황).
    def fake_discover(self, config, cursor):
        for i in range(100):
            yield DiscoveredRef(url=f"https://arxiv.org/abs/{i}", hint_modified=None)

    monkeypatch.setattr(cl.ArxivConnector, "discover", fake_discover)
    monkeypatch.setattr(cl, "_get", lambda url: (b"content", {"Content-Type": "x"}))
    monkeypatch.setattr(cl, "_save_zone",
                        lambda *a, **k: (f"doc-{hash(a[1])%1000:03d}", True))
    monkeypatch.setattr(cl, "_sleep_for_arxiv", lambda: None)
    monkeypatch.setattr(cl, "time", _NoSleep())

    counts = cl.collect_arxiv(total=5)
    assert counts["saved"] == 5  # limit 5에서 정지 (100개 반환에도)
    assert counts["skipped"] == 0
