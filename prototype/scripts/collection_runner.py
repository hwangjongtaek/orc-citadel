"""Viewer 수집 지시를 allowlist source에 대해 실행하는 단발 runner."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

import orc_citadel.collect_large as cl
from orc_citadel.collect_large import SOURCES, _stored_urls
from orc_citadel.event_stream import KafkaEventProducer


def _write_status(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def collect_selected(source_ids: list[str], event_producer=None) -> dict:
    """등록 source만 URL-idempotent 방식으로 수집한다."""
    if event_producer is None:
        event_producer = KafkaEventProducer.from_env()
    sources = {}
    for source_id in source_ids:
        kind, spec = SOURCES[source_id]
        known = _stored_urls(source_id)
        result = cl.COLLECTORS[kind](
            spec, source_id, known_urls=known, event_producer=event_producer)
        sources[source_id] = {
            "saved": result["saved"], "skipped": result["skipped"], "errors": result["errors"],
        }
    return {"total_new": sum(result["saved"] for result in sources.values()),
            "sources": sources}




def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True)
    parser.add_argument("--source", action="append", dest="source_ids", required=True)
    args = parser.parse_args(argv)
    state_path = Path(args.state)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    try:
        summary = collect_selected(args.source_ids)
    except Exception as exc:
        state.update({"status": "failed", "error": str(exc),
                      "completed_at": datetime.now(timezone.utc).isoformat()})
        _write_status(state_path, state)
        raise
    state.update({"status": "succeeded", "summary": summary,
                  "completed_at": datetime.now(timezone.utc).isoformat()})
    _write_status(state_path, state)


if __name__ == "__main__":
    main()
