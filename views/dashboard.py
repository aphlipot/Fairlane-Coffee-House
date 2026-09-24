from datetime import datetime, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from core import ai, db, finance, hours, hr, orders, reservations, sample_data, ui

BLUE, MAIZE = "#00274C", "#FFCB05"

ui.header("Manager dashboard", "Profit, orders, products, and staffing for the period you choose.")
ui.require_role("manager")

# ---------- period ----------
PERIODS = {"Last 7 days": 7, "Last 30 days": 30, "Last 90 days": 90, "Month to date": "mtd"}
choice = st.segmented_control("Period", list(PERIODS), default="Last 30 days", label_visibility="collapsed") or "Last 30 days"
today_start = datetime.combine(hours.today(), datetime.min.time())
end = today_start + timedelta(days=1)
if PERIODS[choice] == "mtd":
    start = today_start.replace(day=1)
else:
    start = end - timedelta(days=PERIODS[choice])
prev_start, prev_end = start - (end - start), start
st.caption(f"{start:%b %d, %Y} to {(end - timedelta(days=1)):%b %d, %Y}. Changes compare with the {(end - start).days} days before.")

summary, daily, (o, i, s, e) = finance.pnl(start, end)
prev, _, (po, _, ps, _) = finance.pnl(prev_start, prev_end)

if o.empty and s.empty:
    st.info("No orders or shifts in this period yet. Load sample data to see the dashboard in action, "
            "or add staff and shifts on the Staff and payroll page.")
    if st.button("Load 30 days of sample data", type="primary"):
        with st.spinner("Creating sample orders, shifts, and expenses"):
            n = sample_data.load()
        st.success(f"Added {n:,} sample orders.")
        st.rerun()
    st.stop()

live = o[o["status"] != "cancelled"] if not o.empty else o
p_live = po[po["status"] != "cancelled"] if not po.empty else po
rev = summary["revenue"] or 0.0


def pct(part, whole):
    return part / whole if whole else 0.0


# The prior period needs real activity for a comparison to mean anything.
has_prior = prev["revenue"] >= 0.25 * rev and prev["revenue"] > 0


def delta(cur, before, points=False):
    if not has_prior or not before:
        return None
    if points:
        return f"{(cur - before) * 100:+.1f} pts"
    return f"{(cur - before) / abs(before):+.0%}"


overview, orders_tab, products_tab, hr_tab = st.tabs(["Profit and loss", "Orders", "Products", "HR and labor"])

# ---------- profit and loss ----------
with overview:
    m = st.columns(4)
    m[0].metric("Revenue", ui.money(rev), delta(rev, prev["revenue"]))
    m[1].metric("Gross profit", ui.money(summary["gross_profit"]), delta(summary["gross_profit"], prev["gross_profit"]))
    m[2].metric("Net profit", ui.money(summary["net_profit"]), delta(summary["net_profit"], prev["net_profit"]))
    m[3].metric("Net margin", f"{pct(summary['net_profit'], rev):.1%}",
                delta(pct(summary["net_profit"], rev), pct(prev["net_profit"], prev["revenue"]), points=True))
    m = st.columns(4)
    m[0].metric("Cost of goods", ui.money(summary["cogs"]), f"{pct(summary['cogs'], rev):.1%} of sales",
                delta_color="off", delta_arrow="off")
    m[1].metric("Labor", ui.money(summary["labor"]), f"{pct(summary['labor'], rev):.1%} of sales",
                delta_color="off", delta_arrow="off")
    m[2].metric("Overhead", ui.money(summary["fixed"] + summary["one_off"]),
                f"{pct(summary['fixed'] + summary['one_off'], rev):.1%} of sales", delta_color="off", delta_arrow="off")
    m[3].metric("Prime cost", ui.money(summary["cogs"] + summary["labor"]),
                f"{pct(summary['cogs'] + summary['labor'], rev):.1%} of sales", delta_color="off", delta_arrow="off",
                help="Cost of goods plus labor. Most cafés aim for 60% of sales or less.")

    # Leave out today while it has no sales yet, so a partial day doesn't skew the charts.
    chart_daily = daily.iloc[:-1] if len(daily) > 1 and daily["Revenue"].iloc[-1] == 0 else daily

    left, right = st.columns([1, 1], gap="large")
    with left:
        st.markdown("**Revenue and net profit by day**")
        st.line_chart(chart_daily[["Revenue", "Net profit"]], color=[BLUE, MAIZE])
        st.markdown("**Where each day's money went**")
        st.bar_chart(chart_daily[["Cost of goods", "Labor", "Overhead", "Card fees"]], stack=True)
    with right:
        st.markdown("**Profit and loss statement**")
        rows = [
            ("Revenue", rev),
            ("Cost of goods sold", -summary["cogs"]),
            ("Gross profit", summary["gross_profit"]),
            ("Labor with payroll taxes", -summary["labor"]),
            ("Card processing fees", -summary["card_fees"]),
            ("Fixed overhead (prorated)", -summary["fixed"]),
            ("Other expenses", -summary["one_off"]),
            ("Net profit", summary["net_profit"]),
        ]
        statement = pd.DataFrame([{"Line": a, "Amount": ui.money(b), "Share": f"{pct(b, rev):.1%}"} for a, b in rows])
        st.dataframe(statement, hide_index=True, width="stretch")
        st.download_button("Download P&L (CSV)", daily.round(2).to_csv(index_label="Date"), "fairlane_daily_pnl.csv", "text/csv")

        st.markdown("**Watch list**")
        alerts = []
        if pct(summary["cogs"], rev) > 0.32:
            alerts.append(f"Cost of goods is {pct(summary['cogs'], rev):.0%} of sales. Target is under 32%.")
        if pct(summary["labor"], rev) > 0.32:
            alerts.append(f"Labor is {pct(summary['labor'], rev):.0%} of sales. Target is under 32%.")
        if summary["ot_hours"] > 0:
            alerts.append(f"{summary['ot_hours']:.1f} overtime hours this period.")
        done = live[live["completed_at"].notna()] if not live.empty else live
        if not done.empty:
            late = (pd.to_datetime(done["completed_at"]) - pd.to_datetime(done["scheduled_for"].fillna(done["est_ready_at"]))).dt.total_seconds() / 60
            on_time = (late <= 3).mean()
            if on_time < 0.85:
                alerts.append(f"Only {on_time:.0%} of orders were ready on time. Target is 85% or better.")
        fb = db.one("SELECT AVG(stars) AS a, COUNT(*) AS n FROM feedback WHERE created_at >= ? AND created_at < ?",
                    (hours.iso(start), hours.iso(end)))
        if fb and fb["n"] and fb["a"] < 3.5:
            alerts.append(f"Average review score is {fb['a']:.1f} of 5 across {fb['n']} reviews.")
        if summary["net_profit"] < 0:
            alerts.append("The café lost money this period.")
        st.markdown("\n".join(f"- {a}" for a in alerts) if alerts else "Nothing needs attention.")

# ---------- orders ----------
with orders_tab:
    if live.empty:
        st.write("No orders in this period.")
    else:
        items_per = i.groupby("order_id")["quantity"].sum().mean() if not i.empty else 0
        m = st.columns(4)
        m[0].metric("Orders", f"{len(live):,}", delta(len(live), len(p_live)))
        m[1].metric("Average ticket", ui.money(live["total"].mean()),
                    delta(live["total"].mean(), p_live["total"].mean() if not p_live.empty else 0))
        m[2].metric("Items per order", f"{items_per:.2f}")
        m[3].metric("Cancelled", f"{(o['status'] == 'cancelled').mean():.1%}")

        done = live[live["completed_at"].notna()].copy()
        if not done.empty:
            done["due"] = pd.to_datetime(done["scheduled_for"].fillna(done["est_ready_at"]))
            done["late_min"] = (pd.to_datetime(done["completed_at"]) - done["due"]).dt.total_seconds() / 60
            curb = done[done["arrived_at"].notna()]
            curb_wait = ((pd.to_datetime(curb["completed_at"]) - pd.to_datetime(curb["arrived_at"])).dt.total_seconds() / 60).mean() if not curb.empty else None
            m = st.columns(4)
            m[0].metric("Ready on time", f"{(done['late_min'] <= 3).mean():.0%}", help="Finished within 3 minutes of the promised time.")
            m[1].metric("Average minutes late", f"{done.loc[done['late_min'] > 3, 'late_min'].mean():.1f}" if (done["late_min"] > 3).any() else "0")
            m[2].metric("Curbside wait after check-in", f"{curb_wait:.1f} min" if curb_wait is not None else "n/a")
            m[3].metric("Ordered ahead", f"{live['scheduled_for'].notna().mean():.0%}")

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Busiest times (average orders per hour)**")
            heat = live.assign(Day=live["created_at"].dt.day_name(), Hour=live["created_at"].dt.hour)
            n_weeks = max(1, (end - start).days / 7)
            heat = heat.groupby(["Day", "Hour"]).size().div(n_weeks).reset_index(name="Orders")
            chart = alt.Chart(heat).mark_rect().encode(
                x=alt.X("Hour:O", title="Hour of day"),
                y=alt.Y("Day:O", sort=hours.DAY_NAMES, title=None),
                color=alt.Color("Orders:Q", scale=alt.Scale(range=["#F4F6F9", MAIZE, BLUE]), legend=alt.Legend(title="Orders")),
                tooltip=["Day", "Hour", alt.Tooltip("Orders:Q", format=".1f")],
            )
            st.altair_chart(chart, width="stretch")
        with c2:
            st.markdown("**How customers get their orders**")
            mix = live.groupby("fulfillment").agg(Orders=("id", "count"), Revenue=("total", "sum")).rename(index=orders.FULFILLMENT_LABELS)
            st.bar_chart(mix["Orders"], horizontal=True)
            mix["Revenue"] = mix["Revenue"].map(ui.money)
            mix["Share"] = (mix["Orders"] / mix["Orders"].sum()).map("{:.0%}".format)
            st.dataframe(mix, width="stretch")

    st.markdown("**Reservations**")
    rv = pd.DataFrame(db.query("SELECT * FROM reservations WHERE start_at >= ? AND start_at < ?", (hours.iso(start), hours.iso(end))))
    if rv.empty:
        st.write("No reservations in this period.")
    else:
        kept = rv[rv["status"].isin(["completed", "seated", "booked"])]
        open_hours = sum((lambda o_c: (o_c[1] - o_c[0]).total_seconds() / 3600)(hours.hours_for((start + timedelta(days=d)).date()))
                         for d in range((end - start).days))
        table_hours_available = open_hours * len(reservations.TABLES)
        m = st.columns(4)
        m[0].metric("Reservations", f"{len(rv):,}")
        m[1].metric("Guests seated", f"{int(kept['party_size'].sum()):,}")
        m[2].metric("No-show rate", f"{(rv['status'] == 'no_show').mean():.1%}")
        m[3].metric("Table-hours booked", f"{len(kept) * 1.5 / table_hours_available:.0%}" if table_hours_available else "n/a",
                    help="Share of available table time that was reserved.")

# ---------- products ----------
with products_tab:
    if i.empty:
        st.write("No items sold in this period.")
    else:
        prod = i.assign(Revenue=i["unit_price"] * i["quantity"], Cost=i["unit_cost"] * i["quantity"]).groupby(
            ["category", "product"]).agg(Units=("quantity", "sum"), Revenue=("Revenue", "sum"), Cost=("Cost", "sum")).reset_index()
        prod["Profit"] = prod["Revenue"] - prod["Cost"]
        prod["Margin"] = prod["Profit"] / prod["Revenue"]
        prod["Profit per unit"] = prod["Profit"] / prod["Units"]
        # Menu engineering (Kasavana and Smith): popularity vs. contribution margin.
        pop_line = 0.7 / len(prod)
        cm_line = prod["Profit"].sum() / prod["Units"].sum()
        prod["Mix"] = prod["Units"] / prod["Units"].sum()

        def classify(r):
            popular, profitable = r["Mix"] >= pop_line, r["Profit per unit"] >= cm_line
            return {(True, True): "Star", (True, False): "Plowhorse", (False, True): "Puzzle", (False, False): "Dog"}[(popular, profitable)]

        prod["Class"] = prod.apply(classify, axis=1)

        c1, c2 = st.columns([3, 2], gap="large")
        with c1:
            st.markdown("**Menu engineering**")
            st.caption("Stars: keep and feature. Plowhorses: popular but thin margin, so review price or cost. "
                       "Puzzles: profitable but slow, so promote them. Dogs: consider replacing.")
            scatter = alt.Chart(prod).mark_circle(size=160, opacity=0.9, stroke=BLUE, strokeWidth=1).encode(
                x=alt.X("Units:Q", title="Units sold"),
                y=alt.Y("Profit per unit:Q", title="Profit per unit ($)"),
                color=alt.Color("Class:N", scale=alt.Scale(domain=["Star", "Plowhorse", "Puzzle", "Dog"],
                                                           range=[BLUE, MAIZE, "#7FB2E5", "#C9CED6"])),
                tooltip=["product", "Class", "Units", alt.Tooltip("Profit per unit:Q", format="$.2f"), alt.Tooltip("Margin:Q", format=".0%")],
            )
            rule_y = alt.Chart(pd.DataFrame({"y": [cm_line]})).mark_rule(strokeDash=[4, 4], color="#7A8699").encode(y="y:Q")
            rule_x = alt.Chart(pd.DataFrame({"x": [pop_line * prod["Units"].sum()]})).mark_rule(strokeDash=[4, 4], color="#7A8699").encode(x="x:Q")
            st.altair_chart(scatter + rule_x + rule_y, width="stretch")
        with c2:
            st.markdown("**Revenue by category**")
            st.bar_chart(prod.groupby("category")["Revenue"].sum(), horizontal=True)
            best = prod.sort_values("Profit", ascending=False).iloc[0]
            worst = prod.sort_values("Margin").iloc[0]
            st.markdown(f"Top profit item: **{best['product']}** ({ui.money(best['Profit'])}).  \n"
                        f"Lowest margin: **{worst['product']}** ({worst['Margin']:.0%}).")

        table = prod.sort_values("Profit", ascending=False)[["product", "category", "Class", "Units", "Revenue", "Cost", "Profit", "Margin"]]
        table = table.assign(Margin=table["Margin"] * 100)
        st.dataframe(
            table.rename(columns={"product": "Item", "category": "Category"}), hide_index=True, width="stretch",
            column_config={"Revenue": st.column_config.NumberColumn(format="dollar"), "Cost": st.column_config.NumberColumn(format="dollar"),
                           "Profit": st.column_config.NumberColumn(format="dollar"), "Margin": st.column_config.NumberColumn(format="%.1f%%")},
        )
        st.page_link("views/costs.py", label="Update item costs", icon=":material/price_change:")

# ---------- HR ----------
with hr_tab:
    emps = hr.employees(active_only=True)
    labor = summary["labor"]
    hrs_worked = summary["labor_hours"]
    m = st.columns(4)
    m[0].metric("Active staff", len(emps))
    m[1].metric("Hours worked", f"{hrs_worked:,.0f}", delta(hrs_worked, prev["labor_hours"]))
    m[2].metric("Labor cost", ui.money(labor), delta(labor, prev["labor"]), delta_color="inverse")
    m[3].metric("Labor % of sales", f"{pct(labor, rev):.1%}",
                delta(pct(labor, rev), pct(prev["labor"], prev["revenue"]), points=True), delta_color="inverse")
    m = st.columns(4)
    m[0].metric("Sales per labor hour", ui.money(pct(rev, hrs_worked)), help="Revenue divided by hours worked.")
    m[1].metric("Orders per labor hour", f"{pct(len(live), hrs_worked):.1f}")
    m[2].metric("Overtime hours", f"{summary['ot_hours']:.1f}", delta_color="inverse")
    m[3].metric("Average hourly rate", ui.money(sum(e_["hourly_rate"] for e_ in emps) / len(emps)) if emps else "n/a")

    if s.empty:
        st.write("No shifts logged in this period.")
        st.page_link("views/staff.py", label="Add staff and log shifts", icon=":material/badge:")
    else:
        c1, c2 = st.columns(2, gap="large")
        with c1:
            st.markdown("**Orders per staff member, by hour**")
            st.caption("Averages per open day. Tall bars mean each person is handling more orders, so consider adding help then.")
            cover = {}
            for _, row in s.iterrows():
                t, stop = row["start_at"], pd.to_datetime(row["end_at"])
                while t < stop:
                    nxt = min(stop, (t + pd.Timedelta(hours=1)).floor("h"))
                    cover[t.hour] = cover.get(t.hour, 0) + (nxt - t).total_seconds() / 3600
                    t = nxt
            n_days = max(1, s["start_at"].dt.normalize().nunique())
            staffing = pd.DataFrame({"Staff on floor": pd.Series(cover) / n_days})
            if not live.empty:
                staffing["Orders per hour"] = live.groupby(live["created_at"].dt.hour).size() / n_days
                staffing["Orders per staff member"] = staffing["Orders per hour"] / staffing["Staff on floor"]
            staffing = staffing.fillna(0).sort_index()
            load = staffing.reset_index(names="h")
            load = load[load["h"].between(6, 22)]
            load["Hour"] = load["h"].map(lambda h: f"{(h - 1) % 12 + 1} {'AM' if h < 12 else 'PM'}")
            ycol = "Orders per staff member" if "Orders per staff member" in load else "Staff on floor"
            st.altair_chart(alt.Chart(load).mark_bar(color=BLUE).encode(
                x=alt.X("Hour:N", sort=list(load["Hour"]), title=None), y=alt.Y(f"{ycol}:Q", title=ycol),
                tooltip=["Hour", alt.Tooltip("Staff on floor:Q", format=".1f"), alt.Tooltip(f"{ycol}:Q", format=".1f")]),
                width="stretch")
            if ycol == "Orders per staff member" and not load.empty:
                peak = load.loc[load[ycol].idxmax()]
                st.caption(f"Busiest per person: {peak['Hour']}, about {peak[ycol]:.1f} orders per staff member.")
        with c2:
            st.markdown("**Labor cost as a share of sales by day**")
            lp = (100 * daily["Labor"] / daily["Revenue"].where(daily["Revenue"] > 0)).rename("Labor % of sales").to_frame().dropna()
            lp["Target (30%)"] = 30.0
            st.line_chart(lp, color=[BLUE, MAIZE])

        st.markdown("**Hours and pay by employee**")
        by_emp = s.groupby(["name", "position"]).agg(Shifts=("id", "count"), Hours=("hours", "sum"),
                                                     Overtime=("ot_hours", "sum"), Cost=("cost", "sum")).reset_index()
        by_emp = by_emp.sort_values("Hours", ascending=False).rename(columns={"name": "Employee", "position": "Position"})
        st.dataframe(by_emp, hide_index=True, width="stretch",
                     column_config={"Hours": st.column_config.NumberColumn(format="%.1f"),
                                    "Overtime": st.column_config.NumberColumn(format="%.1f"),
                                    "Cost": st.column_config.NumberColumn("Cost with taxes", format="dollar")})
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Labor cost by position**")
            st.bar_chart(s.groupby("position")["cost"].sum().rename("Cost"), horizontal=True)

    with (c2 if not s.empty else st.container()):
        st.markdown("**Hiring pipeline**")
        iv = pd.DataFrame(db.query("SELECT * FROM interviews WHERE created_at >= ? AND created_at < ?", (hours.iso(start), hours.iso(end))))
        if iv.empty:
            st.write("No applicants in this period.")
        else:
            funnel = iv["status"].value_counts().reindex(["new", "contacted", "hired", "declined"]).fillna(0)
            funnel.index = ["New", "Contacted", "Hired", "Declined"]
            st.bar_chart(funnel)
            st.caption(f"{len(iv)} applicants, average AI score {iv['score'].dropna().mean():.1f} of 10."
                       if iv["score"].notna().any() else f"{len(iv)} applicants.")
            st.page_link("views/hiring.py", label="Review applicants", icon=":material/group_add:")

# ---------- AI brief ----------
st.divider()
st.subheader("AI brief")
ui.ai_mode_note()
if st.button("Write the brief"):
    lines = [
        f"Period: {start:%Y-%m-%d} to {end:%Y-%m-%d} ({summary['days']} days).",
        f"Revenue {rev:.2f} (prior period {prev['revenue']:.2f}). Net profit {summary['net_profit']:.2f} (prior {prev['net_profit']:.2f}).",
        f"Cost of goods {pct(summary['cogs'], rev):.1%}, labor {pct(summary['labor'], rev):.1%}, overhead {pct(summary['fixed'] + summary['one_off'], rev):.1%} of sales.",
        f"Labor hours {summary['labor_hours']:.0f}, overtime {summary['ot_hours']:.1f}, sales per labor hour {pct(rev, summary['labor_hours']):.2f}.",
    ]
    if not live.empty:
        lines.append(f"Orders {len(live)}, average ticket {live['total'].mean():.2f}. Fulfillment mix {live['fulfillment'].value_counts().to_dict()}.")
        lines.append(f"Orders by hour: {live.groupby(live['created_at'].dt.hour).size().to_dict()}.")
    if not i.empty:
        lines.append("Items (units, profit): " + "; ".join(f"{r.product} {r.Units} {r.Profit:.0f} {r.Class}" for r in prod.itertuples()))
    with st.spinner("Writing"):
        brief = ai.insight_brief("\n".join(lines))
    if brief:
        st.markdown(brief)
    else:
        st.write("Add an OpenAI API key to generate the brief. Here is the data it would use:")
        st.code("\n".join(lines))

with st.expander("Demo data"):
    st.caption("Adds 30 days of sample customers, orders, shifts, expenses, reservations, reviews, and applicants. "
               "Sample customers log in with the password Sample#2026.")
    if st.button("Load sample data"):
        with st.spinner("Creating sample data"):
            n = sample_data.load()
        st.success(f"Added {n:,} sample orders.")
        st.rerun()
