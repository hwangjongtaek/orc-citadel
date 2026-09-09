"""P1 트랙 a — viewer 조사 그래프(War Table) 렌더링 데이터.

`_api_investigate` 응답이 조사 subgraph(entities·relationships·relation_paths·
independence_summary)를 포함하는지 검증 — browser War Table 렌더링의 데이터 계약.
read-only 결정적 (불변식 §3-3).
"""
from __future__ import annotations

import json
import types

from orc_citadel.curated_zone import CuratedZone
from orc_citadel.pipeline_runner import run_pipeline
from orc_citadel.viewer import Handler

NVIDIA_HTML = b"""<html><head>
<title>NVIDIA Conference Call</title>
<meta property="article:published_time" content="2026-08-01T14:00:00+00:00"/>
</head><body><article>
<h1>NVIDIA Sets Conference Call</h1>
<p>NVIDIA will host a conference call on Wednesday, August 26.</p>
<p>NVIDIA powers the data center and announces new accelerator products.</p>
</article></body></html>"""


def _build_facade():
    from orc_citadel.viewer import _build

    # _build() 는 Module-level DB(실 data/duckdb)를 씀 — 여기선 인메모리 파이프라인으로 대체.
    z = CuratedZone(":memory:")
    z.initialize()
    run_pipeline([{"source_id": "test", "url": "https://e/n",
                   "doc_id": "doc-viewer00000000000000001", "content": NVIDIA_HTML}], z)
    from orc_citadel.api_facade import ApiFacade
    from orc_citadel.graph_service import GraphService

    g = GraphService()
    events = []
    for a in z.assertions():
        for seq, (node, uid) in enumerate(((a["subject_id"], f"n-{a['assertion_id']}"),
                                           (a["claim_id"], f"n2-{a['assertion_id']}"))):
            events.append({"mutation_id": uid, "idempotency_key": uid,
                           "op": "create_node", "payload": {"id": node, "props": {}}})
        events.append({"mutation_id": f"e-{a['assertion_id']}",
                       "idempotency_key": f"e-{a['assertion_id']}",
                       "op": "create_edge",
                       "payload": {"type": "ABOUT", "from": a["subject_id"],
                                   "to": a["claim_id"], "props": {}}})
    g.apply(events)
    return ApiFacade(z, g)


def test_investigate_response_includes_wargraph_subgraph():
    """_api_investigate 가 subgraph(War Table 데이터) 를 응답에 포함."""
    facade = _build_facade()
    subj = facade.zone.assertions()[0]["subject_id"]
    # Handler._api_investigate 는 self.facade 만 사용 — stub self 로 unbound 호출.
    self = types.SimpleNamespace(facade=facade)
    resp = json.loads(Handler._api_investigate(self, {"subject": subj}))
    assert resp["subject_id"] == subj
    # War Table — 조사 subgraph (entities·relationships) + relation_paths + independence
    sg = resp["subgraph"]
    assert "entities" in sg and "relationships" in sg
    assert any(e["id"] == subj for e in sg["entities"])
    assert any(rl["from"] == subj for rl in sg["relationships"])
    assert "relation_paths" in resp
    assert "independence_summary" in resp
    assert resp["audit"]["passed"] is True


def test_investigate_response_exposes_planned_subclaims():
    """_api_investigate 가 Planner(07 §3.2)의 subclaim 트리를 응답에 노출."""
    facade = _build_facade()
    subj = facade.zone.assertions()[0]["subject_id"]
    self = types.SimpleNamespace(facade=facade)
    resp = json.loads(Handler._api_investigate(self, {"subject": subj}))
    assert "planned_subclaims" in resp
    planned = resp["planned_subclaims"]
    assert isinstance(planned, list) and planned
    # known/gap 라벨 필수 (07 §3.2 불변식) — 그래프 지식이면 known.
    assert all("known" in p and "gap_reason" in p for p in planned)
    assert any(p["known"] for p in planned)


def test_investigate_accepts_free_text_question():
    """`?question=` — 자유 질문을 entity name 으로 해소해 조사한다 (W1).

    파이프라인이 만든 entities 표면형('NVIDIA')이 질문에 등장 → org-id 해소 →
    known subject 를 seed 로 조사·보고서·subgraph 가 채워진다.
    """
    facade = _build_facade()
    subj = facade.zone.assertions()[0]["subject_id"]
    self = types.SimpleNamespace(facade=facade)
    resp = json.loads(Handler._api_investigate(
        self, {"question": "NVIDIA 신제품 발표를 조사하라"}))
    assert resp["question"] == "NVIDIA 신제품 발표를 조사하라"
    assert any(r["known"] and r["subject_id"] == subj for r in resp["resolved"])
    # 해소된 known subject 가 조사 seed — 기존 subject= 경로와 같은 산출 형태.
    assert resp["subject_id"] == subj
    assert any(e["id"] == subj for e in resp["subgraph"]["entities"])


def test_investigate_unresolved_question_is_honest_empty():
    """해소 실패 질문 — 가공 없이 gap·빈 산출 (§6.2), 500 아님."""
    facade = _build_facade()
    self = types.SimpleNamespace(facade=facade)
    resp = json.loads(Handler._api_investigate(
        self, {"question": "알수없는대상 동향 조사"}))
    assert resp["resolved"] and not any(r["known"] for r in resp["resolved"])
    assert resp["coverage"] == 0.0
    assert resp["statements"] == []
    assert resp["subgraph"]["entities"] == []


def test_investigate_subject_param_still_works():
    """기존 `?subject=` 계약 유지 — question 미지정 시 동작 불변."""
    facade = _build_facade()
    subj = facade.zone.assertions()[0]["subject_id"]
    self = types.SimpleNamespace(facade=facade)
    resp = json.loads(Handler._api_investigate(self, {"subject": subj}))
    assert resp["subject_id"] == subj
    assert resp["question"] is None


# --- LLM 종합 모드 (W2 — mode=llm 옵트인·evidence-first 유지) ---------------------


class _FakeLlm:
    model = "fake-model"
    provider = "fake"
    last_usage = {"input_tokens": 10, "output_tokens": 5}

    def __init__(self, payload=None, error=False):
        self._payload, self._error = payload, error

    def messages_create(self, model, system, user, max_tokens, temperature):
        if self._error:
            raise RuntimeError("simulated")
        return self._payload


def test_investigate_mode_llm_replaces_statements_with_verified_llm_output():
    """mode=llm — LLM 문장으로 교체하되 Audit §3.9 역추적 통과분만 싣는다."""
    facade = _build_facade()
    subj = facade.zone.assertions()[0]["subject_id"]
    real_claim = facade.zone.assertions()[0]["claim_id"]
    payload = {"statements": [
        {"text": "LLM 요약 문장", "modality": "asserted", "claim_ref": real_claim},
        {"text": "전망 문장", "modality": "prediction"},
    ]}
    self = types.SimpleNamespace(facade=facade, llm_client=_FakeLlm(payload))
    resp = json.loads(Handler._api_investigate(
        self, {"subject": subj, "mode": "llm"}))
    assert resp["mode"] == "llm"
    assert resp["llm"]["used"] is True
    assert resp["llm"]["usage"] == {"input_tokens": 10, "output_tokens": 5}
    assert [s["text"] for s in resp["statements"]] == ["LLM 요약 문장", "전망 문장"]
    # LLM 문장도 §3.9 역추적 대상 — audit 는 최종 문장 기준.
    assert resp["audit"]["passed"] is True
    assert resp["audit_trace"]["blocked_statements"] == []


def test_investigate_mode_llm_failure_falls_back_deterministic():
    """LLM 오류 — 결정적 문장 유지 + llm.used=False 정직 표기 (500 아님)."""
    facade = _build_facade()
    subj = facade.zone.assertions()[0]["subject_id"]
    self = types.SimpleNamespace(facade=facade, llm_client=_FakeLlm(error=True))
    resp = json.loads(Handler._api_investigate(
        self, {"subject": subj, "mode": "llm"}))
    assert resp["mode"] == "deterministic"
    assert resp["llm"]["used"] is False and resp["llm"]["error"]
    assert resp["statements"], "결정적 문장이 유지되어야 한다"


def test_investigate_default_mode_has_no_llm():
    """mode 미지정 — 기존 결정적 경로 그대로, llm 필드는 None."""
    facade = _build_facade()
    subj = facade.zone.assertions()[0]["subject_id"]
    self = types.SimpleNamespace(facade=facade)
    resp = json.loads(Handler._api_investigate(self, {"subject": subj}))
    assert resp["mode"] == "deterministic"
    assert resp["llm"] is None


def test_investigate_response_exposes_audit_trace():
    """_api_investigate 가 §3.9 역추적 trace(연결률 = 1.0)를 응답에 노출."""
    facade = _build_facade()
    subj = facade.zone.assertions()[0]["subject_id"]
    self = types.SimpleNamespace(facade=facade)
    resp = json.loads(Handler._api_investigate(self, {"subject": subj}))
    assert "audit_trace" in resp
    tr = resp["audit_trace"]
    # pipeline 계약(§8.2 ADR-305) — 모든 검증가능 문장이 span까지 역추적.
    assert tr["linkage_ratio"] == 1.0
    assert tr["blocked_statements"] == []


def test_investigate_response_exposes_d8_dashboard():
    """_api_investigate 가 D8 Investigation 대시보드(coverage·독립·비용·latency)를 노출."""
    facade = _build_facade()
    subj = facade.zone.assertions()[0]["subject_id"]
    self = types.SimpleNamespace(facade=facade)
    resp = json.loads(Handler._api_investigate(self, {"subject": subj}))
    assert "dashboard" in resp
    d = resp["dashboard"]
    # D8 — investigation_id 분해 + evidence coverage + 독립 증거 수 (11 §2.2).
    assert "investigation_id" in d
    assert d["evidence_coverage"]["measured"] is True
    assert "independent_evidence" in d
    assert "cost" in d and "latency_ms" in d


def test_investigate_response_exposes_retrieval():
    """_api_investigate 가 SEARCH 스테이지의 retrieved 후보를 응답에 노출 (07 §4)."""
    facade = _build_facade()
    subj = facade.zone.assertions()[0]["subject_id"]
    self = types.SimpleNamespace(facade=facade)
    resp = json.loads(Handler._api_investigate(self, {"subject": subj}))
    assert "retrieved" in resp
    assert isinstance(resp["retrieved"], list)
    # read-only — retrieved는 조회 산출물, 응답이 zone을 수정하지 않음.
    assert len(facade.zone.assertions()) >= 1
