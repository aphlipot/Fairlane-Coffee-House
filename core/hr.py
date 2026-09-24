"""Employees and shifts for payroll and labor analytics."""
from datetime import datetime

from core import db, hours

POSITIONS = ["Barista", "Shift Lead", "Kitchen Prep", "Assistant Manager"]


def employees(active_only=False):
    sql = "SELECT * FROM employees" + (" WHERE status = 'active'" if active_only else "") + " ORDER BY status, name"
    return db.query(sql)


def add_employee(name, position, rate, hire_date, user_id=None):
    if not name.strip():
        return False, "Enter a name."
    if rate <= 0:
        return False, "Enter an hourly rate above zero."
    db.execute(
        "INSERT INTO employees (user_id, name, position, hourly_rate, hire_date, status, created_at) VALUES (?,?,?,?,?,?,?)",
        (user_id, name.strip(), position, float(rate), hire_date.isoformat(), "active", hours.iso(hours.now())),
    )
    return True, f"Added {name.strip()}."


def update_employee(emp_id, position, rate, status):
    db.execute("UPDATE employees SET position = ?, hourly_rate = ?, status = ? WHERE id = ?",
               (position, float(rate), status, emp_id))


def log_shift(emp_id, start, end):
    if end <= start:
        return False, "The shift has to end after it starts."
    hrs = round((end - start).total_seconds() / 3600, 2)
    if hrs > 14:
        return False, "Shifts over 14 hours look like a typo. Check the times."
    clash = db.one("SELECT id FROM shifts WHERE employee_id = ? AND start_at < ? AND end_at > ?",
                   (emp_id, hours.iso(end), hours.iso(start)))
    if clash:
        return False, "This overlaps another shift for the same person."
    db.execute("INSERT INTO shifts (employee_id, start_at, end_at, hours, created_at) VALUES (?,?,?,?,?)",
               (emp_id, hours.iso(start), hours.iso(end), hrs, hours.iso(hours.now())))
    return True, f"Logged {hrs:g} hours."


def delete_shift(shift_id):
    db.execute("DELETE FROM shifts WHERE id = ?", (shift_id,))


def shifts_between(start: datetime, end: datetime):
    return db.query(
        """SELECT s.*, e.name, e.position, e.hourly_rate FROM shifts s JOIN employees e ON e.id = s.employee_id
           WHERE s.start_at >= ? AND s.start_at < ? ORDER BY s.start_at""",
        (hours.iso(start), hours.iso(end)),
    )
