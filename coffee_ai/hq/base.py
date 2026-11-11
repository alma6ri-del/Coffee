"""BaseAgent: the Claude tool-use loop shared by every agent on the platform.

Every agent:
  - talks to other agents only through the HQ message bus (so it is logged and drawn),
  - reports anything that goes wrong to the bug monitor,
  - announces when it is working or idle.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import anthropic

if TYPE_CHECKING:
    from .platform import HQ

MODEL = "claude-opus-5-5"
MAX_STEPS = 12

WEB_SEARCH = {"type": "web_search_20260209", "name": "web_search", "max_uses": 6}
WEB_FETCH = {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 4}


class BaseAgent:
    name = "agent"           # id used on the bus
    title = "Agent"          # display name
    role = ""                # one-line description for the dashboard and the GM
    effort = "medium"        # low | medium | high | xhigh | max
    server_tools: list[dict] = []

    def __init__(self, hq: HQ):
        self.hq = hq
        self.history: list = []
        self.mission = ""
        self.depth = 0

    # ---- override in subclasses -------------------------------------------
    def system_prompt(self) -> str:
        raise NotImplementedError

    def tools(self) -> list:
        """Custom tools (functions decorated with @beta_tool)."""
        return []

    # ---- public API --------------------------------------------------------
    def handle(self, task: str, sender: str, mission: str = "", depth: int = 0) -> str:
        """Do one task for another agent. Stateless: each task starts fresh."""
        self.mission, self.depth = mission, depth
        return self._run([{"role": "user", "content": f"Message from {sender}:\n\n{task}"}], keep=False)

    def chat(self, text: str) -> str:
        """Multi-turn conversation with a person (keeps history)."""
        self.mission, self.depth = "chat", 0
        start = len(self.history)
        self.history.append({"role": "user", "content": text})
        return self._run(self.history, keep=True, start=start)

    # ---- the loop ----------------------------------------------------------
    def _run(self, messages: list, keep: bool, start: int = 0) -> str:
        bus, monitor = self.hq.bus, self.hq.monitor
        bus.publish(self.name, self.name, "status", "working", self.mission)
        custom = {t.name: t for t in self.tools()}
        tool_params = [t.to_dict() for t in custom.values()] + list(self.server_tools)
        if not keep:
            messages = list(messages)
        try:
            for _ in range(MAX_STEPS):
                response = self.hq.client.beta.messages.create(
                    model=MODEL,
                    max_tokens=16000,
                    system=self.system_prompt(),
                    tools=tool_params,
                    messages=messages,
                    output_config={"effort": self.effort},
                    # On a refusal, the API re-runs the request on a fallback model.
                    betas=["server-side-fallback-2026-07-01"],
                    fallbacks="default",
                )
                messages.append({"role": "assistant", "content": response.content})
                self._watch_server_tools(response)

                if response.stop_reason == "refusal":
                    monitor.report(self.name, "refusal", "The model declined this request.", "low", self.mission)
                    return "I can't help with that request."
                if response.stop_reason == "max_tokens":
                    monitor.report(self.name, "max_tokens", "Answer was cut off at max_tokens.", "medium", self.mission)
                    return self._text(response) + "\n\n[answer truncated]"
                if response.stop_reason == "pause_turn":
                    continue
                if response.stop_reason != "tool_use":
                    return self._text(response)

                results = []
                for block in response.content:
                    if block.type == "tool_use":
                        results.append(self._call_tool(custom, block))
                messages.append({"role": "user", "content": results})

            monitor.report(self.name, "step_limit", f"Stopped after {MAX_STEPS} steps.", "medium", self.mission)
            return "I ran out of steps before finishing this task."
        except anthropic.APIError as exc:
            monitor.report(self.name, "api_error", f"{type(exc).__name__}: {exc}", "high", self.mission)
            if keep:
                del messages[start:]  # drop the failed turn so the chat can continue
            raise
        except Exception as exc:
            monitor.report(self.name, "crash", f"{type(exc).__name__}: {exc}", "high", self.mission)
            if keep:
                del messages[start:]  # drop the failed turn so the chat can continue
            return f"ERROR in {self.title}: {exc}"
        finally:
            bus.publish(self.name, self.name, "status", "idle", self.mission)

    def _call_tool(self, custom: dict, block) -> dict:
        args = json.dumps(block.input)[:200]
        self.hq.bus.publish(self.name, self.name, "tool", f"{block.name}({args})", self.mission)
        tool = custom.get(block.name)
        try:
            if tool is None:
                raise ValueError(f"Unknown tool {block.name}")
            output, is_error = tool.call(block.input), False
        except Exception as exc:
            self.hq.monitor.report(self.name, "tool_error", f"{block.name}: {exc}", "medium", self.mission)
            output, is_error = f"Error: {exc}", True
        return {"type": "tool_result", "tool_use_id": block.id, "content": output, "is_error": is_error}

    def _watch_server_tools(self, response) -> None:
        """Log web searches, and report server-tool errors (they do not raise)."""
        for block in response.content:
            if block.type == "server_tool_use":
                query = block.input.get("query") or block.input.get("url") or ""
                self.hq.bus.publish(self.name, self.name, "tool", f"{block.name}: {query}", self.mission)
            elif block.type in ("web_search_tool_result", "web_fetch_tool_result"):
                content = block.content
                code = getattr(content, "error_code", None)
                if code:
                    self.hq.monitor.report(self.name, "web_tool_error", f"{block.type}: {code}", "low", self.mission)

    @staticmethod
    def _text(response) -> str:
        return "".join(b.text for b in response.content if b.type == "text").strip()
