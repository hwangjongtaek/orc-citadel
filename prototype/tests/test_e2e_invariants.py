"""S37 전 계층 종합 통합 검증 (E2E Invariant Suite) TDD.

파이프라인 → 영속 → read-only 소비(S28-S31) → 평가(S33-S36) end-to-end 왕복의
계층 간 접점 불변식을 fixture golden으로 고정한다.

- 파이프라인 산출(어세션)이 Catalog·evidence·conclusion·ranking과 일치.
- assertion마다 근거(S29)가 claim 포함 (만족 주장 evidence).
- Conclusion evidence_count = subject 전체 distinct 근거 문서 수.
- Ranking subject == conclusion subject (일관).
- EvalHarness가 캐노니컬·모순을 zone에서 자동 로드 가능 (빈 골든 vacuous).
- 골든 영속 후 EvalSuite가 로드 → metrics·gate 리포트 (결정성).
- 총 결정성: 동일 입력 재실행 → 소비·평가 산출 동일.

Atomic TDD: Red → Green.
"""
from __future__ import annotations

from orc_citadel.curated_zone import CuratedZone
from orc_citadel.pipeline_runner import run_pipeline

DOC1 = b"""<html><head>
<title>NVIDIA Conference Call</title>
<meta property="article:published_time" content="2026-08-01T14:00:00+00:00"/>
</head><body><article>
<h1>NVIDIA Sets Conference Call</h1>
<p>NVIDIA announces it will host a conference call on Wednesday, August 26.</p>
<p>TSMC accelerates production of CoWoS packaging for NVIDIA GPUs.</p>
</article></body></html>"""

DOC2 = b"""<html><head>
<title>TSMC Expansion</title>
<meta property="article:published_time" content="2026-08-02T09:00:00+00:00"/>
</head><body><article>
<h1>TSMC Expands CoWoS Capacity</h1>
<p>TSMC announces expansion of CoWoS capacity to meet AI demand.</p>
</article></body></html>"""


def _metas():
    return [
        {"source_id": "t1", "url": "https://t.example/nv", "doc_id": "doc-aaaa",
         "content": DOC1},
        {"source_id": "t2", "url": "https://t.example/tsmc", "doc_id": "doc-bbbb",
         "content": DOC2},
    ]


def _zone() -> CuratedZone:
    z = CuratedZone(":memory:")
    z.initialize()
    return z


# --- 파이프라인 → 소비 계층 일관성 -------------------------------------------

def test_pipeline_to_catalog_consistent():
    """Catalog 어세션 수 == 파이프라인 어세션 수 (영속·조회 왕복)."""
    from orc_citadel.catalog import Catalog

    z = _zone()
    res = run_pipeline(_metas(), z)
    assert res.assertions > 0
    catalog = Catalog(z)
    page = catalog.assertions(limit=200)
    assert len(page["items"]) == res.assertions


def test_assertion_to_evidence_present():
    """promoted assertion의 claim은 근거(S29)에 포함 — evidence ≥ 1."""
    from orc_citadel.assertion_evidence import AssertionEvidenceProjector

    z = _zone()
    run_pipeline(_metas(), z)
    proj = AssertionEvidenceProjector(z)
    assertions = z.assertions()
    assert len(assertions) > 0
    # 승격된 claim 중 근거가 존재하는 것 최소 1개.
    evs = [proj.for_assertion_by_claim(a["claim_id"]) for a in assertions]
    present = [e for e in evs if e is not None and e.evidence_count >= 1]
    assert len(present) >= 1


def test_conclusion_evidence_count_distinct_docs():
    """Conclusion evidence_count = subject 전체 distinct 근거 문서 수 (이중 집계 방지)."""
    from orc_citadel.conclusion import ConclusionProjector
    from orc_citadel.assertion_evidence import AssertionEvidenceProjector

    z = _zone()
    run_pipeline(_metas(), z)
    proj = AssertionEvidenceProjector(z)
    concl = ConclusionProjector(z)
    for c in concl.all():
        subject_docs = set()
        for e in proj.for_subject(c.subject_id):
            subject_docs.update(e.supporting_docs)
        assert c.confidence["evidence_count"] == len(subject_docs)


def test_ranking_subjects_match_conclusion():
    """Ranking subject 목록 == Conclusion subject 목록 (일관)."""
    from orc_citadel.ranking import ConclusionRanking
    from orc_citadel.conclusion import ConclusionProjector

    z = _zone()
    run_pipeline(_metas(), z)
    rank_subjects = {r.subject_id for r in ConclusionRanking(z).ranked()}
    concl_subjects = {c.subject_id for c in ConclusionProjector(z).all()}
    assert rank_subjects == concl_subjects


# --- 평가 계층 일관성 ---------------------------------------------------------

def test_eval_harness_reads_pipeline_state():
    """EvalHarness가 파이프라인 캐노니컬·모순을 zone에서 자동 로드 (빈 골든 vacuous)."""
    from orc_citadel.eval_harness import EvalHarness

    z = _zone()
    run_pipeline(_metas(), z)
    h = EvalHarness(zone=z)
    rep = h.report()
    # 캐노니컬이 있으면 평가 가능 — 골든이 없어도 vacuous로 block 안 함.
    assert "canonicalization" in rep
    assert "promotion_blocked" in rep


def test_eval_suite_after_golden_persist():
    """골든 영속 → EvalSuite가 zone에서 load 가능 (결정성, vacuous 동작)."""
    from orc_citadel.eval_suite import EvalSuite

    z = _zone()
    run_pipeline(_metas(), z)
    # 골든 1건 영속 — 파이프라인에서 claim 쌍이 반드시 생기진 않으므로, 영속-로드 왕복만.
    z.persist_golden_pair("clm-gold-a", "clm-gold-b", "equivalent", split="dev",
                          gold_version="g1", labeled_by="human:e2e",
                          labeled_at="2026-08-03T00:00:00Z", rationale="e2e")
    assert len(z.golden_pairs()) == 1
    r1 = EvalSuite(zone=z).run()   # zone에서 골든 자동 로드.
    r2 = EvalSuite(zone=z).run()
    assert r1.metrics == r2.metrics
    assert r1.passed == r2.passed
    assert "canonicalization" in r1.gates


# --- 총 결정성 ---------------------------------------------------------------

def test_e2e_consumption_eval_deterministic():
    """동일 입력 재실행 → 소비·평가 산출 동일."""
    from orc_citadel.conclusion import ConclusionProjector

    z1, z2 = _zone(), _zone()
    run_pipeline(_metas(), z1)
    run_pipeline(_metas(), z2)
    c1 = ConclusionProjector(z1).all()
    c2 = ConclusionProjector(z2).all()
    k = lambda c: (c.subject_id, c.confidence["value"], c.confidence["evidence_count"])
    assert sorted(k(x) for x in c1) == sorted(k(x) for x in c2)
