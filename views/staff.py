from datetime import datetime, time, timedelta

import pandas as pd
import streamlit as st

from core import auth, finance, hours, hr, ui

ui.header("Staff and payroll", "Keep the team roster and pay rates current, and log shifts. The dashboard uses these for labor cost.")
ui.require_role("manager")

roster, shifts_tab = st.tabs(["Team", "Shifts"])

with roster:
    emps = hr.employees()
    if emps:
        df = pd.DataFrame(emps)[["id", "name", "position", "hourly_rate", "hire_date", "status"]]
        edited = st.data_editor(
            df, hide_index=True, width="stretch", disabled=["id", "name", "hire_date"], key="roster_editor",
            column_config={
                "id": None,
                "name": "Name",
                "position": st.column_config.SelectboxColumn("Position", options=hr.POSITIONS, required=True),
                "hourly_rate": st.column_config.NumberColumn("Hourly rate", min_value=0.0, step=0.25, format="$%.2f"),
                "hire_date": "Hired",
                "status": st.column_config.SelectboxColumn("Status", options=["active", "inactive"], required=True),
            },
        )
        if st.button("Save changes", type="primary"):
            for _, r in edited.iterrows():
                hr.update_employee(int(r["id"]), r["position"], r["hourly_rate"], r["status"])
            st.success("Team updated.")
            st.rerun()
    else:
        st.write("No employees yet. Add your first team member below.")

    st.subheader("Add an employee")
    with st.form("add_emp", clear_on_submit=True):
        c1, c2 = st.columns(2)
        name = c1.text_input("Name")
        position = c2.selectbox("Position", hr.POSITIONS)
        rate = c1.number_input("Hourly rate ($)", min_value=0.0, value=15.50, step=0.25)
        hired = c2.date_input("Hire date", value=hours.today())
        accounts = {u["id"]: f"{u['full_name'] or u['username']} ({u['username']})" for u in auth.all_users() if u["role"] in ("staff", "manager")}
        link = st.selectbox("Link to an app login (optional)", [None] + list(accounts), format_func=lambda k: "None" if k is None else accounts[k])
        if st.form_submit_button("Add employee", type="primary"):
            ok, msg = hr.add_employee(name, position, rate, hired, link)
            (st.success if ok else st.error)(msg)
            if ok:
                st.rerun()
    r = finance.rates()
    st.caption(f"Labor cost adds {r['payroll_burden_pct']:g}% for payroll taxes and benefits, and pays "
               f"{r['overtime_multiplier']:g}x for hours past 40 in a week. Change these on the Costs page.")

with shifts_tab:
    active = hr.employees(active_only=True)
    if not active:
        st.write("Add an employee first.")
    else:
        st.subheader("Log a shift")
        with st.form("log_shift", clear_on_submit=True):
            c = st.columns(4)
            emp = c[0].selectbox("Employee", active, format_func=lambda e: e["name"])
            day = c[1].date_input("Date", value=hours.today())
            start_t = c[2].time_input("Start", value=time(7, 0), step=900)
            end_t = c[3].time_input("End", value=time(15, 0), step=900)
            if st.form_submit_button("Log shift", type="primary"):
                start = datetime.combine(day, start_t)
                end = datetime.combine(day + timedelta(days=1 if end_t <= start_t else 0), end_t)
                ok, msg = hr.log_shift(emp["id"], start, end)
                (st.success if ok else st.error)(msg)

    st.subheader("Recent shifts")
    week_start = datetime.combine(hours.today() - timedelta(days=hours.today().weekday()), time())
    c1, c2 = st.columns(2)
    frm = c1.date_input("From", value=(week_start - timedelta(days=7)).date())
    to = c2.date_input("To", value=hours.today())
    rows = hr.shifts_between(datetime.combine(frm, time()), datetime.combine(to + timedelta(days=1), time()))
    if not rows:
        st.write("No shifts in this range.")
    else:
        sdf = finance.labor_costs(pd.DataFrame(rows).assign(start_at=lambda d: pd.to_datetime(d["start_at"])))
        st.metric("Hours in range", f"{sdf['hours'].sum():,.1f}")
        st.dataframe(
            sdf.sort_values("start_at", ascending=False).assign(
                Date=lambda d: d["start_at"].dt.strftime("%a %b %d"),
                Start=lambda d: d["start_at"].dt.strftime("%I:%M %p"),
                End=lambda d: pd.to_datetime(d["end_at"]).dt.strftime("%I:%M %p"),
            )[["Date", "name", "position", "Start", "End", "hours", "ot_hours", "cost"]],
            hide_index=True, width="stretch",
            column_config={"name": "Employee", "position": "Position", "hours": st.column_config.NumberColumn("Hours", format="%.2f"),
                           "ot_hours": st.column_config.NumberColumn("Overtime", format="%.2f"),
                           "cost": st.column_config.NumberColumn("Cost with taxes", format="$%.2f")},
        )
        with st.expander("Delete a shift"):
            pick = st.selectbox("Shift", rows[::-1][:200],
                                format_func=lambda r: f"{r['name']}, {hours.fmt_dt(r['start_at'])} to {hours.fmt_time(hours.parse(r['end_at']))}")
            if st.button("Delete shift"):
                hr.delete_shift(pick["id"])
                st.rerun()
