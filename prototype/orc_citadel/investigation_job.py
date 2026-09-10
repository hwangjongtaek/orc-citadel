"""기존 evidence만 읽는 조사 실행 경로.

HTTP handler와 영속 worker가 같은 Planner → Runner → Synthesizer/Audit 경로를
사용한다. graph·curated zone에는 쓰지 않는다.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from pathlib import Path

from .api_facade import ApiFacade
from .curated_zone import CuratedZone
from .graph_service import GraphService
from .investigation import Subclaim
from .investigation_dashboard import Coverage, investigation_dashboard
from .investigation_runner import InvestigationRunner
from .planner import InvestigationPlanner
from .synthesis import Audit, Synthesizer


def build_read_facade(db_path: str | Path) -> ApiFacade:
    """Worker마다 독립된 read-only DuckDB 연결과 그래프 projection을 연다."""
    zone = CuratedZone(str(db_path), read_only=True)
    graph = GraphService()
    for assertion in zone.assertions():
        for node, event_id in (
            (assertion["subject_id"], f"n-{assertion['assertion_id']}"),
            (assertion["claim_id"], f"n2-{assertion['assertion_id']}"),
        ):
            graph.apply([{
                "mutation_id": event_id,
                "idempotency_key": event_id,
                "op": "create_node",
                "payload": {"id": node, "props": {}, "labels": []},
            }])
        graph.apply([{
            "mutation_id": f"e-{assertion['assertion_id']}",
            "idempotency_key": f"e-{assertion['assertion_id']}",
            "op": "create_edge",
            "payload": {
                "type": "ABOUT",
                "from": assertion["subject_id"],
                "to": assertion["claim_id"],
                "props": {},
            },
        }])
    return ApiFacade(zone, graph)


def execute_read_only_investigation(
    facade: ApiFacade,
    *,
    subject_id: str = "",
    question: str = "",
    mode: str = "deterministic",
    llm_client=None,
    investigation_id: str | None = None,
    scope: dict | None = None,
) -> dict:
    """현재 read-only 조사 결과를 계산한다. 영속은 호출자가 소유한다."""
    planner = InvestigationPlanner(facade.zone)
    planned = planner.plan(question or subject_id, scope=scope)
    seed = subject_id or next(
        (subclaim.subject_id for subclaim in planned.subclaims if subclaim.known), "")
    subclaims = [
        Subclaim(subclaim.id, subclaim.text, subject_id=subclaim.subject_id)
        for subclaim in planned.subclaims
    ]


    investigation = InvestigationRunner(facade.zone, facade.graph).run(subclaims)
    report = Synthesizer(facade.zone).synthesize(investigation, seed or question)
    graph_view = facade.get_investigation_graph(seed, hops=1) if seed else {
        "subgraph": {"entities": [], "relationships": []},
        "relation_paths": [],
        "independence_summary": {},
    }
    planned_view = [{
        "id": subclaim.id,
        "text": subclaim.text,
        "known": subclaim.known,
        "gap_reason": subclaim.gap_reason,
    } for subclaim in planned.subclaims]

    statements = list(report.statements)
    llm_view = None
    if mode == "llm":
        from . import llm_investigation as li

        client = llm_client or li.default_client()
        evidence = li.evidence_rows(facade.zone, seed) if seed else []
        if client is None:
            llm_view = {"used": False,
                        "error": "LLM 미설정 (LLM_* env) — 결정적 문장 유지"}
        elif not evidence:
            llm_view = {"used": False, "error": "근거 claim 없음 — LLM 종합 생략"}
        else:
            name = next((entry["canonical_name"] for entry in facade.zone.entities()
                         if entry["entity_id"] == seed), seed)
            output = li.LlmSynthesis(client).synthesize(name, question or seed, evidence)
            if output is None or not output["statements"]:
                llm_view = {"used": False,
                            "error": "LLM 호출 실패/산출 없음 — 결정적 문장 유지"}
            else:
                trace = Audit().trace(output["statements"], facade.zone)
                statements = [statement for statement, row in zip(
                    output["statements"], trace["trace"]) if row["verified"]]
                llm_view = {
                    "used": True,
                    "model": output["model"],
                    "provider": output["provider"],
                    "usage": output["usage"],
                    "discarded": output["discarded"],
                    "blocked": len(output["statements"]) - len(statements),
                }

    audit_trace = Audit().trace(statements, facade.zone)
    audit = Audit().verify_from_trace(audit_trace)
    independent_evidence = investigation.coverage and graph_view[
        "independence_summary"].get("independent_source_count", 0)
    dashboard = investigation_dashboard(
        investigation_id=investigation_id or f"inv-{(seed or question)[:16]}",
        coverage=Coverage(
            covered=int(round(investigation.coverage * len(planned.subclaims))),
            planned=len(planned.subclaims),
            gaps=investigation.gaps,
        ),
        independent_evidence=independent_evidence,
        elapsed_ms=0,
    )
    return {
        "subject_id": seed,
        "question": question or None,
        "resolved": [{"subject_id": subclaim.subject_id, "surface": subclaim.surface,
                      "known": subclaim.known} for subclaim in planned.subclaims],
        "planned_subclaims": planned_view,
        "coverage": investigation.coverage,
        "iterations": investigation.iterations,
        "terminated_by": investigation.terminated_by,
        "gaps": investigation.gaps,
        "counter_evidence": list(investigation.counter_evidence),
        "retrieved": list(investigation.retrieved)[:10],
        "conclusion": report.conclusion,
        "statements": statements,
        "open_questions": report.open_questions,
        "audit": audit,
        "mode": "llm" if llm_view and llm_view["used"] else "deterministic",
        "llm": llm_view,
        "audit_trace": audit_trace,
        "dashboard": dashboard,
        "subgraph": graph_view["subgraph"],
        "relation_paths": graph_view["relation_paths"],
        "independence_summary": graph_view["independence_summary"],
    }


class InvestigationWorker:
    """단일 host worker의 한 번 claim·실행·영속 단위."""

    def __init__(
        self,
        store,
        *,
        worker_id: str,
        facade_factory,
        execute=execute_read_only_investigation,
        lease_seconds: float = 60,
        heartbeat_interval: float | None = None,
    ) -> None:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds는 0보다 커야 합니다")
        interval = heartbeat_interval if heartbeat_interval is not None else lease_seconds / 3
        if interval <= 0 or interval >= lease_seconds:
            raise ValueError("heartbeat_interval은 0보다 크고 lease_seconds보다 작아야 합니다")
        self._store = store
        self._worker_id = worker_id
        self._facade_factory = facade_factory
        self._execute = execute
        self._lease_seconds = lease_seconds
        self._heartbeat_interval = interval
    def _execute_claimed(self, claimed: dict) -> tuple[dict | None, bool]:
        """RUN 동안 lease를 갱신하고 결과와 claim 소유 여부를 반환한다."""
        def run() -> dict:
            facade = None
            try:
                facade = self._facade_factory()
                return self._execute(
                    facade,
                    subject_id=claimed["subject_id"] or "",
                    question=claimed["question"],
                    mode=claimed["mode"],
                    investigation_id=claimed["investigation_id"],
                    scope=claimed["scope"],
                )
            finally:
                zone = getattr(facade, "zone", None)
                close = getattr(zone, "close", None)
                if callable(close):
                    close()

        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="investigation-run") as pool:
            future = pool.submit(run)
            while True:
                try:
                    return future.result(timeout=self._heartbeat_interval), True
                except FutureTimeoutError:
                    if future.done():
                        return future.result(), True
                    if not self._store.renew_lease(
                        job_id=claimed["job_id"],
                        claim_token=claimed["claim_token"],
                        lease_seconds=self._lease_seconds,
                    ):
                        future.result()
                        return None, False


    def run_once(self) -> bool:
        """하나의 queued/stale job을 처리했으면 True를 반환한다."""
        claimed = self._store.claim_next(
            worker_id=self._worker_id, lease_seconds=self._lease_seconds
        )
        if claimed is None:
            return False
        if self._cancel_at_boundary(claimed):
            return True

        self._store.record_step(
            claimed["investigation_id"], step_id="step-001", stage="PLAN",
            payload={"question": claimed["question"], "subject_id": claimed["subject_id"],
                     "scope": claimed["scope"]},
            correlation_id=claimed["correlation_id"],
        )
        if self._cancel_at_boundary(claimed):
            return True

        self._store.record_step(
            claimed["investigation_id"], step_id="step-002", stage="RUN",
            payload={"mode": claimed["mode"]}, correlation_id=claimed["correlation_id"],
        )
        try:
            result, owns_claim = self._execute_claimed(claimed)
        except Exception as exc:
            if not self._cancel_at_boundary(claimed):
                self._store.fail(
                    job_id=claimed["job_id"], claim_token=claimed["claim_token"],
                    error={"code": "investigation_execution_failed", "message": str(exc)},
                )
            return True
        if not owns_claim:
            return True
        if self._cancel_at_boundary(claimed):
            return True

        self._store.record_step(
            claimed["investigation_id"], step_id="step-003", stage="SYNTHESIZE",
            payload={"statements": len(result.get("statements", []))},
            correlation_id=claimed["correlation_id"],
        )
        if self._cancel_at_boundary(claimed):
            return True

        self._store.record_step(
            claimed["investigation_id"], step_id="step-004", stage="AUDIT",
            payload=result.get("audit_trace", {}),
            correlation_id=claimed["correlation_id"],
        )
        if self._cancel_at_boundary(claimed):
            return True

        self._store.complete(
            job_id=claimed["job_id"],
            claim_token=claimed["claim_token"],
            report=result,
            audit_trace=result.get("audit_trace", {}),
            coverage={"ratio": result.get("coverage"), "gaps": result.get("gaps", [])},
            termination=result.get("terminated_by"),
        )
        return True

    def _cancel_at_boundary(self, claimed: dict) -> bool:
        if not self._store.is_cancel_requested(
            claimed["job_id"], claimed["claim_token"]
        ):
            return False
        self._store.mark_cancelled(
            job_id=claimed["job_id"], claim_token=claimed["claim_token"]
        )
        return True
