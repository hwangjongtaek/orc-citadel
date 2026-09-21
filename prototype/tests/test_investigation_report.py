"""Audited investigation HTML report generation contract."""
from __future__ import annotations

import base64
import hashlib
import json
import re
from urllib.parse import quote

import pytest

from orc_citadel.investigation_report import (
    OUTPUT_SCHEMA_VERSION,
    PROMPT_TEMPLATE_HASH,
    TEMPLATE_VERSION,
    HtmlReportGenerator,
    default_report_profile,
    style_csp_hash,
)


def _canonical(value) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _result() -> dict:
    trace = {
        "trace": [
            {
                "statement_ref": "st0",
                "claim_ref": "clm/a 한글",
                "source_span": {
                    "doc_id": "doc-1",
                    "segment_id": "doc-1#p0",
                    "char_start": 4,
                    "char_end": 28,
                    "content_hash": "sha256:source",
                },
                "verified": True,
            },
            {
                "statement_ref": "st1",
                "claim_ref": None,
                "source_span": None,
                "verified": True,
            },
            {
                "statement_ref": "st2",
                "claim_ref": "clm-2",
                "source_span": {
                    "doc_id": "doc-2",
                    "segment_id": "doc-2#p3",
                    "char_start": 30,
                    "char_end": 57,
                    "content_hash": "sha256:source-2",
                },
                "verified": True,
            },
        ],
        "blocked_statements": [],
        "verifiable": 2,
        "linked": 2,
        "verified_statements": 2,
        "linkage_ratio": 1.0,
    }
    return {
        "subject_id": "org/A 한글",
        "question": "공급망 다변화가 진행되었는가?",
        "coverage": 0.67,
        "terminated_by": "budget",
        "gaps": ["subclaim-3"],
        "conclusion": {
            "value": 0.71,
            "evidence_count": 7,
            "independent_source_count": 2,
            "basis": "독립 출처와 반증을 함께 평가",
            "dimensions": {"support": 0.8, "contradiction": 0.2, "coverage": 0.67},
        },
        "statements": [
            {"text": "공급처가 둘로 늘었다.", "modality": "asserted", "claim_ref": "clm/a 한글"},
            {"text": "추가 공급처가 생길 수 있다.", "modality": "prediction", "claim_ref": None},
            {"text": "기존 계약은 유지되었다.", "modality": "fact", "claim_ref": "clm-2"},
        ],
        "open_questions": [
            {"subquestion": "양산 물량은 얼마인가?", "reason": "증거 부족", "coverage": 0.67}
        ],
        "counter_evidence": [
            {
                "contradiction_candidates": [
                    {
                        "claim_a": "clm/a 한글",
                        "claim_b": "clm-2",
                        "conflict_type": "scope",
                        "rationale": "제품 범위가 다르다.",
                        "judged_by": "deterministic",
                    }
                ]
            }
        ],
        "retrieved": [
            {
                "doc_id": "doc-3",
                "segment_id": "doc-3#p2",
                "score": 0.83,
                "retrieval_path": "bm25::context_window",
            }
        ],
        "timeline": [
            {
                "valid_at": "2026-06-01",
                "observed_at": "2026-06-03",
                "change": "계약 발표",
                "supersedes": None,
            }
        ],
        "independence_summary": {
            "evidence_count": 7,
            "independent_source_count": 2,
            "dedup_ratio": 0.71,
            "note": "독립 출처 2건 / 근거 7건",
        },
        "audit": {"passed": True, "violations": []},
        "audit_trace": trace,
    }


def _meta(result: dict) -> dict:
    return {
        "investigation_id": "inv/report 한글",
        "question": result["question"],
        "subject_id": result["subject_id"],
        "scope": {"depth": "standard"},
        "status": "completed",
        "generated_at": "2026-09-20T10:00:00Z",
        "as_of": "2026-09-19T00:00:00Z",
        "correlation_id": "corr-1",
        "version_tuple": {
            "ontology_version": "1.0.0",
            "schema_version": "1.0.0",
            "prompt_template_hash": "sha256:source-prompt",
            "model_id": "deterministic",
            "extraction_code_version": "1.0.0",
        },
        "audit_trace": result["audit_trace"],
    }


def test_offline_fallback_is_byte_deterministic_and_hash_verifiable():
    result = _result()
    meta = _meta(result)
    generator = HtmlReportGenerator(client=False)

    first = generator.generate(result, meta, default_report_profile())
    second = generator.generate(result, meta, default_report_profile())

    assert first == second
    assert first.generation_mode == "deterministic_fallback"
    assert first.fallback_reason == "llm_unavailable"
    assert first.content_hash == "sha256:" + hashlib.sha256(first.html_bytes).hexdigest()
    assert first.source_report_hash == "sha256:" + hashlib.sha256(
        _canonical({"report": result, "audit_trace": result["audit_trace"]})
    ).hexdigest()
    assert first.draft_hash == "sha256:" + hashlib.sha256(_canonical(first.draft_json)).hexdigest()
    assert first.as_store_dict()["html_bytes"] == first.html_bytes
    assert default_report_profile() == {
        "generation_mode": "llm_assisted",
        "template_version": TEMPLATE_VERSION,
        "output_schema_version": OUTPUT_SCHEMA_VERSION,
        "prompt_template_hash": PROMPT_TEMPLATE_HASH,
    }

    style = re.search(rb"<style>(.*?)</style>", first.html_bytes, re.DOTALL).group(1)
    assert style_csp_hash(TEMPLATE_VERSION) == base64.b64encode(hashlib.sha256(style).digest()).decode("ascii")


class _Client:
    provider = "test-provider"
    model = "test-model"
    last_usage = {"input_tokens": 12, "output_tokens": 8}

    def __init__(self, response):
        self.response = response
        self.calls = []

    def messages_create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _draft(result: dict, meta: dict, **updates) -> dict:
    source_hash = "sha256:" + hashlib.sha256(
        _canonical({"report": result, "audit_trace": result["audit_trace"]})
    ).hexdigest()
    draft = {
        "draft_schema_version": "1.0.0",
        "investigation_id": meta["investigation_id"],
        "template_version": TEMPLATE_VERSION,
        "source_report_hash": source_hash,
        "summary_statement_refs": ["st1"],
        "sections": [{"section_key": "limitations", "statement_refs": ["st2"]}],
    }
    draft.update(updates)
    return draft


def test_llm_may_only_reorder_refs_and_omitted_refs_append_to_findings():
    result = _result()
    meta = _meta(result)
    client = _Client(_draft(result, meta))

    artifact = HtmlReportGenerator(client).generate(result, meta, default_report_profile())

    assert artifact.generation_mode == "llm_assisted"
    assert artifact.fallback_reason is None
    assert artifact.provider == "test-provider"
    assert artifact.model_id == "test-model"
    assert artifact.usage == {"input_tokens": 12, "output_tokens": 8}
    assert artifact.draft_json["summary_statement_refs"] == ["st1"]
    assert artifact.draft_json["sections"] == [
        {"section_key": "limitations", "statement_refs": ["st2"]},
        {"section_key": "findings", "statement_refs": ["st0"]},
    ]
    prompt = json.loads(client.calls[0]["user"])
    assert prompt["statements"][0]["statement_ref"] == "st0"
    assert "source_span" not in prompt["statements"][0]
    assert "retrieved" not in prompt


def test_renderer_escapes_hostile_values_and_only_builds_encoded_internal_links():
    result = _result()
    result["question"] = '</h1><script src="https://evil.invalid/x"></script>'
    result["statements"][0]["text"] = '<img src=x onerror="alert(1)"> & evidence'
    meta = _meta(result)
    meta["question"] = result["question"]

    artifact = HtmlReportGenerator(client=False).generate(result, meta, default_report_profile())
    html = artifact.html_bytes.decode("utf-8")
    lowered = html.lower()

    assert "&lt;/h1&gt;&lt;script" in html
    assert "&lt;img src=x onerror=&quot;alert(1)&quot;&gt; &amp; evidence" in html
    assert f'/witnesses?claim={quote("clm/a 한글", safe="")}' in html
    assert f'/table?subject={quote("org/A 한글", safe="")}' in html
    assert f'/api/investigations/{quote(meta["investigation_id"], safe="")}/report' in html
    assert lowered.count("<style>") == 1
    for forbidden in ("<script", "<form", "<iframe", "<object", "<embed", "javascript:"):
        assert forbidden not in lowered
    assert not re.search(r"<[^>]+\son[a-z]+\s*=", lowered)


@pytest.mark.parametrize(
    "mutate,reason",
    [
        (lambda draft: draft.update({"extra": "new prose"}), "invalid_draft"),
        (lambda draft: draft.update({"summary_statement_refs": ["st999"]}), "invalid_draft"),
    ],
)
def test_invalid_or_unknown_reference_discards_entire_llm_draft(mutate, reason):
    result = _result()
    meta = _meta(result)
    draft = _draft(result, meta)
    mutate(draft)

    artifact = HtmlReportGenerator(_Client(draft)).generate(result, meta, default_report_profile())

    assert artifact.generation_mode == "deterministic_fallback"
    assert artifact.fallback_reason == reason
    assert set(artifact.draft_json["summary_statement_refs"]) <= {"st0", "st1", "st2"}
    assert "st999" not in json.dumps(artifact.draft_json)


def test_unverified_reference_and_outer_audit_mismatch_use_audit_rejected_fallback():
    result = _result()
    result["audit_trace"]["trace"][2]["verified"] = False
    result["audit_trace"]["linked"] = 1
    result["audit_trace"]["verified_statements"] = 1
    meta = _meta(result)
    meta["audit_trace"] = json.loads(json.dumps(result["audit_trace"]))
    draft = _draft(result, meta, summary_statement_refs=["st2"])

    artifact = HtmlReportGenerator(_Client(draft)).generate(result, meta, default_report_profile())
    assert artifact.fallback_reason == "audit_rejected"
    assert "st2" not in json.dumps(artifact.draft_json)

    inconsistent = _meta(_result())
    inconsistent["audit_trace"]["trace"][0]["claim_ref"] = "different-claim"
    artifact = HtmlReportGenerator(client=False).generate(_result(), inconsistent, default_report_profile())
    assert artifact.fallback_reason == "audit_rejected"


def test_modality_and_provenance_invariants_block_ineligible_statements():
    result = _result()
    result["statements"][0]["claim_ref"] = None
    result["audit_trace"]["trace"][1]["claim_ref"] = "invented"
    meta = _meta(result)

    artifact = HtmlReportGenerator(client=False).generate(result, meta, default_report_profile())

    assert artifact.fallback_reason == "audit_rejected"
    selected = artifact.draft_json["summary_statement_refs"] + [
        ref for section in artifact.draft_json["sections"] for ref in section["statement_refs"]
    ]
    assert "st0" not in selected
    assert "st1" not in selected


def test_provider_failure_falls_back_honestly_without_losing_provider_metadata():
    result = _result()
    artifact = HtmlReportGenerator(_Client(RuntimeError("provider down"))).generate(
        result, _meta(result), default_report_profile()
    )

    assert artifact.generation_mode == "deterministic_fallback"
    assert artifact.fallback_reason == "llm_provider_error"
    assert artifact.provider == "test-provider"
    assert artifact.model_id == "test-model"


def test_html_larger_than_one_mib_is_rejected_not_truncated():
    result = _result()
    result["statements"][0]["text"] = "x" * 600_000
    meta = _meta(result)

    with pytest.raises(ValueError, match="1 MiB"):
        HtmlReportGenerator(client=False).generate(result, meta, default_report_profile())


def test_oversized_source_is_rejected_before_calling_provider():
    result = _result()
    result["statements"][0]["text"] = "x" * 800_000
    client = _Client(_draft(_result(), _meta(_result())))

    with pytest.raises(ValueError, match="source exceeds 768 KiB"):
        HtmlReportGenerator(client).generate(
            result,
            _meta(result),
            default_report_profile(),
        )

    assert client.calls == []
