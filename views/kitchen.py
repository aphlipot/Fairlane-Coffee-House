import streamlit as st

from core import hours, orders, ui

ui.header("Kitchen", "Orders sorted by curbside arrivals, AI priority, then due time. Scheduled orders appear "
          f"{orders.RELEASE_LEAD_MINUTES} minutes before pickup.")
user = ui.require_role("staff", "manager")
staff_name = user["full_name"] or user["username"]

c1, c2 = st.columns(2)
limit = c1.number_input("Number of orders to show", 1, 50, 10)
status = c2.selectbox("Order status", ["to_be_processed", "in_progress"], format_func=orders.STATUS_LABELS.get)

NEXT = {"to_be_processed": ("Start", "in_progress"), "in_progress": ("Mark ready", "ready")}
PRIORITY_COLORS = {0: "gray", 1: "blue", 2: "orange", 3: "red"}


@st.fragment(run_every="20s")
def queue():
    waiting = len(orders.kitchen_queue("to_be_processed", 500))
    making = len(orders.kitchen_queue("in_progress", 500))
    m = st.columns(3)
    m[0].metric("To be processed", waiting)
    m[1].metric("In progress", making)
    m[2].metric("Scheduled later", len(orders.upcoming_scheduled()))

    rows = orders.kitchen_queue(status, int(limit))
    if not rows:
        st.write("No orders in this status.")
    now = hours.now()
    for o in rows:
        due = orders.due_time(o)
        late = due < now
        with st.container(border=True):
            top = st.columns([3, 2, 2])
            top[0].markdown(f"**#{o['id']} {o['customer_name']}**, {orders.FULFILLMENT_LABELS[o['fulfillment']]}")
            top[1].badge(orders.PRIORITY_LABELS[o["priority"]], color=PRIORITY_COLORS[o["priority"]])
            top[2].markdown(("**Late.** " if late else "") + f"Due {hours.fmt_time(due)}")
            if o["priority_reason"]:
                st.caption(f"Priority note: {o['priority_reason']}")
            if o["arrived_at"]:
                st.warning(f"Customer is here (curbside{', spot ' + o['parking_spot'] if o['parking_spot'] else ''}).")
            for i in orders.items_for(o["id"]):
                line = orders.describe_item(i)
                if i["special_request"]:
                    line += f". **{i['special_request']}**"
                st.write(line)
            if o["notes"]:
                st.info(o["notes"])
            label, nxt = NEXT[status]
            if st.button(label, key=f"k_{o['id']}", type="primary"):
                orders.set_status(o["id"], nxt, staff_name)
                st.rerun()


queue()

with st.expander("Scheduled for later"):
    upcoming = orders.upcoming_scheduled()
    if not upcoming:
        st.write("Nothing scheduled.")
    for o in upcoming:
        st.write(f"#{o['id']} {o['customer_name']}, {orders.FULFILLMENT_LABELS[o['fulfillment']]}, "
                 f"{hours.fmt_dt(o['scheduled_for'])}: " + ", ".join(orders.describe_item(i) for i in orders.items_for(o["id"])))
