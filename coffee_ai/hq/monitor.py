"""Bug monitor: records every failure an agent hits and alerts the General Manager."""

import json
import threading
import time
from pathlib import Path

BUGS_FILE = Path(__file__).resolve().parents[2] / "data" / "bugs.jsonl"


class BugMonitor:
    def __init__(self, bus, bugs_file: Path = BUGS_FILE):
        self.bus = bus
        self.bugs_file = bugs_file
        self._lock = threading.Lock()

    def report(self, agent: str, kind: str, detail: str, severity: str = "medium", mission: str = "") -> None:
        bug = {"ts": time.time(), "agent": agent, "kind": kind, "severity": severity, "detail": detail[:1000]}
        with self._lock:
            self.bugs_file.parent.mkdir(parents=True, exist_ok=True)
            with self.bugs_file.open("a") as f:
                f.write(json.dumps(bug) + "\n")
        self.bus.publish(agent, "gm", "bug", f"[{severity}] {kind}: {detail[:300]}", mission)

    def all(self, limit: int = 50) -> list[dict]:
        if not self.bugs_file.exists():
            return []
        bugs = []
        for line in self.bugs_file.read_text().splitlines()[-limit:]:
            try:
                bugs.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return bugs

    def summary(self) -> dict:
        bugs = self.all(limit=500)
        by_agent: dict[str, int] = {}
        by_kind: dict[str, int] = {}
        for b in bugs:
            by_agent[b["agent"]] = by_agent.get(b["agent"], 0) + 1
            by_kind[b["kind"]] = by_kind.get(b["kind"], 0) + 1
        return {"total": len(bugs), "by_agent": by_agent, "by_kind": by_kind, "latest": bugs[-10:]}
