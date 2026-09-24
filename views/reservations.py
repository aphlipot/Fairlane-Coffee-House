from datetime import timedelta

import streamlit as st

from core import hours, reservations as res, ui

ui.header("Reserve a table", f"Tables seat 2, 4, or 6. Each reservation holds your table for {res.SEATING_MINUTES} minutes.")
user = ui.require_login("Log in to reserve a table.")

book, mine = st.columns([3, 2], gap="large")

with book:
    st.subheader("Book")
    c1, c2 = st.columns(2)
    party = c1.number_input("Party size", min_value=1, max_value=res.MAX_ONLINE_PARTY, value=2)
    day = c2.date_input("Date", value=hours.today(), min_value=hours.today(),
                        max_value=hours.today() + timedelta(days=res.BOOK_AHEAD_DAYS))
    times = res.available_times(day, int(party))
    if not times:
        st.warning("No tables are open for that date and party size. Try another day.")
    else:
        start = st.selectbox("Time", times, format_func=hours.fmt_time)
        with st.form("book_table"):
            name = st.text_input("Name on the reservation", value=user["full_name"] or user["username"])
            phone = st.text_input("Phone", value=user["phone"] or "")
            notes = st.text_input("Notes (optional)", placeholder="Birthday, high chair, quiet table for studying...")
            if st.form_submit_button("Reserve table", type="primary"):
                if not name.strip():
                    st.error("Add a name for the reservation.")
                else:
                    ok, result = res.book(user, start, int(party), name, phone, notes)
                    if ok:
                        r = res.get(result)
                        st.success(f"Reserved for {party} on {hours.fmt_dt(r['start_at'])}. Confirmation #{result}, table {r['table_id']}.")
                    else:
                        st.error(result)
    st.caption(f"Groups larger than {res.MAX_ONLINE_PARTY}: email fairlanecoffeehouse@gmail.com and we'll set something up.")

with mine:
    st.subheader("Your reservations")
    upcoming = res.for_user(user["id"])
    if not upcoming:
        st.write("No upcoming reservations.")
    for r in upcoming:
        with st.container(border=True):
            st.markdown(f"**{hours.fmt_dt(r['start_at'])}**, party of {r['party_size']}")
            st.caption(f"Confirmation #{r['id']}, table {r['table_id']}" + (f". {r['notes']}" if r["notes"] else ""))
            with st.expander("Change or cancel"):
                d = hours.parse(r["start_at"]).date()
                new_party = st.number_input("Party size", 1, res.MAX_ONLINE_PARTY, r["party_size"], key=f"rp_{r['id']}")
                new_day = st.date_input("Date", value=d, min_value=hours.today(),
                                        max_value=hours.today() + timedelta(days=res.BOOK_AHEAD_DAYS), key=f"rd_{r['id']}")
                opts = res.available_times(new_day, int(new_party), exclude_id=r["id"])
                if opts:
                    new_time = st.selectbox("Time", opts, format_func=hours.fmt_time, key=f"rt_{r['id']}")
                    if st.button("Save changes", key=f"rs_{r['id']}"):
                        ok, msg = res.reschedule(r["id"], user["id"], new_time, int(new_party))
                        st.toast(msg)
                        st.rerun()
                else:
                    st.caption("No open times for that date and party size.")
                if st.button("Cancel reservation", key=f"rc_{r['id']}"):
                    ok, msg = res.cancel(r["id"], user["id"])
                    st.toast(msg)
                    st.rerun()
