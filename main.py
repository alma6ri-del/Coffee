"""Chat with your coffee shop AI from the terminal.

    python main.py            # customer assistant (menu, hours, orders)
    python main.py --owner    # owner assistant (marketing, sales, ideas)
"""

import sys

import anthropic

from coffee_ai.agent import CoffeeAgent


def main() -> None:
    mode = "owner" if "--owner" in sys.argv else "customer"
    agent = CoffeeAgent(mode=mode)
    print(f"Coffee AI ({mode} mode). Type 'quit' to exit.\n")
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
            print(f"\nAI: {agent.ask(text)}\n")
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
