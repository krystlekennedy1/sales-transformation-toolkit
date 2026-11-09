"""Append-only JSON Lines audit log. Every detect, diagnose and decide step is recorded."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


class AuditLog:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, finding_id: str, step: str, **details) -> None:
        entry = {"ts": datetime.now(timezone.utc).isoformat(), "finding_id": finding_id, "step": step, **details}
        with self.path.open("a") as fh:
            fh.write(json.dumps(entry, default=str) + "\n")

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]

    def recent_actions(self, within_days: int) -> set[str]:
        """Finding ids that already received a draft or escalation inside the cooldown window."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=within_days)
        seen = set()
        for e in self.entries():
            if e.get("step") == "decide" and e.get("status") in ("drafted", "escalated"):
                if datetime.fromisoformat(e["ts"]) >= cutoff:
                    seen.add(e["finding_id"])
        return seen
