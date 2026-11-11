"""Offline tests for Coffee HQ: a scripted fake Claude client drives the agents."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

from coffee_ai import tools
from coffee_ai.hq import HQ, platform
from coffee_ai.hq.bus import MessageBus
from coffee_ai.hq.monitor import BugMonitor


def text(t):
    return NS(type="text", text=t)


def tool_use(i, name, inp):
    return NS(type="tool_use", id=i, name=name, input=inp)


def reply(stop, *blocks):
    return NS(stop_reason=stop, content=list(blocks))


SCRIPTS = {
    "General Manager Agent": [
        reply("tool_use", tool_use("g1", "delegate", {"agent": "social", "task": "Find campaigns"}),
              tool_use("g2", "bug_report", {}), tool_use("g3", "health_check", {})),
        reply("end_turn", text("## Summary\n- Briefing done")),
    ],
    "Social Media Agent": [
        reply("tool_use",
              NS(type="server_tool_use", id="s0", name="web_search", input={"query": "coffee trends"}),
              NS(type="web_search_tool_result", content=NS(error_code="max_uses_exceeded")),
              tool_use("s1", "consult", {"agent": "analyst", "question": "Best sellers?"})),
        reply("tool_use", tool_use("s2", "consult", {"agent": "barista", "question": "hi"})),
        reply("end_turn", text("Campaign: Iced Mocha reel")),
    ],
    "Business Analyst Agent": [
        reply("tool_use", tool_use("a1", "sales_summary", {})),
        reply("tool_use", tool_use("a2", "does_not_exist", {})),
        reply("end_turn", text("Latte sells best")),
    ],
}


class FakeClient:
    def __init__(self):
        self.queues = {k: list(v) for k, v in SCRIPTS.items()}
        self.calls = []
        self.beta = NS(messages=NS(create=self.create))

    def create(self, **kw):
        self.calls.append({**kw, "messages": list(kw["messages"])})
        for key, queue in self.queues.items():
            if key in kw["system"]:
                return queue.pop(0)
        raise AssertionError("unexpected agent")


class HQTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._orig = (tools.ORDERS_FILE, platform.REPORTS_DIR)
        tools.ORDERS_FILE = self.tmp / "orders.json"
        platform.REPORTS_DIR = self.tmp / "reports"
        self.hq = HQ()
        self.hq.bus = MessageBus(self.tmp / "events.jsonl")
        self.hq.monitor = BugMonitor(self.hq.bus, self.tmp / "bugs.jsonl")
        self.hq._client = FakeClient()

    def tearDown(self):
        tools.ORDERS_FILE, platform.REPORTS_DIR = self._orig

    def test_mission_flows_through_the_network(self):
        briefing, path = self.hq.run_mission("Grow sales")
        self.assertIn("Briefing done", briefing)
        self.assertTrue(path.exists())

        routes = [(e["from"], e["to"], e["kind"]) for e in self.hq.bus.events if e["kind"] != "status"]
        for expected in [("owner", "gm", "mission"), ("gm", "social", "task"),
                         ("social", "analyst", "consult"), ("analyst", "social", "reply"),
                         ("social", "gm", "result"), ("gm", "owner", "report")]:
            self.assertIn(expected, routes)

        # Barista is not a peer of social, so that consult is refused without a message.
        self.assertNotIn(("social", "barista", "consult"), routes)

        bugs = self.hq.monitor.summary()
        self.assertEqual(bugs["by_kind"], {"web_tool_error": 1, "tool_error": 1})
        self.assertIn(("social", "gm", "bug"), routes)

        # Every agent finished idle.
        self.assertTrue(all(s == "idle" for s in self.hq.bus.status.values()))

        # Tool results were returned in a single user message with matching ids.
        last_gm = [c for c in self.hq._client.calls if "General Manager" in c["system"]][-1]
        results = last_gm["messages"][-1]["content"]
        self.assertEqual([r["tool_use_id"] for r in results], ["g1", "g2", "g3"])
        self.assertTrue(all(c["fallbacks"] == "default" for c in self.hq._client.calls))

    def test_crash_is_reported_and_chat_recovers(self):
        def boom(**kw):
            raise RuntimeError("network down")
        self.hq._client.beta.messages.create = boom
        out = self.hq.agents["barista"].chat("hello")
        self.assertIn("ERROR", out)
        self.assertEqual(self.hq.agents["barista"].history, [])
        self.assertEqual(self.hq.monitor.summary()["by_kind"], {"crash": 1})

    def test_topology_covers_all_channels(self):
        topo = self.hq.topology()
        ids = {n["id"] for n in topo["nodes"]}
        for a, b in topo["channels"]:
            self.assertIn(a, ids)
            self.assertIn(b, ids)
        live = {n["id"] for n in topo["nodes"] if n["status"] == "live"}
        self.assertEqual(live, set(self.hq.agents))


if __name__ == "__main__":
    unittest.main()
