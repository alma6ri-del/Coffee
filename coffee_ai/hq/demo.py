"""Demo: replays a sample mission on the bus so you can watch the network with no API key.

Every message is marked [DEMO]; nothing here is real research.
"""

import time

SCRIPT = [
    ("owner", "gm", "mission", "Plan next month: how do we bring more people in, and is there any new tech worth buying?"),
    ("gm", "gm", "status", "working"),
    ("gm", "social", "task", "Screen social media for coffee trends near our shop and propose 3-5 campaigns to attract new buyers."),
    ("social", "social", "status", "working"),
    ("gm", "innovation", "task", "Build a Technology Radar of coffee innovations from the last 12 months that fit a small shop."),
    ("innovation", "innovation", "status", "working"),
    ("social", "social", "tool", "web_search: trending iced coffee drinks this season"),
    ("innovation", "innovation", "tool", "web_search: new espresso machine technology 2026"),
    ("social", "analyst", "consult", "Which drinks sell best, and which have the best margin to promote?"),
    ("analyst", "analyst", "status", "working"),
    ("analyst", "analyst", "tool", "sales_summary({})"),
    ("analyst", "social", "reply", "Top sellers: Latte, Cold Brew, Iced Mocha. Iced Mocha has the highest price; oat milk add-ons are popular."),
    ("analyst", "analyst", "status", "idle"),
    ("innovation", "innovation", "tool", "web_fetch: article on AI-driven grinder calibration"),
    ("innovation", "social", "consult", "Would customers care about a 'zero-waste cup' story on social?"),
    ("social", "innovation", "reply", "Yes - sustainability posts get strong engagement with students and remote workers."),
    ("social", "social", "tool", "web_search: local events this month coffee pop-up"),
    ("social", "gm", "bug", "[low] web_tool_error: web_fetch_tool_result: url_not_accessible"),
    ("innovation", "gm", "result", "Radar: ADOPT smart grinder calibration; TRIAL oat-milk on tap; WATCH robotic baristas."),
    ("innovation", "innovation", "status", "idle"),
    ("social", "gm", "result", "Campaigns: 1) 'Study Hours' student deal (TikTok), 2) Iced Mocha reel, 3) Zero-waste cup story, 4) Weekend pop-up."),
    ("social", "social", "status", "idle"),
    ("gm", "gm", "tool", "bug_report({})"),
    ("gm", "gm", "tool", "health_check({})"),
    ("gm", "owner", "report", "Briefing ready: 4 campaigns, 3 tech picks, 1 low-severity web fetch bug (no action needed)."),
    ("gm", "gm", "status", "idle"),
]


def run_demo(bus, delay: float = 1.2) -> None:
    mission = time.strftime("DEMO-%H%M%S")
    for sender, recipient, kind, text in SCRIPT:
        bus.publish(sender, recipient, kind, text if kind == "status" else f"[DEMO] {text}", mission)
        if kind != "status":
            time.sleep(delay)
