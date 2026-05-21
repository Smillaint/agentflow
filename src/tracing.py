# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class TraceStore:
    """Append-only JSONL trace store for replay, eval, and debugging."""

    def __init__(self, trace_dir: str = "./runs/traces"):
        self.trace_dir = Path(trace_dir)
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        self.trace_file = self.trace_dir / "traces.jsonl"

    def save(self, payload: dict[str, Any]) -> dict[str, Any]:
        record = {
            "run_id": payload.get("run_id") or str(uuid.uuid4()),
            "created_at": datetime.now(timezone.utc).isoformat(),
            **payload,
        }
        with self.trace_file.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def list_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        if not self.trace_file.exists():
            return []
        lines = self.trace_file.read_text(encoding="utf-8").splitlines()
        records = [json.loads(line) for line in lines[-limit:] if line.strip()]
        return list(reversed(records))
