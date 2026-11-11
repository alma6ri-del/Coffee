"""Message bus: every message between agents goes through here and is logged.

The log (data/hq_events.jsonl) is what the dashboard draws: each event is a
message travelling along a link between two agents.
"""

import json
import threading
import time
from pathlib import Path

LOG_FILE = Path(__file__).resolve().parents[2] / "data" / "hq_events.jsonl"

# Event kinds:
#   mission  owner -> gm           a goal you give the platform
#   task     gm -> specialist      delegated work
#   consult  specialist -> peer    one agent asking another for input
#   reply    peer -> specialist    answer to a consult
#   result   specialist -> gm      finished work
#   report   gm -> owner           final briefing
#   tool     agent -> agent        the agent used a tool (web search, data lookup)
#   bug      agent -> gm           a problem the monitor detected
#   status   agent -> agent        working / idle


class MessageBus:
    def __init__(self, log_file: Path = LOG_FILE, keep: int = 2000):
        self.log_file = log_file
        self.keep = keep
        self._lock = threading.Lock()
        self.events: list[dict] = []
        self.status: dict[str, str] = {}
        self._next_id = 1
        self._load()

    def _load(self) -> None:
        if not self.log_file.exists():
            return
        for line in self.log_file.read_text().splitlines()[-self.keep:]:
            try:
                self.events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        if self.events:
            self._next_id = self.events[-1]["id"] + 1

    def publish(self, sender: str, recipient: str, kind: str, text: str, mission: str = "") -> dict:
        with self._lock:
            event = {
                "id": self._next_id,
                "ts": time.time(),
                "from": sender,
                "to": recipient,
                "kind": kind,
                "text": text,
                "mission": mission,
            }
            self._next_id += 1
            if kind == "status":
                self.status[sender] = text
            self.events.append(event)
            del self.events[: -self.keep]
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            with self.log_file.open("a") as f:
                f.write(json.dumps(event) + "\n")
            return event

    def since(self, last_id: int) -> list[dict]:
        with self._lock:
            return [e for e in self.events if e["id"] > last_id]
