"""Chat with your coffee shop AI from the terminal.

    python main.py            # AI Barista for customers (menu, hours, orders)
    python main.py --owner    # Business Analyst for you (marketing, sales, ideas)

Both are agents of Coffee HQ, so their errors show up in the bug monitor.
For the full multi-agent platform, run `python hq.py serve`.
"""

import sys

import anthropic

from coffee_ai.hq import HQ


def main() -> None:
    mode = "owner" if "--owner" in sys.argv else "customer"
    agent = HQ().agents["analyst" if mode == "owner" else "barista"]
    print(f"{agent.title} ({mode} mode). Type 'quit' to exit.\n")
    while True:
        try:
            text = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if text.lower() in {"quit", "exit"}:
            break
        if not text:
            continue
        try:
            print(f"\nAI: {agent.chat(text)}\n")
        except anthropic.AuthenticationError:
            print("Missing or invalid API key. Set ANTHROPIC_API_KEY first.")
            break
        except anthropic.RateLimitError:
            print("Rate limited - wait a moment and try again.\n")
        except anthropic.APIConnectionError:
            print("Network problem reaching the API - try again.\n")
        except anthropic.APIStatusError as exc:
            print(f"API error {exc.status_code}: {exc.message}\n")


if __name__ == "__main__":
    main()
