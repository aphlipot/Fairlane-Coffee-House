import io
from collections import Counter
from datetime import timedelta

import pandas as pd
import streamlit as st

from core import ai, db, feedback, hours, orders, sample_data, ui

ui.header("Insights", "Sales, customer sentiment, and preferences in one place.")
ui.require_role("manager")
ui.ai_mode_note()

days = st.segmented_control("Period", [7, 30, 90], default=30, format_func=lambda d: f"Last {d} days")
days = days or 30
end = hours.now()
start = end - timedelta(days=days)

o_rows = db.query("SELECT * FROM orders WHERE created_at >= ?", (hours.iso(start),))
i_rows = db.query(
    """SELECT i.*, o.created_at, o.user_id, o.customer_name FROM order_items i JOIN orders o ON o.id = i.order_id
       WHERE o.created_at >= ? AND o.status != 'cancelled'""", (hours.iso(start),))
f_rows = feedback.between(start, end + timedelta(days=1))

if not o_rows and not f_rows:
    st.info("No orders or feedback in this period yet.")
    if st.button("Load 30 days of sample data"):
        with st.spinner("Creating sample orders and reviews"):
            n = sample_data.load()
        st.success(f"Added {n} sample orders.")
        st.rerun()
    st.stop()

odf = pd.DataFrame(o_rows)
odf["created_at"] = pd.to_datetime(odf["created_at"])
live = odf[odf["status"] != "cancelled"]
idf = pd.DataFrame(i_rows)

sales_tab, sentiment_tab, prefs_tab, score_tab = st.tabs(
    ["Sales and operations", "Customer sentiment", "Customer preferences", "Score reviews from text"])

with sales_tab:
    m = st.columns(4)
    m[0].metric("Revenue", ui.money(live["total"].sum()))
    m[1].metric("Orders", f"{len(live):,}")
    m[2].metric("Average ticket", ui.money(live["total"].mean() if len(live) else 0))
    m[3].metric("Cancelled", f"{(odf['status'] == 'cancelled').mean():.0%}")

    daily = live.groupby(live["created_at"].dt.date)["total"].sum().rename("Revenue")
    st.markdown("**Revenue by day**")
    st.line_chart(daily)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Top items by quantity**")
        if not idf.empty:
            st.bar_chart(idf.groupby("product")["quantity"].sum().sort_values(ascending=False).head(10), horizontal=True)
    with c2:
        st.markdown("**Orders by hour of day**")
        st.bar_chart(live.groupby(live["created_at"].dt.hour).size().rename("Orders"))
    st.markdown("**How customers get their orders**")
    mix = live["fulfillment"].map(orders.FULFILLMENT_LABELS).value_counts()
    st.bar_chart(mix, horizontal=True)

with sentiment_tab:
    if not f_rows:
        st.write("No feedback in this period.")
    else:
        fdf = pd.DataFrame(f_rows)
        fdf["created_at"] = pd.to_datetime(fdf["created_at"])
        m = st.columns(3)
        m[0].metric("Average score", f"{fdf['stars'].mean():.1f} of 5")
        m[1].metric("Positive", f"{(fdf['sentiment'] == 'positive').mean():.0%}")
        m[2].metric("Negative", f"{(fdf['sentiment'] == 'negative').mean():.0%}")
        st.markdown("**Weekly average sentiment score (1 to 5)**")
        st.line_chart(fdf.set_index("created_at")["stars"].resample("W").mean().rename("Score"))
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Sentiment mix**")
            st.bar_chart(fdf["sentiment"].value_counts())
        with c2:
            st.markdown("**Topics customers mention**")
            topics = Counter(t for ts in fdf["topics"] for t in ts)
            if topics:
                st.bar_chart(pd.Series(topics).sort_values(ascending=False), horizontal=True)
        st.markdown("**Needs follow-up**")
        neg = fdf[fdf["sentiment"].isin(["negative", "mixed"])].sort_values("created_at", ascending=False).head(10)
        for _, r in neg.iterrows():
            with st.container(border=True):
                st.caption(f"{r['name']}, {hours.fmt_dt(r['created_at'].to_pydatetime())}, score {r['stars']:.1f}")
                st.write(r["comment"])
                st.markdown(f"_Suggested reply: {r['reply']}_")

with prefs_tab:
    if idf.empty:
        st.write("No order items in this period.")
    else:
        st.markdown("**What regulars order**")
        per = (idf.groupby(["customer_name", "product"])["quantity"].sum().reset_index()
               .sort_values(["customer_name", "quantity"], ascending=[True, False]))
        fav = per.groupby("customer_name").head(1).rename(columns={"product": "Favorite item", "quantity": "Times ordered"})
        visits = live.groupby("customer_name").size().rename("Orders")
        spend = live.groupby("customer_name")["total"].sum().rename("Spend")
        table = fav.set_index("customer_name").join(visits).join(spend).sort_values("Spend", ascending=False)
        table["Spend"] = table["Spend"].map(ui.money)
        st.dataframe(table, width="stretch")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Popular sizes**")
            st.bar_chart(idf[idf["size"] != ""]["size"].value_counts())
        with c2:
            st.markdown("**Popular flavors**")
            st.bar_chart(idf[idf["flavor"] != ""]["flavor"].value_counts())

with score_tab:
    st.write("Paste reviews, one per line, or upload a CSV with a column named review. "
             "Each review gets a sentiment label, a 1 to 5 score, and topics.")
    text = st.text_area("Reviews", height=150, placeholder="The latte was great but the line was long.\nCurbside was fast!")
    upload = st.file_uploader("Or upload a CSV", type=["csv"])
    save = st.checkbox("Also save these to customer feedback")
    if st.button("Score reviews", type="primary"):
        reviews = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if upload is not None:
            df = pd.read_csv(upload)
            col = next((c for c in df.columns if c.lower() in ("review", "reviews", "comment", "text")), None)
            if col is None:
                st.error("The CSV needs a column named review.")
                st.stop()
            reviews += [str(x) for x in df[col].dropna()]
        reviews = reviews[:100]
        if not reviews:
            st.error("Add at least one review.")
            st.stop()
        results = []
        bar = st.progress(0.0, text="Scoring")
        for n, r in enumerate(reviews):
            a = ai.analyze_sentiment(r)
            if save:
                feedback.save(None, r, source="import", analysis=a, name="Imported review")
            results.append({"Review": r, "Sentiment": a["sentiment"], "Score (1 to 5)": a["stars"],
                            "Topics": ", ".join(a["topics"]), "Summary": a["summary"]})
            bar.progress((n + 1) / len(reviews), text=f"Scored {n + 1} of {len(reviews)}")
        out = pd.DataFrame(results)
        st.dataframe(out, hide_index=True, width="stretch")
        st.metric("Average score", f"{out['Score (1 to 5)'].mean():.2f}")
        st.download_button("Download results (CSV)", out.to_csv(index=False), "scored_reviews.csv", "text/csv")

st.divider()
st.subheader("AI brief")
st.caption("A short summary of this period with suggested actions.")
if st.button("Write the brief"):
    lines = [f"Period: last {days} days.",
             f"Revenue {live['total'].sum():.2f}, orders {len(live)}, average ticket {live['total'].mean():.2f}.",
             f"Fulfillment mix: {live['fulfillment'].value_counts().to_dict()}.",
             f"Orders by hour: {live.groupby(live['created_at'].dt.hour).size().to_dict()}."]
    if not idf.empty:
        lines.append(f"Top items: {idf.groupby('product')['quantity'].sum().sort_values(ascending=False).head(8).to_dict()}.")
    if f_rows:
        fdf = pd.DataFrame(f_rows)
        lines.append(f"Feedback count {len(fdf)}, average score {fdf['stars'].mean():.2f}, "
                     f"sentiment {fdf['sentiment'].value_counts().to_dict()}.")
        lines.append(f"Topics: {dict(Counter(t for ts in fdf['topics'] for t in ts))}.")
        lines.append("Recent negative comments: " + " | ".join(fdf[fdf['sentiment'] == 'negative']['comment'].tail(5)))
    res_count = db.one("SELECT COUNT(*) AS n FROM reservations WHERE start_at >= ? AND status != 'cancelled'", (hours.iso(start),))
    lines.append(f"Reservations: {res_count['n']}.")
    with st.spinner("Writing"):
        brief = ai.insight_brief("\n".join(lines))
    if brief:
        st.markdown(brief)
    else:
        st.write("Add an OpenAI API key to generate the brief. Here is the data it would use:")
        st.code("\n".join(lines))

with st.expander("Demo data"):
    st.caption("Adds 30 days of sample customers, orders, and reviews so the charts have something to show. "
               "Sample customers log in with the password Sample#2026.")
    if st.button("Load sample data"):
        with st.spinner("Creating sample orders and reviews"):
            n = sample_data.load()
        st.success(f"Added {n} sample orders.")
        st.rerun()
