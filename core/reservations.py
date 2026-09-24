"""Table reservations with automatic table assignment."""
from datetime import timedelta

from core import db, hours

# (table id, seats)
TABLES = [("A1", 2), ("A2", 2), ("A3", 2), ("A4", 2), ("B1", 4), ("B2", 4), ("B3", 4), ("B4", 4), ("C1", 6), ("C2", 6)]
SEATING_MINUTES = 90
STEP_MINUTES = 30
MAX_ONLINE_PARTY = 6
BOOK_AHEAD_DAYS = 30
STATUS_LABELS = {"booked": "Booked", "seated": "Seated", "completed": "Completed", "cancelled": "Cancelled", "no_show": "No-show"}


def _busy(start, end, exclude_id=None):
    rows = db.query(
        "SELECT table_id FROM reservations WHERE status IN ('booked','seated') AND start_at < ? AND end_at > ? AND id != ?",
        (hours.iso(end), hours.iso(start), exclude_id or -1),
    )
    return {r["table_id"] for r in rows}


def find_table(start, party, exclude_id=None):
    busy = _busy(start, start + timedelta(minutes=SEATING_MINUTES), exclude_id)
    for table_id, seats in sorted(TABLES, key=lambda t: t[1]):
        if seats >= party and table_id not in busy:
            return table_id
    return None


def available_times(day, party, exclude_id=None):
    open_dt, close_dt = hours.hours_for(day)
    last = close_dt - timedelta(minutes=SEATING_MINUTES)
    t = open_dt
    if day == hours.today():
        t = max(t, hours.ceil_to(hours.now() + timedelta(minutes=30), STEP_MINUTES))
    times = []
    while t <= last:
        if find_table(t, party, exclude_id):
            times.append(t)
        t += timedelta(minutes=STEP_MINUTES)
    return times


def book(user, start, party, name, phone, notes=""):
    if party > MAX_ONLINE_PARTY:
        return False, f"Online booking is for up to {MAX_ONLINE_PARTY} guests. Email us for larger groups."
    if user and db.one(
        "SELECT id FROM reservations WHERE user_id = ? AND status = 'booked' AND start_at < ? AND end_at > ?",
        (user["id"], hours.iso(start + timedelta(minutes=SEATING_MINUTES)), hours.iso(start)),
    ):
        return False, "You already have a reservation that overlaps this time."
    with db.transaction() as conn:
        table = find_table(start, party)
        if not table:
            return False, "That time was just taken. Pick another."
        cur = conn.execute(
            """INSERT INTO reservations (user_id, name, phone, party_size, start_at, end_at, table_id, status, notes, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (user["id"] if user else None, name.strip(), phone.strip(), party, hours.iso(start),
             hours.iso(start + timedelta(minutes=SEATING_MINUTES)), table, "booked", notes.strip(), hours.iso(hours.now())),
        )
    return True, cur.lastrowid


def get(res_id):
    return db.one("SELECT * FROM reservations WHERE id = ?", (res_id,))


def for_user(user_id):
    return db.query(
        "SELECT * FROM reservations WHERE user_id = ? AND status = 'booked' AND end_at >= ? ORDER BY start_at",
        (user_id, hours.iso(hours.now())),
    )


def cancel(res_id, user_id):
    r = get(res_id)
    if not r or r["user_id"] != user_id or r["status"] != "booked":
        return False, "Reservation not found."
    db.execute("UPDATE reservations SET status = 'cancelled' WHERE id = ?", (res_id,))
    return True, "Reservation cancelled."


def reschedule(res_id, user_id, new_start, party):
    r = get(res_id)
    if not r or r["user_id"] != user_id or r["status"] != "booked":
        return False, "Reservation not found."
    with db.transaction() as conn:
        table = find_table(new_start, party, exclude_id=res_id)
        if not table:
            return False, "That time is no longer available."
        conn.execute("UPDATE reservations SET start_at = ?, end_at = ?, party_size = ?, table_id = ? WHERE id = ?",
                     (hours.iso(new_start), hours.iso(new_start + timedelta(minutes=SEATING_MINUTES)), party, table, res_id))
    return True, f"Moved to {hours.fmt_dt(new_start)}."


def for_day(day):
    return db.query(
        "SELECT * FROM reservations WHERE start_at LIKE ? AND status != 'cancelled' ORDER BY start_at",
        (f"{day.isoformat()}%",),
    )


def set_status(res_id, status):
    db.execute("UPDATE reservations SET status = ? WHERE id = ?", (status, res_id))
