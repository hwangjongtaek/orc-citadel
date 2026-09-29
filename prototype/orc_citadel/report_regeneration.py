"""완료됐지만 HTML artifact 가 없는 조사의 리포트 재작성.

조사당 artifact 는 불변 1개다. 이 모듈은 **없는 경우에만** 만든다 — 기존
artifact 를 교체하지 않으며, 원본 report/audit_trace 도 바꾸지 않는다. 생성은
최초 생성과 같은 `HtmlReportGenerator` 를 쓰므로 LLM 이 없으면 deterministic
fallback 이 정직하게 기록된다.
"""
from __future__ import annotations

from .investigation_report import HtmlReportGenerator, default_report_profile


def regenerate_report(store, investigation_id: str, *, generator=None) -> str:
    """결과: attached | exists | not_found | not_completed | source_missing | source_changed"""
    source = store.get_regeneration_source(investigation_id)
    if source is None:
        return "not_found"
    if source["status"] != "completed":
        return "not_completed"
    if source["has_artifact"]:
        return "exists"
    report = source["report"]
    if not isinstance(report, dict):
        return "source_missing"
    audit_trace = source["audit_trace"]
    if not isinstance(audit_trace, dict):
        audit_trace = report.get("audit_trace", {})
    profile = source["report_profile"] or default_report_profile()
    meta = {
        "investigation_id": investigation_id,
        "question": source["question"],
        "subject_id": source["subject_id"],
        "scope": source["scope"],
        "mode": source["mode"],
        "status": "completed",
        "version_tuple": source["version_tuple"],
        "correlation_id": source["correlation_id"],
        "audit_trace": audit_trace,
    }
    artifact = (generator or HtmlReportGenerator()).generate(report, meta, profile)
    return store.attach_report_artifact(
        investigation_id, artifact=artifact.as_store_dict(), report_profile=profile)
