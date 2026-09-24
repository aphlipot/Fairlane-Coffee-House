"""Orders: cart, order ahead (pickup and curbside), kitchen and service queues."""
from datetime import datetime, timedelta

import streamlit as st

from core import ai, db, hours, menu

STATUS_LABELS = {
    "to_be_processed": "To be processed",
    "in_progress": "In progress",
    "ready": "Ready",
    "completed": "Completed",
    "cancelled": "Cancelled",
}
FULFILLMENT_LABELS = {"pickup": "In-store pickup", "curbside": "Curbside pickup", "dine_in": "Dine in"}
PRIORITY_LABELS = {0: "Normal", 1: "Elevated", 2: "High", 3: "Urgent"}
SLOT_MINUTES = 15
SLOT_CAPACITY = 6          # scheduled orders allowed per 15-minute pickup slot
RELEASE_LEAD_MINUTES = 20  # scheduled orders reach the kitchen this long before pickup
ORDER_AHEAD_DAYS = 7


# ---------- cart ----------
def cart():
    return st.session_state.setdefault("cart", [])


def add_to_cart(category, product, flavor, size, quantity, special):
    p = menu.find(product)[1]
    cart().append({
        "category": category, "product": product, "flavor": flavor or "", "size": size or "",
        "quantity": int(quantity), "unit_price": menu.price_for(p, size),
        "calories": menu.calories_for(p, size), "special_request": special.strip(),
    })


def cart_total(items=None):
    return round(sum(i["unit_price"] * i["quantity"] for i in (items if items is not None else cart())), 2)


def describe_item(i):
    parts = [p for p in [i.get("size"), i.get("flavor")] if p]
    return f"{i['quantity']} x {i['product']}" + (f" ({', '.join(parts)})" if parts else "")


# ---------- timing ----------
def prep_minutes(items):
    if not items:
        return 0
    longest = max(menu.PREP_MINUTES.get(i["category"], 3) for i in items)
    units = sum(i["quantity"] for i in items)
    return int(longest + 1.5 * (units - 1))


def queue_minutes():
    row = db.one(
        "SELECT COUNT(*) AS n FROM orders WHERE status IN ('to_be_processed','in_progress') "
        "AND (scheduled_for IS NULL OR scheduled_for <= ?)",
        (hours.iso(hours.now() + timedelta(minutes=RELEASE_LEAD_MINUTES)),),
    )
    return 2 * (row["n"] if row else 0)


def estimate_ready(items, at=None):
    return (at or hours.now()) + timedelta(minutes=prep_minutes(items) + queue_minutes())


def slot_counts(day):
    rows = db.query(
        "SELECT scheduled_for FROM orders WHERE status != 'cancelled' AND scheduled_for LIKE ?",
        (f"{day.isoformat()}%",),
    )
    counts = {}
    for r in rows:
        counts[r["scheduled_for"]] = counts.get(r["scheduled_for"], 0) + 1
    return counts


def pickup_slots(day, items):
    """Open 15-minute pickup slots for a day, respecting hours, prep time, and slot capacity."""
    open_dt, close_dt = hours.hours_for(day)
    earliest = hours.ceil_to(estimate_ready(items), SLOT_MINUTES)
    t = max(open_dt + timedelta(minutes=SLOT_MINUTES), earliest)
    counts = slot_counts(day)
    slots = []
    while t <= close_dt - timedelta(minutes=SLOT_MINUTES):
        if counts.get(hours.iso(t), 0) < SLOT_CAPACITY:
            slots.append(t)
        t += timedelta(minutes=SLOT_MINUTES)
    return slots


# ---------- placing and changing orders ----------
def place_order(user, items, fulfillment, scheduled_for=None, notes="", vehicle=""):
    if not items:
        return False, "Your cart is empty."
    now = hours.now()
    if scheduled_for is None and not hours.is_open(now):
        return False, "We're closed right now. Choose a pickup time for later."
    if scheduled_for is not None:
        o, c = hours.hours_for(scheduled_for.date())
        if not (o <= scheduled_for < c) or scheduled_for < now:
            return False, "That pickup time is outside business hours. Pick another slot."
        if slot_counts(scheduled_for.date()).get(hours.iso(scheduled_for), 0) >= SLOT_CAPACITY:
            return False, "That pickup slot just filled up. Pick another."
    if fulfillment == "curbside" and not vehicle.strip():
        return False, "Tell us your vehicle so we can find you at the curb."

    items_text = "; ".join(describe_item(i) + (f" [{i['special_request']}]" if i["special_request"] else "") for i in items)
    all_notes = " ".join([notes.strip()] + [i["special_request"] for i in items if i["special_request"]]).strip()
    priority, reason = ai.prioritize_order(all_notes, items_text, fulfillment)
    est = scheduled_for or estimate_ready(items, now)

    with db.transaction() as conn:
        cur = conn.execute(
            """INSERT INTO orders (user_id, customer_name, fulfillment, scheduled_for, status, priority,
               priority_reason, notes, vehicle, est_ready_at, total, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (user["id"], user["full_name"] or user["username"], fulfillment, hours.iso(scheduled_for),
             "to_be_processed", priority, reason, notes.strip(), vehicle.strip(), hours.iso(est),
             cart_total(items), hours.iso(now), hours.iso(now)),
        )
        order_id = cur.lastrowid
        for i in items:
            conn.execute(
                """INSERT INTO order_items (order_id, category, product, flavor, size, quantity, unit_price,
                   calories, special_request) VALUES (?,?,?,?,?,?,?,?,?)""",
                (order_id, i["category"], i["product"], i["flavor"], i["size"], i["quantity"],
                 i["unit_price"], i["calories"], i["special_request"]),
            )
    return True, order_id


def get(order_id):
    return db.one("SELECT * FROM orders WHERE id = ?", (order_id,))


def items_for(order_id):
    return db.query("SELECT * FROM order_items WHERE order_id = ? ORDER BY id", (order_id,))


def for_user(user_id, active=True):
    statuses = "('to_be_processed','in_progress','ready')" if active else "('completed','cancelled')"
    return db.query(f"SELECT * FROM orders WHERE user_id = ? AND status IN {statuses} ORDER BY created_at DESC",
                    (user_id,))


def can_modify(order):
    return order["status"] == "to_be_processed"


def _owned(order_id, user_id):
    order = get(order_id)
    if not order or order["user_id"] != user_id:
        return None
    return order


def cancel(order_id, user_id):
    order = _owned(order_id, user_id)
    if not order:
        return False, "Order not found."
    if not can_modify(order):
        return False, "This order is already being made and can't be cancelled here. Please talk to a barista."
    db.execute("UPDATE orders SET status = 'cancelled', updated_at = ? WHERE id = ?", (hours.iso(hours.now()), order_id))
    return True, "Order cancelled."


def remove_item(order_id, item_id, user_id):
    order = _owned(order_id, user_id)
    if not order or not can_modify(order):
        return False, "This order can no longer be changed."
    db.execute("DELETE FROM order_items WHERE id = ? AND order_id = ?", (item_id, order_id))
    rest = items_for(order_id)
    if not rest:
        return cancel(order_id, user_id)
    total = round(sum(i["unit_price"] * i["quantity"] for i in rest), 2)
    db.execute("UPDATE orders SET total = ?, updated_at = ? WHERE id = ?", (total, hours.iso(hours.now()), order_id))
    return True, "Item removed."


def reschedule(order_id, user_id, new_time):
    order = _owned(order_id, user_id)
    if not order or not can_modify(order):
        return False, "This order can no longer be changed."
    db.execute("UPDATE orders SET scheduled_for = ?, est_ready_at = ?, updated_at = ? WHERE id = ?",
               (hours.iso(new_time), hours.iso(new_time), hours.iso(hours.now()), order_id))
    return True, f"Pickup moved to {hours.fmt_dt(new_time)}."


def check_in(order_id, user_id, spot):
    order = _owned(order_id, user_id)
    if not order:
        return False, "Order not found."
    db.execute("UPDATE orders SET arrived_at = ?, parking_spot = ?, updated_at = ? WHERE id = ?",
               (hours.iso(hours.now()), spot.strip(), hours.iso(hours.now()), order_id))
    return True, "Thanks. We know you're here and will bring your order out."


# ---------- staff queues ----------
def due_time(order):
    return hours.parse(order["scheduled_for"] or order["est_ready_at"] or order["created_at"])


def kitchen_queue(status, limit):
    release = hours.iso(hours.now() + timedelta(minutes=RELEASE_LEAD_MINUTES))
    return db.query(
        """SELECT * FROM orders WHERE status = ? AND (scheduled_for IS NULL OR scheduled_for <= ?)
           ORDER BY (arrived_at IS NOT NULL) DESC, priority DESC, COALESCE(scheduled_for, est_ready_at) ASC LIMIT ?""",
        (status, release, limit),
    )


def upcoming_scheduled(limit=50):
    release = hours.iso(hours.now() + timedelta(minutes=RELEASE_LEAD_MINUTES))
    return db.query(
        "SELECT * FROM orders WHERE status = 'to_be_processed' AND scheduled_for > ? ORDER BY scheduled_for LIMIT ?",
        (release, limit),
    )


def service_queue(limit):
    return db.query(
        """SELECT * FROM orders WHERE status = 'ready'
           ORDER BY (arrived_at IS NOT NULL) DESC, arrived_at ASC, COALESCE(scheduled_for, est_ready_at) ASC LIMIT ?""",
        (limit,),
    )


def curbside_waiting():
    return db.query(
        "SELECT * FROM orders WHERE fulfillment = 'curbside' AND arrived_at IS NOT NULL "
        "AND status IN ('to_be_processed','in_progress','ready') ORDER BY arrived_at"
    )


def set_status(order_id, status, staff_name):
    now = hours.iso(hours.now())
    completed = now if status == "completed" else None
    db.execute("UPDATE orders SET status = ?, updated_at = ?, handled_by = ?, completed_at = COALESCE(?, completed_at) WHERE id = ?",
               (status, now, staff_name, completed, order_id))
