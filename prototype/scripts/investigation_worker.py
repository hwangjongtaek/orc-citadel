"""PostgreSQL queue에서 durable read-only investigation을 실행하는 단일 host worker."""
from __future__ import annotations

import os
import pathlib
import socket
import time

import psycopg

from orc_citadel.investigation_job import InvestigationWorker, build_read_facade
from orc_citadel.investigation_store import InvestigationStore
from orc_citadel.investigation_report import HtmlReportGenerator
from orc_citadel.llm_providers import build_llm_client
from orc_citadel.postgres_mutation_log import build_dsn

WAREHOUSE_ROOT = pathlib.Path(__file__).resolve().parent.parent / "data" / "iceberg"
POLL_SECONDS = 1


def main() -> None:
    worker_id = f"{socket.gethostname()}-{os.getpid()}"
    with psycopg.connect(build_dsn(), autocommit=True) as conn:
        store = InvestigationStore(conn)
        store.ensure_tables()
        worker = InvestigationWorker(
            store,
            worker_id=worker_id,
            facade_factory=lambda: build_read_facade(WAREHOUSE_ROOT),
            report_generator=HtmlReportGenerator(build_llm_client()),
        )
        while True:
            if not worker.run_once():
                time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
