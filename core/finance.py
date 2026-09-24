"""Cost settings and profit and loss calculations for the manager dashboard."""
from datetime import timedelta

import pandas as pd

from core import db, hours, hr

DEFAULT_FIXED = {
    "Rent": 6500.0,
    "Utilities": 900.0,
    "Salaried staff": 5500.0,
    "Insurance": 350.0,
    "Software and app fees": 300.0,
    "Equipment lease": 400.0,
}
DEFAULT_RATES = {"card_fee_pct": 2.9, "payroll_burden_pct": 12.0, "overtime_multiplier": 1.5}
EXPENSE_CATEGORIES = ["Supplies", "Repairs", "Marketing", "Equipment", "Training", "Other"]
DAYS_PER_MONTH = 30.44


def fixed_costs():
    return db.get_setting("fixed_costs", DEFAULT_FIXED)


def rates():
    return {**DEFAULT_RATES, **db.get_setting("rates", {})}


def add_expense(category, amount, day, note):
    if amount <= 0:
        return False, "Enter an amount above zero."
    db.execute("INSERT INTO expenses (category, amount, expense_date, note, created_at) VALUES (?,?,?,?,?)",
               (category, float(amount), day.isoformat(), note.strip(), hours.iso(hours.now())))
    return True, "Expense saved."


def expenses_between(start, end):
    return db.query("SELECT * FROM expenses WHERE expense_date >= ? AND expense_date < ? ORDER BY expense_date DESC",
                    (start.date().isoformat(), end.date().isoformat()))


def frames(start, end):
    """Orders, items, shifts, and expenses for a period as DataFrames."""
    o = pd.DataFrame(db.query("SELECT * FROM orders WHERE created_at >= ? AND created_at < ?",
                              (hours.iso(start), hours.iso(end))))
    i = pd.DataFrame(db.query(
        """SELECT i.*, o.created_at, o.customer_name, o.user_id FROM order_items i JOIN orders o ON o.id = i.order_id
           WHERE o.created_at >= ? AND o.created_at < ? AND o.status != 'cancelled'""",
        (hours.iso(start), hours.iso(end))))
    s = pd.DataFrame(hr.shifts_between(start, end))
    e = pd.DataFrame(expenses_between(start, end))
    for df, col in [(o, "created_at"), (i, "created_at"), (s, "start_at")]:
        if not df.empty:
            df[col] = pd.to_datetime(df[col])
    if not e.empty:
        e["expense_date"] = pd.to_datetime(e["expense_date"])
    return o, i, s, e


def labor_costs(shifts):
    """Add regular, overtime, and total cost columns. Overtime is hours past 40 in a Monday-to-Sunday week."""
    if shifts.empty:
        return shifts
    r = rates()
    s = shifts.sort_values("start_at").copy()
    s["week"] = s["start_at"].dt.to_period("W-SUN")
    s["cum"] = s.groupby(["employee_id", "week"])["hours"].cumsum()
    s["ot_hours"] = (s["cum"] - 40).clip(lower=0).clip(upper=s["hours"])
    s["reg_hours"] = s["hours"] - s["ot_hours"]
    burden = 1 + r["payroll_burden_pct"] / 100
    s["cost"] = (s["reg_hours"] + s["ot_hours"] * r["overtime_multiplier"]) * s["hourly_rate"] * burden
    return s


def pnl(start, end):
    """Profit and loss summary and a daily series for the period."""
    o, i, s, e = frames(start, end)
    r = rates()
    live = o[o["status"] != "cancelled"] if not o.empty else o
    days = max(1, (end.date() - start.date()).days)
    revenue = float(live["total"].sum()) if not live.empty else 0.0
    cogs = float((i["unit_cost"] * i["quantity"]).sum()) if not i.empty else 0.0
    s = labor_costs(s)
    labor = float(s["cost"].sum()) if not s.empty else 0.0
    card = revenue * r["card_fee_pct"] / 100
    fixed_daily = sum(fixed_costs().values()) / DAYS_PER_MONTH
    fixed = fixed_daily * days
    one_off = float(e["amount"].sum()) if not e.empty else 0.0
    gross = revenue - cogs
    net = gross - labor - card - fixed - one_off
    summary = {
        "revenue": revenue, "cogs": cogs, "gross_profit": gross, "labor": labor, "card_fees": card,
        "fixed": fixed, "one_off": one_off, "net_profit": net, "days": days,
        "labor_hours": float(s["hours"].sum()) if not s.empty else 0.0,
        "ot_hours": float(s["ot_hours"].sum()) if not s.empty else 0.0,
    }

    idx = pd.date_range(start.date(), end.date() - timedelta(days=1), freq="D")
    daily = pd.DataFrame(index=idx)
    daily["Revenue"] = live.groupby(live["created_at"].dt.normalize())["total"].sum() if not live.empty else 0.0
    daily["Cost of goods"] = (i.assign(c=i["unit_cost"] * i["quantity"]).groupby(i["created_at"].dt.normalize())["c"].sum()
                              if not i.empty else 0.0)
    daily["Labor"] = s.groupby(s["start_at"].dt.normalize())["cost"].sum() if not s.empty else 0.0
    daily["Overhead"] = fixed_daily
    if not e.empty:
        daily["Overhead"] = daily["Overhead"].add(e.groupby(e["expense_date"].dt.normalize())["amount"].sum(), fill_value=0)
    daily = daily.fillna(0)
    daily["Card fees"] = daily["Revenue"] * r["card_fee_pct"] / 100
    daily["Net profit"] = daily["Revenue"] - daily[["Cost of goods", "Labor", "Overhead", "Card fees"]].sum(axis=1)
    return summary, daily, (o, i, s, e)
