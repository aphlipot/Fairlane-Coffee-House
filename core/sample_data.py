"""Demo data so the Insights charts have something to show. Uses basic sentiment (no API cost)."""
import json
import random
from datetime import timedelta

from core import ai, auth, db, hours, menu

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
NAMES = ["Jordan Lee", "Priya Shah", "Marcus Hill", "Ana Torres", "Sam Carter", "Leila Haddad", "Chris Young", "Mei Chen"]


def load(days=30, seed=7):
    rng = random.Random(seed)
    now = hours.now()
    users = []
    for n in NAMES:
        uname = n.lower().replace(" ", ".")
        row = db.one("SELECT id, full_name, username FROM users WHERE username = ?", (uname,))
        if not row:
            db.execute(
                "INSERT INTO users (username, email, full_name, password_hash, role, created_at) VALUES (?,?,?,?,?,?)",
                (uname, f"{uname}@example.com", n, auth.hash_secret("Sample#2026"), "customer", hours.iso(now)),
            )
            row = db.one("SELECT id, full_name, username FROM users WHERE username = ?", (uname,))
        users.append(row)
    favorites = {u["id"]: rng.sample(menu.all_products(), 3) for u in users}
    order_count = 0
    for d in range(days, 0, -1):
        day = (now - timedelta(days=d)).date()
        o_dt, c_dt = hours.hours_for(day)
        span = int((c_dt - o_dt).total_seconds() // 60) - 30
        for _ in range(rng.randint(12, 28)):
            u = rng.choice(users)
            minute = int(rng.triangular(0, span, span * 0.25))
            created = o_dt + timedelta(minutes=minute)
            picks = [rng.choice(favorites[u["id"]]) if rng.random() < 0.7 else rng.choice(menu.all_products())
                     for _ in range(rng.choice([1, 1, 1, 2, 2, 3]))]
            fulfillment = rng.choices(["pickup", "curbside", "dine_in"], [0.45, 0.25, 0.30])[0]
            status = "cancelled" if rng.random() < 0.04 else "completed"
            items = []
            for cat, p in picks:
                size = menu.sizes(p)[rng.randint(0, 2)] if menu.sizes(p) else ""
                flavor = rng.choice(menu.flavors(p)) if menu.flavors(p) else ""
                items.append((cat, p["Product Name"], flavor, size, 1, menu.price_for(p, size), menu.calories_for(p, size)))
            total = round(sum(i[5] for i in items), 2)
            with db.transaction() as conn:
                cur = conn.execute(
                    """INSERT INTO orders (user_id, customer_name, fulfillment, status, priority, est_ready_at, total,
                       created_at, updated_at, completed_at, vehicle) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (u["id"], u["full_name"], fulfillment, status, 0, hours.iso(created + timedelta(minutes=6)), total,
                     hours.iso(created), hours.iso(created), hours.iso(created + timedelta(minutes=rng.randint(4, 14))),
                     "Silver Ford Escape" if fulfillment == "curbside" else ""),
                )
                for it in items:
                    conn.execute(
                        """INSERT INTO order_items (order_id, category, product, flavor, size, quantity, unit_price, calories)
                           VALUES (?,?,?,?,?,?,?,?)""", (cur.lastrowid,) + it)
            order_count += 1
        if rng.random() < 0.8:
            text = rng.choice(SAMPLE_REVIEWS)
            a = ai._basic_sentiment(text)
            u = rng.choice(users)
            db.execute(
                """INSERT INTO feedback (user_id, name, rating, comment, sentiment, sentiment_score, stars, topics,
                   summary, reply, source, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (u["id"], u["full_name"], max(1, min(5, round(a["stars"]))), text, a["sentiment"], a["score"], a["stars"],
                 json.dumps(a["topics"]), a["summary"], a["reply"], "sample",
                 hours.iso(o_dt + timedelta(hours=rng.randint(1, 8)))),
            )
    return order_count
