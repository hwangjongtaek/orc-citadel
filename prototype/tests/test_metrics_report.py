"""MVP #4 평가 수치 공개 (설계 10 §1.2·§2.1) TDD.

실데이터 골든셋 대비 ER·Claim Extraction 평가 수치를 검증 가능한 리포트로 공개.
- Claim extraction (canonicalization) — 골든 equivalent/unrelated 쌍이 있으면 측정·공개.
- honest gap — contradiction(골든 contradicts 미확보)·entity resolution(entity pair
  골든 미구축)은 vacuous pass 없이 '미측정'으로 명시.
- **read-only** (불변식 §3-3): 조회만, 골든·baseline 영속 없음. 결정적.

Atomic TDD: Red → Green.
"""
from __future__ import annotations

import pytest

from orc_citadel.metrics_report import generate_metrics_report
from orc_citadel.curated_zone import CuratedZone
from orc_citadel.canonicalize import CanonicalClaim


def _zone() -> CuratedZone:
    """equivalent 골든 1쌍 + 캐노니컬 병합 — claim extraction만 측정 가능한 상태."""
    z = CuratedZone(":memory:")
    z.initialize()
    z.persist_golden_pair("clm-a", "clm-b", "equivalent", "dev", "g1",
                          "human:x", "t", "x")
    z.persist_canonical(CanonicalClaim("ccl-1", "org-a", "announces", "org-b",
                                       "x", ["clm-a", "clm-b"]))
    z.set_claim_canonical("clm-a", "ccl-1")
    z.set_claim_canonical("clm-b", "ccl-1")
    return z


def test_report_structure():
    """slices/summary/format 포함."""
    rep = generate_metrics_report(_zone())
    assert "claim_extraction" in rep.slices
    assert "contradiction" in rep.slices
    assert "entity_resolution" in rep.slices
    assert isinstance(rep.summary, str) and rep.summary
    assert isinstance(rep.format(), str)


def test_claim_extraction_published():
    """골든 equivalent 쌍 + 병합 → 측정·공개 (F1/P/R 계산, gate 존재)."""
    rep = generate_metrics_report(_zone())
    s = rep.slices["claim_extraction"]
    assert s.measured is True
    assert s.metrics["tp"] == 1
    assert s.metrics["precision"] == pytest.approx(1.0)
    assert s.metrics["f1"] == pytest.approx(1.0)
    assert s.gate["threshold"] == 0.85
    assert s.gate["pass"] is True


def test_contradiction_honest_gap():
    """골든에 contradicts 쌍이 없으면 vacuous pass가 아닌 미측정으로 명시."""
    rep = generate_metrics_report(_zone())
    s = rep.slices["contradiction"]
    assert s.measured is False
    assert s.metrics is None
    assert s.gate is None
    assert s.note  # 미측정 이유 명시.


def test_entity_resolution_gap():
    """entity pair 골든 미구축 → 미측정 (Phase 2 골든 확장 후 측정)."""
    rep = generate_metrics_report(_zone())
    s = rep.slices["entity_resolution"]
    assert s.measured is False
    assert s.metrics is None
    assert s.note


def test_unrelated_nonmerge_no_fp():
    """unrelated 골든이 병합되면 오병합(fp) 감지 → 정직한 측정."""
    z = _zone()
    z.persist_golden_pair("clm-u1", "clm-u2", "unrelated", "dev", "g1",
                          "human:x", "t", "x")
    # unrelated 쌍은 캐노니컬 병합 없음(member_of 없음) → 오병합 없어야 (fp=0).
    rep = generate_metrics_report(z)
    s = rep.slices["claim_extraction"]
    assert s.metrics["fp"] == 0


def test_read_only_no_original_mutation():
    """리포트는 조회만 — 골든·baseline 영속 없음 (read-only)."""
    z = _zone()
    generate_metrics_report(z)
    assert len(z.golden_pairs()) == 1     # 기존 골든 그대로.
    assert z.active_baseline() is None    # baseline 생성 없음.
    assert len(z.promotion_baselines()) == 0


def test_determinism():
    """동일 zone → 동일 리포트."""
    z = _zone()
    a = generate_metrics_report(z)
    b = generate_metrics_report(z)
    assert a.format() == b.format()
    assert a.summary == b.summary
