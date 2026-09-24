"""Customer feedback storage with sentiment scores."""
import json

from core import ai, db, hours


def save(user, comment, rating=None, order_id=None, source="app", analysis=None, name=None):
    a = analysis or ai.analyze_sentiment(comment)
    fid = db.execute(
        """INSERT INTO feedback (user_id, name, order_id, rating, comment, sentiment, sentiment_score, stars,
           topics, summary, reply, source, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (user["id"] if user else None, name or (user and (user["full_name"] or user["username"])), order_id, rating,
         comment.strip(), a["sentiment"], a["score"], a["stars"], json.dumps(a["topics"]), a["summary"],
         a["reply"], source, hours.iso(hours.now())),
    )
    return fid, a


def for_user(user_id):
    return db.query("SELECT * FROM feedback WHERE user_id = ? ORDER BY created_at DESC", (user_id,))


def between(start, end):
    rows = db.query("SELECT * FROM feedback WHERE created_at >= ? AND created_at < ? ORDER BY created_at",
                    (hours.iso(start), hours.iso(end)))
    for r in rows:
        r["topics"] = json.loads(r["topics"] or "[]")
    return rows
