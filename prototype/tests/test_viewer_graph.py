"""영속 worker가 호출하는 read-only 조사 실행 결과 계약.

동기 HTTP route 제거 뒤에도 Planner → Runner → Synthesizer/Audit의 기존 동작을
직접 검증한다. graph·curated zone은 읽기 전용이다.
"""
from __future__ import annotations

from orc_citadel.curated_zone import CuratedZone
from orc_citadel.investigation_job import execute_read_only_investigation
from orc_citadel.pipeline_runner import run_pipeline

NVIDIA_HTML = b"""<html><head>
<title>NVIDIA Conference Call</title>
<meta property="article:published_time" content="2026-08-01T14:00:00+00:00"/>
</head><body><article>
<h1>NVIDIA Sets Conference Call</h1>
<p>NVIDIA will host a conference call on Wednesday, August 26.</p>
<p>NVIDIA powers the data center and announces new accelerator products.</p>
</article></body></html>"""


def _build_facade():
    zone = CuratedZone(":memory:")
    zone.initialize()
    run_pipeline([{
        "source_id": "test",
        "url": "https://e/n",
        "doc_id": "doc-viewer00000000000000001",
        "content": NVIDIA_HTML,
    }], zone)
    from orc_citadel.api_facade import ApiFacade
    from orc_citadel.graph_service import GraphService

    graph = GraphService()
    events = []
    for assertion in zone.assertions():
        for node, uid in (
            (assertion["subject_id"], f"n-{assertion['assertion_id']}"),
            (assertion["claim_id"], f"n2-{assertion['assertion_id']}"),
        ):
            events.append({
                "mutation_id": uid,
                "idempotency_key": uid,
                "op": "create_node",
                "payload": {"id": node, "props": {}},
            })
        events.append({
            "mutation_id": f"e-{assertion['assertion_id']}",
            "idempotency_key": f"e-{assertion['assertion_id']}",
            "op": "create_edge",
            "payload": {
                "type": "ABOUT",
                "from": assertion["subject_id"],
                "to": assertion["claim_id"],
                "props": {},
            },
        })
    graph.apply(events)
    return ApiFacade(zone, graph)


def test_investigation_result_includes_wargraph_subgraph():
    facade = _build_facade()
    subject = facade.zone.assertions()[0]["subject_id"]

    result = execute_read_only_investigation(facade, subject_id=subject)

    assert result["subject_id"] == subject
    subgraph = result["subgraph"]
    assert "entities" in subgraph and "relationships" in subgraph
    assert any(entity["id"] == subject for entity in subgraph["entities"])
    assert any(relation["from"] == subject for relation in subgraph["relationships"])
    assert "relation_paths" in result
    assert "independence_summary" in result
    assert result["audit"]["passed"] is True


def test_investigation_result_exposes_planned_subclaims():
    facade = _build_facade()
    subject = facade.zone.assertions()[0]["subject_id"]

    result = execute_read_only_investigation(facade, subject_id=subject)

    planned = result["planned_subclaims"]
    assert isinstance(planned, list) and planned
    assert all("known" in subclaim and "gap_reason" in subclaim for subclaim in planned)
    assert any(subclaim["known"] for subclaim in planned)


def test_investigation_accepts_free_text_question():
    facade = _build_facade()
    subject = facade.zone.assertions()[0]["subject_id"]

    result = execute_read_only_investigation(
        facade, question="NVIDIA 신제품 발표를 조사하라"
    )

    assert result["question"] == "NVIDIA 신제품 발표를 조사하라"
    assert any(row["known"] and row["subject_id"] == subject for row in result["resolved"])
    assert result["subject_id"] == subject
    assert any(entity["id"] == subject for entity in result["subgraph"]["entities"])


def test_investigation_unresolved_question_is_honest_empty():
    facade = _build_facade()

    result = execute_read_only_investigation(
        facade, question="알수없는대상 동향 조사"
    )

    assert result["resolved"] and not any(row["known"] for row in result["resolved"])
    assert result["coverage"] == 0.0
    assert result["statements"] == []
    assert result["subgraph"]["entities"] == []


def test_investigation_subject_input_still_works():
    facade = _build_facade()
    subject = facade.zone.assertions()[0]["subject_id"]

    result = execute_read_only_investigation(facade, subject_id=subject)

    assert result["subject_id"] == subject
    assert result["question"] is None


class _FakeLlm:
    model = "fake-model"
    provider = "fake"
    last_usage = {"input_tokens": 10, "output_tokens": 5}

    def __init__(self, payload=None, error=False):
        self._payload = payload
        self._error = error

    def messages_create(self, model, system, user, max_tokens, temperature):
        if self._error:
            raise RuntimeError("simulated")
        return self._payload


def test_investigation_llm_mode_keeps_only_verified_output():
    facade = _build_facade()
    subject = facade.zone.assertions()[0]["subject_id"]
    claim = facade.zone.assertions()[0]["claim_id"]
    payload = {"statements": [
        {"text": "LLM 요약 문장", "modality": "asserted", "claim_ref": claim},
        {"text": "전망 문장", "modality": "prediction"},
    ]}

    result = execute_read_only_investigation(
        facade, subject_id=subject, mode="llm", llm_client=_FakeLlm(payload)
    )

    assert result["mode"] == "llm"
    assert result["llm"]["used"] is True
    assert result["llm"]["usage"] == {"input_tokens": 10, "output_tokens": 5}
    assert [statement["text"] for statement in result["statements"]] == [
        "LLM 요약 문장", "전망 문장",
    ]
    assert result["audit"]["passed"] is True
    assert result["audit_trace"]["blocked_statements"] == []


def test_investigation_llm_failure_falls_back_deterministic():
    facade = _build_facade()
    subject = facade.zone.assertions()[0]["subject_id"]

    result = execute_read_only_investigation(
        facade, subject_id=subject, mode="llm", llm_client=_FakeLlm(error=True)
    )

    assert result["mode"] == "deterministic"
    assert result["llm"]["used"] is False
    assert result["llm"]["error"]
    assert result["statements"]


def test_investigation_default_mode_has_no_llm():
    facade = _build_facade()
    subject = facade.zone.assertions()[0]["subject_id"]

    result = execute_read_only_investigation(facade, subject_id=subject)

    assert result["mode"] == "deterministic"
    assert result["llm"] is None


def test_investigation_result_exposes_audit_trace():
    facade = _build_facade()
    subject = facade.zone.assertions()[0]["subject_id"]

    result = execute_read_only_investigation(facade, subject_id=subject)

    trace = result["audit_trace"]
    assert trace["linkage_ratio"] == 1.0
    assert trace["blocked_statements"] == []


def test_investigation_dashboard_uses_persisted_id():
    facade = _build_facade()
    subject = facade.zone.assertions()[0]["subject_id"]

    result = execute_read_only_investigation(
        facade, subject_id=subject, investigation_id="inv-persisted"
    )

    dashboard = result["dashboard"]
    assert dashboard["investigation_id"] == "inv-persisted"
    assert dashboard["evidence_coverage"]["measured"] is True
    assert "independent_evidence" in dashboard
    assert "cost" in dashboard and "latency_ms" in dashboard


def test_investigation_result_exposes_retrieval():
    facade = _build_facade()
    subject = facade.zone.assertions()[0]["subject_id"]

    result = execute_read_only_investigation(facade, subject_id=subject)

    assert isinstance(result["retrieved"], list)
    assert len(facade.zone.assertions()) >= 1
