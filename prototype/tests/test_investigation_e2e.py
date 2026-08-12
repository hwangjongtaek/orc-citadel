"""P1 트랙 C — 5개 조사 질문 end-to-end (design 07 §4, 09 §3) + DoD ②.

pipeline(run_pipeline) 결과 → assertions → InvestigationRunner → Synthesizer 를 잇는
end-to-end 드라이버 — 5개 조사 질문(subclaim) 정의, 조사 루프 실행, 보고서가
**검증 가능한 문장(claim_ref, evidence-first)** 을 산출하는지 검증.
"""
from __future__ import annotations

from orc_citadel.api_facade import ApiFacade
from orc_citadel.curated_zone import CuratedZone
from orc_citadel.investigation import Subclaim
from orc_citadel.investigation_runner import InvestigationRunner
from orc_citadel.pipeline_runner import run_pipeline
from orc_citadel.synthesis import Synthesizer

NVIDIA_HTML = b"""<html><head>
<title>NVIDIA Conference Call</title>
<meta property="article:published_time" content="2026-08-01T14:00:00+00:00"/>
</head><body><article>
<h1>NVIDIA Sets Conference Call</h1>
<p>NVIDIA will host a conference call on Wednesday, August 26.</p>
<p>NVIDIA powers the data center and announces new accelerator products.</p>
</article></body></html>"""


def _metas():
    return {"source_id": "test", "url": "https://test.example/nvidia",
            "doc_id": "doc-e2e0000000000000000000001", "content": NVIDIA_HTML}


def _graph(z):
    """assertions → ABOUT 그래프 (subject→claim) — 조사 탐색용."""
    from orc_citadel.graph_service import GraphService

    g = GraphService()
    events = []
    for a in z.assertions():
        events.append({"mutation_id": f"m-{a['assertion_id']}",
                       "idempotency_key": f"k-{a['assertion_id']}",
                       "op": "create_node",
                       "payload": {"id": a["claim_id"], "props": {}}})
        events.append({"mutation_id": f"m2-{a['assertion_id']}",
                       "idempotency_key": f"k2-{a['assertion_id']}",
                       "op": "create_node",
                       "payload": {"id": a["subject_id"], "props": {}}})
        events.append({"mutation_id": f"m3-{a['assertion_id']}",
                       "idempotency_key": f"k3-{a['assertion_id']}",
                       "op": "create_edge",
                       "payload": {"type": "ABOUT", "from": a["subject_id"],
                                   "to": a["claim_id"], "props": {}}})
    g.apply(events)
    return g


# 5개 조사 질문 (07 §4) — subject 기반 subclaim.
FIVE_QUESTIONS = [
    Subclaim("q1", "announces?", subject_id="org-nvidia"),
    Subclaim("q2", "powers?", subject_id="org-nvidia"),
    Subclaim("q3", "hosts?", subject_id="org-nvidia"),
    Subclaim("q4", "announces?", subject_id="org-nvidia"),
    Subclaim("q5", "supplies?", subject_id="org-nvidia"),
]


def test_five_questions_end_to_end_report_with_claim_ref():
    """pipeline → 5개 질문 조사 → 보고서가 claim_ref(검증 가능 문장) 산출 (DoD ②)."""
    z = CuratedZone()
    z.initialize()
    res = run_pipeline([_metas()], z)
    assert res.assertions >= 1

    g = _graph(z)
    inv = InvestigationRunner(z, g).run(FIVE_QUESTIONS)
    report = Synthesizer(z).synthesize(inv, subject_id="org-nvidia")

    assert report.subject_id == "org-nvidia"
    # evidence-first 불변식 — audit passed (무출처 asserted 없음).
    assert report.audit["passed"] is True
    assert report.audit["violations"] == []
    # 조사 루프가 종료 기준(coverage 등)에 도달했다.
    assert inv.terminated_by in ("coverage", "no_new_evidence", "budget")
    # 산출된 asserted 문장이 있으면 claim_ref 필수 (DoD ②, evidence-first).
    for st in report.statements:
        if st["modality"] in ("fact", "asserted"):
            assert st.get("claim_ref"), f"asserted 문장은 claim_ref 필수: {st}"

