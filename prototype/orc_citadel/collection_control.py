"""등록된 source의 수집을 별도 프로세스로 지시하는 운영 제어."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .collect_large import SOURCES
from .identity import new_ulid


class CollectionControl:
    """Viewer가 직접 수집하지 않고 allowlist runner를 기동한다."""

    def __init__(self, data_dir: str | Path, *, popen=subprocess.Popen) -> None:
        self.data_dir = Path(data_dir)
        self.status_path = self.data_dir / "collection-run.json"
        self._popen = popen
        self._runner = Path(__file__).resolve().parent.parent / "scripts" / "collection_runner.py"

    @staticmethod
    def sources() -> list[dict]:
        return [
            {"source_id": source_id, "kind": kind}
            for source_id, (kind, _) in sorted(SOURCES.items())
        ]

    def status(self) -> dict:
        if not self.status_path.exists():
            return {"status": "idle"}
        try:
            result = json.loads(self.status_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"status": "unknown"}
        return result if isinstance(result, dict) else {"status": "unknown"}

    def trigger(self, source_ids: list[str]) -> dict:
        if not source_ids:
            raise ValueError("source_ids는 최소 한 개가 필요합니다")
        if not all(isinstance(source_id, str) and source_id in SOURCES
                   for source_id in source_ids):
            raise ValueError("등록된 source만 수집할 수 있습니다")
        source_ids = list(dict.fromkeys(source_ids))
        if self.status().get("status") in {"queued", "running"}:
            raise RuntimeError("수집이 이미 실행 중입니다")

        run_id = new_ulid("collect")
        state = {
            "run_id": run_id,
            "status": "queued",
            "source_ids": source_ids,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        self._write_status(state)
        args = [sys.executable, str(self._runner), "--state", str(self.status_path)]
        for source_id in source_ids:
            args.extend(["--source", source_id])
        process = self._popen(args)
        state.update({"status": "running", "pid": process.pid})
        self._write_status(state)
        return state

    def _write_status(self, state: dict) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.status_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.status_path)
