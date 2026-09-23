from datetime import timedelta

import streamlit as st

from core import hours, menu, orders, ui

ui.header("Order", "Build your order, then choose in-store pickup, curbside, or dine in.")
user = ui.require_login("Log in to place an order. It keeps your order history and lets us bring curbside orders to your car.")

# Preselect an item when arriving from the menu, home page, or assistant.
prefill = st.session_state.pop("prefill", None)
if prefill:
    st.session_state["o_cat"], st.session_state["o_prod"] = prefill

build, basket = st.columns([3, 2], gap="large")

with build:
    st.subheader("Add items")
    cat = st.selectbox("Category", menu.categories(), key="o_cat")
    names = [p["Product Name"] for p in menu.products(cat)]
    if st.session_state.get("o_prod") not in names:
        st.session_state["o_prod"] = names[0]
    name = st.selectbox("Item", names, key="o_prod")
    p = menu.find(name)[1]
    st.caption(p["Description"])

    c1, c2 = st.columns(2)
    flavor = c1.selectbox("Flavor", menu.flavors(p), key=f"o_flavor_{name}") if menu.flavors(p) else ""
    size = c2.selectbox("Size", menu.sizes(p), index=1 if len(menu.sizes(p)) > 1 else 0, key=f"o_size_{name}") if menu.sizes(p) else ""
    c3, c4 = st.columns([1, 2])
    qty = c3.number_input("Quantity", min_value=1, max_value=20, value=1, key="o_qty")
    special = c4.text_input("Special request", placeholder="Oat milk, extra hot, no ice...", key="o_special")
    st.markdown(f"{ui.money(menu.price_for(p, size) * qty)}, {menu.calories_for(p, size) * qty} cal")
    if st.button("Add to order", type="primary"):
        orders.add_to_cart(cat, name, flavor, size, qty, special)
        st.toast(f"Added {name}.")
        st.rerun()

with basket:
    st.subheader("Your order")
    cart = orders.cart()
    if not cart:
        st.write("Nothing here yet. Add an item to get started.")
    for idx, item in enumerate(cart):
        row = st.columns([5, 2, 1])
        row[0].markdown(orders.describe_item(item) + (f"  \n_{item['special_request']}_" if item["special_request"] else ""))
        row[1].write(ui.money(item["unit_price"] * item["quantity"]))
        if row[2].button("✕", key=f"rm_{idx}", help="Remove"):
            cart.pop(idx)
            st.rerun()
    if cart:
        cal = sum(i["calories"] * i["quantity"] for i in cart)
        st.markdown(f"**Total {ui.money(orders.cart_total())}**  \n{cal} calories")
        if st.button("Clear order", type="tertiary"):
            cart.clear()
            st.rerun()

if not orders.cart():
    st.stop()

st.divider()
st.subheader("Pickup and timing")
is_open, status_text = hours.status_line()
st.caption(status_text)

fulfillment = st.radio(
    "How do you want it?", list(orders.FULFILLMENT_LABELS), format_func=orders.FULFILLMENT_LABELS.get, horizontal=True,
)

when_options = ["asap", "later"] if is_open else ["later"]
if fulfillment == "dine_in":
    when_options = ["asap"] if is_open else []
if not when_options:
    st.warning("Dine-in orders are placed while we're open. You can reserve a table for later.")
    st.page_link("views/reservations.py", label="Reserve a table", icon=":material/table_restaurant:")
    st.stop()

when = st.radio(
    "When?", when_options, horizontal=True,
    format_func=lambda w: "As soon as possible" if w == "asap" else "Schedule for later",
)

scheduled = None
if when == "asap":
    ready = orders.estimate_ready(orders.cart())
    st.info(f"Estimated ready time: about {hours.fmt_time(ready)}.")
else:
    days, slots_by_day = [], {}
    for i in range(orders.ORDER_AHEAD_DAYS):
        d = hours.today() + timedelta(days=i)
        slots = orders.pickup_slots(d, orders.cart())
        if slots:
            days.append(d)
            slots_by_day[d] = slots
    if not days:
        st.warning("No pickup slots are open in the next week. Please try again later.")
        st.stop()
    c1, c2 = st.columns(2)
    day = c1.selectbox("Day", days, format_func=hours.day_label)
    scheduled = c2.selectbox("Pickup time", slots_by_day[day], format_func=hours.fmt_time)

vehicle = ""
if fulfillment == "curbside":
    vehicle = st.text_input("Your vehicle", placeholder="Color, make, and model. Example: blue Ford Escape")
    st.caption("When you park, open My orders and tap I'm here. We'll bring your order out.")

notes = st.text_area("Note for the café (optional)", placeholder="Anything we should know, like an allergy or a tight schedule.")

if st.button(f"Place order for {ui.money(orders.cart_total())}", type="primary"):
    ok, result = orders.place_order(user, list(orders.cart()), fulfillment, scheduled, notes, vehicle)
    if ok:
        orders.cart().clear()
        order = orders.get(result)
        st.session_state["last_order"] = result
        st.success(f"Order #{result} placed. {'Pickup' if fulfillment != 'dine_in' else 'Ready'} at {hours.fmt_dt(order['est_ready_at'])}.")
        st.page_link("views/my_orders.py", label="Track your order", icon=":material/receipt_long:")
    else:
        st.error(result)
