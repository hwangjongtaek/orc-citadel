"""P1 트랙 C — DoD ② 최종 보고서/근거 문장에 source span 연결 (design 03 §8, ADR-305).

Phase 1 DoD ②: "최종 보고서 검증 가능 문장에 source span 연결". 현재 provenance
trail 은 claim → doc 까지만 char span 이 없다. 그런데 char span 은 파이프라인이
`extraction_records`(element_id=claim_id, segment_id, char_start/end) 로 이미 영속했다.
이 테스트는 `get_evidence_provenance` trail 이 `extraction_record` step 을 읽어
**segment_id / char_start / char_end** 를 노출하는지 검증한다 (불변식 §3-2 왕복).
"""
from __future__ import annotations

import pytest

from orc_citadel.api_facade import ApiFacade
from orc_citadel.curated_zone import CuratedZone
from tests.test_api_facade import _make_graph, _seed_claims  # noqa: F401


def test_provenance_trail_includes_char_span():
    """provenance trail 이 extraction_record 의 segment_id·char span 을 노출 (DoD ②)."""
    z = CuratedZone(":memory:")
    z.initialize()
    # claim + assertion 시드
    _seed_claims(z, [
        {"cid": "clm-a", "doc": "d1", "subj": "org-a", "pred": "announces", "obj": "org-b"},
    ])
    # 파이프라인과 동일하게 claim 에 대한 extraction_record 영속 (char span 포함).
    z.persist_extraction_record(
        element_id="clm-a", doc_id="d1", segment_id="d1#p0.s3",
        char_start=41, char_end=97, content_hash="sha256:abc", model_id="det",
    )
    f = ApiFacade(z, _make_graph())
    items = f.get_claim_evidence("clm-a")["items"]
    evid = items[0]["evidence_id"]
    trail = f.get_evidence_provenance(evid)
    assert trail is not None
    steps = {s["step"]: s for s in trail["trail"]}
    # char span step 존재 — DoD ② (원문 offset 왕복, 불변식 §3-2)
    assert "extraction_record" in steps
    er = steps["extraction_record"]
    assert er["segment_id"] == "d1#p0.s3"
    assert er["char_start"] == 41
    assert er["char_end"] == 97
    # document step 은 유지
    assert "document" in steps
