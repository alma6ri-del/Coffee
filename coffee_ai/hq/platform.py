"""HQ: wires the agents, the message bus and the bug monitor together."""

from __future__ import annotations

import os
import re
import threading
import time
from pathlib import Path

import anthropic

from ..tools import BUSINESS_FILE
from .agents import CHANNELS, LIVE_AGENTS, NODES
from .bus import MessageBus
from .monitor import BugMonitor

REPORTS_DIR = Path(__file__).resolve().parents[2] / "data" / "reports"


class HQ:
    def __init__(self):
        self.bus = MessageBus()
        self.monitor = BugMonitor(self.bus)
        self._client: anthropic.Anthropic | None = None
        self.agents = {cls.name: cls(self) for cls in LIVE_AGENTS}
        self.mission_lock = threading.Lock()

    @property
    def client(self) -> anthropic.Anthropic:
        if self._client is None:
            self._client = anthropic.Anthropic()
        return self._client

    # ---- communication -----------------------------------------------------
    def request(self, sender: str, recipient: str, text: str, mission: str, depth: int,
                kind: str = "task", reply_kind: str = "result") -> str:
        """Send a message to an agent and wait for its answer. Both legs are logged."""
        self.bus.publish(sender, recipient, kind, text, mission)
        answer = self.agents[recipient].handle(text, sender, mission, depth)
        self.bus.publish(recipient, sender, reply_kind, answer, mission)
        return answer

    def run_mission(self, text: str) -> tuple[str, Path]:
        """Give the General Manager a mission; returns the briefing and where it was saved."""
        with self.mission_lock:  # one mission at a time
            mission = time.strftime("M%Y%m%d-%H%M%S")
            try:
                briefing = self.request("owner", "gm", text, mission, 0, kind="mission", reply_kind="report")
            except anthropic.APIError as exc:
                briefing = f"Mission failed: {type(exc).__name__}: {exc}"
                self.bus.publish("gm", "owner", "report", briefing, mission)
            REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            slug = re.sub(r"[^a-z0-9]+", "-", text.lower())[:40].strip("-")
            path = REPORTS_DIR / f"{mission}-{slug}.md"
            path.write_text(f"# Mission: {text}\n\n{briefing}\n")
            return briefing, path

    # ---- monitoring --------------------------------------------------------
    def health(self) -> dict:
        has_key = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
        return {
            "api_credentials": "found in environment" if has_key else
                               "not in environment (fine if you used `ant auth login`)",
            "business_file": "ok" if BUSINESS_FILE.exists() else "MISSING data/business.json",
            "agents": {name: self.bus.status.get(name, "idle") for name in self.agents},
            "bugs_logged": self.monitor.summary()["total"],
        }

    def topology(self) -> dict:
        nodes = []
        for node_id, meta in NODES.items():
            agent = self.agents.get(node_id)
            nodes.append({
                "id": node_id,
                **meta,
                "role": agent.role if agent else meta.get("role", "The business owner. Gives missions, approves actions."),
            })
        return {"nodes": nodes, "channels": [list(c) for c in CHANNELS]}
