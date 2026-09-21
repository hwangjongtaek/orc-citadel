"""Secure, deterministic HTML artifacts for audited investigation results.

The optional LLM is only an editor of opaque ``stN`` references.  Canonical
statement text, provenance links, document structure, and all markup remain
owned by this module.
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
from dataclasses import dataclass
from urllib.parse import quote

from orc_citadel.llm_providers import build_llm_client

TEMPLATE_VERSION = "citadel-report-1"
OUTPUT_SCHEMA_VERSION = "report-draft/1.0.0"
_DRAFT_SCHEMA_VERSION = "1.0.0"
_MAX_HTML_BYTES = 1024 * 1024
_MAX_SOURCE_REPORT_BYTES = 768 * 1024
_MAX_META_BYTES = 128 * 1024
_MAX_PROMPT_BYTES = 896 * 1024
_SECTION_KEYS = ("findings", "counter_evidence", "timeline", "limitations")
_ALLOWED_MODALITIES = ("fact", "asserted", "prediction", "opinion")

_SYSTEM_PROMPT = """You edit an already-audited investigation report.
Return exactly one JSON object and no markdown or explanation. You may only
select, order, and group the supplied statement_ref values. Never write prose,
HTML, CSS, claims, confidence values, headings, or evidence judgments.
Required schema (no additional properties):
{"draft_schema_version":"1.0.0","investigation_id":"...","template_version":"citadel-report-1","source_report_hash":"sha256:...","summary_statement_refs":["st0"],"sections":[{"section_key":"findings|counter_evidence|timeline|limitations","statement_refs":["st1"]}]}
Use at most five summary refs, one to eight sections, unique section_key values,
and never repeat a statement_ref.
"""
PROMPT_TEMPLATE_HASH = "sha256:" + hashlib.sha256(_SYSTEM_PROMPT.encode("utf-8")).hexdigest()

# This is the one and only style block emitted by the renderer.  CSP hashes the
# exact UTF-8 bytes between the style tags (not the tags themselves).
_STYLE = """
:root{color-scheme:dark;--void:#07111c;--night:#0d1b2a;--card:#111820;--stone:#26313a;--line:#3a4651;--text:#d6ccb8;--muted:#a69d8d;--green:#45e06f;--amber:#ffb13b;--red:#e05252;--parchment:#c8b58e;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
*{box-sizing:border-box}html{background:var(--void);color:var(--text);line-height:1.55}body{margin:0;background:var(--void)}a{color:var(--green);text-underline-offset:.18em}header,main,footer{width:min(70rem,calc(100% - 2rem));margin-inline:auto}header{padding:3rem 0 2rem;border-bottom:1px solid var(--line)}main{padding:1.5rem 0 3rem}footer{padding:1.5rem 0 3rem;border-top:1px solid var(--line);color:var(--muted);font-size:.8rem}h1,h2,h3{line-height:1.2;margin:0 0 .75rem}h1{font-size:clamp(1.8rem,4vw,3rem)}h2{font-size:1.35rem;color:var(--parchment)}h3{font-size:1rem}p{margin:.4rem 0 1rem}.eyebrow,.muted,dt{color:var(--muted)}.eyebrow{text-transform:uppercase;letter-spacing:.12em;font-size:.72rem;font-weight:700}.meta,.kpis,.audit-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(10rem,1fr));gap:.75rem;margin-top:1.25rem}.card,section{background:var(--card);border:1px solid var(--line);border-radius:.35rem}.card{padding:1rem}section{padding:1.25rem;margin:1rem 0}article{border-left:.2rem solid var(--line);padding:.25rem 0 .25rem 1rem;margin:1rem 0}.verified{border-left-color:var(--green)}.badge{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:.12rem .55rem;margin:0 .35rem .25rem 0;color:var(--muted);font-size:.72rem;font-weight:700}.badge.verified{border-color:var(--green);color:var(--green)}.badge.warning{border-color:var(--amber);color:var(--amber)}dl{margin:.25rem 0}dt{font-size:.72rem;text-transform:uppercase;letter-spacing:.08em}dd{margin:0 0 .6rem;overflow-wrap:anywhere}.toc{display:flex;gap:.5rem 1rem;flex-wrap:wrap;margin-top:1.25rem}.toc a{font-size:.8rem}table{width:100%;border-collapse:collapse;margin:.75rem 0;font-size:.9rem}th,td{text-align:left;vertical-align:top;border-bottom:1px solid var(--line);padding:.55rem;overflow-wrap:anywhere}th{color:var(--muted)}code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:.85em;overflow-wrap:anywhere}.empty{color:var(--muted);font-style:italic}.skip{position:absolute;left:-10000px;top:auto}.skip:focus{left:1rem;top:1rem;background:var(--card);padding:.5rem;z-index:1}
@media(max-width:42rem){header,main,footer{width:min(100% - 1rem,70rem)}header{padding-top:2rem}section{padding:1rem}.table-scroll{overflow-x:auto}}
@media print{:root{color-scheme:light}html,body{background:#fff;color:#111}header,main,footer{width:100%}.card,section{background:#fff;border-color:#777}a{color:#0645ad}.toc,.screen-only{display:none}section,article,tr{break-inside:avoid}#method{break-before:page}a[href^="/witnesses"]::after,a[href^="/table"]::after{content:" (" attr(href) ")";font-size:.75em}*{box-shadow:none!important}}
"""


def _canonical_bytes(value) -> bytes:
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("report data must be canonical JSON") from exc
    return text.encode("utf-8")


def _hash(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _json_copy(value):
    return json.loads(_canonical_bytes(value).decode("utf-8"))


def default_report_profile() -> dict:
    """Return a fresh, pinned report-generation profile for new jobs."""
    return {
        "generation_mode": "llm_assisted",
        "template_version": TEMPLATE_VERSION,
        "output_schema_version": OUTPUT_SCHEMA_VERSION,
        "prompt_template_hash": PROMPT_TEMPLATE_HASH,
    }


def style_csp_hash(template_version: str) -> str:
    """Return the base64 SHA-256 digest for this template's exact style bytes."""
    if template_version != TEMPLATE_VERSION:
        raise ValueError(f"unsupported report template: {template_version}")
    return base64.b64encode(hashlib.sha256(_STYLE.encode("utf-8")).digest()).decode("ascii")


@dataclass(frozen=True)
class RenderedArtifact:
    html_bytes: bytes
    content_hash: str
    source_report_hash: str
    draft_json: dict
    draft_hash: str
    generation_mode: str
    fallback_reason: str | None
    template_version: str
    output_schema_version: str
    provider: str | None
    model_id: str | None
    prompt_template_hash: str | None
    usage: dict
    audit_summary: dict

    def as_store_dict(self) -> dict:
        """Return only generator-owned columns; the store adds DB-owned metadata."""
        return {
            "html_bytes": self.html_bytes,
            "content_hash": self.content_hash,
            "source_report_hash": self.source_report_hash,
            "draft_json": _json_copy(self.draft_json),
            "draft_hash": self.draft_hash,
            "generation_mode": self.generation_mode,
            "fallback_reason": self.fallback_reason,
            "template_version": self.template_version,
            "output_schema_version": self.output_schema_version,
            "provider": self.provider,
            "model_id": self.model_id,
            "prompt_template_hash": self.prompt_template_hash,
            "usage": _json_copy(self.usage),
            "audit_summary": _json_copy(self.audit_summary),
        }


def _escape(value) -> str:
    if value is None or value == "":
        text = "unavailable"
    elif isinstance(value, (dict, list)):
        text = _canonical_bytes(value).decode("utf-8")
    elif isinstance(value, bool):
        text = "true" if value else "false"
    else:
        text = str(value)
    return html.escape(text, quote=True)


def _internal_url(path: str, value: object) -> str:
    return html.escape(path + quote(str(value), safe=""), quote=True)


def _valid_span(span) -> bool:
    if not isinstance(span, dict):
        return False
    for key in ("doc_id", "segment_id", "content_hash"):
        if not isinstance(span.get(key), str) or not span[key]:
            return False
    start, end = span.get("char_start"), span.get("char_end")
    return (
        isinstance(start, int)
        and not isinstance(start, bool)
        and isinstance(end, int)
        and not isinstance(end, bool)
        and 0 <= start <= end
    )


def _same_json(left, right) -> bool:
    try:
        return _canonical_bytes(left) == _canonical_bytes(right)
    except ValueError:
        return False


def _audit_statements(result: dict, meta: dict, audit_trace: dict):
    statements = result.get("statements")
    rows = audit_trace.get("trace") if isinstance(audit_trace, dict) else None
    statements = statements if isinstance(statements, list) else []
    rows = rows if isinstance(rows, list) else []
    all_refs: dict[str, dict] = {}
    eligible: dict[str, dict] = {}
    rejected = not isinstance(result.get("statements", []), list)
    blocked = 0
    verifiable = 0
    linked = 0

    if len(rows) != len(statements):
        rejected = True
        blocked += abs(len(rows) - len(statements)) or 1

    for index, statement in enumerate(statements):
        ref = f"st{index}"
        row = rows[index] if index < len(rows) else None
        if isinstance(statement, dict):
            all_refs[ref] = statement
        else:
            rejected = True
            blocked += 1
            continue
        modality = statement.get("modality")
        claim_ref = statement.get("claim_ref")
        if modality in ("fact", "asserted"):
            verifiable += 1
        valid = (
            isinstance(statement.get("text"), str)
            and bool(statement["text"].strip())
            and modality in _ALLOWED_MODALITIES
            and isinstance(row, dict)
            and row.get("statement_ref") == ref
            and row.get("verified") is True
            and row.get("claim_ref") == claim_ref
        )
        if modality in ("fact", "asserted"):
            valid = valid and isinstance(claim_ref, str) and bool(claim_ref) and _valid_span(
                row.get("source_span") if isinstance(row, dict) else None
            )
            if valid:
                linked += 1
        elif modality in ("prediction", "opinion"):
            valid = valid and claim_ref is None and row.get("source_span") is None
        else:
            valid = False
        if valid:
            eligible[ref] = {"statement": statement, "trace": row}
        else:
            rejected = True
            blocked += 1

    supplied_blocked = audit_trace.get("blocked_statements", []) if isinstance(audit_trace, dict) else []
    if not isinstance(supplied_blocked, list):
        rejected = True
        blocked += 1
    elif supplied_blocked:
        rejected = True
        blocked += len(supplied_blocked)
    for key, actual in (("verifiable", verifiable), ("linked", linked)):
        supplied = audit_trace.get(key) if isinstance(audit_trace, dict) else None
        if supplied is not None and (not isinstance(supplied, int) or isinstance(supplied, bool) or supplied != actual):
            rejected = True
            blocked += 1
    audit_verdict = result.get("audit")
    if isinstance(audit_verdict, dict) and (
        audit_verdict.get("passed") is False or bool(audit_verdict.get("violations"))
    ):
        rejected = True
        blocked += max(1, len(audit_verdict.get("violations") or []))

    embedded = result.get("audit_trace")
    outer = meta.get("audit_trace")
    if embedded is not None and outer is not None and not _same_json(embedded, outer):
        rejected = True
        blocked += 1
    for key in ("question", "subject_id"):
        if result.get(key) is not None and meta.get(key) is not None and result[key] != meta[key]:
            rejected = True
            blocked += 1

    summary = {"linked": linked, "verifiable": verifiable, "blocked": blocked}
    return all_refs, eligible, rejected, summary


def _fallback_draft(investigation_id: str, source_hash: str, eligible: dict) -> dict:
    refs = list(eligible)
    summary = refs[:5]
    return {
        "draft_schema_version": _DRAFT_SCHEMA_VERSION,
        "investigation_id": investigation_id,
        "template_version": TEMPLATE_VERSION,
        "source_report_hash": source_hash,
        "summary_statement_refs": summary,
        "sections": [{"section_key": "findings", "statement_refs": refs[5:]}],
    }


def _validate_draft(raw, investigation_id: str, source_hash: str, all_refs: dict, eligible: dict):
    required = {
        "draft_schema_version",
        "investigation_id",
        "template_version",
        "source_report_hash",
        "summary_statement_refs",
        "sections",
    }
    if not isinstance(raw, dict) or set(raw) != required:
        return None, "invalid_draft"
    if (
        raw.get("draft_schema_version") != _DRAFT_SCHEMA_VERSION
        or raw.get("investigation_id") != investigation_id
        or raw.get("template_version") != TEMPLATE_VERSION
        or raw.get("source_report_hash") != source_hash
    ):
        return None, "invalid_draft"
    summary = raw.get("summary_statement_refs")
    sections = raw.get("sections")
    if not isinstance(summary, list) or len(summary) > 5 or not isinstance(sections, list) or not 1 <= len(sections) <= 8:
        return None, "invalid_draft"

    seen_refs: set[str] = set()
    seen_sections: set[str] = set()
    for ref in summary:
        if not isinstance(ref, str) or ref in seen_refs:
            return None, "invalid_draft"
        if ref not in all_refs:
            return None, "invalid_draft"
        if ref not in eligible:
            return None, "audit_rejected"
        seen_refs.add(ref)
    normalized_sections = []
    for section in sections:
        if not isinstance(section, dict) or set(section) != {"section_key", "statement_refs"}:
            return None, "invalid_draft"
        key, refs = section.get("section_key"), section.get("statement_refs")
        if key not in _SECTION_KEYS or key in seen_sections or not isinstance(refs, list):
            return None, "invalid_draft"
        seen_sections.add(key)
        copied_refs = []
        for ref in refs:
            if not isinstance(ref, str) or ref in seen_refs:
                return None, "invalid_draft"
            if ref not in all_refs:
                return None, "invalid_draft"
            if ref not in eligible:
                return None, "audit_rejected"
            seen_refs.add(ref)
            copied_refs.append(ref)
        normalized_sections.append({"section_key": key, "statement_refs": copied_refs})

    omitted = [ref for ref in eligible if ref not in seen_refs]
    if omitted:
        findings = next((section for section in normalized_sections if section["section_key"] == "findings"), None)
        if findings is None:
            findings = {"section_key": "findings", "statement_refs": []}
            normalized_sections.append(findings)
        findings["statement_refs"].extend(omitted)
    return {
        "draft_schema_version": _DRAFT_SCHEMA_VERSION,
        "investigation_id": investigation_id,
        "template_version": TEMPLATE_VERSION,
        "source_report_hash": source_hash,
        "summary_statement_refs": list(summary),
        "sections": normalized_sections,
    }, None


def _prompt_payload(result: dict, meta: dict, source_hash: str, eligible: dict, audit_summary: dict) -> dict:
    statements = []
    for ref, item in eligible.items():
        statement = item["statement"]
        statements.append(
            {
                "statement_ref": ref,
                "text": statement["text"],
                "modality": statement["modality"],
                "claim_ref": statement.get("claim_ref"),
            }
        )
    return {
        "draft_schema_version": _DRAFT_SCHEMA_VERSION,
        "investigation_id": str(meta.get("investigation_id") or "unavailable"),
        "template_version": TEMPLATE_VERSION,
        "source_report_hash": source_hash,
        "question": meta.get("question", result.get("question")),
        "scope": meta.get("scope") or {},
        "conclusion": result.get("conclusion") or {},
        "statements": statements,
        "open_questions": result.get("open_questions") or [],
        "coverage": result.get("coverage"),
        "termination": result.get("terminated_by"),
        "independence_summary": result.get("independence_summary") or {},
        "timeline_available": isinstance(result.get("timeline"), list) and bool(result.get("timeline")),
        "audit_summary": audit_summary,
        "version_tuple": meta.get("version_tuple") or {},
    }


def _statement_article(ref: str, item: dict) -> str:
    statement, trace = item["statement"], item["trace"]
    modality = statement["modality"]
    parts = [
        '<article class="verified">',
        f'<span class="badge verified">{_escape(modality)}</span>',
        f'<span class="badge">{_escape(ref)}</span>',
        f'<p>{_escape(statement["text"])}</p>',
    ]
    claim_ref = statement.get("claim_ref")
    if claim_ref:
        parts.append(
            f'<p><a href="{_internal_url("/witnesses?claim=", claim_ref)}">Hall of Witnesses에서 근거 열기 · {_escape(claim_ref)}</a></p>'
        )
        span = trace.get("source_span") or {}
        parts.append(
            f'<p class="muted">source {_escape(span.get("doc_id"))} · {_escape(span.get("segment_id"))} · chars {_escape(span.get("char_start"))}–{_escape(span.get("char_end"))}</p>'
        )
    else:
        parts.append('<p class="muted">비검증 양태 문장 · provenance claim 없음</p>')
    parts.append("</article>")
    return "".join(parts)


def _table(headers: list[str], rows: list[list[object]]) -> str:
    if not rows:
        return '<p class="empty">사용 가능한 감사 데이터가 없습니다.</p>'
    head = "".join(f"<th scope=\"col\">{_escape(label)}</th>" for label in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{cell if isinstance(cell, _Markup) else _escape(cell)}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return f'<div class="table-scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


class _Markup(str):
    """Marker for renderer-owned, already-escaped internal markup."""


def _render_html(result: dict, meta: dict, draft: dict, eligible: dict, generation_mode: str, fallback_reason: str | None, provider, model_id, prompt_hash: str, audit_summary: dict, source_hash: str) -> bytes:
    investigation_id = str(meta.get("investigation_id") or "unavailable")
    question = meta.get("question", result.get("question"))
    subject = meta.get("subject_id", result.get("subject_id"))
    fallback_badge = fallback_reason or "none"
    summary_html = "".join(_statement_article(ref, eligible[ref]) for ref in draft["summary_statement_refs"])
    if not summary_html:
        summary_html = '<p class="empty">감사를 통과한 핵심 문장이 없습니다.</p>'

    section_titles = {
        "findings": "Findings · 조사 결과",
        "counter_evidence": "Counter-evidence · 반증",
        "timeline": "Timeline findings · 시간축 결과",
        "limitations": "Limitations · 한계",
    }
    finding_groups = []
    for section in draft["sections"]:
        articles = "".join(_statement_article(ref, eligible[ref]) for ref in section["statement_refs"])
        if not articles:
            articles = '<p class="empty">선택된 문장이 없습니다.</p>'
        finding_groups.append(
            f'<article><h3>{section_titles[section["section_key"]]}</h3>{articles}</article>'
        )

    evidence_rows = []
    for ref, item in eligible.items():
        statement, trace = item["statement"], item["trace"]
        if statement["modality"] not in ("fact", "asserted"):
            continue
        span = trace["source_span"]
        link = _Markup(
            f'<a href="{_internal_url("/witnesses?claim=", statement["claim_ref"])}">{_escape(statement["claim_ref"])}</a>'
        )
        evidence_rows.append([
            "SUPPORTS",
            statement["text"],
            f'{span["doc_id"]} · {span["segment_id"]} · {span["char_start"]}–{span["char_end"]}',
            link,
        ])
    contradictions = []
    raw_counter = result.get("counter_evidence")
    for group in raw_counter if isinstance(raw_counter, list) else []:
        candidates = group.get("contradiction_candidates") if isinstance(group, dict) else None
        for candidate in candidates if isinstance(candidates, list) else []:
            if isinstance(candidate, dict):
                contradictions.append([
                    "CONTRADICTS",
                    candidate.get("rationale"),
                    f'{candidate.get("claim_a") or "unavailable"} ↔ {candidate.get("claim_b") or "unavailable"}',
                    candidate.get("conflict_type"),
                ])

    timeline_rows = []
    timeline = result.get("timeline")
    for event in timeline if isinstance(timeline, list) else []:
        if isinstance(event, dict):
            timeline_rows.append([
                event.get("valid_at", event.get("valid_from")),
                event.get("observed_at"),
                event.get("change", event.get("event")),
                event.get("supersedes"),
            ])
    retrieval_rows = []
    retrieved = result.get("retrieved")
    for row in retrieved if isinstance(retrieved, list) else []:
        if isinstance(row, dict):
            retrieval_rows.append([
                row.get("doc_id"),
                row.get("segment_id"),
                row.get("score"),
                row.get("retrieval_path"),
            ])

    gap_rows = []
    open_questions = result.get("open_questions")
    for entry in open_questions if isinstance(open_questions, list) else []:
        if isinstance(entry, dict):
            gap_rows.append([entry.get("subquestion"), entry.get("reason"), entry.get("coverage")])
        else:
            gap_rows.append([entry, "unavailable", result.get("coverage")])
    gaps = result.get("gaps")
    known_questions = {str(row[0]) for row in gap_rows}
    for gap in gaps if isinstance(gaps, list) else []:
        if str(gap) not in known_questions:
            gap_rows.append([gap, "조사 coverage gap", result.get("coverage")])

    confidence = result.get("conclusion") if isinstance(result.get("conclusion"), dict) else {}
    dimensions = confidence.get("dimensions") if isinstance(confidence.get("dimensions"), dict) else {}
    dimension_rows = [[key, dimensions[key]] for key in sorted(dimensions)]
    independence = result.get("independence_summary") if isinstance(result.get("independence_summary"), dict) else {}
    version_tuple = meta.get("version_tuple") if isinstance(meta.get("version_tuple"), dict) else {}
    version_rows = [[key, version_tuple[key]] for key in sorted(version_tuple)]
    termination = result.get("terminated_by")
    budget_note = '<p class="badge warning">예산 한도 도달로 종료됨 · 남은 gap을 확인하십시오.</p>' if termination == "budget" else ""
    json_url = _internal_url(f"/api/investigations/{quote(investigation_id, safe='')}/", "report")
    graph_link = (
        f'<a href="{_internal_url("/table?subject=", subject)}">War Table에서 subject 열기</a>'
        if subject not in (None, "")
        else '<span class="muted">subject unavailable</span>'
    )

    document = f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Investigation Report · {_escape(investigation_id)}</title><style>{_STYLE}</style></head><body>
<a class="skip screen-only" href="#executive-summary">본문으로 건너뛰기</a>
<header><p class="eyebrow">Campaign Ledger · Investigation Report</p><h1>{_escape(question)}</h1><p class="muted">Evidence first · audited investigation artifact</p>
<div class="meta"><div class="card"><dl><dt>Status</dt><dd>{_escape(meta.get("status") or "completed")}</dd><dt>Investigation</dt><dd><code>{_escape(investigation_id)}</code></dd></dl></div><div class="card"><dl><dt>Scope</dt><dd>{_escape(meta.get("scope") or {})}</dd><dt>As of</dt><dd>{_escape(meta.get("as_of"))}</dd></dl></div><div class="card"><dl><dt>Generated</dt><dd>{_escape(meta.get("generated_at"))}</dd><dt>Report mode</dt><dd>{_escape(generation_mode)} · fallback {_escape(fallback_badge)}</dd></dl></div></div>
<nav class="toc screen-only" aria-label="Report sections"><a href="#executive-summary">Summary</a><a href="#confidence">Confidence</a><a href="#findings">Findings</a><a href="#evidence">Evidence</a><a href="#timeline">Timeline</a><a href="#gaps">Gaps</a><a href="#method">Method &amp; Audit</a></nav></header>
<main>
<section id="executive-summary"><h2>Executive Summary · 감사 요약</h2>{summary_html}</section>
<section id="confidence"><h2>Confidence · 신뢰도</h2><div class="kpis"><div class="card"><dl><dt>Value</dt><dd>{_escape(confidence.get("value"))}</dd></dl></div><div class="card"><dl><dt>Evidence count</dt><dd>{_escape(confidence.get("evidence_count"))}</dd></dl></div><div class="card"><dl><dt>Independent sources</dt><dd>{_escape(confidence.get("independent_source_count", independence.get("independent_source_count")))}</dd></dl></div></div><p><strong>Basis:</strong> {_escape(confidence.get("basis"))}</p>{_table(["Dimension", "Value"], dimension_rows)}</section>
<section id="findings"><h2>Findings · 조사 결과</h2>{''.join(finding_groups) or '<p class="empty">감사를 통과한 조사 결과가 없습니다.</p>'}</section>
<section id="evidence"><h2>Supporting &amp; Contradicting Evidence · 근거와 반증</h2><h3>Supporting evidence</h3>{_table(["Relation", "Statement", "Source span", "Provenance"], evidence_rows)}<h3>Contradicting evidence</h3>{_table(["Relation", "Rationale", "Claims", "Type"], contradictions)}<p>{graph_link}</p></section>
<section id="timeline"><h2>Timeline &amp; Retrieval · 시간축과 검색</h2><h3>Timeline</h3>{_table(["Valid time", "Observed time", "Change", "Supersedes"], timeline_rows)}<h3>Retrieval facts</h3>{_table(["Document", "Segment", "Score", "Path"], retrieval_rows)}</section>
<section id="gaps"><h2>Gaps &amp; Open Questions · 공백과 후속 질문</h2>{budget_note}{_table(["Question or gap", "Reason", "Coverage"], gap_rows)}</section>
<section id="method"><h2>Method &amp; Audit · 방법과 감사</h2><div class="audit-grid"><div class="card"><dl><dt>Coverage</dt><dd>{_escape(result.get("coverage"))}</dd><dt>Termination</dt><dd>{_escape(termination)}</dd><dt>Independence</dt><dd>{_escape(independence.get("note"))}</dd></dl></div><div class="card"><dl><dt>Linked / verifiable / blocked</dt><dd>{_escape(audit_summary["linked"])} / {_escape(audit_summary["verifiable"])} / {_escape(audit_summary["blocked"])}</dd><dt>Generation</dt><dd>{_escape(generation_mode)} · {_escape(provider)} · {_escape(model_id)}</dd><dt>Prompt / template</dt><dd><code>{_escape(prompt_hash)}</code><br>{_escape(TEMPLATE_VERSION)} · {_escape(OUTPUT_SCHEMA_VERSION)}</dd></dl></div></div><h3>Version tuple</h3>{_table(["Axis", "Version"], version_rows)}<p><a href="{json_url}">원본 JSON report 열기</a></p></section>
</main>
<footer><p><code>{_escape(investigation_id)}</code> · correlation <code>{_escape(meta.get("correlation_id"))}</code> · generated {_escape(meta.get("generated_at"))} · {_escape(TEMPLATE_VERSION)}</p><p>source hash <code>{_escape(source_hash[:19])}</code> · content hash is SHA-256 of the exact stored bytes</p><p>Evidence first · generated from audited investigation data</p></footer>
</body></html>'''
    rendered = document.encode("utf-8")
    if len(rendered) > _MAX_HTML_BYTES:
        raise ValueError("rendered investigation report exceeds 1 MiB")
    return rendered


class HtmlReportGenerator:
    """Generate a reference-only draft and render an immutable HTML artifact."""

    def __init__(self, client=None) -> None:
        self._client = None if client is False else (build_llm_client() if client is None else client)

    def generate(self, result, investigation_meta, report_profile) -> RenderedArtifact:
        if not isinstance(result, dict) or not isinstance(investigation_meta, dict) or not isinstance(report_profile, dict):
            raise TypeError("result, investigation_meta, and report_profile must be dicts")
        if report_profile.get("template_version") != TEMPLATE_VERSION:
            raise ValueError("unsupported report template profile")
        if report_profile.get("output_schema_version") != OUTPUT_SCHEMA_VERSION:
            raise ValueError("unsupported report draft schema profile")
        if report_profile.get("prompt_template_hash") != PROMPT_TEMPLATE_HASH:
            raise ValueError("report prompt template hash mismatch")
        if report_profile.get("generation_mode") != "llm_assisted":
            raise ValueError("unsupported report generation mode")

        meta_bytes = _canonical_bytes(investigation_meta)
        if len(meta_bytes) > _MAX_META_BYTES:
            raise ValueError("investigation report metadata exceeds 128 KiB")
        embedded = result.get("audit_trace")
        outer = investigation_meta.get("audit_trace")
        audit_trace = outer if isinstance(outer, dict) else embedded if isinstance(embedded, dict) else {}
        source_bytes = _canonical_bytes({"report": result, "audit_trace": audit_trace})
        if len(source_bytes) > _MAX_SOURCE_REPORT_BYTES:
            raise ValueError("investigation report source exceeds 768 KiB")
        source_hash = _hash(source_bytes)
        investigation_id = str(
            investigation_meta.get("investigation_id") or "unavailable"
        )
        all_refs, eligible, audit_rejected, audit_summary = _audit_statements(
            result, investigation_meta, audit_trace
        )

        provider = getattr(self._client, "provider", None) if self._client is not None else None
        model_id = getattr(self._client, "model", None) if self._client is not None else None
        usage = {}
        draft = None
        fallback_reason = None
        if audit_rejected:
            fallback_reason = "audit_rejected"
        elif self._client is None or not callable(getattr(self._client, "messages_create", None)):
            fallback_reason = "llm_unavailable"
        else:
            payload = _prompt_payload(result, investigation_meta, source_hash, eligible, audit_summary)
            prompt_bytes = _canonical_bytes(payload)
            if len(prompt_bytes) > _MAX_PROMPT_BYTES:
                raise ValueError("investigation report prompt exceeds 896 KiB")
            try:
                raw = self._client.messages_create(
                    model=None,
                    system=_SYSTEM_PROMPT,
                    user=prompt_bytes.decode("utf-8"),
                    max_tokens=2048,
                    temperature=0,
                )
                raw_usage = getattr(self._client, "last_usage", {})
                usage = _json_copy(raw_usage) if isinstance(raw_usage, dict) else {}
            except Exception:  # provider failure is an explicit, durable fallback reason
                fallback_reason = "llm_provider_error"
            else:
                draft, fallback_reason = _validate_draft(
                    raw, investigation_id, source_hash, all_refs, eligible
                )

        generation_mode = "llm_assisted"
        if draft is None:
            generation_mode = "deterministic_fallback"
            fallback_reason = fallback_reason or "invalid_draft"
            draft = _fallback_draft(investigation_id, source_hash, eligible)
        draft = _json_copy(draft)
        draft_hash = _hash(_canonical_bytes(draft))
        html_bytes = _render_html(
            result,
            investigation_meta,
            draft,
            eligible,
            generation_mode,
            fallback_reason,
            provider,
            model_id,
            report_profile["prompt_template_hash"],
            audit_summary,
            source_hash,
        )
        return RenderedArtifact(
            html_bytes=html_bytes,
            content_hash=_hash(html_bytes),
            source_report_hash=source_hash,
            draft_json=draft,
            draft_hash=draft_hash,
            generation_mode=generation_mode,
            fallback_reason=fallback_reason,
            template_version=TEMPLATE_VERSION,
            output_schema_version=OUTPUT_SCHEMA_VERSION,
            provider=provider,
            model_id=model_id,
            prompt_template_hash=report_profile["prompt_template_hash"],
            usage=usage,
            audit_summary=audit_summary,
        )
