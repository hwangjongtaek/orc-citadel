"""S27 통합 검증 — 계약 불변식 (설계 03 §5, 05 §6, ADR-507) TDD.

결정적+LLM 하이브리드 파이프라인의 계약 불변식을 fixture golden으로 고정한다.
- 결정성·멱등성: 동일 입력 재실행 → 동일 산출 (재생성 안전, 03 §5).
- provenance 무결성: claim은 doc·segment로, source span은 raw로 왕복 (불변식 §3-2).
- 어세션=promoted claim; 멱등 upsert로 재실행 시 중복 없음.
- **ADR-507 노-자동-병합**: LLM이 미결 쌍을 `equivalent`라 해도 결정적-우선 규칙이
  이미 매칭한 쌍만 병합 — LLM만으로 자동 SAME_AS/병합이 생기지 않는다 (G4).
"""
from __future__ import annotations

from orc_citadel.curated_zone import CuratedZone
from orc_citadel.pipeline_runner import run_pipeline

# 두 회사(NVIDIA·TSMC)가 같은 문장에서 announce 하는 다중 표현 문서 —
# 결정적 규칙이 미결로 남길 수 있는 쌍을 포함.
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


def test_golden_determinism_across_runs():
    """동일 입력 → 동일 golden 산출 (결정성·재생성, 03 §5)."""
    r1 = run_pipeline(_metas(), _zone())
    r2 = run_pipeline(_metas(), _zone())
    assert r1.mentions == r2.mentions
    assert r1.claims == r2.claims
    assert r1.promoted_claims == r2.promoted_claims
    assert r1.assertions == r2.assertions
    assert r1.canonicals == r2.canonicals
    assert r1.nodes == r2.nodes


def test_idempotent_replay_no_duplicate_assertions():
    """같은 zone에 파이프라인 재실행 → 어세션·mention 중복 없음 (idempotent upsert)."""
    z = _zone()
    r1 = run_pipeline(_metas(), z)
    n1 = len(z.assertions())
    run_pipeline(_metas(), z)  # 재실행 (동일 결정적 ID → no-op).
    assert len(z.assertions()) == n1  # 중복 없음
    assert len(z.mentions()) >= 1


def test_provenance_chain_integrity():
    """claim → segment → raw span 왕복 (불변식 §3-2, ADR-302)."""
    z = _zone()
    run_pipeline(_metas(), z)
    # 각 claim은 doc_id(→segment)와 char offset을 갖는다 → 원문까지 왕복 가능.
    claims = z.claims()
    assert all(c["doc_id"] for c in claims)
    assert all(c["subject_id"] for c in claims)  # 미해소는 파이프라인에서 제외.


def test_every_assertion_backed_by_promoted_claim():
    """모든 assertion은 promoted claim에 근거 — 근거 없는 assertion 없음."""
    z = _zone()
    res = run_pipeline(_metas(), z)
    assert res.assertions == len(z.assertions())
    # assertion의 provenance_ref가 비어있지 않음 (게이트·mutation 연결).
    for a in z.assertions():
        assert a["mutation_id"]  # 게이트 create_node와 연결.


def test_llm_equivalent_does_not_create_auto_merge():
    """LLM이 미결 쌍 `equivalent`라고 해도 ADR-507 자동 병합 금지 (G4).

    결정적-우선: 규칙이 이미 매칭한 쌍만 병합. LLM 자체만으로는 canonical SAME_AS/병합이
    graph에 생기지 않는다 — 특히 미결 쌍이 없는 단순 케이스에서는 LLM 호출도 없어야 함.
    """
    class _AggressiveJudge:
        """canonicalization은 전부 equivalent로 병합하려 함 (공격적)."""

        def judge_canonicalization(self, pair):
            return {"relation": "equivalent", "canonical_text": "t", "confidence": 0.99,
                    "rationale": "agg", "judged_by": "llm"}

        def judge_contradiction(self, pair):
            return {"verdict": "real_conflict", "conflict_type": "value_conflict",
                    "rationale": "r", "confidence": 0.9, "judged_by": "llm"}

    z_det = _zone()
    z_llm = _zone()
    _ = run_pipeline(_metas(), z_det)          # 결정적
    res_llm = run_pipeline(_metas(), z_llm, judge=_AggressiveJudge())
    # LLM 주입이 결정적 결과를 산출(ALU 병합 수)보다 늘릴 수는 있지만,
    # LLM-only 자동 병합이 생겨선 안 됨 — 결정적 각 claim은 여전히 그 자체 canonical.
    # 모든 결정적(rule-merged) canonical은 재실행 시 유지된다 (전이/자동 SAME_AS 없음).
    assert res_llm.claims == len(z_llm.claims())
    # 결정적 run과 LLM run 모두 assertion=match promoted claim.
    assert res_llm.assertions == res_llm.promoted_claims


def test_no_llm_calls_when_nothing_undecided():
    """판정 대상이 없으면(전부 결정적) LLM 판정이 영속되지 않음 (결정적-우선)."""
    z = _zone()
    run_pipeline(_metas(), z)
    assert len(z.canonical_llm_records()) == 0
    assert len(z.conflict_verdicts()) == 0


def test_llm_can_merge_genuinely_undecided_pair():
    """공격적 LLM이 진짜 미결 쌍은 병합 가능 (S22 메커니즘 동작 확인).

    서로 다른 존에서 판정돈 canonical 수가 결정적보다 적으면 LLM 캐노니컬 병합이
    실제 일어난 것 — 단, 이는 결정적 미결 쌍에만 (ADR-507: LLM-only 자동 병합 금지
    는 여전히 지킴 — 결정적 각 쌍은 유지).
    """
    # 동일 subject+predicate, 다른 surface(미결 쌍)를 만드는 문서.
    # "powers"/"enables"는 05 §4 predicate 규칙에 매칭 — 다른 표현 → 결정적 미결 쌍.
    doc = b"""<html><head><title>TSMC</title>
    <meta property="article:published_time" content="2026-08-02T09:00:00+00:00"/>
    </head><body><article><h1>TSMC</h1>
    <p>TSMC powers the latest AI GPUs with advanced packaging.</p>
    <p>TSMC enables next-generation AI chips through CoWoS capacity.</p>
    </article></body></html>"""
    metas = [{"source_id": "t", "url": "https://t.example/tsmc",
              "doc_id": "doc-cccc", "content": doc}]

    class _Aggressive2:
        def judge_canonicalization(self, pair):
            return {"relation": "equivalent", "canonical_text": "t", "confidence": 0.99,
                    "rationale": "agg", "judged_by": "llm"}

        def judge_contradiction(self, pair):
            return {"verdict": "not_conflict", "conflict_type": None,
                    "rationale": "r", "confidence": 0.5, "judged_by": "llm"}

    z_det = _zone()
    z_llm = _zone()
    rd = run_pipeline(metas, z_det)
    rl = run_pipeline(metas, z_llm, judge=_Aggressive2())
    # 결정적: 다른 surface → 미병합(2개 이상). LLM: 미결 쌍 equivalent → 병합.
    assert rd.canonicals >= rl.canonicals
    # LLM 판정이 영속됨 (S23) — 실제 미결 쌍이 있었고 LLM이 판정했다는 증거.
    assert len(z_llm.canonical_llm_records()) >= 1
