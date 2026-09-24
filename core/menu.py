"""Menu data loaded from data/menu.json. Items may hold a single value or a list per size."""
import json
import os

import streamlit as st

from core.db import BASE_DIR

MENU_PATH = os.path.join(BASE_DIR, "data", "menu.json")

# Minutes of prep per unit by category, used for ready-time estimates.
PREP_MINUTES = {"Coffee": 4, "Soft Drinks": 6, "Desserts": 1}


@st.cache_data
def load_menu():
    with open(MENU_PATH, encoding="utf-8") as f:
        return json.load(f)


def categories():
    return list(load_menu().keys())


def products(category):
    return load_menu()[category]


def all_products():
    return [(cat, p) for cat, items in load_menu().items() for p in items]


def find(name):
    for cat, p in all_products():
        if p["Product Name"].lower() == name.lower():
            return cat, p
    return None, None


def flavors(p):
    return p["Flavor"] if isinstance(p["Flavor"], list) else None


def sizes(p):
    return p["Size"] if isinstance(p["Size"], list) else None


def price_for(p, size=None):
    if isinstance(p["Price"], list):
        return p["Price"][p["Size"].index(size) if size in p["Size"] else 0]
    return p["Price"]


def calories_for(p, size=None):
    if isinstance(p["Calorie"], list):
        return p["Calorie"][p["Size"].index(size) if size in p["Size"] else 0]
    return p["Calorie"]


def price_label(p):
    if isinstance(p["Price"], list):
        return f"${min(p['Price']):.2f} to ${max(p['Price']):.2f}"
    return f"${p['Price']:.2f}"


def names_in_text(text):
    """Menu product names mentioned in a block of text, longest names matched first."""
    lowered = text.lower()
    found = []
    for _, p in sorted(all_products(), key=lambda x: -len(x[1]["Product Name"])):
        name = p["Product Name"].lower()
        if name in lowered:
            found.append(p["Product Name"])
            lowered = lowered.replace(name, " ")
    return found


def menu_as_text():
    lines = []
    for cat, items in load_menu().items():
        lines.append(f"{cat}:")
        for p in items:
            size = ", ".join(p["Size"]) if isinstance(p["Size"], list) else p["Size"]
            flavor = ", ".join(p["Flavor"]) if isinstance(p["Flavor"], list) else p["Flavor"]
            cal = "/".join(str(c) for c in p["Calorie"]) if isinstance(p["Calorie"], list) else p["Calorie"]
            lines.append(
                f"- {p['Product Name']}: {p['Description']} Flavor: {flavor or 'n/a'}. "
                f"Size: {size or 'one size'}. Calories: {cal}. Price: {price_label(p)}."
            )
    return "\n".join(lines)


def _cost_key(p, size):
    return f"{p['Product Name']}|{size or ''}"


def default_cost(p, size=None):
    """Ingredient and packaging cost per unit from menu.json (30% of price if missing)."""
    cost = p.get("Cost")
    if cost is None:
        return round(price_for(p, size) * 0.30, 2)
    if isinstance(cost, list):
        return cost[p["Size"].index(size) if size in p["Size"] else 0]
    return cost


def cost_for(p, size=None):
    """Current unit cost, using manager overrides from the Costs page when set."""
    from core import db
    overrides = db.get_setting("item_costs", {})
    return overrides.get(_cost_key(p, size), default_cost(p, size))


def cost_rows():
    """One row per product and size for the cost editor."""
    rows = []
    for cat, p in all_products():
        for size in (sizes(p) or [""]):
            rows.append({"key": _cost_key(p, size), "Category": cat, "Item": p["Product Name"], "Size": size or "One size",
                         "Price": price_for(p, size), "Cost": cost_for(p, size)})
    return rows
