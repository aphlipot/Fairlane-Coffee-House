import pandas as pd
import streamlit as st

from core import db, finance, hours, menu, ui

ui.header("Costs", "Monthly overhead, one-off expenses, fee rates, and what each menu item costs to make.")
ui.require_role("manager")

overhead, expenses, items = st.tabs(["Overhead and rates", "Expenses", "Item costs"])

with overhead:
    fixed = finance.fixed_costs()
    r = finance.rates()
    with st.form("overhead"):
        st.markdown("**Monthly fixed costs**")
        st.caption("Spread evenly across each day on the dashboard.")
        cols = st.columns(3)
        new_fixed = {}
        for n, (label, amount) in enumerate(fixed.items()):
            new_fixed[label] = cols[n % 3].number_input(label, min_value=0.0, value=float(amount), step=50.0, key=f"fx_{label}")
        extra_name = st.text_input("Add another monthly cost (name)", placeholder="Cleaning service")
        extra_amt = st.number_input("Amount per month ($)", min_value=0.0, value=0.0, step=25.0)
        st.markdown("**Rates**")
        c = st.columns(3)
        card = c[0].number_input("Card processing fee (%)", 0.0, 10.0, float(r["card_fee_pct"]), step=0.1)
        burden = c[1].number_input("Payroll taxes and benefits (% of wages)", 0.0, 60.0, float(r["payroll_burden_pct"]), step=0.5)
        ot = c[2].number_input("Overtime pay multiplier", 1.0, 3.0, float(r["overtime_multiplier"]), step=0.25)
        if st.form_submit_button("Save", type="primary"):
            if extra_name.strip() and extra_amt > 0:
                new_fixed[extra_name.strip()] = extra_amt
            new_fixed = {k: v for k, v in new_fixed.items() if v > 0}
            db.set_setting("fixed_costs", new_fixed)
            db.set_setting("rates", {"card_fee_pct": card, "payroll_burden_pct": burden, "overtime_multiplier": ot})
            st.success("Saved. Set a cost to 0 to remove it.")
            st.rerun()
    st.metric("Total fixed costs per month", ui.money(sum(fixed.values())))

with expenses:
    with st.form("expense", clear_on_submit=True):
        c = st.columns([2, 1, 1])
        cat = c[0].selectbox("Category", finance.EXPENSE_CATEGORIES)
        amt = c[1].number_input("Amount ($)", min_value=0.0, step=10.0)
        day = c[2].date_input("Date", value=hours.today())
        note = st.text_input("Note", placeholder="Espresso machine repair")
        if st.form_submit_button("Add expense", type="primary"):
            ok, msg = finance.add_expense(cat, amt, day, note)
            (st.success if ok else st.error)(msg)
    rows = db.query("SELECT * FROM expenses ORDER BY expense_date DESC, id DESC LIMIT 200")
    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df[["expense_date", "category", "amount", "note"]], hide_index=True, width="stretch",
                     column_config={"expense_date": "Date", "category": "Category", "note": "Note",
                                    "amount": st.column_config.NumberColumn("Amount", format="$%.2f")})
        with st.expander("Delete an expense"):
            pick = st.selectbox("Expense", rows, format_func=lambda x: f"{x['expense_date']}, {x['category']}, {ui.money(x['amount'])}")
            if st.button("Delete expense"):
                db.execute("DELETE FROM expenses WHERE id = ?", (pick["id"],))
                st.rerun()

with items:
    st.caption("Ingredient and packaging cost per unit. New orders use these costs; past orders keep the cost from when they were placed.")
    df = pd.DataFrame(menu.cost_rows())
    df["Margin"] = (df["Price"] - df["Cost"]) / df["Price"]
    edited = st.data_editor(
        df, hide_index=True, width="stretch", disabled=["Category", "Item", "Size", "Price", "Margin"], key="cost_editor",
        column_config={"key": None, "Price": st.column_config.NumberColumn(format="$%.2f"),
                       "Cost": st.column_config.NumberColumn(min_value=0.0, step=0.05, format="$%.2f"),
                       "Margin": st.column_config.NumberColumn("Margin (at last save)", format="percent")},
    )
    if st.button("Save item costs", type="primary"):
        db.set_setting("item_costs", {r["key"]: float(r["Cost"]) for _, r in edited.iterrows()})
        st.success("Item costs saved.")
        st.rerun()
    st.caption("Prices come from data/menu.json.")
