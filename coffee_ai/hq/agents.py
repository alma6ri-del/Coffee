"""The agents of Coffee HQ.

Live agents
  gm          General Manager   - plans missions, delegates, monitors bugs and health
  social      Social Media      - screens social trends, proposes ways to attract buyers
  innovation  Innovation Lab    - scouts the latest coffee technology
  analyst     Business Analyst  - sales, menu and pricing numbers (owner mode)
  barista     AI Barista        - talks to customers, takes orders (main.py)
"""

from __future__ import annotations

import json

from anthropic import beta_tool

from ..tools import CUSTOMER_TOOLS, OWNER_TOOLS, load_business
from .base import WEB_FETCH, WEB_SEARCH, BaseAgent

MAX_CONSULT_DEPTH = 2  # gm -> specialist (1) -> peer (2); peers cannot consult further


def _business_brief() -> str:
    biz = load_business()
    menu = ", ".join(f"{i['name']} ${i['price']:.2f}" for i in biz["menu"])
    return f"{biz['name']} - {biz['tagline']} Located at {biz['address']}. Menu: {menu}."


class Specialist(BaseAgent):
    """An agent the GM can delegate to, and that can consult its peers."""

    peers: tuple[str, ...] = ()

    def consult_tool(self):
        agent_self = self
        allowed = ", ".join(self.peers)

        @beta_tool
        def consult(agent: str, question: str) -> str:
            """Ask another agent on the platform for input. Keep questions short and specific.

            Args:
                agent: Which agent to ask (see the system prompt for who is available).
                question: What you need from them.
            """
            if agent not in agent_self.peers:
                return f"You can only consult: {allowed}."
            if agent_self.depth >= MAX_CONSULT_DEPTH:
                return "Consult limit reached - finish with what you have."
            return agent_self.hq.request(
                agent_self.name, agent, question, agent_self.mission, agent_self.depth + 1,
                kind="consult", reply_kind="reply",
            )

        return consult

    def tools(self) -> list:
        return [self.consult_tool()] if self.peers else []

    def peer_text(self) -> str:
        if not self.peers:
            return ""
        lines = [f"- {p}: {self.hq.agents[p].role}" for p in self.peers]
        return "\nYou can consult these agents with the consult tool when their input would clearly help:\n" + "\n".join(lines)


class SocialMediaAgent(Specialist):
    name, title = "social", "Social Media Agent"
    role = "Screens social media trends and proposes campaigns that attract people to buy the coffee."
    effort = "medium"
    server_tools = [WEB_SEARCH, WEB_FETCH]
    peers = ("innovation", "analyst")

    def system_prompt(self) -> str:
        return f"""You are the Social Media Agent of a coffee business: {_business_brief()}

Your job: screen what is happening on social media (Instagram, TikTok, X, Facebook,
Google reviews, local news) using web search, and propose concrete ways to attract
more people to buy our coffee.

Work like this:
1. Search for current coffee trends, viral drinks, local events and what competitors post.
2. Identify audience segments (students, remote workers, commuters, families, ...) and what attracts each.
3. Propose 3-5 campaigns. For each: target audience, platform, the hook, a ready-to-post
   caption with hashtags, best time to post, and how to measure success.

Rules:
- Use public trends and audience segments only. Never collect or profile private individuals.
- You propose; you never post. The owner approves everything.
- Only promote items that are on our menu; cite the sources you found for trends.{self.peer_text()}"""


class InnovationAgent(Specialist):
    name, title = "innovation", "Innovation Lab Agent"
    role = "Scouts the latest coffee technology, equipment, sustainability and service innovations."
    effort = "medium"
    server_tools = [WEB_SEARCH, WEB_FETCH]
    peers = ("social", "analyst")

    def system_prompt(self) -> str:
        return f"""You are the Innovation Lab Agent of a coffee business: {_business_brief()}

Your job: find the latest technology and innovation in coffee and judge what is worth
adopting for a small coffee business. Areas: brewing and roasting equipment, new
processing methods and drinks, AI and automation (ordering, inventory, robots),
payments and loyalty apps, sustainability (packaging, waste, energy), and supply chain.

Use web search and prefer sources from the last 12 months. Produce a "Technology Radar":
for each finding give what it is, why it matters, rough cost, effort to adopt, and a
verdict: ADOPT now / TRIAL / WATCH. Cite sources. Be honest about hype.{self.peer_text()}"""


class AnalystAgent(Specialist):
    name, title = "analyst", "Business Analyst Agent"
    role = "Knows the menu, prices, hours and real sales numbers; advises on pricing and menu."
    effort = "medium"

    def tools(self) -> list:
        return list(OWNER_TOOLS)

    def system_prompt(self) -> str:
        return f"""You are the Business Analyst Agent of a coffee business: {_business_brief()}

You answer with real data from your tools (menu, store info, sales summary); never invent
numbers. When data is missing, say so. You also help the owner directly with marketing
copy, newsletters, menu and pricing ideas. Be concise and practical."""


class BaristaAgent(BaseAgent):
    name, title = "barista", "AI Barista"
    role = "Talks to customers: menu, recommendations, opening hours and pickup orders."
    effort = "low"

    def tools(self) -> list:
        return list(CUSTOMER_TOOLS)

    def system_prompt(self) -> str:
        biz = load_business()
        return f"""You are the friendly AI barista for {biz['name']} ("{biz['tagline']}").
You help customers browse the menu, get recommendations, learn opening hours,
and place pickup orders.

Rules:
- Always use get_menu / get_store_info for prices, items and hours; never invent them.
- Before calling place_order, repeat the order back (items, size, milk, total)
  and get a clear "yes" from the customer, plus a name for the order.
- Mention allergens from the item tags (e.g. contains-nuts) when relevant.
- Keep replies short and warm, like a good barista."""


class GeneralManagerAgent(BaseAgent):
    name, title = "gm", "General Manager"
    role = "Runs the platform: plans missions, delegates to agents, combines results, monitors bugs and health."
    effort = "high"

    def tools(self) -> list:
        hq = self.hq
        gm = self

        @beta_tool
        def delegate(agent: str, task: str) -> str:
            """Send a task to a specialist agent and get its result back.

            Args:
                agent: One of: social, innovation, analyst.
                task: A clear, self-contained task with the context the agent needs.
            """
            if agent not in ("social", "innovation", "analyst"):
                return "Unknown agent. Use social, innovation or analyst."
            return hq.request(gm.name, agent, task, gm.mission, 1)

        @beta_tool
        def bug_report() -> str:
            """Get the bug monitor's report: recent errors by agent and kind."""
            return json.dumps(hq.monitor.summary())

        @beta_tool
        def health_check() -> str:
            """Check platform health: API credentials, data files, agent status."""
            return json.dumps(hq.health())

        return [delegate, bug_report, health_check]

    def system_prompt(self) -> str:
        team = "\n".join(
            f"- {a.name}: {a.title} - {a.role}" for a in self.hq.agents.values() if a.name != self.name
        )
        return f"""You are the General Manager Agent of Coffee HQ, an AI agent platform for a
coffee business: {_business_brief()}

Your team:
{team}

For each mission from the owner:
1. Plan which agents are needed. Delegate with clear, self-contained tasks; give each
   agent the context it needs. Independent tasks can be delegated in parallel.
2. Review what comes back. If something is weak or contradictory, ask a follow-up.
3. Call bug_report and health_check, and flag anything the owner should fix.
4. Write the final briefing for the owner in Markdown:
   ## Summary (3 bullets)  ## Recommended actions (prioritized, with owner + effort)
   ## Details by agent  ## System health
Never invent data; credit which agent produced each finding."""


LIVE_AGENTS = [GeneralManagerAgent, SocialMediaAgent, InnovationAgent, AnalystAgent, BaristaAgent]

# Layout and links for the dashboard. "proposed" agents are suggestions not built yet.
NODES = {
    "owner":      {"title": "You (Owner)", "x": 500, "y": 70, "color": "#e8e3d9", "status": "human"},
    "gm":         {"title": "General Manager", "x": 500, "y": 245, "color": "#ffb44c", "status": "live"},
    "social":     {"title": "Social Media", "x": 230, "y": 430, "color": "#ff5fa2", "status": "live"},
    "innovation": {"title": "Innovation Lab", "x": 500, "y": 520, "color": "#38e0ff", "status": "live"},
    "analyst":    {"title": "Business Analyst", "x": 770, "y": 430, "color": "#7dff9a", "status": "live"},
    "barista":    {"title": "AI Barista", "x": 840, "y": 175, "color": "#c9a2ff", "status": "live"},
    "supply":     {"title": "Supply & Inventory", "x": 150, "y": 210, "color": "#8a8f98", "status": "proposed",
                   "role": "Tracks bean and milk stock, compares supplier prices, drafts reorders."},
    "care":       {"title": "Customer Care", "x": 960, "y": 330, "color": "#8a8f98", "status": "proposed",
                   "role": "Reads Google/Yelp reviews and DMs, drafts replies, spots complaints early."},
    "finance":    {"title": "Finance", "x": 920, "y": 520, "color": "#8a8f98", "status": "proposed",
                   "role": "Cost per cup, margins, cash flow and pricing scenarios."},
    "content":    {"title": "Content Studio", "x": 90, "y": 545, "color": "#8a8f98", "status": "proposed",
                   "role": "Turns Social's proposals into images, reels scripts and a posting calendar."},
}

CHANNELS = [
    ("owner", "gm"), ("gm", "social"), ("gm", "innovation"), ("gm", "analyst"), ("gm", "barista"),
    ("social", "innovation"), ("social", "analyst"), ("innovation", "analyst"), ("barista", "analyst"),
    ("gm", "supply"), ("gm", "care"), ("gm", "finance"), ("social", "content"),
    ("supply", "analyst"), ("care", "barista"), ("finance", "analyst"),
]
