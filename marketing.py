from collections import Counter
from datetime import timedelta

import streamlit as st

from core import ai, db, feedback, hours, ui

ui.header("Marketing studio", "Draft slogans, posts, emails, and promotions grounded in what customers actually buy and say.")
user = ui.require_role("manager")
ui.ai_mode_note()

KINDS = ["Slogans (10 options)", "Instagram post", "Email newsletter", "Promotion plan for a slow period",
         "Fairlane Pass membership pitch", "Community event idea"]


def data_context():
    start = hours.now() - timedelta(days=30)
    top = db.query(
        """SELECT i.product, SUM(i.quantity) AS q FROM order_items i JOIN orders o ON o.id = i.order_id
           WHERE o.created_at >= ? AND o.status != 'cancelled' GROUP BY i.product ORDER BY q DESC LIMIT 5""",
        (hours.iso(start),))
    counts = {r["h"]: r["n"] for r in db.query(
        """SELECT CAST(strftime('%H', created_at) AS INTEGER) AS h, COUNT(*) AS n FROM orders
           WHERE created_at >= ? AND status != 'cancelled' GROUP BY h""", (hours.iso(start),))}
    open_hours = range(7, 21)
    by_hour = sorted(({"h": h, "n": counts.get(h, 0)} for h in open_hours), key=lambda r: r["n"])[:3] if counts else []
    fb = feedback.between(start, hours.now() + timedelta(days=1))
    topics = Counter(t for f in fb for t in f["topics"])
    parts = []
    if top:
        parts.append("Best sellers last 30 days: " + ", ".join(f"{r['product']} ({r['q']})" for r in top))
    if by_hour:
        parts.append("Slowest hours: " + ", ".join(f"{r['h']}:00" for r in by_hour))
    if fb:
        pos = sum(f["sentiment"] == "positive" for f in fb) / len(fb)
        parts.append(f"{len(fb)} reviews, {pos:.0%} positive. Most mentioned: " + ", ".join(t for t, _ in topics.most_common(4)))
    return "\n".join(parts) or "No sales or review data yet."


with st.form("brief"):
    kind = st.selectbox("What do you need?", KINDS)
    c1, c2 = st.columns(2)
    goal = c1.text_input("Goal", placeholder="Fill the 2 to 4 PM slump")
    audience = c2.text_input("Audience", placeholder="Graduate students at Fairlane Center")
    tone = c1.selectbox("Tone", ["Warm and friendly", "Playful", "Professional", "Bold"])
    channel = c2.selectbox("Channel", ["Instagram", "Email", "In-store sign", "App notification", "LinkedIn"])
    context = st.text_area("Business context (from your data, edit as needed)", value=data_context(), height=110)
    go = st.form_submit_button("Draft it", type="primary")

if go:
    with st.spinner("Drafting"):
        text = ai.marketing_copy(kind, goal or "grow repeat visits", audience or "Fairlane Center community",
                                 tone, channel, context)
    db.execute("INSERT INTO marketing_assets (created_by, kind, brief, content, created_at) VALUES (?,?,?,?,?)",
               (user["username"], kind, f"{goal} | {audience} | {tone} | {channel}", text, hours.iso(hours.now())))
    with st.container(border=True):
        st.markdown(text)
    st.download_button("Download as text", text, "fairlane_marketing.txt")

past = db.query("SELECT * FROM marketing_assets ORDER BY created_at DESC LIMIT 20")
if past:
    st.subheader("Saved drafts")
    for a in past:
        with st.expander(f"{a['kind']}, {hours.fmt_dt(a['created_at'])}"):
            st.caption(a["brief"])
            st.markdown(a["content"])
