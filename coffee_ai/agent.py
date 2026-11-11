"""The AI assistant: a Claude agent that uses your business tools."""

import anthropic

from .tools import CUSTOMER_TOOLS, OWNER_TOOLS, load_business

MODEL = "claude-opus-5-5"
MAX_STEPS = 10  # safety cap on tool calls per customer message

CUSTOMER_PROMPT = """You are the friendly AI barista for {name} ("{tagline}").
You help customers browse the menu, get recommendations, learn opening hours,
and place pickup orders.

Rules:
- Always use get_menu / get_store_info for prices, items and hours; never invent them.
- Before calling place_order, repeat the order back (items, size, milk, total)
  and get a clear "yes" from the customer, plus a name for the order.
- Mention allergens from the item tags (e.g. contains-nuts) when relevant.
- Keep replies short and warm, like a good barista."""

OWNER_PROMPT = """You are the business assistant for the owner of {name}.
You help with marketing and running the shop: social media posts, promotions,
email newsletters, menu ideas and pricing, and reviewing sales.

Use get_menu, get_store_info and sales_summary for real numbers; never invent
sales figures. Give practical, specific suggestions for a small coffee business."""


class CoffeeAgent:
    """A multi-turn chat agent. Call ask() once per user message."""

    def __init__(self, mode: str = "customer"):
        self.client = anthropic.Anthropic()
        biz = load_business()
        template, tools = (
            (OWNER_PROMPT, OWNER_TOOLS) if mode == "owner" else (CUSTOMER_PROMPT, CUSTOMER_TOOLS)
        )
        self.system = template.format(name=biz["name"], tagline=biz["tagline"])
        self.tools = {t.name: t for t in tools}
        self.tool_params = [t.to_dict() for t in tools]
        self.messages: list = []  # full history, including tool calls and results

    def ask(self, user_text: str) -> str:
        self.messages.append({"role": "user", "content": user_text})

        for _ in range(MAX_STEPS):
            response = self.client.beta.messages.create(
                model=MODEL,
                max_tokens=16000,
                system=self.system,
                tools=self.tool_params,
                messages=self.messages,
                output_config={"effort": "low"},  # chat is quick; raise for harder owner tasks
                # If the model declines a request, the API re-runs it on a fallback model.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
            # Append the whole content (thinking + tool calls), unchanged.
            self.messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "refusal":
                return "Sorry, I can't help with that."
            if response.stop_reason == "pause_turn":
                continue
            if response.stop_reason != "tool_use":
                return "".join(b.text for b in response.content if b.type == "text")

            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                tool = self.tools.get(block.name)
                try:
                    if tool is None:
                        raise ValueError(f"Unknown tool {block.name}")
                    output, is_error = tool.call(block.input), False
                except Exception as exc:  # report tool failures back to the model
                    output, is_error = f"Error: {exc}", True
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output,
                    "is_error": is_error,
                })
            # All results go back in one user message.
            self.messages.append({"role": "user", "content": results})

        return "Sorry, that took too many steps. Could you try rephrasing?"
