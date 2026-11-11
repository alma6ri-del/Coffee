"""Coffee HQ - multi-agent platform command line.

    python hq.py serve                      # open the live dashboard (http://127.0.0.1:8765)
    python hq.py mission "your goal"        # run a mission in the terminal
    python hq.py demo                       # replay a sample mission (no API key needed)
    python hq.py health                     # platform health + bug summary
"""

import argparse
import json

from coffee_ai.hq import HQ


def main() -> None:
    parser = argparse.ArgumentParser(description="Coffee HQ agent platform")
    sub = parser.add_subparsers(dest="cmd", required=True)
    serve_p = sub.add_parser("serve", help="start the dashboard")
    serve_p.add_argument("--port", type=int, default=8765)
    mission_p = sub.add_parser("mission", help="give the General Manager a mission")
    mission_p.add_argument("text")
    sub.add_parser("demo", help="replay a sample mission on the bus")
    sub.add_parser("health", help="show health and bugs")
    args = parser.parse_args()

    hq = HQ()
    if args.cmd == "serve":
        from coffee_ai.hq.server import serve
        serve(hq, args.port)
    elif args.cmd == "mission":
        # Print the conversation between agents as it happens.
        original = hq.bus.publish

        def echo(sender, recipient, kind, text, mission=""):
            event = original(sender, recipient, kind, text, mission)
            if kind != "status":
                arrow = sender if sender == recipient else f"{sender} -> {recipient}"
                print(f"[{kind:>7}] {arrow}: {text[:160].replace(chr(10), ' ')}")
            return event

        hq.bus.publish = echo
        briefing, path = hq.run_mission(args.text)
        print("\n" + briefing + f"\n\nSaved to {path}")
    elif args.cmd == "demo":
        from coffee_ai.hq.demo import run_demo
        run_demo(hq.bus, delay=0.3)
        print("Demo mission written to the bus. Run `python hq.py serve` to see the log.")
    elif args.cmd == "health":
        print(json.dumps({"health": hq.health(), "bugs": hq.monitor.summary()}, indent=2))


if __name__ == "__main__":
    main()
