"""Demo data so the dashboards have something to show. Uses basic sentiment scoring (no API cost)."""
import json
import random
from datetime import timedelta

from core import ai, auth, db, hours, menu, reservations

SAMPLE_REVIEWS = [
    "Latte was smooth and creamy, and the barista was really friendly.",
    "Curbside pickup was quick. They brought it right to my car.",
    "Waited almost 15 minutes for a cortado. Too slow when I'm between classes.",
    "Mango boba tea is my favorite. Great flavor and fresh pearls.",
    "My order was wrong and missing the muffin.",
    "Cozy place to study. Tables were clean and the wifi worked well.",
    "Coffee was lukewarm and a bit bitter today.",
    "Love the order ahead feature, my usual is always ready.",
    "Prices are a little expensive for the size, but the taste is excellent.",
    "Staff were polite but it was noisy and crowded at lunch.",
    "Best affogato I've had. Rich and delicious.",
    "The app said ready but I still waited at the counter.",
]
FIRST = ["Jordan", "Priya", "Marcus", "Ana", "Sam", "Leila", "Chris", "Mei", "Omar", "Grace", "Tyler", "Nadia",
         "Diego", "Hannah", "Ravi", "Zoe", "Malik", "Emma", "Yusuf", "Claire"]
LAST = ["Lee", "Shah", "Hill", "Torres", "Carter", "Haddad", "Young", "Chen", "Farah", "Kowalski", "Brooks", "Nguyen"]
STAFF = [("Avery Brooks", "Shift Lead", 19.50), ("Jamal Reed", "Shift Lead", 19.00), ("Sofia Ramirez", "Barista", 16.50),
         ("Ethan Park", "Barista", 16.00), ("Maya Patel", "Barista", 16.25), ("Noah Kim", "Barista", 15.75),
         ("Lina Saleh", "Barista", 15.75), ("Ben Walsh", "Kitchen Prep", 16.00), ("Tara Quinn", "Barista", 15.50)]
APPLICANTS = [("Riley Ford", "Barista", 8, "Advance", "contacted"), ("Kenji Ito", "Barista", 6, "Hold", "new"),
              ("Aisha Bello", "Shift Lead", 9, "Advance", "hired"), ("Luke Morris", "Barista", 4, "Decline", "declined"),
              ("Fatima Noor", "Kitchen Prep", 7, "Advance", "new"), ("Owen Price", "Barista", 5, "Hold", "new"),
              ("Isla Grant", "Shift Lead", 7, "Advance", "contacted"), ("Mateo Cruz", "Barista", 8, "Advance", "hired"),
              ("Ruby Shaw", "Kitchen Prep", 3, "Decline", "declined"), ("Adam Novak", "Barista", 6, "Hold", "new")]
# Relative order volume by weekday (Mon..Sun) and a campus-style hourly curve.
WEEKDAY_WEIGHT = [1.05, 1.1, 0.85, 1.1, 1.0, 0.8, 0.65]
HOUR_WEIGHT = {7: 1.4, 8: 2.2, 9: 1.8, 10: 1.3, 11: 1.4, 12: 1.9, 13: 1.4, 14: 0.8, 15: 0.9, 16: 1.0,
               17: 0.9, 18: 0.7, 19: 0.6, 20: 0.5, 21: 0.4}


def load(days=30, seed=7):
    rng = random.Random(seed)
    now = hours.now()
    today = now.date()
    pw_hash = auth.hash_secret("Sample#2026")

    with db.transaction() as conn:
        # Customers
        users = []
        for n in range(120):
            name = f"{FIRST[n % len(FIRST)]} {LAST[(n * 7) % len(LAST)]}"
            uname = f"{name.lower().replace(' ', '.')}{n}"
            row = conn.execute("SELECT id, full_name FROM users WHERE username = ?", (uname,)).fetchone()
            if not row:
                conn.execute("INSERT INTO users (username, email, full_name, password_hash, role, created_at) VALUES (?,?,?,?,?,?)",
                             (uname, f"{uname}@example.com", name, pw_hash, "customer", hours.iso(now - timedelta(days=days))))
                row = conn.execute("SELECT id, full_name FROM users WHERE username = ?", (uname,)).fetchone()
            users.append(dict(row))
        # Regulars order far more often than occasional visitors.
        user_weights = [rng.paretovariate(1.3) for _ in users]
        favorites = {u["id"]: rng.sample(menu.all_products(), 3) for u in users}

        # Staff
        staff = []
        for name, pos, rate in STAFF:
            row = conn.execute("SELECT id FROM employees WHERE name = ?", (name,)).fetchone()
            if not row:
                cur = conn.execute("INSERT INTO employees (name, position, hourly_rate, hire_date, status, created_at) VALUES (?,?,?,?,?,?)",
                                   (name, pos, rate, (today - timedelta(days=rng.randint(60, 700))).isoformat(), "active", hours.iso(now)))
                staff.append(cur.lastrowid)
            else:
                staff.append(row["id"])

        order_count = 0
        for d in range(days, 0, -1):
            day = today - timedelta(days=d)
            o_dt, c_dt = hours.hours_for(day)

            # Shifts: two openers, two closers, one mid shift on long days.
            span = (c_dt - o_dt).total_seconds() / 3600
            blocks = [(o_dt - timedelta(minutes=30), min(o_dt + timedelta(hours=7.5), c_dt))] * 2
            blocks += [(max(c_dt - timedelta(hours=7.5), o_dt), c_dt + timedelta(minutes=30))] * 2
            if span > 10:
                blocks.append((o_dt + timedelta(hours=4), o_dt + timedelta(hours=9)))
            crew = rng.sample(staff, len(blocks))
            for emp, (s, e) in zip(crew, blocks):
                if conn.execute("SELECT 1 FROM shifts WHERE employee_id = ? AND start_at = ?", (emp, hours.iso(s))).fetchone():
                    continue
                conn.execute("INSERT INTO shifts (employee_id, start_at, end_at, hours, created_at) VALUES (?,?,?,?,?)",
                             (emp, hours.iso(s), hours.iso(e), round((e - s).total_seconds() / 3600, 2), hours.iso(now)))

            # Orders
            open_hours = [h for h in range(o_dt.hour, c_dt.hour)]
            weights = [HOUR_WEIGHT.get(h, 0.5) for h in open_hours]
            n_orders = int(rng.gauss(335, 30) * WEEKDAY_WEIGHT[day.weekday()] * (len(open_hours) / 12) ** 0.5)
            for _ in range(n_orders):
                u = rng.choices(users, user_weights)[0]
                created = o_dt.replace(hour=rng.choices(open_hours, weights)[0]) + timedelta(minutes=rng.randint(0, 59))
                picks = [rng.choice(favorites[u["id"]]) if rng.random() < 0.7 else rng.choice(menu.all_products())
                         for _ in range(rng.choice([1, 1, 2, 2, 2, 3]))]
                fulfillment = rng.choices(["pickup", "curbside", "dine_in"], [0.45, 0.2, 0.35])[0]
                status = "cancelled" if rng.random() < 0.03 else "completed"
                items = []
                for cat, p in picks:
                    size = menu.sizes(p)[rng.choices([0, 1, 2], [0.3, 0.45, 0.25])[0]] if menu.sizes(p) else ""
                    flavor = rng.choice(menu.flavors(p)) if menu.flavors(p) else ""
                    items.append((cat, p["Product Name"], flavor, size, 1, menu.price_for(p, size),
                                  menu.calories_for(p, size), menu.cost_for(p, size)))
                total = round(sum(it[5] for it in items), 2)
                scheduled = created + timedelta(minutes=rng.choice([20, 30, 45, 60])) if fulfillment != "dine_in" and rng.random() < 0.4 else None
                due = scheduled or created + timedelta(minutes=5 + 2 * len(items))
                done = due + timedelta(minutes=rng.choice([-3, -2, -1, -1, 0, 0, 0, 1, 1, 2, 2, 3, 4, 6, 9]))
                arrived = due + timedelta(minutes=rng.randint(-3, 4)) if fulfillment == "curbside" else None
                if arrived and arrived > done:
                    done = arrived + timedelta(minutes=rng.randint(1, 3))
                cur = conn.execute(
                    """INSERT INTO orders (user_id, customer_name, fulfillment, scheduled_for, status, priority, est_ready_at,
                       total, created_at, updated_at, completed_at, arrived_at, vehicle) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (u["id"], u["full_name"], fulfillment, hours.iso(scheduled), status, 0, hours.iso(due), total,
                     hours.iso(created), hours.iso(done), hours.iso(done) if status == "completed" else None,
                     hours.iso(arrived), "Silver Ford Escape" if fulfillment == "curbside" else ""),
                )
                conn.executemany(
                    """INSERT INTO order_items (order_id, category, product, flavor, size, quantity, unit_price, calories, unit_cost)
                       VALUES (?,?,?,?,?,?,?,?,?)""", [(cur.lastrowid,) + it for it in items])
                order_count += 1

            # Reservations
            for _ in range(rng.randint(4, 12)):
                start = o_dt + timedelta(minutes=30 * rng.randint(0, max(0, int((span - 1.5) * 2))))
                party = rng.choices([2, 3, 4, 5, 6], [0.45, 0.2, 0.2, 0.08, 0.07])[0]
                table = next((t for t, seats in sorted(reservations.TABLES, key=lambda x: x[1]) if seats >= party), "C1")
                u = rng.choice(users)
                conn.execute(
                    """INSERT INTO reservations (user_id, name, party_size, start_at, end_at, table_id, status, created_at)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (u["id"], u["full_name"], party, hours.iso(start), hours.iso(start + timedelta(minutes=90)), table,
                     rng.choices(["completed", "no_show", "cancelled"], [0.86, 0.07, 0.07])[0], hours.iso(start - timedelta(days=2))),
                )

            # Feedback
            for _ in range(rng.randint(0, 3)):
                text = rng.choice(SAMPLE_REVIEWS)
                a = ai._basic_sentiment(text)
                u = rng.choice(users)
                conn.execute(
                    """INSERT INTO feedback (user_id, name, rating, comment, sentiment, sentiment_score, stars, topics,
                       summary, reply, source, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (u["id"], u["full_name"], max(1, min(5, round(a["stars"]))), text, a["sentiment"], a["score"],
                     a["stars"], json.dumps(a["topics"]), a["summary"], a["reply"], "sample",
                     hours.iso(o_dt + timedelta(hours=rng.randint(1, 8)))),
                )

            # One-off expenses
            if day.weekday() == 0:
                conn.execute("INSERT INTO expenses (category, amount, expense_date, note, created_at) VALUES (?,?,?,?,?)",
                             ("Supplies", round(rng.uniform(180, 320), 2), day.isoformat(), "Cleaning and paper goods", hours.iso(now)))
            if rng.random() < 0.06:
                conn.execute("INSERT INTO expenses (category, amount, expense_date, note, created_at) VALUES (?,?,?,?,?)",
                             (rng.choice(["Repairs", "Marketing", "Training"]), round(rng.uniform(120, 650), 2),
                              day.isoformat(), "Sample expense", hours.iso(now)))

        # Job applicants
        for i, (name, pos, score, rec, status) in enumerate(APPLICANTS):
            if conn.execute("SELECT 1 FROM interviews WHERE name = ?", (name,)).fetchone():
                continue
            conn.execute(
                """INSERT INTO interviews (name, email, position, transcript, score, recommendation, summary, status, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (name, f"{name.split()[0].lower()}@example.com", pos, "[]", score, rec,
                 "Sample applicant for the demo.", status, hours.iso(now - timedelta(days=rng.randint(1, days)))),
            )
    return order_count
