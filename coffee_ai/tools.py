"""Tools the AI assistant can call. They read and write your business data."""

import json
import uuid
from datetime import datetime
from pathlib import Path

from anthropic import beta_tool

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
BUSINESS_FILE = DATA_DIR / "business.json"
ORDERS_FILE = DATA_DIR / "orders.json"


def load_business() -> dict:
    return json.loads(BUSINESS_FILE.read_text())


def _load_orders() -> list:
    if ORDERS_FILE.exists():
        return json.loads(ORDERS_FILE.read_text())
    return []


def _save_orders(orders: list) -> None:
    ORDERS_FILE.write_text(json.dumps(orders, indent=2))


@beta_tool
def get_menu(category: str = "") -> str:
    """Get the menu with prices, descriptions and tags.

    Args:
        category: Optional filter: "coffee", "tea" or "food". Empty returns everything.
    """
    biz = load_business()
    items = [i for i in biz["menu"] if not category or i["category"] == category]
    return json.dumps(
        {"items": items, "sizes": biz["sizes"], "milk_options": biz["milk_options"]}
    )


@beta_tool
def get_store_info() -> str:
    """Get opening hours, address, phone number and store policies."""
    biz = load_business()
    info = {k: biz[k] for k in ("name", "address", "phone", "hours", "policies")}
    info["now"] = datetime.now().strftime("%A %H:%M")
    return json.dumps(info)


@beta_tool
def place_order(customer_name: str, items: list[dict], pickup_time: str = "") -> str:
    """Place a pickup order. Only call after the customer has confirmed the items.

    Args:
        customer_name: Name to put on the order.
        items: List of objects with "id" (menu id), "quantity" (int), and optional
            "size" (small/medium/large) and "milk" (whole/oat/almond/soy).
        pickup_time: Requested pickup time, e.g. "8:30". Empty means as soon as possible.
    """
    biz = load_business()
    menu = {i["id"]: i for i in biz["menu"]}
    lines, total = [], 0.0
    for it in items:
        item = menu.get(it.get("id"))
        if item is None:
            return json.dumps({"error": f"Unknown menu id: {it.get('id')}"})
        qty = int(it.get("quantity", 1))
        size = it.get("size") or "small"
        milk = it.get("milk") or "whole"
        if size not in biz["sizes"] or milk not in biz["milk_options"]:
            return json.dumps({"error": f"Invalid size or milk for {item['name']}"})
        extras = biz["sizes"][size] if item["category"] != "food" else 0.0
        if "milky" in item["tags"]:
            extras += biz["milk_options"][milk]
        price = round((item["price"] + extras) * qty, 2)
        total += price
        lines.append({"name": item["name"], "quantity": qty, "size": size, "milk": milk, "price": price})

    order = {
        "order_id": uuid.uuid4().hex[:8].upper(),
        "customer_name": customer_name,
        "items": lines,
        "total": round(total, 2),
        "pickup_time": pickup_time or "ASAP (~10 min)",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "status": "received",
    }
    orders = _load_orders()
    orders.append(order)
    _save_orders(orders)
    return json.dumps(order)


@beta_tool
def get_order_status(order_id: str) -> str:
    """Look up an existing order by its order id.

    Args:
        order_id: The 8-character order id given when the order was placed.
    """
    for order in _load_orders():
        if order["order_id"] == order_id.upper():
            return json.dumps(order)
    return json.dumps({"error": "Order not found"})


@beta_tool
def sales_summary() -> str:
    """Owner only: summarize all orders so far (count, revenue, best sellers)."""
    orders = _load_orders()
    counts: dict[str, int] = {}
    for o in orders:
        for line in o["items"]:
            counts[line["name"]] = counts.get(line["name"], 0) + line["quantity"]
    return json.dumps({
        "order_count": len(orders),
        "revenue": round(sum(o["total"] for o in orders), 2),
        "items_sold": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
    })


CUSTOMER_TOOLS = [get_menu, get_store_info, place_order, get_order_status]
OWNER_TOOLS = [get_menu, get_store_info, sales_summary]
