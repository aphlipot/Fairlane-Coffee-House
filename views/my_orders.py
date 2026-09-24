import streamlit as st

from core import hours, menu, orders, ui

ui.header("My orders", "Track orders, check in for curbside, and make changes before we start on them.")
user = ui.require_login()


@st.fragment(run_every="30s")
def active_orders():
    active = orders.for_user(user["id"], active=True)
    if not active:
        st.write("You have no open orders.")
        st.page_link("views/order.py", label="Start an order", icon=":material/shopping_bag:")
        return
    for o in active:
        items = orders.items_for(o["id"])
        with st.container(border=True):
            top = st.columns([3, 2])
            top[0].markdown(f"**Order #{o['id']}**, {orders.FULFILLMENT_LABELS[o['fulfillment']]}")
            top[1].markdown(f"**{orders.STATUS_LABELS[o['status']]}**")
            label = "Pickup" if o["scheduled_for"] else "Estimated ready"
            st.caption(f"{label}: {hours.fmt_dt(orders.due_time(o))}. Total {ui.money(o['total'])}.")
            st.write("  \n".join(orders.describe_item(i) for i in items))

            if o["fulfillment"] == "curbside":
                if o["arrived_at"]:
                    st.success(f"Checked in at {hours.fmt_time(hours.parse(o['arrived_at']))}"
                               + (f", spot {o['parking_spot']}" if o["parking_spot"] else "") + ". We're on our way.")
                else:
                    with st.form(f"arrive_{o['id']}"):
                        spot = st.text_input("Parking spot or landmark (optional)", placeholder="Spot 4, near the east doors")
                        if st.form_submit_button("I'm here", type="primary"):
                            ok, msg = orders.check_in(o["id"], user["id"], spot)
                            (st.success if ok else st.error)(msg)
                            st.rerun()

            if orders.can_modify(o):
                with st.expander("Change or cancel"):
                    for i in items:
                        c = st.columns([5, 1])
                        c[0].write(orders.describe_item(i))
                        if c[1].button("Remove", key=f"rmi_{i['id']}"):
                            ok, msg = orders.remove_item(o["id"], i["id"], user["id"])
                            st.toast(msg)
                            st.rerun()
                    if o["scheduled_for"]:
                        day = hours.parse(o["scheduled_for"]).date()
                        slots = orders.pickup_slots(day, items)
                        if slots:
                            c = st.columns([3, 2])
                            new = c[0].selectbox("New pickup time", slots, format_func=hours.fmt_time, key=f"rs_{o['id']}")
                            if c[1].button("Move pickup", key=f"mv_{o['id']}"):
                                ok, msg = orders.reschedule(o["id"], user["id"], new)
                                st.toast(msg)
                                st.rerun()
                    if st.button("Cancel order", key=f"cx_{o['id']}"):
                        ok, msg = orders.cancel(o["id"], user["id"])
                        st.toast(msg)
                        st.rerun()
            else:
                st.caption("We've started this order, so it can't be changed in the app. Talk to a barista if you need help.")


active_orders()

st.subheader("Past orders")
past = orders.for_user(user["id"], active=False)
if not past:
    st.write("Completed and cancelled orders will show here.")
for o in past[:20]:
    items = orders.items_for(o["id"])
    c = st.columns([1, 4, 2, 1.3])
    c[0].write(f"#{o['id']}")
    c[1].write(", ".join(orders.describe_item(i) for i in items) or "No items")
    c[2].write(f"{orders.STATUS_LABELS[o['status']]}, {hours.fmt_dt(o['created_at'])}")
    if items and c[3].button("Reorder", key=f"ro_{o['id']}"):
        for i in items:
            cat, p = menu.find(i["product"])
            if p:
                orders.add_to_cart(cat, i["product"], i["flavor"], i["size"], i["quantity"], i["special_request"] or "")
        st.switch_page("views/order.py")
