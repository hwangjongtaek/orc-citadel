"""PostgreSQL queue에서 durable read-only investigation을 실행하는 단일 host worker."""
from __future__ import annotations

import os
import pathlib
import socket
import time

import psycopg

from orc_citadel.investigation_job import InvestigationWorker, build_read_facade
from orc_citadel.investigation_store import InvestigationStore
from orc_citadel.postgres_mutation_log import build_dsn

DATA_DB = pathlib.Path(__file__).resolve().parent.parent / "data" / "curated.duckdb"
POLL_SECONDS = 1


def main() -> None:
    worker_id = f"{socket.gethostname()}-{os.getpid()}"
    with psycopg.connect(build_dsn(), autocommit=True) as conn:
        store = InvestigationStore(conn)
        store.ensure_tables()
        worker = InvestigationWorker(
            store,
            worker_id=worker_id,
            facade_factory=lambda: build_read_facade(DATA_DB),
        )
        while True:
            if not worker.run_once():
                time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
