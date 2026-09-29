"""근거 기록(extraction_record)의 원문 해시 — 리포트 감사가 통과하려면 필요하다.

2026-09-29 prod 실측: 조사 리포트 4건 중 2건이 `audit_rejected`(verifiable 3 → linked 0),
2건은 문장 0건이었다. 엔진 감사는 span 이 있으면 "역추적됨"으로 통과시키지만 리포트
검증기는 `content_hash` 가 비어 있으면 거른다 — 파이프라인이 그 값을 남기지 않았다.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from orc_citadel.curated_zone import CuratedZone
from orc_citadel.investigation_report import HtmlReportGenerator, default_report_profile
from orc_citadel.pipeline_runner import run_pipeline
from orc_citadel.provenance_backfill import backfill_content_hashes
from orc_citadel.raw_shard import RawShardStore
from orc_citadel.synthesis import Audit

CONTENT = b"""<html><head><title>NVIDIA Conference Call</title>
<meta property="article:published_time" content="2026-08-01T14:00:00+00:00"/>
</head><body><article><h1>NVIDIA Sets Conference Call</h1>
<p>NVIDIA will host a conference call on Wednesday, August 26.</p>
<p>NVIDIA powers the data center and announces new accelerator products.</p>
</article></body></html>"""
DOC_ID = "doc-prov00000000000000001"
RAW_HASH = "sha256:" + hashlib.sha256(CONTENT).hexdigest()


def _metas():
    return {"source_id": "test", "url": "https://test.example/nvidia",
            "doc_id": DOC_ID, "content": CONTENT}


def _report_summary(zone):
    """파이프라인이 만든 claim 을 문장으로 세워 리포트 검증기까지 통과시킨다."""
    claim_ids = [a["claim_id"] for a in zone.assertions()]
    assert claim_ids, "픽스처가 assertion 을 못 만들었다 — 검증 대상이 없다"
    statements = [{"text": f"주장 {i}", "modality": "asserted", "claim_ref": cid}
                  for i, cid in enumerate(claim_ids)]
    trace = Audit().trace(statements, zone)
    art = HtmlReportGenerator(client=False).generate(
        {"statements": statements, "audit_trace": trace},
        {"investigation_id": "inv-prov", "audit_trace": trace},
        default_report_profile())
    return trace, art


def test_pipeline_records_the_source_content_hash():
    zone = CuratedZone(":memory:")
    zone.initialize()
    run_pipeline([_metas()], zone)

    records = zone.extraction_records()
    assert records, "추출 기록이 없다"
    assert {r["content_hash"] for r in records} == {RAW_HASH}


def test_report_audit_accepts_claims_produced_by_the_real_pipeline():
    """엔진 감사와 리포트 검증이 같은 결론을 내야 한다 — 어긋나면 audit_rejected 다."""
    zone = CuratedZone(":memory:")
    zone.initialize()
    run_pipeline([_metas()], zone)

    trace, art = _report_summary(zone)

    assert trace["verifiable"] >= 1 and trace["linked"] == trace["verifiable"]
    assert art.fallback_reason != "audit_rejected", art.audit_summary
    assert art.audit_summary["linked"] == trace["linked"]
    assert art.audit_summary["blocked"] == 0


@pytest.fixture
def legacy(tmp_path):
    """수정 이전에 쌓인 상태: 추출 기록의 content_hash 가 NULL 이고 원문은 raw 에 있다."""
    raw = RawShardStore(tmp_path / "raw")
    doc_id, _ = raw.append("test", "https://test.example/nvidia", CONTENT, {})
    raw.flush()
    zone = CuratedZone(tmp_path / "iceberg")
    zone.initialize()
    zone.persist_extraction_record(element_id="clm-known", doc_id=doc_id,
                                   segment_id=f"{doc_id}#p0", char_start=0, char_end=5)
    zone.persist_extraction_record(element_id="clm-orphan", doc_id="doc-not-in-raw",
                                   segment_id="doc-not-in-raw#p0", char_start=0, char_end=5)
    zone.close()
    return tmp_path


def _hashes(data_dir):
    zone = CuratedZone(data_dir / "iceberg")
    zone.initialize()
    try:
        return {r["element_id"]: r["content_hash"] for r in zone.extraction_records()}
    finally:
        zone.close()


def test_backfill_defaults_to_dry_run_and_changes_nothing(legacy):
    report = backfill_content_hashes(legacy)

    assert report == {"missing": 2, "resolvable": 1, "unresolvable": 1, "applied": False}
    assert _hashes(legacy) == {"clm-known": None, "clm-orphan": None}


def test_backfill_fills_what_it_can_and_reports_the_rest_honestly(legacy):
    report = backfill_content_hashes(legacy, dry_run=False)

    assert report == {"missing": 2, "resolvable": 1, "unresolvable": 1, "applied": True}
    hashes = _hashes(legacy)
    assert hashes["clm-known"] == RAW_HASH
    # 원문을 못 찾은 기록은 지어내지 않고 NULL 그대로 둔다 (honest-gap §6.2).
    assert hashes["clm-orphan"] is None


def test_backfill_is_idempotent(legacy):
    backfill_content_hashes(legacy, dry_run=False)

    again = backfill_content_hashes(legacy, dry_run=False)

    assert again["missing"] == 1 and again["resolvable"] == 0
    assert _hashes(legacy)["clm-known"] == RAW_HASH
