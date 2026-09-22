"""Durable reconciliation outbox for raw collection reference events."""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .event_stream import EventEnvelope, MAX_SCALAR_CHARS

OUTBOX_BATCH_SIZE = 1_000


def _digest(*parts: str) -> str:
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


def s1_idempotency_key(source_id: str, url: str, fetch_window: str) -> str:
    """ADR-402 key: source, URL and deterministic discovery window."""
    return "fetch:" + _digest(source_id, url, fetch_window)


def fetch_correlation_id(source_id: str, url: str, fetch_window: str) -> str:
    return "corr-" + _digest(source_id, url, fetch_window)[:24]


def _event_id(event_type: str, idempotency_key: str) -> str:
    digest = hashlib.sha256(f"{event_type}:{idempotency_key}".encode()).hexdigest()[:24]
    return f"evt-{digest}"


def _input_ref(url: str) -> str:
    if len(url) <= MAX_SCALAR_CHARS:
        return url
    return "url-sha256:" + hashlib.sha256(url.encode("utf-8")).hexdigest()


class CollectionEventOutbox:
    """Reconcile immutable raw rows and publish each S1/S2 pair after durability."""

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / "collection-events.sqlite3"
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS raw_events ("
                "source_id TEXT NOT NULL, doc_id TEXT NOT NULL, url TEXT NOT NULL, "
                "fetched_at TEXT NOT NULL, fetch_window TEXT NOT NULL, "
                "correlation_id TEXT NOT NULL, s1_acked INTEGER NOT NULL DEFAULT 0, "
                "s2_acked INTEGER NOT NULL DEFAULT 0, delivered_at TEXT, "
                "PRIMARY KEY(source_id, doc_id))"
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        return conn

    def reconcile(self, records: Iterable[dict]) -> int:
        """Insert missing durable raw rows in bounded transactions."""
        inserted = 0
        batch: list[tuple[str, ...]] = []
        with self._connect() as conn:
            for record in records:
                source_id = record["source_id"]
                doc_id = record["doc_id"]
                url = record["url"]
                window = str(record.get("fetch_window") or "full")
                correlation = str(
                    record.get("fetch_correlation_id")
                    or fetch_correlation_id(source_id, url, window)
                )
                batch.append((source_id, doc_id, url, record["fetched_at"], window,
                              correlation))
                if len(batch) == OUTBOX_BATCH_SIZE:
                    inserted += self._insert_batch(conn, batch)
                    conn.commit()
                    batch.clear()
            if batch:
                inserted += self._insert_batch(conn, batch)
        return inserted

    @staticmethod
    def _insert_batch(conn: sqlite3.Connection, rows: list[tuple[str, ...]]) -> int:
        before = conn.total_changes
        conn.executemany(
            "INSERT OR IGNORE INTO raw_events "
            "(source_id,doc_id,url,fetched_at,fetch_window,correlation_id) "
            "VALUES (?,?,?,?,?,?)",
            rows,
        )
        return conn.total_changes - before

    def drain(self, producer, *, batch_size: int = OUTBOX_BATCH_SIZE) -> int:
        """Publish bounded pending rows, recording only acknowledged stages."""
        delivered = 0
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT source_id,doc_id,url,fetched_at,fetch_window,correlation_id,"
                "s1_acked,s2_acked FROM raw_events WHERE delivered_at IS NULL "
                "ORDER BY source_id,doc_id LIMIT ?",
                (batch_size,),
            ).fetchall()
            for row in rows:
                source_id, doc_id, url, fetched_at, window, correlation, s1_acked, s2_acked = row
                raw_ref = f"raw://{source_id}/{doc_id}"
                input_ref = _input_ref(url)
                occurred_at = datetime.fromisoformat(fetched_at)
                if occurred_at.tzinfo is None:
                    occurred_at = occurred_at.replace(tzinfo=timezone.utc)
                if not s1_acked:
                    key = s1_idempotency_key(source_id, url, window)
                    producer.publish(EventEnvelope(
                        event_version=1,
                        event_id=_event_id("document_fetched", key),
                        stage="S1",
                        event_type="document_fetched",
                        status="succeeded",
                        input_ref=input_ref,
                        output_ref=raw_ref,
                        idempotency_key=key,
                        correlation_id=correlation,
                        attempt_count=0,
                        occurred_at=occurred_at,
                        payload={"source_id": source_id},
                    ))
                    conn.execute(
                        "UPDATE raw_events SET s1_acked=1 WHERE source_id=? AND doc_id=?",
                        (source_id, doc_id),
                    )
                    conn.commit()
                if not s2_acked:
                    producer.publish(EventEnvelope(
                        event_version=1,
                        event_id=_event_id("raw_stored", doc_id),
                        stage="S2",
                        event_type="raw_stored",
                        status="succeeded",
                        input_ref=input_ref,
                        output_ref=raw_ref,
                        idempotency_key=doc_id,
                        correlation_id=correlation,
                        attempt_count=0,
                        occurred_at=occurred_at,
                        payload={"source_id": source_id},
                    ))
                    conn.execute(
                        "UPDATE raw_events SET s2_acked=1 WHERE source_id=? AND doc_id=?",
                        (source_id, doc_id),
                    )
                    conn.commit()
                conn.execute(
                    "UPDATE raw_events SET delivered_at=? "
                    "WHERE source_id=? AND doc_id=? AND s1_acked=1 AND s2_acked=1",
                    (datetime.now(timezone.utc).isoformat(), source_id, doc_id),
                )
                conn.commit()
                delivered += 1
        return delivered

    def pending_count(self) -> int:
        with self._connect() as conn:
            return conn.execute(
                "SELECT count(*) FROM raw_events WHERE delivered_at IS NULL"
            ).fetchone()[0]
