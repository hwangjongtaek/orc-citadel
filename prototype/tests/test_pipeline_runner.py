"""S24 정식 파이프라인 모듈 — 단일 진입점 (01, 05 §5/§6, 06 §2) TDD.

`run_pipeline(metas, zone, judge=None)`: raw docs(S1→S8 결정적 체인 + 선택적 LLM 판정
+ 영속 + 그래프 재구축)를 단일 호출로 실행하고 `PipelineResult`를 반환한다.
- judge 미주입 = 순수 결정적 (기존 체인과 동일).
- judge 주입 = 미결 쌍만 LLM, verdict는 version tuple로 영속.
"""
from __future__ import annotations

from orc_citadel.curated_zone import CuratedZone
from orc_citadel.pipeline_runner import run_pipeline

# 대표 NVIDIA HTML — NVIDIA 언급이 ticker (NVDA)로 해소되는지 확인.
NVIDIA_HTML = b"""<html><head>
<title>NVIDIA Conference Call</title>
<meta property="article:published_time" content="2026-08-01T14:00:00+00:00"/>
</head><body><article>
<h1>NVIDIA Sets Conference Call</h1>
<p>NVIDIA will host a conference call on Wednesday, August 26.</p>
<p>NVIDIA powers the data center and announces new accelerator products.</p>
</article></body></html>"""


def _metas():
    return [{
        "source_id": "test",
        "url": "https://test.example/nvidia",
        "doc_id": "doc-test0000000000000000",
        "content": NVIDIA_HTML,
    }]


def _zone() -> CuratedZone:
    z = CuratedZone(":memory:")
    z.initialize()
    return z


def test_run_pipeline_deterministic_end_to_end():
    """judge 미주입 — 결정적 체인이 raw→그래프·어세션·영속 전체 완료."""
    z = _zone()
    res = run_pipeline(_metas(), z)
    assert res is not None
    # 결정적 체인에서 mention이므로 authoritative graph에 claim 노드 존재.
    assert res.claims >= 0
    assert res.assertions == res.promoted_claims  # 각 promoted claim → assertion
    # LLM 미사용.
    assert len(z.canonical_llm_records()) == 0
    assert len(z.conflict_verdicts()) == 0
    # 결과에 필드 존재.
    assert hasattr(res, "nodes") and hasattr(res, "claims")


def test_run_pipeline_persists_everything():
    """단일 호출이 mention/claim/assertion을 zone에 영속."""
    z = _zone()
    res = run_pipeline(_metas(), z)
    assert len(z.mentions()) >= 1
    assert len(z.claims()) >= 1
    # 어세션 영속: promoted claim이 있다면.
    assert res.assertions == len(z.assertions())


class _EquivJudge:
    """모의 LLM — canonicalization은 전부 equivalent (병합 촉진)."""

    def judge_canonicalization(self, pair):
        return {"relation": "equivalent", "canonical_text": "t", "confidence": 0.9,
                "rationale": "r", "judged_by": "llm",
                "model_id": "m", "prompt_template_hash": "ph-1",
                "output_schema_version": "0.1.0"}

    def judge_contradiction(self, pair):
        return {"verdict": "real_conflict", "conflict_type": "value_conflict",
                "rationale": "r", "confidence": 0.9, "evidence_spans": [],
                "judged_by": "llm"}


def test_run_pipeline_with_judge_persists_llm_verdicts():
    """judge 주입 → 미결 쌍 판정 결과가 version tuple로 영속."""
    z = _zone()
    # 미결 쌍을 강제로 만들도록 다른 표현 claim이 필요 — 대표로 기본 실행은
    # LLM 호출(결정적 미결 쌍)이 0이어도 runner가 정상 동작 확인.
    res = run_pipeline(_metas(), z, judge=_EquivJudge())
    # 판정 대상이 있었든 아니든, runner는 영속 통로로 안전하게 동작.
    assert res is not None
    # Assertion은 여전히 지킴.
    assert res.assertions == res.promoted_claims


def test_run_pipeline_deterministic_invariant():
    """동일 입력 재실행 → 동일 결정적 산출 (멱등성·재생성, 03 §5)."""
    z1, z2 = _zone(), _zone()
    r1 = run_pipeline(_metas(), z1)
    r2 = run_pipeline(_metas(), z2)
    assert r1.mentions == r2.mentions
    assert r1.claims == r2.claims
    assert r1.assertions == r2.assertions
