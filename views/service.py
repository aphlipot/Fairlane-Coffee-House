from datetime import timedelta

import streamlit as st

from core import hours, orders, reservations as res, ui

ui.header("Service desk", "Hand off ready orders, run curbside, and manage today's tables.")
user = ui.require_role("staff", "manager")
staff_name = user["full_name"] or user["username"]

handoff, tables = st.tabs(["Orders and curbside", "Reservations"])

with handoff:
    @st.fragment(run_every="20s")
    def service_orders():
        waiting = orders.curbside_waiting()
        if waiting:
            st.subheader("Curbside arrivals")
            for o in waiting:
                mins = int((hours.now() - hours.parse(o["arrived_at"])).total_seconds() // 60)
                st.warning(f"#{o['id']} {o['customer_name']}: {o['vehicle'] or 'vehicle not given'}"
                           + (f", spot {o['parking_spot']}" if o["parking_spot"] else "")
                           + f". Waiting {mins} min. Order is {orders.STATUS_LABELS[o['status']].lower()}.")
        st.subheader("Ready for handoff")
        limit = st.number_input("Number of orders to show", 1, 50, 10, key="svc_limit")
        ready = orders.service_queue(int(limit))
        if not ready:
            st.write("No orders are waiting for handoff.")
        for o in ready:
            with st.container(border=True):
                c = st.columns([4, 2])
                c[0].markdown(f"**#{o['id']} {o['customer_name']}**, {orders.FULFILLMENT_LABELS[o['fulfillment']]}")
                c[1].write(f"Due {hours.fmt_time(orders.due_time(o))}")
                if o["fulfillment"] == "curbside":
                    where = f"Here, spot {o['parking_spot']}" if o["arrived_at"] and o["parking_spot"] else ("Here" if o["arrived_at"] else "Not here yet")
                    st.caption(f"{o['vehicle']}. {where}.")
                st.write(", ".join(orders.describe_item(i) for i in orders.items_for(o["id"])))
                if st.button("Handed off", key=f"s_{o['id']}", type="primary"):
                    orders.set_status(o["id"], "completed", staff_name)
                    st.rerun()

    service_orders()

with tables:
    day = st.date_input("Date", value=hours.today(), key="svc_day")
    booked = res.for_day(day)
    seats_total = sum(s for _, s in res.TABLES)
    guests = sum(r["party_size"] for r in booked if r["status"] in ("booked", "seated"))
    m = st.columns(3)
    m[0].metric("Reservations", len([r for r in booked if r["status"] in ("booked", "seated")]))
    m[1].metric("Guests expected", guests)
    m[2].metric("Tables", f"{len(res.TABLES)} ({seats_total} seats)")
    if not booked:
        st.write("No reservations for this date.")
    for r in booked:
        with st.container(border=True):
            c = st.columns([2, 3, 2])
            c[0].markdown(f"**{hours.fmt_time(hours.parse(r['start_at']))}**, table {r['table_id']}")
            c[1].write(f"{r['name']}, party of {r['party_size']}" + (f". {r['notes']}" if r["notes"] else ""))
            c[2].write(res.STATUS_LABELS[r["status"]])
            if r["status"] in ("booked", "seated"):
                b = st.columns(3)
                if r["status"] == "booked" and b[0].button("Seat", key=f"seat_{r['id']}"):
                    res.set_status(r["id"], "seated")
                    st.rerun()
                if r["status"] == "seated" and b[0].button("Finish", key=f"done_{r['id']}"):
                    res.set_status(r["id"], "completed")
                    st.rerun()
                if r["status"] == "booked" and b[1].button("No-show", key=f"ns_{r['id']}"):
                    res.set_status(r["id"], "no_show")
                    st.rerun()
